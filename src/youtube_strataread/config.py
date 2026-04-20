"""Configuration & API key management for four provider families:

    openai     — OpenAI's own API (reasoning via ``reasoning_effort``)
    anthropic  — Anthropic Claude (extended thinking)
    gemini     — Google Gemini (thinking_config)
    compat     — Any OpenAI-compatible third-party relay (user-supplied base_url)

Key resolution order, per provider:
    1. system keyring  (service=``youtube-strataread``, username=<provider>)
    2. environment variable ``BY_<PROVIDER>_API_KEY``
    3. config.toml ``[providers.<provider>].api_key``
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit
from platformdirs import user_config_dir

try:
    import keyring
    import keyring.errors  # noqa: F401
    _KEYRING_AVAILABLE = True
except Exception:  # pragma: no cover - best effort
    keyring = None  # type: ignore[assignment]
    _KEYRING_AVAILABLE = False

APP_NAME = "youtube-strataread"
KEYRING_SERVICE = APP_NAME

# ---------------------------------------------------------------------------
# Supported providers.
# ---------------------------------------------------------------------------
SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini", "compat")
DEFAULT_PROVIDER = "anthropic"

# Default model per provider. All four are deep-thinking capable so every
# provider's default is a "think hard" model.
DEFAULT_MODELS = {
    "openai": "o4-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "gemini": "gemini-2.5-pro",
    # Compat has no sensible default model -- users point it at whatever
    # proxy they use (e.g. an OpenRouter / self-hosted relay / Zenmux).
    "compat": "gpt-4o-mini",
}

# Default base_url per provider. ``None`` means "use the SDK default".
DEFAULT_BASE_URLS: dict[str, str | None] = {
    "openai": None,  # SDK default: https://api.openai.com/v1
    "anthropic": None,  # SDK default: https://api.anthropic.com
    "gemini": None,  # SDK default: Google's endpoint
    "compat": None,  # MUST be configured by the user
}


@dataclass
class ProviderConfig:
    name: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    # Which wire protocol to use when hitting the endpoint.
    #   "openai"    -> Chat Completions compatible (openai, compat)
    #   "anthropic" -> Messages API (anthropic)
    #   "gemini"    -> Google GenAI
    api_flavor: str = "openai"


@dataclass
class AppConfig:
    default_provider: str = DEFAULT_PROVIDER
    providers: dict[str, dict[str, str]] = field(default_factory=dict)
    path: Path | None = None


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
def config_dir() -> Path:
    d = Path(user_config_dir(APP_NAME))
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.toml"


# ---------------------------------------------------------------------------
# load/save
# ---------------------------------------------------------------------------
def load() -> AppConfig:
    path = config_path()
    if not path.exists():
        return AppConfig(path=path)
    raw = tomlkit.parse(path.read_text(encoding="utf-8"))
    default = str(raw.get("default", {}).get("provider", DEFAULT_PROVIDER))
    providers_raw = raw.get("providers", {}) or {}
    providers: dict[str, dict[str, str]] = {}
    for name, data in providers_raw.items():
        providers[str(name)] = {str(k): str(v) for k, v in dict(data).items()}
    return AppConfig(default_provider=default, providers=providers, path=path)


def save(cfg: AppConfig) -> None:
    path = cfg.path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    doc.add("default", tomlkit.table())
    doc["default"]["provider"] = cfg.default_provider  # type: ignore[index]
    providers_tbl = tomlkit.table()
    for name, data in cfg.providers.items():
        sub = tomlkit.table()
        for k, v in data.items():
            sub[k] = v
        providers_tbl[name] = sub
    doc["providers"] = providers_tbl
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


# ---------------------------------------------------------------------------
# mutators
# ---------------------------------------------------------------------------
def set_key(provider: str, api_key: str) -> str:
    """Save an API key. Returns the storage backend used ('keyring' or 'config')."""
    _require_supported(provider)
    if _KEYRING_AVAILABLE:
        try:
            keyring.set_password(KEYRING_SERVICE, provider, api_key)
            return "keyring"
        except Exception:  # pragma: no cover
            pass
    cfg = load()
    cfg.providers.setdefault(provider, {})
    cfg.providers[provider]["api_key"] = api_key
    save(cfg)
    return "config"


def set_base_url(provider: str, base_url: str) -> None:
    _require_supported(provider)
    cfg = load()
    cfg.providers.setdefault(provider, {})
    cfg.providers[provider]["base_url"] = base_url
    save(cfg)


def set_model(provider: str, model: str) -> None:
    _require_supported(provider)
    cfg = load()
    cfg.providers.setdefault(provider, {})
    cfg.providers[provider]["model"] = model
    save(cfg)


def set_default_provider(provider: str) -> None:
    _require_supported(provider)
    cfg = load()
    cfg.default_provider = provider
    save(cfg)


# ---------------------------------------------------------------------------
# resolvers
# ---------------------------------------------------------------------------
def resolve_key(provider: str) -> str | None:
    _require_supported(provider)
    if _KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(KEYRING_SERVICE, provider)
            if value:
                return value
        except Exception:
            pass
    env_name = f"BY_{provider.upper()}_API_KEY"
    env_val = os.environ.get(env_name)
    if env_val:
        return env_val
    cfg = load()
    return cfg.providers.get(provider, {}).get("api_key")


_FLAVOR_BY_PROVIDER = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "compat": "openai",
}


def resolve_provider_config(provider: str | None) -> ProviderConfig:
    cfg = load()
    name = provider or cfg.default_provider or DEFAULT_PROVIDER
    # Backwards-compat: the config.toml on disk may still list a provider
    # (e.g. ``zenmux``) that no longer exists after a refactor. Fall back to
    # the baked-in default instead of failing the whole invocation.
    if name not in SUPPORTED_PROVIDERS:
        name = DEFAULT_PROVIDER
    _require_supported(name)
    data = cfg.providers.get(name, {})
    model = data.get("model") or DEFAULT_MODELS[name]
    base_url = data.get("base_url") or DEFAULT_BASE_URLS.get(name)
    flavor = _FLAVOR_BY_PROVIDER[name]
    return ProviderConfig(
        name=name,
        model=model,
        base_url=base_url,
        api_key=resolve_key(name),
        api_flavor=flavor,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def mask_key(key: str | None) -> str:
    if not key:
        return "<not set>"
    if len(key) <= 4:
        return "*" * len(key)
    return f"****{key[-4:]}"


def _require_supported(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"unsupported provider '{provider}'. Choose one of: "
            + ", ".join(SUPPORTED_PROVIDERS)
        )
