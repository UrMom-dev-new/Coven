"""Configuration loading and validation for Coven."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any


VALID_PRIORITIES = {"low", "normal", "high"}
VALID_QUALITIES = {"low", "balanced"}
VALID_MOTION_MODES = {"full", "tableau", "off"}
VALID_WITCH_ID = set("abcdefghijklmnopqrstuvwxyz0123456789_-")


class ConfigError(ValueError):
    """Raised when configuration cannot be safely used."""


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    data_dir: Path | None


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    hermes_executable: str
    allow_demo_mode: bool
    hermes_api_base_url: str
    hermes_api_key_env: str


@dataclass(frozen=True)
class ProviderConfig:
    ollama_base_url: str
    ollama_model: str
    openai_key_env: str
    openai_model: str


@dataclass(frozen=True)
class CinematicConfig:
    failure_scene: bool
    reduced_motion_mode: str
    mute_by_default: bool


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    runtime: RuntimeConfig
    providers: ProviderConfig
    cinematics: CinematicConfig

    @property
    def demo_mode(self) -> bool:
        return self.runtime.mode == "demo"


def parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    raise ConfigError(f"Expected a boolean value, got {value!r}.")


def parse_env_bool(name: str, *, default: bool = False) -> bool:
    return parse_bool(os.environ.get(name), default=default)


def validate_identifier(value: Any, *, field: str = "identifier") -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field} must be a string.")
    text = value.strip()
    if not text or len(text) > 64 or any(char not in VALID_WITCH_ID for char in text):
        raise ConfigError(f"{field} must use lowercase letters, digits, underscore or dash.")
    return text


def validate_priority(value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError("priority must be a string.")
    priority = value.strip().lower()
    if priority not in VALID_PRIORITIES:
        raise ConfigError(f"priority must be one of {sorted(VALID_PRIORITIES)}.")
    return priority


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Configuration JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be a JSON object.")
    return data


def load_app_config(path: Path | None = None) -> AppConfig:
    data: dict[str, Any] = {}
    if path is not None:
        data = load_json_file(path)

    server = _object(data.get("server", {}), "server")
    runtime = _object(data.get("runtime", {}), "runtime")
    providers = _object(data.get("providers", {}), "providers")
    ollama = _object(providers.get("ollama", {}), "providers.ollama")
    openai = _object(providers.get("openai", {}), "providers.openai")
    cinematics = _object(data.get("cinematics", {}), "cinematics")

    env_demo = os.environ.get("COVEN_DEMO_MODE")
    mode = _string(runtime.get("mode", "live"), "runtime.mode").strip().lower()
    if env_demo is not None:
        mode = "demo" if parse_env_bool("COVEN_DEMO_MODE") else "live"
    if mode not in {"live", "demo"}:
        raise ConfigError("runtime.mode must be live or demo.")

    host = _string(server.get("host", "127.0.0.1"), "server.host")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ConfigError("server.host must be a loopback host.")

    port = _int(server.get("port", int(os.environ.get("COVEN_PORT", "8765"))), "server.port")
    if not (1 <= port <= 65535):
        raise ConfigError("server.port must be between 1 and 65535.")

    data_dir = None
    if "dataDir" in server:
        data_dir = Path(_string(server["dataDir"], "server.dataDir")).expanduser()

    motion = _string(cinematics.get("reducedMotionMode", "tableau"), "cinematics.reducedMotionMode")
    if motion not in VALID_MOTION_MODES:
        raise ConfigError("cinematics.reducedMotionMode is invalid.")

    return AppConfig(
        server=ServerConfig(host=host, port=port, data_dir=data_dir),
        runtime=RuntimeConfig(
            mode=mode,
            hermes_executable=_string(runtime.get("hermesExecutable", "hermes"), "runtime.hermesExecutable"),
            allow_demo_mode=parse_bool(runtime.get("allowDemoMode", True), default=True),
            hermes_api_base_url=_string(runtime.get("hermesApiBaseUrl", ""), "runtime.hermesApiBaseUrl"),
            hermes_api_key_env=_string(runtime.get("hermesApiKeyEnvironmentVariable", "HERMES_API_SERVER_KEY"), "runtime.hermesApiKeyEnvironmentVariable"),
        ),
        providers=ProviderConfig(
            ollama_base_url=_string(ollama.get("baseUrl", "http://127.0.0.1:11434/v1"), "providers.ollama.baseUrl"),
            ollama_model=_string(ollama.get("model", ""), "providers.ollama.model"),
            openai_key_env=_string(openai.get("apiKeyEnvironmentVariable", "OPENAI_API_KEY"), "providers.openai.apiKeyEnvironmentVariable"),
            openai_model=_string(openai.get("model", ""), "providers.openai.model"),
        ),
        cinematics=CinematicConfig(
            failure_scene=parse_bool(cinematics.get("failureScene", True), default=True),
            reduced_motion_mode=motion,
            mute_by_default=parse_bool(cinematics.get("muteByDefault", False), default=False),
        ),
    )


def validate_profiles_file(path: Path) -> list[dict[str, Any]]:
    data = load_json_file(path)
    witches = data.get("witches")
    if not isinstance(witches, list) or not witches:
        raise ConfigError("config/witches.json must contain a non-empty witches array.")

    ids: set[str] = set()
    validated: list[dict[str, Any]] = []
    required = {
        "id",
        "name",
        "title",
        "station",
        "responsibilities",
        "defaultLimits",
        "providerLabel",
        "voice",
        "accent",
        "asset",
    }
    for index, raw in enumerate(witches):
        if not isinstance(raw, dict):
            raise ConfigError(f"witches[{index}] must be an object.")
        missing = sorted(required - set(raw))
        if missing:
            raise ConfigError(f"witches[{index}] is missing {missing}.")
        item: dict[str, Any] = {}
        item["id"] = validate_identifier(raw["id"], field=f"witches[{index}].id")
        if item["id"] in ids:
            raise ConfigError(f"Duplicate witch id: {item['id']}")
        ids.add(item["id"])
        for key in required - {"id"}:
            value = raw[key]
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"witches[{index}].{key} must be a non-empty string.")
            item[key] = value.strip()
        validated.append(item)
    return validated


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be an object.")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field} must be a string.")
    return value


def _int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{field} must be an integer.")
    return value
