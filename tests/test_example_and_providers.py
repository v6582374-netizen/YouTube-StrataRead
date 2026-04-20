from __future__ import annotations

from bionic_youtube import config
from bionic_youtube.utils.sample import sample_dir, sample_markdown


def test_supported_providers() -> None:
    assert config.SUPPORTED_PROVIDERS == ("openai", "anthropic", "gemini", "compat")


def test_default_provider_is_anthropic() -> None:
    assert config.DEFAULT_PROVIDER == "anthropic"


def test_default_models_present_for_every_provider() -> None:
    for name in config.SUPPORTED_PROVIDERS:
        assert config.DEFAULT_MODELS[name]


def test_resolve_provider_config_sets_flavor() -> None:
    pc = config.resolve_provider_config("gemini")
    assert pc.name == "gemini"
    assert pc.api_flavor == "gemini"


def test_bundled_sample_is_accessible() -> None:
    d = sample_dir()
    assert d.is_dir()
    assert (d / "raw.srt").exists()
    md = sample_markdown()
    assert md.suffix == ".md"
    assert md.stat().st_size > 1000  # the Ivanka outline is ~20KB
