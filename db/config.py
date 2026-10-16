"""SurrealDB settings for the new demo. Connection wiring belongs to the storage worker."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    uri: str = field(repr=False)
    db_name: str = "relay"
    namespace: str = "relay"
    username: str = ""
    password: str = field(default="", repr=False)


def read_dotenv(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            values[key.removeprefix("export ").strip()] = value.strip().strip("'\"")
    return values


def load_settings(env: Mapping[str, str] | None = None, dotenv: str | Path | None = ".env") -> Settings:
    values = {**(read_dotenv(dotenv) if dotenv else {}), **(os.environ if env is None else env)}
    uri = values.get("SURREAL_URL", "").strip()
    parsed = urlparse(uri)
    if parsed.scheme not in {"ws", "wss", "http", "https"} or not parsed.hostname:
        raise ConfigError("SURREAL_URL must be an explicit http(s) or ws(s) service URL")
    return Settings(uri, values.get("SURREAL_DATABASE") or "relay",
                    values.get("SURREAL_NAMESPACE") or "relay", values.get("SURREAL_USERNAME", ""),
                    values.get("SURREAL_PASSWORD", ""))
