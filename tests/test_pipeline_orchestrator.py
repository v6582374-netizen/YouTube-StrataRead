from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import youtube_strataread.pipeline.orchestrator as orchestrator
from youtube_strataread.ai.base import LLMError
from youtube_strataread.config import ProviderConfig, TranslationConfig


class FakeProgress:
    last: FakeProgress | None = None

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.added: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        FakeProgress.last = self

    def __enter__(self) -> FakeProgress:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False

    def add_task(self, description: str, **fields: object) -> int:
        payload = {"description": description, **fields}
        self.added.append(payload)
        return 1

    def update(self, task_id: int, **fields: object) -> None:
        self.updates.append({"task_id": task_id, **fields})


def test_run_pipeline_shows_thinking_until_first_chunk(monkeypatch, tmp_path: Path) -> None:
    class FakeLLM:
        def chat(self, **kwargs: object) -> str:
            on_stream = kwargs["on_stream"]
            assert callable(on_stream)
            on_stream("hello")
            return "hello"

    _setup_pipeline(monkeypatch, llm=FakeLLM())
    result = orchestrator.run_pipeline(
        url="https://youtu.be/demo",
        parent=tmp_path,
        provider="compat",
    )

    progress = FakeProgress.last
    assert progress is not None
    assert progress.added[0]["status"] == "thinking..."
    statuses = [update["status"] for update in progress.updates if "status" in update]
    assert "5 chars" in statuses
    assert "0 chars" not in statuses
    assert result.markdown_path.read_text(encoding="utf-8") == "hello\n"


def test_run_pipeline_surfaces_retrying_status_before_full_response(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeLLM:
        def chat(self, **kwargs: object) -> str:
            on_status = kwargs["on_status"]
            on_stream = kwargs["on_stream"]
            assert callable(on_status)
            assert callable(on_stream)
            on_status("thinking... (retrying full response)")
            on_stream("fallback body")
            return "fallback body"

    _setup_pipeline(monkeypatch, llm=FakeLLM())
    orchestrator.run_pipeline(
        url="https://youtu.be/demo",
        parent=tmp_path,
        provider="compat",
    )

    progress = FakeProgress.last
    assert progress is not None
    statuses = [progress.added[0]["status"]]
    statuses.extend(update["status"] for update in progress.updates if "status" in update)
    assert "thinking..." in statuses
    assert "thinking... (retrying full response)" in statuses
    assert "13 chars" in statuses


def test_run_pipeline_translates_non_chinese_transcript_before_llm(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, object] = {}

    class FakeLLM:
        def chat(self, **kwargs: object) -> str:
            seen["llm_user"] = kwargs["user"]
            on_stream = kwargs["on_stream"]
            assert callable(on_stream)
            on_stream("md")
            return "md"

    class FakeTranslator:
        def __init__(self, config: TranslationConfig, *, api_key: str) -> None:
            seen["translation_config"] = config
            seen["translation_api_key"] = api_key

        def translate(self, text: str, **kwargs: object) -> str:
            seen["translation_input"] = text
            seen["translation_language"] = kwargs["subtitle_language"]
            on_stream = kwargs["on_stream"]
            assert callable(on_stream)
            on_stream("你好 transcript")
            return "你好 transcript"

    _setup_pipeline(monkeypatch, llm=FakeLLM())
    monkeypatch.setattr(
        orchestrator,
        "resolve_translation_config",
        lambda **kwargs: TranslationConfig(mode="auto"),
    )
    monkeypatch.setattr(orchestrator, "resolve_key", lambda provider: "glm-key")
    monkeypatch.setattr(orchestrator, "ZhipuAgentTranslator", FakeTranslator)

    result = orchestrator.run_pipeline(
        url="https://youtu.be/demo",
        parent=tmp_path,
        provider="compat",
    )

    assert seen["translation_api_key"] == "glm-key"
    assert seen["translation_input"] == "hello transcript"
    assert seen["translation_language"] == "en"
    assert seen["llm_user"] == "你好 transcript"
    assert result.translated_path is not None
    assert result.translated_path.read_text(encoding="utf-8") == "你好 transcript\n"


def test_run_pipeline_falls_back_when_auto_translation_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    seen: dict[str, object] = {}

    class FakeLLM:
        def chat(self, **kwargs: object) -> str:
            seen["llm_user"] = kwargs["user"]
            return "md"

    class FakeTranslator:
        def __init__(self, config: TranslationConfig, *, api_key: str) -> None:
            pass

        def translate(self, text: str, **kwargs: object) -> str:
            raise LLMError("boom")

    _setup_pipeline(monkeypatch, llm=FakeLLM())
    monkeypatch.setattr(
        orchestrator,
        "resolve_translation_config",
        lambda **kwargs: TranslationConfig(mode="auto"),
    )
    monkeypatch.setattr(orchestrator, "resolve_key", lambda provider: "glm-key")
    monkeypatch.setattr(orchestrator, "ZhipuAgentTranslator", FakeTranslator)

    result = orchestrator.run_pipeline(
        url="https://youtu.be/demo",
        parent=tmp_path,
        provider="compat",
    )

    assert seen["llm_user"] == "hello transcript"
    assert result.translated_path is None
    assert not (result.out_dir / "translated.txt").exists()


def _setup_pipeline(monkeypatch, *, llm: object) -> None:
    monkeypatch.setattr(orchestrator, "Progress", FakeProgress)
    monkeypatch.setattr(
        orchestrator,
        "resolve_provider_config",
        lambda provider, compat_profile=None: ProviderConfig(
            name=provider or "compat",
            model="claude-sonnet-4-6",
            base_url="https://relay.example/v1",
            api_key="test-key",
            api_flavor="openai",
            profile_name=compat_profile,
        ),
    )
    monkeypatch.setattr(orchestrator, "get_provider", lambda pc: llm)
    monkeypatch.setattr(
        orchestrator,
        "download_subtitles",
        lambda *args, **kwargs: SimpleNamespace(
            video_id="vid123",
            title="Demo",
            language="en",
            is_auto=False,
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nhello\n",
        ),
    )
    monkeypatch.setattr(orchestrator, "load_cues", lambda text: ["cue"])
    monkeypatch.setattr(orchestrator, "cues_to_lines", lambda cues: ["hello transcript"])
    monkeypatch.setattr(orchestrator, "load_prompt", lambda path: "prompt")
