from __future__ import annotations

from pathlib import Path

import pytest

from bionic_youtube.ai import prompts as prompts_mod


def test_materialises_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    text = prompts_mod.load_prompt()
    assert (tmp_path / "prompts.md").exists()
    assert (tmp_path / "README.md").exists()
    assert text.strip() == prompts_mod.DEFAULT_PROMPT.strip()


def test_user_edit_is_respected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    prompts_mod.load_prompt()  # seed default
    (tmp_path / "prompts.md").write_text("CUSTOM-PROMPT-BODY", encoding="utf-8")
    assert prompts_mod.load_prompt() == "CUSTOM-PROMPT-BODY"


def test_reset_restores_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    prompts_mod.load_prompt()
    (tmp_path / "prompts.md").write_text("tampered", encoding="utf-8")
    prompts_mod.reset_prompt()
    assert prompts_mod.load_prompt().strip() == prompts_mod.DEFAULT_PROMPT.strip()


def test_legacy_files_are_renamed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    # Pretend an earlier version left 3-file layout behind.
    (tmp_path / "translate.md").write_text("old translate", encoding="utf-8")
    (tmp_path / "clean.md").write_text("old clean", encoding="utf-8")
    (tmp_path / "outline.md").write_text("old outline", encoding="utf-8")
    prompts_mod.load_prompt()
    for name in ("translate.md", "clean.md", "outline.md"):
        assert not (tmp_path / name).exists(), f"{name} should have been renamed"
        assert (tmp_path / (name + ".legacy")).exists()


def test_list_prompts_discovers_user_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    prompts_mod.load_prompt()  # seed default
    (tmp_path / "podcast.md").write_text("podcast system prompt", encoding="utf-8")
    (tmp_path / "lecture.md").write_text("lecture prompt", encoding="utf-8")
    found = prompts_mod.list_prompts()
    names = [f.name for f in found]
    # README is excluded
    assert "README.md" not in names
    # default is pinned first
    assert names[0] == prompts_mod.PROMPT_FILENAME
    # all custom files surface
    assert "podcast.md" in names
    assert "lecture.md" in names


def test_load_prompt_with_explicit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BY_PROMPTS_DIR", str(tmp_path))
    prompts_mod.load_prompt()  # seed default
    custom = tmp_path / "podcast.md"
    custom.write_text("PODCAST-ONLY-PROMPT", encoding="utf-8")
    assert prompts_mod.load_prompt(custom) == "PODCAST-ONLY-PROMPT"
    # default still works unchanged
    assert prompts_mod.load_prompt().strip() == prompts_mod.DEFAULT_PROMPT.strip()


def test_default_prompt_is_verbatim() -> None:
    """The author's prompt must be stored byte-for-byte."""
    # A few signature phrases that must appear exactly as written.
    body = prompts_mod.DEFAULT_PROMPT
    assert "针对这份字幕文件，按照如下的思路处理。" in body
    assert "所谓原子模块" in body
    assert "一级标题一定要以问句的形式呈现" in body
    assert "一份骨架丰满且形式优雅的 md 文件" in body
