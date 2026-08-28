from collections.abc import Mapping
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

# Matches Hermes's own api_server startup guard (gateway/platforms/api_server.py):
# it refuses to start with a key shorter than this.
MIN_API_SERVER_KEY_LENGTH = 16


def _load_gateway_config() -> dict:
    try:
        raw = CONFIG_PATH.read_text()
    except OSError as exc:
        raise RuntimeError(
            f"cannot read gateway config at {CONFIG_PATH}: {exc}"
        ) from exc

    config = yaml.safe_load(raw)
    if not isinstance(config, dict):
        raise TypeError(f"gateway config at {CONFIG_PATH} must parse to a mapping")

    return config


def _read_required_api_server_key(environ: Mapping[str, str]) -> str:
    """Read and validate API_SERVER_KEY. Fails closed: never generates or logs the value.

    API_SERVER_KEY has one source of truth — the Toolforge envvar provisioned once during
    operator setup (#30) and injected into this process's environment. Both the gateway and
    the proxy read the same value; neither may generate or persist an independent one.
    """
    value = environ.get("API_SERVER_KEY", "")
    if not value:
        raise RuntimeError(
            "API_SERVER_KEY is not set. This process never generates its own key — "
            "provision it once via Toolforge envvars and ensure it is injected into this "
            "process's environment before starting."
        )
    if len(value) < MIN_API_SERVER_KEY_LENGTH:
        raise RuntimeError(
            f"API_SERVER_KEY is shorter than {MIN_API_SERVER_KEY_LENGTH} characters — "
            "refusing to start with a weak key."
        )
    if any(character.isspace() for character in value):
        raise RuntimeError("API_SERVER_KEY must not contain whitespace")
    return value
