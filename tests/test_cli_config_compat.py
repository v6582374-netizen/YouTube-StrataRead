from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from youtube_strataread.cli import app

runner = CliRunner()


def test_config_compat_set_and_list(monkeypatch, tmp_path: Path) -> None:
    import youtube_strataread.config as config

    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)
    target = tmp_path / "config.toml"

    result = runner.invoke(
        app,
        [
            "--config",
            str(target),
            "config",
            "compat",
            "set",
            "shenma",
            "--key",
            "secret-key",
            "--base-url",
            "https://api.whatai.cc/v1",
            "--model",
            "claude-sonnet-4-5",
            "--temperature",
            "off",
        ],
    )

    assert result.exit_code == 0

    list_result = runner.invoke(
        app,
        ["--config", str(target), "config", "compat", "list"],
    )

    assert list_result.exit_code == 0
    assert "default compat profile" in list_result.stdout
    assert "shenma" in list_result.stdout
    assert "https://api.whatai.cc/v1" in list_result.stdout
    assert "temperature=off" in list_result.stdout


def test_config_compat_can_enable_temperature(monkeypatch, tmp_path: Path) -> None:
    import youtube_strataread.config as config

    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)
    target = tmp_path / "config.toml"

    result = runner.invoke(
        app,
        [
            "--config",
            str(target),
            "config",
            "compat",
            "set",
            "aigocode",
            "--key",
            "secret-key",
            "--base-url",
            "https://api.aigocode.com/v1",
            "--temperature",
            "on",
        ],
    )

    assert result.exit_code == 0

    get_result = runner.invoke(
        app,
        ["--config", str(target), "config", "compat", "get", "aigocode"],
    )

    assert get_result.exit_code == 0
    assert "temperature=on" in get_result.stdout


def test_config_show_displays_multiple_compat_profiles(monkeypatch, tmp_path: Path) -> None:
    import youtube_strataread.config as config

    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)
    target = tmp_path / "config.toml"

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
            "use_temperature": "false",
        },
    }
    cfg.default_compat_profile = "shenma"
    config.save(cfg)

    result = runner.invoke(
        app,
        ["--config", str(target), "config", "show"],
    )

    assert result.exit_code == 0
    assert "default compat profile: shenma" in result.stdout
    assert "compat: profiles=2" in result.stdout
    assert "compat:shenma *" in result.stdout
    assert "compat:aigocode" in result.stdout
    assert "temperature=on" in result.stdout
    assert "temperature=off" in result.stdout


def test_config_translation_set_and_show(monkeypatch, tmp_path: Path) -> None:
    import youtube_strataread.config as config

    target = tmp_path / "config.toml"
    monkeypatch.setattr(config, "config_path", lambda: target)

    result = runner.invoke(
        app,
        [
            "--config",
            str(target),
            "config",
            "translation",
            "set",
            "--mode",
            "force",
            "--agent",
            "social_translation_agent",
            "--target-lang",
            "en",
            "--chunk-chars",
            "5000",
        ],
    )

    assert result.exit_code == 0
    assert "mode=force" in result.stdout
    assert "agent=social_translation_agent" in result.stdout

    show_result = runner.invoke(
        app,
        ["--config", str(target), "config", "translation", "show"],
    )

    assert show_result.exit_code == 0
    assert "translation mode=force" in show_result.stdout
    assert "target=en" in show_result.stdout
    assert "chunk_chars=5000" in show_result.stdout
