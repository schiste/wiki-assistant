from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

MAX_REQUEST_BYTES = 65_536
MAX_UPSTREAM_BYTES = 1_048_576
MVP_BROWSER_ORIGIN = "https://fr.wikipedia.org"
SESSION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
StartResponse = Callable[[str, list[tuple[str, str]]], object]
AttestationVerifier = Callable[[Mapping[str, object], Mapping[str, object]], None]


class RequestRejected(Exception):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class UpstreamUnavailable(Exception):
    pass


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


@dataclass(frozen=True)
class ProxyConfig:
    hermes_base_url: str
    api_server_key: str
    upstream_timeout_seconds: float = 90.0

    @classmethod
    def from_environment(cls) -> ProxyConfig:
        base_url = os.environ.get("HERMES_BASE_URL", "").strip()
        api_server_key = os.environ.get("API_SERVER_KEY", "").strip()
        timeout = os.environ.get("HERMES_TIMEOUT_SECONDS", "90").strip()

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

        return cls(base_url.rstrip("/"), api_server_key, timeout_seconds)


class HermesClient:
    def __init__(self, config: ProxyConfig):
        self._config = config
        self._opener = urllib.request.build_opener(NoRedirectHandler)

    def chat(self, message: str, session_id: str, session_key: str) -> str:
        request_body = json.dumps(
            {
                "model": "llm-qwen36-27b",
                "messages": [{"role": "user", "content": message}],
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
            with self._opener.open(
                request, timeout=self._config.upstream_timeout_seconds
            ) as response:
                raw_payload = response.read(MAX_UPSTREAM_BYTES + 1)
            if len(raw_payload) > MAX_UPSTREAM_BYTES:
                raise UpstreamUnavailable
            payload = json.loads(raw_payload)
            reply = payload["choices"][0]["message"]["content"]
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            OSError,
            TimeoutError,
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


class ProxyApplication:
    def __init__(
        self,
        config: ProxyConfig,
        hermes_client: HermesClient,
        verify_attestation: AttestationVerifier,
    ):
        self._config = config
        self._hermes_client = hermes_client
        self._verify_attestation = verify_attestation

    def __call__(
        self, environ: Mapping[str, object], start_response: StartResponse
    ) -> Iterable[bytes]:
        try:
            return self._dispatch(environ, start_response)
        except RequestRejected as error:
            return self._json_response(
                start_response,
                error.status,
                {"error": {"code": error.code, "message": error.message}},
                self._cors_response_headers(environ),
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

        session_token = body.get("session_id")
        if session_token is None:
            session_token = secrets.token_urlsafe(32)
        if not isinstance(session_token, str) or not SESSION_TOKEN_PATTERN.fullmatch(
            session_token
        ):
            raise RequestRejected(
                "400 Bad Request", "invalid_session", "session_id is invalid"
            )

        hermes_session_id = self._derive_session_value("transcript", session_token)
        hermes_session_key = self._derive_session_value("memory", session_token)
        reply = self._hermes_client.chat(
            message.strip(), hermes_session_id, hermes_session_key
        )
        return self._json_response(
            start_response,
            "200 OK",
            {"session_id": session_token, "reply": reply, "links": []},
            self._cors_response_headers(environ),
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
) -> ProxyApplication:
    resolved_config = config or ProxyConfig.from_environment()
    return ProxyApplication(
        resolved_config,
        hermes_client or HermesClient(resolved_config),
        verify_attestation or reject_unconfigured_attestation,
    )
