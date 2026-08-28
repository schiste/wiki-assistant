from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

MAX_REQUEST_BYTES = 65_536
MAX_UPSTREAM_BYTES = 1_048_576
MVP_BROWSER_ORIGIN = "https://fr.wikipedia.org"
MVP_MODEL_IDS = ("llm-qwen36-27b", "llm-qwen3-14b")
MEDIAWIKI_CODING_SAFETY_INSTRUCTION = (
    "When suggesting JavaScript, CSS, or Lua for MediaWiki, never suggest disabling "
    "or weakening CSRF token handling, origin checks, or permission checks."
)
SESSION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
# Architecture §12, decided in #22. Global (per proxy process — see Procfile's `--workers 1`;
# a global cap needs a single process, since a plain in-process semaphore isn't shared across
# gunicorn worker processes and this MVP has no external coordination store to make it so),
# independent of gunicorn's own raw connection/thread handling.
MAX_IN_FLIGHT_UPSTREAM_CALLS = 8
MAX_QUEUED_UPSTREAM_CALLS = 16
OVERLOADED_RETRY_AFTER_SECONDS = 5.0
# Accident guard against a buggy/looping client, not a real abuse control — the session token
# is trivially resettable client-side, so it can't be treated as identity (§12, #22).
SESSION_RATE_LIMIT_MAX_REQUESTS = 30
SESSION_RATE_LIMIT_WINDOW_SECONDS = 3600.0
SESSION_RATE_LIMIT_SWEEP_INTERVAL_SECONDS = 60.0
StartResponse = Callable[[str, list[tuple[str, str]]], object]
AttestationVerifier = Callable[[Mapping[str, object], Mapping[str, object]], None]

# Architecture §9.4's exact domain list. Deliberately excludes wmcloud.org, wmflabs.org, and
# toolforge.org — Toolforge tool pages are maintainer-submitted content, a different trust
# level than the core Wikimedia projects below, not a canonical article destination.
ALLOWED_WIKI_DOMAINS = (
    "wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "wiktionary.org",
    "wikisource.org",
    "wikiquote.org",
    "wikinews.org",
    "wikibooks.org",
    "wikiversity.org",
    "wikivoyage.org",
    "wikispecies.org",
    "wikifunctions.org",
    "mediawiki.org",
)
# Bare URLs the model's own free-text reply may contain — Hermes has no tool-calling for the
# interactive tier (§5), so a link only ever reaches here as literal URL text the model wrote,
# never as structured output. Trailing punctuation is trimmed at extraction time so a URL at
# the end of a sentence doesn't swallow the closing period/comma/parenthesis into the match.
BARE_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")
TRAILING_PUNCTUATION_PATTERN = re.compile(r"[.,;:!?)\]}>]+$")
ARTICLE_PATH_PATTERN = re.compile(r"^/wiki/([^/]+)$")


def _is_allowed_wiki_hostname(hostname: str) -> bool:
    # Dot-boundary match, never a substring check — "evilwikipedia.org" must not pass just
    # because it ends with the letters "wikipedia.org" (architecture §9.4's own stated bypass).
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ALLOWED_WIKI_DOMAINS
    )


def _extract_article_title(path: str) -> str | None:
    match = ARTICLE_PATH_PATTERN.fullmatch(path)
    if match is None:
        return None
    encoded_title = match.group(1)
    title = urllib.parse.unquote(encoded_title).replace("_", " ")
    # Special: is the one namespace the issue names explicitly as dangerous (login, deletion,
    # user-rights flows) — reject it by its canonical English name even though the strict
    # no-query-string rule below already closes the specific exploit example
    # (Special:UserLogin?returnto=...) on its own. Other namespaces (Template:, Wikipedia:,
    # Category:) stay allowed — WAIT's own product scope needs to cite template/policy pages,
    # not just (Main)-namespace articles.
    if title.lower().startswith("special:"):
        return None
    return title


def _validate_wiki_link(raw_url: str) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    if not parsed.hostname or not _is_allowed_wiki_hostname(parsed.hostname):
        return None
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None
    title = _extract_article_title(parsed.path)
    if title is None:
        return None
    canonical_url = f"https://{parsed.hostname}{parsed.path}"
    return title, canonical_url


def extract_wiki_links(reply_text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for match in BARE_URL_PATTERN.finditer(reply_text):
        candidate = TRAILING_PUNCTUATION_PATTERN.sub("", match.group(0))
        validated = _validate_wiki_link(candidate)
        if validated is None:
            continue
        title, canonical_url = validated
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        links.append({"title": title, "url": canonical_url})
    return links


class RequestRejected(Exception):
    def __init__(
        self,
        status: str,
        code: str,
        message: str,
        retry_after_seconds: float | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


class UpstreamUnavailable(Exception):
    def __init__(self, retryable: bool = False):
        super().__init__()
        self.retryable = retryable


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


@dataclass(frozen=True)
class ProxyConfig:
    hermes_base_url: str
    api_server_key: str
    upstream_timeout_seconds: float = 90.0
    model_ids: tuple[str, ...] = MVP_MODEL_IDS
    upstream_retry_count: int = 1
    upstream_retry_backoff_seconds: float = 0.25

    @classmethod
    def from_environment(cls) -> ProxyConfig:
        base_url = os.environ.get("HERMES_BASE_URL", "").strip()
        api_server_key = os.environ.get("API_SERVER_KEY", "")
        timeout = os.environ.get("HERMES_TIMEOUT_SECONDS", "90").strip()
        model_ids = tuple(
            model_id.strip()
            for model_id in os.environ.get(
                "HERMES_MODEL_IDS", ",".join(MVP_MODEL_IDS)
            ).split(",")
        )
        retry_count = os.environ.get("HERMES_RETRY_COUNT", "1").strip()
        retry_backoff = os.environ.get("HERMES_RETRY_BACKOFF_SECONDS", "0.25").strip()

        parsed_url = urllib.parse.urlsplit(base_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.path not in {"", "/"}
        ):
            raise RuntimeError("HERMES_BASE_URL must be an HTTP(S) origin")
        if len(api_server_key) < 16:
            raise RuntimeError("API_SERVER_KEY must contain at least 16 characters")
        if any(character.isspace() for character in api_server_key):
            raise RuntimeError("API_SERVER_KEY must not contain whitespace")
        try:
            timeout_seconds = float(timeout)
        except ValueError as error:
            raise RuntimeError("HERMES_TIMEOUT_SECONDS must be numeric") from error
        if not 0 < timeout_seconds <= 300:
            raise RuntimeError("HERMES_TIMEOUT_SECONDS must be between 0 and 300")
        if not model_ids or any(not model_id for model_id in model_ids):
            raise RuntimeError("HERMES_MODEL_IDS must be a comma-separated model list")
        try:
            parsed_retry_count = int(retry_count)
        except ValueError as error:
            raise RuntimeError("HERMES_RETRY_COUNT must be an integer") from error
        if parsed_retry_count not in {1, 2}:
            raise RuntimeError("HERMES_RETRY_COUNT must be 1 or 2")
        try:
            retry_backoff_seconds = float(retry_backoff)
        except ValueError as error:
            raise RuntimeError(
                "HERMES_RETRY_BACKOFF_SECONDS must be numeric"
            ) from error
        if not 0 < retry_backoff_seconds <= 5:
            raise RuntimeError("HERMES_RETRY_BACKOFF_SECONDS must be between 0 and 5")

        return cls(
            base_url.rstrip("/"),
            api_server_key,
            timeout_seconds,
            model_ids,
            parsed_retry_count,
            retry_backoff_seconds,
        )


class HermesClient:
    def __init__(self, config: ProxyConfig):
        self._config = config
        self._opener = urllib.request.build_opener(NoRedirectHandler)

    def chat(
        self,
        messages: tuple[dict[str, str], ...],
        session_id: str,
        session_key: str,
    ) -> str:
        deadline = time.monotonic() + self._config.upstream_timeout_seconds
        for model_id in self._config.model_ids:
            for retry_number in range(self._config.upstream_retry_count + 1):
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    raise UpstreamUnavailable
                try:
                    return self._chat_with_model(
                        model_id,
                        messages,
                        session_id,
                        session_key,
                        remaining_seconds,
                    )
                except UpstreamUnavailable as error:
                    if (
                        not error.retryable
                        or retry_number == self._config.upstream_retry_count
                    ):
                        break
                    backoff_seconds = (
                        self._config.upstream_retry_backoff_seconds * 2**retry_number
                    )
                    if backoff_seconds >= deadline - time.monotonic():
                        raise UpstreamUnavailable from error
                    time.sleep(backoff_seconds)
        raise UpstreamUnavailable

    def _chat_with_model(
        self,
        model_id: str,
        messages: tuple[dict[str, str], ...],
        session_id: str,
        session_key: str,
        timeout_seconds: float,
    ) -> str:
        request_body = json.dumps(
            {
                "model": model_id,
                "messages": [
                    {
                        "role": "system",
                        "content": MEDIAWIKI_CODING_SAFETY_INSTRUCTION,
                    },
                    *messages,
                ],
            }
        ).encode()
        request = urllib.request.Request(
            f"{self._config.hermes_base_url}/v1/chat/completions",
            data=request_body,
            headers={
                "Authorization": f"Bearer {self._config.api_server_key}",
                "Content-Type": "application/json",
                "X-Hermes-Session-Id": session_id,
                "X-Hermes-Session-Key": session_key,
            },
            method="POST",
        )

        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                raw_payload = response.read(MAX_UPSTREAM_BYTES + 1)
            if len(raw_payload) > MAX_UPSTREAM_BYTES:
                raise UpstreamUnavailable
            payload = json.loads(raw_payload)
            reply = payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as error:
            retryable = error.code in {408, 425, 429, 500, 502, 503, 504}
            error.close()
            raise UpstreamUnavailable(retryable) from error
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise UpstreamUnavailable(retryable=True) from error
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
        ) as error:
            raise UpstreamUnavailable from error

        if not isinstance(reply, str):
            raise UpstreamUnavailable
        return reply


def reject_unconfigured_attestation(
    environ: Mapping[str, object], body: Mapping[str, object]
) -> None:
    raise RequestRejected(
        "503 Service Unavailable",
        "gadget_attestation_unavailable",
        "Gadget access verification is not configured",
    )


class AdmissionGate:
    def __init__(self, max_in_flight: int, max_queued: int):
        self._max_in_flight = max_in_flight
        self._max_queued = max_queued
        self._condition = threading.Condition()
        self._in_flight = 0
        self._queued = 0

    @contextmanager
    def admit(self) -> Iterator[float]:
        wait_started = time.monotonic()
        with self._condition:
            if self._in_flight >= self._max_in_flight:
                if self._queued >= self._max_queued:
                    raise RequestRejected(
                        "503 Service Unavailable",
                        "overloaded",
                        "The assistant is at capacity, please retry shortly",
                        retry_after_seconds=OVERLOADED_RETRY_AFTER_SECONDS,
                    )
                self._queued += 1
                try:
                    while self._in_flight >= self._max_in_flight:
                        self._condition.wait()
                finally:
                    self._queued -= 1
            self._in_flight += 1
        try:
            yield time.monotonic() - wait_started
        finally:
            with self._condition:
                self._in_flight -= 1
                self._condition.notify()


class SessionRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        sweep_interval_seconds: float = SESSION_RATE_LIMIT_SWEEP_INTERVAL_SECONDS,
        time_source: Callable[[], float] = time.monotonic,
    ):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._sweep_interval_seconds = sweep_interval_seconds
        self._time_source = time_source
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = {}
        self._next_sweep_at = time_source() + sweep_interval_seconds

    def check(self, session_token: str) -> tuple[bool, float]:
        now = self._time_source()
        cutoff = now - self._window_seconds
        with self._lock:
            self._sweep_if_due(now, cutoff)
            timestamps = [
                t for t in self._requests.get(session_token, ()) if t > cutoff
            ]
            allowed = len(timestamps) < self._max_requests
            if allowed:
                timestamps.append(now)
                retry_after_seconds = 0.0
            else:
                retry_after_seconds = max(
                    0.0, timestamps[0] + self._window_seconds - now
                )
            if timestamps:
                self._requests[session_token] = timestamps
            else:
                self._requests.pop(session_token, None)
            return allowed, retry_after_seconds

    def _sweep_if_due(self, now: float, cutoff: float) -> None:
        # Bounds memory to recently active sessions rather than every distinct opaque session
        # token ever minted over this process's lifetime — an abandoned session's single stale
        # timestamp would otherwise never get pruned, since pruning normally only happens when
        # that exact token is checked again.
        if now < self._next_sweep_at:
            return
        self._next_sweep_at = now + self._sweep_interval_seconds
        stale_tokens = [
            token
            for token, timestamps in self._requests.items()
            if not any(t > cutoff for t in timestamps)
        ]
        for token in stale_tokens:
            del self._requests[token]


class ProxyApplication:
    def __init__(
        self,
        config: ProxyConfig,
        hermes_client: HermesClient,
        verify_attestation: AttestationVerifier,
        admission_gate: AdmissionGate | None = None,
        session_rate_limiter: SessionRateLimiter | None = None,
    ):
        self._config = config
        self._hermes_client = hermes_client
        self._verify_attestation = verify_attestation
        self._admission_gate = admission_gate or AdmissionGate(
            MAX_IN_FLIGHT_UPSTREAM_CALLS, MAX_QUEUED_UPSTREAM_CALLS
        )
        self._session_rate_limiter = session_rate_limiter or SessionRateLimiter(
            SESSION_RATE_LIMIT_MAX_REQUESTS, SESSION_RATE_LIMIT_WINDOW_SECONDS
        )

    def __call__(
        self, environ: Mapping[str, object], start_response: StartResponse
    ) -> Iterable[bytes]:
        try:
            return self._dispatch(environ, start_response)
        except RequestRejected as error:
            headers = list(self._cors_response_headers(environ))
            if error.retry_after_seconds is not None:
                headers.append(("Retry-After", str(int(error.retry_after_seconds))))
            return self._json_response(
                start_response,
                error.status,
                {"error": {"code": error.code, "message": error.message}},
                headers,
            )
        except UpstreamUnavailable:
            return self._json_response(
                start_response,
                "503 Service Unavailable",
                {
                    "error": {
                        "code": "upstream_unavailable",
                        "message": "The assistant is temporarily unavailable",
                    }
                },
                self._cors_response_headers(environ),
            )

    def _dispatch(
        self, environ: Mapping[str, object], start_response: StartResponse
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))

        if method == "GET" and path == "/healthz":
            return self._json_response(start_response, "200 OK", {"status": "ok"})
        if path != "/chat" or method not in {"OPTIONS", "POST"}:
            raise RequestRejected("404 Not Found", "not_found", "Route not found")

        self._validate_browser_request(environ)
        if method == "OPTIONS":
            self._validate_preflight_request(environ)
            return self._empty_response(
                start_response,
                "204 No Content",
                self._cors_response_headers(environ, preflight=True),
            )

        body = self._read_json_body(environ)
        self._verify_attestation(environ, body)

        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise RequestRejected(
                "400 Bad Request",
                "invalid_request",
                "message must be a non-empty string",
            )
        history = self._read_history(body.get("history", []))

        session_token = body.get("session_id")
        if session_token is None:
            session_token = secrets.token_urlsafe(32)
        if not isinstance(session_token, str) or not SESSION_TOKEN_PATTERN.fullmatch(
            session_token
        ):
            raise RequestRejected(
                "400 Bad Request", "invalid_session", "session_id is invalid"
            )

        allowed, retry_after_seconds = self._session_rate_limiter.check(session_token)
        if not allowed:
            raise RequestRejected(
                "429 Too Many Requests",
                "rate_limited",
                "Too many requests for this session",
                retry_after_seconds=retry_after_seconds,
            )

        hermes_session_id = self._derive_session_value("transcript", session_token)
        hermes_session_key = self._derive_session_value("memory", session_token)
        messages = (*history, {"role": "user", "content": message.strip()})
        with self._admission_gate.admit() as queue_wait_seconds:
            reply = self._hermes_client.chat(
                messages, hermes_session_id, hermes_session_key
            )
        return self._json_response(
            start_response,
            "200 OK",
            {
                "session_id": session_token,
                "reply": reply,
                "links": extract_wiki_links(reply),
            },
            [
                *self._cors_response_headers(environ),
                ("Server-Timing", f"queue;dur={queue_wait_seconds * 1000:.3f}"),
            ],
        )

    def _validate_browser_request(self, environ: Mapping[str, object]) -> None:
        origin = str(environ.get("HTTP_ORIGIN", ""))
        referer = str(environ.get("HTTP_REFERER", ""))
        fetch_site = str(environ.get("HTTP_SEC_FETCH_SITE", ""))
        fetch_mode = str(environ.get("HTTP_SEC_FETCH_MODE", ""))
        fetch_destination = str(environ.get("HTTP_SEC_FETCH_DEST", ""))

        if origin != MVP_BROWSER_ORIGIN:
            self._reject_browser_request()
        if referer and not self._referer_matches_origin(referer, origin):
            self._reject_browser_request()
        if (fetch_site, fetch_mode, fetch_destination) != (
            "cross-site",
            "cors",
            "empty",
        ):
            self._reject_browser_request()

    def _validate_preflight_request(self, environ: Mapping[str, object]) -> None:
        requested_method = str(environ.get("HTTP_ACCESS_CONTROL_REQUEST_METHOD", ""))
        requested_headers = str(environ.get("HTTP_ACCESS_CONTROL_REQUEST_HEADERS", ""))
        normalized_headers = [
            header.strip().lower() for header in requested_headers.split(",")
        ]
        if requested_method != "POST" or normalized_headers != ["content-type"]:
            self._reject_browser_request()

    @staticmethod
    def _referer_matches_origin(referer: str, expected_origin: str) -> bool:
        try:
            parsed_referer = urllib.parse.urlsplit(referer)
            if parsed_referer.port is not None:
                return False
        except ValueError:
            return False
        referer_origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}"
        return referer_origin == expected_origin

    @staticmethod
    def _reject_browser_request() -> None:
        raise RequestRejected(
            "403 Forbidden",
            "browser_request_rejected",
            "Browser request metadata is not allowed",
        )

    def _read_json_body(self, environ: Mapping[str, object]) -> Mapping[str, object]:
        content_type = str(environ.get("CONTENT_TYPE", ""))
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise RequestRejected(
                "415 Unsupported Media Type",
                "invalid_content_type",
                "Content-Type must be application/json",
            )

        content_length = str(environ.get("CONTENT_LENGTH", "")).strip()
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise RequestRejected(
                "400 Bad Request", "invalid_request", "Content-Length is invalid"
            ) from error
        if not 0 < declared_length <= MAX_REQUEST_BYTES:
            raise RequestRejected(
                "413 Payload Too Large",
                "request_too_large",
                "Request body is too large",
            )

        stream = environ.get("wsgi.input")
        if not hasattr(stream, "read"):
            raise RequestRejected(
                "400 Bad Request", "invalid_request", "Request body is unavailable"
            )
        raw_body = stream.read(declared_length + 1)
        if len(raw_body) != declared_length:
            raise RequestRejected(
                "400 Bad Request", "invalid_request", "Request body length is invalid"
            )
        try:
            body = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestRejected(
                "400 Bad Request", "invalid_json", "Request body must be valid JSON"
            ) from error
        if not isinstance(body, dict):
            raise RequestRejected(
                "400 Bad Request", "invalid_json", "Request body must be a JSON object"
            )
        return body

    @staticmethod
    def _read_history(raw_history: object) -> tuple[dict[str, str], ...]:
        if not isinstance(raw_history, list) or len(raw_history) % 2 != 0:
            raise RequestRejected(
                "400 Bad Request",
                "invalid_history",
                "history must contain complete user and assistant turns",
            )

        history = []
        for index, raw_message in enumerate(raw_history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if (
                not isinstance(raw_message, dict)
                or set(raw_message) != {"role", "content"}
                or raw_message.get("role") != expected_role
                or not isinstance(raw_message.get("content"), str)
                or not raw_message["content"].strip()
            ):
                raise RequestRejected(
                    "400 Bad Request",
                    "invalid_history",
                    "history must alternate non-empty user and assistant messages",
                )
            history.append({"role": expected_role, "content": raw_message["content"]})
        return tuple(history)

    @staticmethod
    def _cors_response_headers(
        environ: Mapping[str, object], preflight: bool = False
    ) -> list[tuple[str, str]]:
        if str(environ.get("PATH_INFO", "/")) != "/chat":
            return []

        vary = "Origin"
        if preflight:
            vary = (
                "Origin, Access-Control-Request-Method, Access-Control-Request-Headers"
            )
        headers = [("Vary", vary)]
        if str(environ.get("HTTP_ORIGIN", "")) != MVP_BROWSER_ORIGIN:
            return headers

        headers.append(("Access-Control-Allow-Origin", MVP_BROWSER_ORIGIN))
        if preflight:
            headers.extend(
                [
                    ("Access-Control-Allow-Methods", "POST"),
                    ("Access-Control-Allow-Headers", "Content-Type"),
                ]
            )
        else:
            # Custom response headers are invisible to browser JS unless explicitly exposed —
            # without this, Retry-After/Server-Timing are set on the wire but unreadable by the
            # gadget's fetch() call, silently defeating the point of setting them.
            headers.append(
                ("Access-Control-Expose-Headers", "Retry-After, Server-Timing")
            )
        return headers

    def _derive_session_value(self, purpose: str, session_token: str) -> str:
        message = f"wait:{purpose}:{session_token}".encode()
        return hmac.new(
            self._config.api_server_key.encode(), message, hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _json_response(
        start_response: StartResponse,
        status: str,
        payload: Mapping[str, object],
        extra_headers: Iterable[tuple[str, str]] = (),
    ) -> list[bytes]:
        body = json.dumps(payload, separators=(",", ":")).encode()
        start_response(
            status,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                *extra_headers,
            ],
        )
        return [body]

    @staticmethod
    def _empty_response(
        start_response: StartResponse,
        status: str,
        extra_headers: Iterable[tuple[str, str]] = (),
    ) -> list[bytes]:
        start_response(
            status,
            [
                ("Content-Length", "0"),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                *extra_headers,
            ],
        )
        return []


def create_application(
    config: ProxyConfig | None = None,
    hermes_client: HermesClient | None = None,
    verify_attestation: AttestationVerifier | None = None,
    admission_gate: AdmissionGate | None = None,
    session_rate_limiter: SessionRateLimiter | None = None,
) -> ProxyApplication:
    resolved_config = config or ProxyConfig.from_environment()
    return ProxyApplication(
        resolved_config,
        hermes_client or HermesClient(resolved_config),
        verify_attestation or reject_unconfigured_attestation,
        admission_gate,
        session_rate_limiter,
    )
