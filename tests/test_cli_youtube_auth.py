from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from youtube_strataread.cli import app
from youtube_strataread.downloader.youtube import SubtitleResult
from youtube_strataread.pipeline.orchestrator import PipelineResult

runner = CliRunner()


def test_fetch_cmd_passes_cookie_options(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    def fake_download_subtitles(
        url: str,
        preferred_lang: str | None = None,
        *,
        cookies_from_browser: str | None = None,
        cookiefile: Path | None = None,
    ) -> SubtitleResult:
        seen["url"] = url
        seen["preferred_lang"] = preferred_lang
        seen["cookies_from_browser"] = cookies_from_browser
        seen["cookiefile"] = cookiefile
        return SubtitleResult(
            video_id="vid123",
            title="Demo",
            language="en",
            is_auto=False,
            srt_text="1\n00:00:00,000 --> 00:00:01,000\nhello\n",
        )

    import youtube_strataread.downloader as downloader

    monkeypatch.setattr(downloader, "download_subtitles", fake_download_subtitles)

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("cookies", encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "fetch",
            "https://youtu.be/abcdefghijk",
            "--lang",
            "en",
            "--cookies-from-browser",
            "safari",
            "--cookies",
            str(cookies),
            "--out",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    assert seen == {
        "url": "https://youtu.be/abcdefghijk",
        "preferred_lang": "en",
        "cookies_from_browser": "safari",
        "cookiefile": cookies.resolve(),
    }


def test_run_cmd_passes_cookie_options(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    def fake_run_pipeline(**kwargs) -> PipelineResult:
        seen.update(kwargs)
        out_dir = tmp_path / "demo"
        out_dir.mkdir()
        md_path = out_dir / "demo.md"
        md_path.write_text("# Demo\n", encoding="utf-8")
        srt_path = out_dir / "raw.srt"
        srt_path.write_text("", encoding="utf-8")
        return PipelineResult(
            video_id="vid123",
            title="Demo",
            slug="demo",
            out_dir=out_dir,
            srt_path=srt_path,
            markdown_path=md_path,
        )

    def fake_run_reader(*, md_path: Path, mode: str, cpm: int | None) -> None:
        seen["reader_md_path"] = md_path
        seen["reader_mode"] = mode
        seen["reader_cpm"] = cpm

    import youtube_strataread.pipeline.orchestrator as orchestrator
    import youtube_strataread.reader.app as reader_app

    monkeypatch.setattr(orchestrator, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(reader_app, "run_reader", fake_run_reader)

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("cookies", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "run",
            "https://youtu.be/abcdefghijk",
            "--provider",
            "openai",
            "--model",
            "o4-mini",
            "--lang",
            "en",
            "--mode",
            "stream",
            "--cpm",
            "900",
            "--cookies-from-browser",
            "firefox:Default",
            "--cookies",
            str(cookies),
            "--out",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert seen["cookies_from_browser"] == "firefox:Default"
    assert seen["cookiefile"] == cookies.resolve()
    assert seen["provider"] == "openai"
    assert seen["model_override"] == "o4-mini"
    assert seen["lang"] == "en"
    assert seen["reader_mode"] == "stream"
    assert seen["reader_cpm"] == 900


def test_run_cmd_passes_compat_profile(monkeypatch, tmp_path) -> None:
    seen: dict[str, object] = {}

    def fake_run_pipeline(**kwargs) -> PipelineResult:
        seen.update(kwargs)
        out_dir = tmp_path / "demo"
        out_dir.mkdir()
        md_path = out_dir / "demo.md"
        md_path.write_text("# Demo\n", encoding="utf-8")
        srt_path = out_dir / "raw.srt"
        srt_path.write_text("", encoding="utf-8")
        return PipelineResult(
            video_id="vid123",
            title="Demo",
            slug="demo",
            out_dir=out_dir,
            srt_path=srt_path,
            markdown_path=md_path,
        )

    def fake_run_reader(*, md_path: Path, mode: str, cpm: int | None) -> None:
        seen["reader_mode"] = mode

    import youtube_strataread.pipeline.orchestrator as orchestrator
    import youtube_strataread.reader.app as reader_app

    monkeypatch.setattr(orchestrator, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(reader_app, "run_reader", fake_run_reader)

    result = runner.invoke(
        app,
        [
            "run",
            "https://youtu.be/abcdefghijk",
            "--provider",
            "compat",
            "--compat-profile",
            "shenma",
            "--model",
            "claude-sonnet-4-5",
            "--out",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert seen["provider"] == "compat"
    assert seen["compat_profile"] == "shenma"
