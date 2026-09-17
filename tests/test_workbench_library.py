from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from youtube_strataread.downloader.youtube import SubtitleResult, YouTubeError
from youtube_strataread.workbench.discovery import Candidate
from youtube_strataread.workbench.library import LibraryService, PreparationService
from youtube_strataread.workbench.workspace import LocalWorkspace


@dataclass
class FakeCaptions:
    result: SubtitleResult | Exception

    def acquire(self, url: str) -> SubtitleResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakeManuscripts:
    markdown: str

    def generate(self, transcript: str) -> str:
        return self.markdown


def candidate(video_id: str, title: str = "A video") -> Candidate:
    return Candidate(
        video_id=video_id,
        channel_id="channel",
        channel_title="A channel",
        title=title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        published_at="2026-09-17T10:00:00Z",
        published_ts=1_789_632_000,
    )


def ready_service(workspace: LocalWorkspace) -> PreparationService:
    return PreparationService(
        workspace=workspace,
        captions=FakeCaptions(
            SubtitleResult(
                video_id="one",
                title="A video",
                language="en",
                is_auto=False,
                srt_text="1\n00:00:00,000 --> 00:00:02,000\nsource-only phrase\n",
            )
        ),
        manuscripts=FakeManuscripts("# 一份可信的中文稿件\n\n可检索的正文。\n"),
    )


def test_prepared_asset_is_searchable_versioned_and_handed_off(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.add_candidate(candidate("one"))
    preparation = ready_service(workspace)
    library = LibraryService(workspace=workspace, preparation=preparation)

    assert preparation.run_next() is True

    inbox = library.list_assets()
    assert inbox["total"] == 1
    asset = inbox["assets"][0]
    assert asset["preparation_state"] == "ready"
    assert asset["reading_state"] == "inbox"
    assert asset["manuscript_version"] == 1

    inspection = library.inspect("one")
    assert inspection["source_trace"]["video_url"].endswith("v=one")
    assert inspection["source_trace"]["transcript_available"] is True
    assert library.document("one")["markdown"].startswith("# 一份可信")
    assert Path(str(library.document("one")["path"])).is_file()

    assert library.search(query="source-only")["total"] == 0
    assert library.search(query="source-only", include_transcript=True)["total"] == 1
    assert library.search(query="可信")["total"] == 1

    library.set_reading_state("one", "to-read")
    assert library.list_assets(reading_state="to-read")["total"] == 1
    library.regenerate("one")
    assert preparation.run_next() is True
    assert library.inspect("one")["manuscript_version"] == 2

    library.delete("one")
    assert library.list_assets()["total"] == 0


def test_unavailable_and_drain_pause_keep_batch_outcomes_visible(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.add_candidate(candidate("one"))
    workspace.add_candidate(candidate("two", "Second video"))
    preparation = PreparationService(
        workspace=workspace,
        captions=FakeCaptions(YouTubeError("no subtitles were available")),
        manuscripts=FakeManuscripts("never used"),
    )
    library = LibraryService(workspace=workspace, preparation=preparation)

    preparation.request_drain_pause()
    assert preparation.run_next() is False

    activity = library.activity()
    assert activity["drain_paused"] is True
    assert activity["unavailable"] == 0
    assert activity["queued"] == 2
    assert activity["cost_estimate"] is None
    assert library.retry_all_failed()["queued"] == 0

    preparation.resume()
    assert preparation.run_next() is True
    activity = library.activity()
    assert activity["unavailable"] == 1
    assert activity["failures"][0]["reason"] == "no subtitles were available"
