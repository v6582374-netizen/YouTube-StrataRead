from __future__ import annotations

from pathlib import Path

import youtube_strataread.config as config


def test_load_migrates_legacy_compat_table(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text(
        """
[default]
provider = "compat"

[providers.compat]
base_url = "https://relay.example/v1"
model = "claude-sonnet-4-5"
""".strip(),
        encoding="utf-8",
    )
    _patch_config_path(monkeypatch, target)

    cfg = config.load()

    assert "compat" not in cfg.providers
    assert cfg.compat_profiles["default"]["base_url"] == "https://relay.example/v1"
    assert cfg.compat_profiles["default"]["model"] == "claude-sonnet-4-5"


def test_resolve_provider_config_uses_named_compat_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)
    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)

    cfg = config.AppConfig(path=target)
    cfg.compat_profiles = {
        "aigocode": {
            "base_url": "https://api.aigocode.com/v1",
            "model": "claude-opus-4-7",
            "api_key": "secret-1",
            "use_temperature": "true",
        },
        "shenma": {
            "base_url": "https://api.whatai.cc/v1",
            "model": "claude-sonnet-4-5",
            "api_key": "secret-2",
        },
    }
    cfg.default_provider = "compat"
    cfg.default_compat_profile = "shenma"
    config.save(cfg)

    pc = config.resolve_provider_config("compat", compat_profile="aigocode")

    assert pc.name == "compat"
    assert pc.profile_name == "aigocode"
    assert pc.label == "compat:aigocode"
    assert pc.base_url == "https://api.aigocode.com/v1"
    assert pc.model == "claude-opus-4-7"
    assert pc.api_key == "secret-1"
    assert pc.use_temperature is True


def test_resolve_compat_key_prefers_profile_env(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)
    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)
    monkeypatch.setenv("BY_COMPAT_SHEN_MA_API_KEY", "env-secret")

    cfg = config.AppConfig(path=target)
    cfg.compat_profiles = {
        "shen-ma": {
            "base_url": "https://api.whatai.cc/v1",
            "model": "claude-sonnet-4-5",
            "api_key": "stored-secret",
        }
    }
    config.save(cfg)

    assert config.resolve_compat_key("shen-ma") == "env-secret"


def test_list_compat_profiles_puts_default_first(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)

    cfg = config.AppConfig(path=target)
    cfg.default_compat_profile = "shenma"
    cfg.compat_profiles = {
        "aigocode": {"base_url": "https://api.aigocode.com/v1"},
        "shenma": {"base_url": "https://api.whatai.cc/v1"},
        "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4/"},
    }
    config.save(cfg)

    assert config.list_compat_profiles() == ["shenma", "aigocode", "zhipu"]


def test_resolve_compat_profile_defaults_temperature_to_off(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)
    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)

    cfg = config.AppConfig(path=target)
    cfg.compat_profiles = {
        "shenma": {
            "base_url": "https://api.whatai.cc/v1",
            "model": "claude-opus-4-7",
            "api_key": "secret-2",
        }
    }
    config.save(cfg)

    pc = config.resolve_provider_config("compat", compat_profile="shenma")

    assert pc.use_temperature is False


def test_resolve_translation_config_defaults(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)

    tc = config.resolve_translation_config()

    assert tc.mode == "auto"
    assert tc.agent_id == "general_translation"
    assert tc.source_lang == "auto"
    assert tc.target_lang == "zh-CN"
    assert tc.strategy == "general"
    assert tc.chunk_chars == 12000


def test_set_translation_config_persists_values(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    _patch_config_path(monkeypatch, target)

    config.set_translation_config(
        mode="force",
        agent_id="social_literature_translation_agent",
        target_lang="en",
        chunk_chars=4000,
    )

    tc = config.resolve_translation_config()
    assert tc.mode == "force"
    assert tc.agent_id == "social_literature_translation_agent"
    assert tc.target_lang == "en"
    assert tc.chunk_chars == 4000


def _patch_config_path(monkeypatch, target: Path) -> None:
    monkeypatch.setattr(config, "config_path", lambda: target)
