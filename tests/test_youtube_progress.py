"""Durable cancellation and observation through real workspace/host boundaries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from test_workbench_library import candidate, ready_service

from youtube_strataread.workbench.workspace import LocalWorkspace


def test_cancel_survives_discovery_restart_retry_and_preserves_materials(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    ready_service(workspace).run_next()
    original = workspace.document("one")
    workspace.queue_regeneration("one")
    assert workspace.change_queue(["one", "one"])["changed"] == ["one"]
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.recover_interrupted_preparations()
    assert not workspace.add_candidate(candidate("one"))
    assert workspace.retry_failed() == 0
    assert workspace.claim_next_queued_asset() is None
    assert workspace.document("one") == original
    assert workspace.retained_transcript("one")
    with pytest.raises(ValueError, match="恢复"):
        workspace.queue_regeneration("one")
    assert workspace.activity()["cancelled"] == 1
    assert workspace.activity()["queued"] == 0
    assert workspace.change_queue(["one"], restore=True)["changed"] == ["one"]
    workspace.set_meta("drain_paused", "1")
    assert workspace.claim_next_queued_asset() is None
    workspace.set_meta("drain_paused", "0")
    workspace.set_excluded_channels(["channel"])
    assert workspace.claim_next_queued_asset() is None
    workspace.set_excluded_channels([])
    assert workspace.claim_next_queued_asset()["video_id"] == "one"


def test_bulk_cancel_reports_items_that_already_started(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    for video_id in ["active", "waiting"]:
        workspace.add_candidate(candidate(video_id))
    assert workspace.claim_next_queued_asset()["video_id"] == "active"
    result = workspace.change_queue(["active", "waiting", "missing"])
    assert result == {
        "changed": ["waiting"],
        "skipped": [
            {"video_id": "active", "state": "acquiring"},
            {"video_id": "missing", "state": "missing"},
        ],
    }
    assert workspace.asset("active")["preparation_state"] == "acquiring"


@pytest.mark.parametrize("attempt", range(8))
def test_claim_cancel_race_has_exactly_one_winner(tmp_path, attempt):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    barrier = Barrier(2)

    def claim():
        barrier.wait()
        return workspace.claim_next_queued_asset()

    def cancel():
        barrier.wait()
        return workspace.change_queue(["one"])

    with ThreadPoolExecutor(2) as pool:
        claim_future, cancel_future = pool.submit(claim), pool.submit(cancel)
        claimed, cancelled = claim_future.result(), cancel_future.result()
    assert bool(claimed) != bool(cancelled["changed"])
    expected = "acquiring" if claimed else "cancelled"
    assert workspace.asset("one")["preparation_state"] == expected


def test_progress_is_durable_ordered_and_deletion_removes_events(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    workspace.claim_next_queued_asset()
    workspace.set_preparation_state("one", "generating")
    workspace.report_stage("one", "review", "第 2 段")
    snapshot = LocalWorkspace.open(tmp_path).activity()
    assert snapshot["current"][0]["preparation_stage"] == "review"
    assert snapshot["current"][0]["stage_updated_at"]
    assert [event["stage"] for event in snapshot["events"]] == ["review", "generating", "checking"]
    workspace.set_preparation_state("one", "ready")
    assert workspace.activity()["current"] == []
    workspace.delete_asset("one")
    with sqlite3.connect(workspace.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM preparation_events").fetchone()[0] == 0


def test_queue_pagination_reaches_every_item(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    for index in range(103):
        workspace.add_candidate(candidate(f"video-{index}"))
    items = [workspace.activity_items(offset=offset) for offset in [0, 50, 100]]
    assert [len(page["items"]) for page in items] == [50, 50, 3]
    assert len({row["video_id"] for page in items for row in page["items"]}) == 103


def test_console_is_bounded_durable_and_separate_from_timeline(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.add_candidate(candidate("one"))
    workspace.claim_next_queued_asset()
    original = workspace.activity()["events"]
    for i in range(505):
        workspace.report_console("one", f"request {i}")
    snapshot = LocalWorkspace.open(tmp_path).activity()
    assert len(snapshot["console"]) == 500
    assert snapshot["console"][0]["message"] == "request 5"
    assert snapshot["console"][-1]["message"] == "request 504"
    assert snapshot["events"] == original
