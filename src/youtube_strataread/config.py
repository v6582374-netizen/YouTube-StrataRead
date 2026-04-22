"""Configuration & API key management for fixed providers and compat profiles.

Fixed providers:
    openai     — OpenAI's own API (reasoning via ``reasoning_effort``)
    anthropic  — Anthropic Claude (extended thinking)
    gemini     — Google Gemini (thinking_config)
    deepseek   — DeepSeek native API (reasoning_content / thinking mode)
    minimax    — MiniMax native API (reasoning_split)
    glm        — GLM native API (thinking mode)

Compat providers:
    compat     — Any OpenAI-compatible third-party relay, stored as named
                 profiles under ``[compat_profiles.<name>]``

Key resolution order, per fixed provider:
    1. system keyring  (service=``youtube-strataread``, username=<provider>)
    2. environment variable ``BY_<PROVIDER>_API_KEY``
    3. config.toml ``[providers.<provider>].api_key``

Key resolution order, per compat profile:
    1. system keyring  (service=``youtube-strataread``, username=``compat:<profile>``)
    2. environment variable ``BY_COMPAT_<PROFILE>_API_KEY``
    3. legacy environment variable ``BY_COMPAT_API_KEY`` (default profile only)
    4. config.toml ``[compat_profiles.<profile>].api_key``
"""
from __future__ import annotations

import contextlib
import os
import re
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
SUPPORTED_PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "compat",
    "deepseek",
    "minimax",
    "glm",
)
FIXED_PROVIDERS = tuple(name for name in SUPPORTED_PROVIDERS if name != "compat")
DEFAULT_PROVIDER = "anthropic"
DEFAULT_COMPAT_PROFILE = "default"

# Default model per provider. Every default is chosen from the vendor's
# currently documented deep-thinking capable lineup.
DEFAULT_MODELS = {
    "openai": "o4-mini",
    "anthropic": "claude-sonnet-4-5-20250929",
    "gemini": "gemini-2.5-pro",
    "compat": "gpt-4o-mini",
    "deepseek": "deepseek-reasoner",
    "minimax": "MiniMax-M2.7",
    "glm": "glm-5.1",
}

# Default base_url per provider. ``None`` means "use the SDK default".
DEFAULT_BASE_URLS: dict[str, str | None] = {
    "openai": None,  # SDK default: https://api.openai.com/v1
    "anthropic": None,  # SDK default: https://api.anthropic.com
    "gemini": None,  # SDK default: Google's endpoint
    "compat": None,  # MUST be configured by the user
    "deepseek": "https://api.deepseek.com",
    "minimax": "https://api.minimaxi.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4/",
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
    #   "deepseek"  -> DeepSeek Chat Completions + reasoning_content
    #   "minimax"   -> MiniMax OpenAI-compatible Chat Completions
    #   "glm"       -> GLM OpenAI-compatible Chat Completions + thinking mode
    api_flavor: str = "openai"
    profile_name: str | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            if self.name == "compat" and self.profile_name:
                self.label = f"{self.name}:{self.profile_name}"
            else:
                self.label = self.name


@dataclass
class AppConfig:
    default_provider: str = DEFAULT_PROVIDER
    default_compat_profile: str = DEFAULT_COMPAT_PROFILE
    providers: dict[str, dict[str, str]] = field(default_factory=dict)
    compat_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
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
    default_tbl = raw.get("default", {}) or {}
    default_provider = str(default_tbl.get("provider", DEFAULT_PROVIDER))
    default_compat_profile = str(
        default_tbl.get("compat_profile", DEFAULT_COMPAT_PROFILE)
    )

    providers_raw = raw.get("providers", {}) or {}
    providers: dict[str, dict[str, str]] = {}
    for name, data in providers_raw.items():
        providers[str(name)] = {str(k): str(v) for k, v in dict(data).items()}

    compat_profiles_raw = raw.get("compat_profiles", {}) or {}
    compat_profiles: dict[str, dict[str, str]] = {}
    for name, data in compat_profiles_raw.items():
        compat_profiles[str(name)] = {str(k): str(v) for k, v in dict(data).items()}

    legacy_compat = providers.pop("compat", None)
    if legacy_compat and DEFAULT_COMPAT_PROFILE not in compat_profiles:
        compat_profiles[DEFAULT_COMPAT_PROFILE] = legacy_compat

    return AppConfig(
        default_provider=default_provider,
        default_compat_profile=default_compat_profile,
        providers=providers,
        compat_profiles=compat_profiles,
        path=path,
    )


def save(cfg: AppConfig) -> None:
    path = cfg.path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = tomlkit.document()
    doc.add("default", tomlkit.table())
    doc["default"]["provider"] = cfg.default_provider  # type: ignore[index]
    doc["default"]["compat_profile"] = cfg.default_compat_profile  # type: ignore[index]

    providers_tbl = tomlkit.table()
    for name, data in cfg.providers.items():
        sub = tomlkit.table()
        for k, v in data.items():
            sub[k] = v
        providers_tbl[name] = sub
    doc["providers"] = providers_tbl

    compat_tbl = tomlkit.table()
    for name, data in cfg.compat_profiles.items():
        sub = tomlkit.table()
        for k, v in data.items():
            sub[k] = v
        compat_tbl[name] = sub
    doc["compat_profiles"] = compat_tbl

    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


# ---------------------------------------------------------------------------
# mutators
# ---------------------------------------------------------------------------
def set_key(provider: str, api_key: str) -> str:
    """Save an API key. Returns the storage backend used ('keyring' or 'config')."""
    _require_supported(provider)
    if provider == "compat":
        return set_compat_key(DEFAULT_COMPAT_PROFILE, api_key)
    return _set_fixed_key(provider, api_key)


def set_base_url(provider: str, base_url: str) -> None:
    _require_supported(provider)
    if provider == "compat":
        set_compat_base_url(DEFAULT_COMPAT_PROFILE, base_url)
        return
    cfg = load()
    cfg.providers.setdefault(provider, {})
    cfg.providers[provider]["base_url"] = base_url
    save(cfg)


def set_model(provider: str, model: str) -> None:
    _require_supported(provider)
    if provider == "compat":
        set_compat_model(DEFAULT_COMPAT_PROFILE, model)
        return
    cfg = load()
    cfg.providers.setdefault(provider, {})
    cfg.providers[provider]["model"] = model
    save(cfg)


def set_default_provider(provider: str) -> None:
    _require_supported(provider)
    cfg = load()
    cfg.default_provider = provider
    save(cfg)


def set_compat_key(profile: str, api_key: str) -> str:
    """Save a compat profile API key. Returns the storage backend used."""
    _require_profile_name(profile)
    username = _compat_keyring_username(profile)
    if _KEYRING_AVAILABLE:
        try:
            keyring.set_password(KEYRING_SERVICE, username, api_key)
            return "keyring"
        except Exception:  # pragma: no cover
            pass
    cfg = load()
    cfg.compat_profiles.setdefault(profile, {})
    cfg.compat_profiles[profile]["api_key"] = api_key
    save(cfg)
    return "config"


def set_compat_base_url(profile: str, base_url: str) -> None:
    _require_profile_name(profile)
    cfg = load()
    cfg.compat_profiles.setdefault(profile, {})
    cfg.compat_profiles[profile]["base_url"] = base_url
    save(cfg)


def set_compat_model(profile: str, model: str) -> None:
    _require_profile_name(profile)
    cfg = load()
    cfg.compat_profiles.setdefault(profile, {})
    cfg.compat_profiles[profile]["model"] = model
    save(cfg)


def set_default_compat_profile(profile: str) -> None:
    _require_profile_name(profile)
    cfg = load()
    if profile not in cfg.compat_profiles:
        raise ValueError(f"compat profile '{profile}' does not exist")
    cfg.default_compat_profile = profile
    save(cfg)


# ---------------------------------------------------------------------------
# resolvers
# ---------------------------------------------------------------------------
def resolve_key(provider: str) -> str | None:
    _require_supported(provider)
    if provider == "compat":
        profile = load().default_compat_profile or DEFAULT_COMPAT_PROFILE
        return resolve_compat_key(profile)
    return _resolve_fixed_key(provider)


def resolve_compat_key(profile: str) -> str | None:
    _require_profile_name(profile)
    username = _compat_keyring_username(profile)
    if _KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(KEYRING_SERVICE, username)
            if value:
                return value
        except Exception:
            pass

    env_val = os.environ.get(_compat_env_name(profile))
    if env_val:
        return env_val
    if profile == DEFAULT_COMPAT_PROFILE:
        legacy_val = os.environ.get("BY_COMPAT_API_KEY")
        if legacy_val:
            return legacy_val

    cfg = load()
    return cfg.compat_profiles.get(profile, {}).get("api_key")


_FLAVOR_BY_PROVIDER = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "compat": "openai",
    "deepseek": "deepseek",
    "minimax": "minimax",
    "glm": "glm",
}


def resolve_provider_config(
    provider: str | None,
    *,
    compat_profile: str | None = None,
) -> ProviderConfig:
    cfg = load()
    name = provider or cfg.default_provider or DEFAULT_PROVIDER
    if name not in SUPPORTED_PROVIDERS:
        name = DEFAULT_PROVIDER
    _require_supported(name)

    if name == "compat":
        profile_name = compat_profile or cfg.default_compat_profile or DEFAULT_COMPAT_PROFILE
        data = cfg.compat_profiles.get(profile_name, {})
        model = data.get("model") or DEFAULT_MODELS[name]
        base_url = data.get("base_url") or DEFAULT_BASE_URLS.get(name)
        return ProviderConfig(
            name=name,
            model=model,
            base_url=base_url,
            api_key=resolve_compat_key(profile_name),
            api_flavor=_FLAVOR_BY_PROVIDER[name],
            profile_name=profile_name,
            label=f"{name}:{profile_name}",
        )

    data = cfg.providers.get(name, {})
    model = data.get("model") or DEFAULT_MODELS[name]
    base_url = data.get("base_url") or DEFAULT_BASE_URLS.get(name)
    return ProviderConfig(
        name=name,
        model=model,
        base_url=base_url,
        api_key=_resolve_fixed_key(name),
        api_flavor=_FLAVOR_BY_PROVIDER[name],
        label=name,
    )


def list_compat_profiles() -> list[str]:
    cfg = load()
    names = sorted(cfg.compat_profiles)
    if cfg.default_compat_profile in names:
        names.remove(cfg.default_compat_profile)
        names.insert(0, cfg.default_compat_profile)
    return names


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


def _require_profile_name(profile: str) -> None:
    if not profile.strip():
        raise ValueError("compat profile name must not be empty")


def _set_fixed_key(provider: str, api_key: str) -> str:
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


def _resolve_fixed_key(provider: str) -> str | None:
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


def _compat_keyring_username(profile: str) -> str:
    return f"compat:{profile}"


def _compat_env_name(profile: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", profile).strip("_").upper()
    slug = slug or DEFAULT_COMPAT_PROFILE.upper()
    return f"BY_COMPAT_{slug}_API_KEY"
