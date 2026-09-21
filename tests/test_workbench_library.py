from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from shorts_fixture import RegularVideos

from youtube_strataread.downloader.youtube import SubtitleResult, YouTubeError
from youtube_strataread.workbench.discovery import Candidate
from youtube_strataread.workbench.library import AutomaticBatch, LibraryService, PreparationService
from youtube_strataread.workbench.workspace import LocalWorkspace


def test_new_video_metadata_survives_preparation_and_workspace_restart(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    queued = workspace.activity_items()["items"][0]
    published_at = queued["published_at"]
    assert published_at == workspace.asset("one")["published_at"]
    assert queued["duration_seconds"] is None

    preparation = ready_service(workspace)
    preparation.captions.result.duration_seconds = 2538
    assert preparation.run_next()

    reopened = LocalWorkspace.open(workspace.root)
    library = LibraryService(workspace=reopened, preparation=ready_service(reopened))
    for video in (
        reopened.snapshot().as_result()["inbox"][0],
        reopened.activity_items("ready")["items"][0],
        library.list_assets()["assets"][0],
        library.inspect("one"),
    ):
        assert video["published_at"] == published_at
        assert video["duration_seconds"] == 2538

    library.regenerate("one")
    assert library.preparation.run_next()
    assert library.inspect("one")["duration_seconds"] == 2538


@dataclass
class FakeCaptions:
    result: SubtitleResult | Exception

    def acquire(self, url: str) -> SubtitleResult:
        if isinstance(self.result, Exception):
            raise self.result
        return replace(self.result, video_id=url.split("=")[-1])


@dataclass
class FakeManuscripts:
    markdown: str

    def generate(self, transcript: str) -> str:
        return self.markdown


def candidate(video_id: str, title: str = "A video") -> Candidate:
    timestamp = time.time() - 60
    return Candidate(
        video_id=video_id,
        channel_id="channel",
        channel_title="A channel",
        title=title,
        url=f"https://www.youtube.com/watch?v={video_id}",
        published_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
        published_ts=timestamp,
    )


def ready_service(workspace: LocalWorkspace) -> PreparationService:
    return PreparationService(
        workspace=workspace,
        shorts=RegularVideos(),
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
    workspace.set_meta("drain_paused", "0")
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
    record = inspection["generation_records"][0]
    assert record == {
        "manuscript_version": 1,
        "generator": "FakeManuscripts",
        "transcript_characters": len("source-only phrase"),
        "manuscript_characters": len("# 一份可信的中文稿件\n\n可检索的正文。\n"),
        "created_at": record["created_at"],
    }
    assert isinstance(record["created_at"], float)
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
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    workspace.add_candidate(candidate("two", "Second video"))
    preparation = PreparationService(
        workspace=workspace,
        captions=FakeCaptions(YouTubeError("no subtitles were available")),
        shorts=RegularVideos(),
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
    assert library.inspect("one")["generation_records"] == []


def test_automatic_batch_bounds_work_and_drains_after_the_current_asset(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    workspace.add_candidate(candidate("two", "Second video"))
    preparation = ready_service(workspace)
    batch = AutomaticBatch(preparation=preparation, limit=1)

    assert batch.run_one() is True
    assert batch.run_one() is False
    assert workspace.activity()["batch"] == {"limit": 1, "completed": 1}
    assert workspace.asset("one")["preparation_state"] == "ready"
    assert workspace.asset("two")["preparation_state"] == "queued"


def test_drain_pause_prevents_an_unclaimed_asset_from_starting(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    preparation = ready_service(workspace)

    preparation.request_drain_pause()

    assert preparation.run_next() is False
    assert workspace.asset("one")["preparation_state"] == "queued"
