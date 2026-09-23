"""Configuration loading and validation for Coven."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any


VALID_PRIORITIES = {"low", "normal", "high"}
VALID_QUALITIES = {"low", "balanced"}
VALID_MOTION_MODES = {"full", "tableau", "off"}
VALID_VOICE_INPUTS = {"push-to-talk", "click-to-toggle"}
VALID_VOICE_ENGINES = {"whisper.cpp"}
VALID_VOICE_MODEL_PROFILES = {"base.en-q5_1", "tiny.en-q5_1", "base.en-q5_0", "tiny.en-q5_0"}
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
class VoiceConfig:
    enabled: bool = True
    default_input: str = "push-to-talk"
    engine: str = "whisper.cpp"
    model_profile: str = "base.en-q5_1"
    language: str = "en"
    microphone_id: str = "default"
    inference_threads: int = 2
    max_duration_seconds: int = 60
    retain_audio: bool = False
    runtime_executable: str = ""
    runtime_dir: Path | None = None
    model_dir: Path | None = None
    max_audio_bytes: int = 12 * 1024 * 1024
    allow_api_transcription: bool = False
    allow_api_speech: bool = False


@dataclass(frozen=True)
class WorkspaceConfig:
    allowed_roots: tuple[Path, ...] = ()


@dataclass(frozen=True)
class OfficeConfig:
    enabled: bool = False
    bridge_executable: str = ""
    operation_timeout_seconds: int = 60


@dataclass(frozen=True)
class MicrosoftGraphConfig:
    enabled: bool = False
    cloud: str = "commercial"
    tenant_id: str = ""
    client_id: str = ""
    token_environment_variable: str = "COVEN_GRAPH_ACCESS_TOKEN"


@dataclass(frozen=True)
class GovDashConfig:
    enabled: bool = False
    route: str = "sharepoint"
    base_url: str = ""
    browser_profile_dir: Path | None = None
    sharepoint_root: str = ""


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    runtime: RuntimeConfig
    providers: ProviderConfig
    cinematics: CinematicConfig
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    office: OfficeConfig = field(default_factory=OfficeConfig)
    microsoft_graph: MicrosoftGraphConfig = field(default_factory=MicrosoftGraphConfig)
    govdash: GovDashConfig = field(default_factory=GovDashConfig)

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
    voice = _object(data.get("voice", {}), "voice")
    cinematics = _object(data.get("cinematics", {}), "cinematics")
    workspace = _object(data.get("workspace", {}), "workspace")
    office = _object(data.get("office", {}), "office")
    microsoft = _object(data.get("microsoftGraph", {}), "microsoftGraph")
    govdash = _object(data.get("govdash", {}), "govdash")

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
        data_dir = _configured_path(_string(server["dataDir"], "server.dataDir"))

    motion = _string(cinematics.get("reducedMotionMode", "tableau"), "cinematics.reducedMotionMode")
    if motion not in VALID_MOTION_MODES:
        raise ConfigError("cinematics.reducedMotionMode is invalid.")
    voice_input = _string(voice.get("defaultInput", "push-to-talk"), "voice.defaultInput").strip().lower()
    if voice_input not in VALID_VOICE_INPUTS:
        raise ConfigError("voice.defaultInput must be push-to-talk or click-to-toggle.")
    voice_engine = _string(voice.get("engine", "whisper.cpp"), "voice.engine").strip().lower()
    if voice_engine not in VALID_VOICE_ENGINES:
        raise ConfigError("voice.engine must be whisper.cpp.")
    voice_profile = _string(voice.get("modelProfile", "base.en-q5_1"), "voice.modelProfile").strip().lower()
    if voice_profile not in VALID_VOICE_MODEL_PROFILES:
        raise ConfigError(f"voice.modelProfile must be one of {sorted(VALID_VOICE_MODEL_PROFILES)}.")
    if parse_bool(voice.get("allowApiTranscription", False), default=False):
        raise ConfigError("voice.allowApiTranscription must remain false for local-only voice.")
    if parse_bool(voice.get("allowApiSpeech", False), default=False):
        raise ConfigError("voice.allowApiSpeech must remain false for local-only voice.")
    graph_cloud = _string(microsoft.get("cloud", "commercial"), "microsoftGraph.cloud").strip().lower()
    if graph_cloud not in {"commercial", "gcc", "gcc_high", "dod"}:
        raise ConfigError("microsoftGraph.cloud must be commercial, gcc, gcc_high or dod.")
    govdash_route = _string(govdash.get("route", "sharepoint"), "govdash.route").strip().lower()
    if govdash_route not in {"sharepoint", "api", "browser"}:
        raise ConfigError("govdash.route must be sharepoint, api or browser.")

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
        voice=VoiceConfig(
            enabled=parse_bool(voice.get("enabled", True), default=True),
            default_input=voice_input,
            engine=voice_engine,
            model_profile=voice_profile,
            language=_string(voice.get("language", "en"), "voice.language").strip().lower() or "en",
            microphone_id=_string(voice.get("microphoneId", "default"), "voice.microphoneId").strip() or "default",
            inference_threads=_positive_int(voice.get("inferenceThreads", 2), "voice.inferenceThreads"),
            max_duration_seconds=_bounded_int(voice.get("maxDurationSeconds", 60), "voice.maxDurationSeconds", minimum=1, maximum=300),
            retain_audio=parse_bool(voice.get("retainAudio", False), default=False),
            runtime_executable=_string(voice.get("runtimeExecutable", ""), "voice.runtimeExecutable"),
            runtime_dir=_optional_path(voice.get("runtimeDir"), "voice.runtimeDir"),
            model_dir=_optional_path(voice.get("modelDir"), "voice.modelDir"),
            max_audio_bytes=_bounded_int(
                voice.get("maxAudioBytes", 12 * 1024 * 1024),
                "voice.maxAudioBytes",
                minimum=64 * 1024,
                maximum=128 * 1024 * 1024,
            ),
            allow_api_transcription=False,
            allow_api_speech=False,
        ),
        workspace=WorkspaceConfig(allowed_roots=_workspace_roots(workspace)),
        office=OfficeConfig(
            enabled=parse_bool(office.get("enabled", False), default=False),
            bridge_executable=_string(office.get("bridgeExecutable", ""), "office.bridgeExecutable"),
            operation_timeout_seconds=_positive_int(office.get("operationTimeoutSeconds", 60), "office.operationTimeoutSeconds"),
        ),
        microsoft_graph=MicrosoftGraphConfig(
            enabled=parse_bool(microsoft.get("enabled", False), default=False),
            cloud=graph_cloud,
            tenant_id=_string(microsoft.get("tenantId", ""), "microsoftGraph.tenantId"),
            client_id=_string(microsoft.get("clientId", ""), "microsoftGraph.clientId"),
            token_environment_variable=_string(
                microsoft.get("tokenEnvironmentVariable", "COVEN_GRAPH_ACCESS_TOKEN"),
                "microsoftGraph.tokenEnvironmentVariable",
            ),
        ),
        govdash=GovDashConfig(
            enabled=parse_bool(govdash.get("enabled", False), default=False),
            route=govdash_route,
            base_url=_string(govdash.get("baseUrl", ""), "govdash.baseUrl"),
            browser_profile_dir=Path(_string(govdash["browserProfileDir"], "govdash.browserProfileDir")).expanduser()
            if "browserProfileDir" in govdash
            else None,
            sharepoint_root=_string(govdash.get("sharePointRoot", ""), "govdash.sharePointRoot"),
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


def _positive_int(value: Any, field: str) -> int:
    parsed = _int(value, field)
    if parsed <= 0:
        raise ConfigError(f"{field} must be positive.")
    return parsed


def _bounded_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    parsed = _int(value, field)
    if not (minimum <= parsed <= maximum):
        raise ConfigError(f"{field} must be between {minimum} and {maximum}.")
    return parsed


def _optional_path(value: Any, field: str) -> Path | None:
    if value in {None, ""}:
        return None
    return _configured_path(_string(value, field))


def _configured_path(value: str) -> Path:
    expanded = os.path.expandvars(value)
    if os.name != "nt":
        for name, replacement in {
            "%LOCALAPPDATA%": os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")),
            "%USERPROFILE%": os.environ.get("USERPROFILE", str(Path.home())),
            "%APPDATA%": os.environ.get("APPDATA", str(Path.home() / ".config")),
        }.items():
            expanded = expanded.replace(name, replacement)
    return Path(expanded).expanduser()


def _workspace_roots(workspace: dict[str, Any]) -> tuple[Path, ...]:
    raw = workspace.get("allowedRoots")
    values: list[str] = []
    if raw is not None:
        if not isinstance(raw, list):
            raise ConfigError("workspace.allowedRoots must be an array of strings.")
        for index, item in enumerate(raw):
            if not isinstance(item, str):
                raise ConfigError(f"workspace.allowedRoots[{index}] must be a string.")
            if item.strip():
                values.append(item.strip())
    env = os.environ.get("COVEN_ALLOWED_WORKSPACE_ROOTS")
    if env:
        values.extend(item for item in env.split(os.pathsep) if item.strip())
    roots = []
    for value in values:
        root = _configured_path(value)
        try:
            root = root.resolve()
        except OSError:
            root = root.absolute()
        roots.append(root)
    return tuple(roots)
