"""Platform identity, conservative admission and durable retry/retention contracts."""

import sqlite3
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from shorts_fixture import player_page
from test_workbench_library import candidate, ready_service

from youtube_strataread.workbench import shorts
from youtube_strataread.workbench.connection import SubscriptionSource
from youtube_strataread.workbench.discovery import SubscriptionDiscovery
from youtube_strataread.workbench.workspace import LocalWorkspace

VIDEO = "normal00001"


@pytest.mark.parametrize("is_short", [True, False])
def test_platform_format_not_duration_or_url_spelling(is_short):
    # Identical two-minute duration: one Short and one ordinary short video.
    assert shorts.classify_page(VIDEO, player_page(VIDEO, is_short)) is is_short


@pytest.mark.parametrize("signal", [None, "false", 0, 1, [], {}])
def test_non_boolean_platform_signals_are_unknown(signal):
    assert shorts.classify_page(VIDEO, player_page(VIDEO, signal)) is None


@pytest.mark.parametrize("status", ["ERROR", "LOGIN_REQUIRED", "UNPLAYABLE"])
def test_unplayable_videos_are_not_admitted(status):
    assert shorts.classify_page(VIDEO, player_page(VIDEO, False, status=status)) is None


def test_recommended_shorts_on_an_unavailable_video_page_cannot_classify_it():
    html = player_page("another0001", True, canonical=f"https://www.youtube.com/shorts/{VIDEO}")
    assert shorts.classify_page(VIDEO, html) is None


@pytest.mark.parametrize(
    "replacement",
    [
        '"externalVideoId": "different01"',
        '"unexpectedKey": "normal00001"',
    ],
)
def test_player_identity_must_match(replacement):
    html = player_page(VIDEO, False)
    if replacement.startswith('"externalVideoId"'):
        html = html.replace(f'"externalVideoId": "{VIDEO}"', replacement)
    else:
        html = html.replace(f'"videoId": "{VIDEO}"', replacement)
    assert shorts.classify_page(VIDEO, html) is None


@pytest.mark.parametrize(
    "canonical",
    [
        "https://www.youtube.com/shorts/normal00001",
        "https://www.youtube.com/watch?v=another0001",
        "https://consent.youtube.com/",
        "https://www.youtube.com/watch?v=normal00001&v=another0001",
    ],
)
def test_conflicting_or_wrong_canonical_is_unknown(canonical):
    assert shorts.classify_page(VIDEO, player_page(VIDEO, False, canonical=canonical)) is None


@pytest.mark.parametrize(
    "html",
    [
        "<html>Before you continue to YouTube</html>",
        "<script>var ytInitialPlayerResponse = {broken};</script>",
        '<link rel="canonical" href="https://www.youtube.com/watch?v=normal00001"><script>var ytInitialPlayerResponse = [];</script>',
    ],
)
def test_changed_or_challenge_pages_are_unknown(html):
    assert shorts.classify_page(VIDEO, html) is None


def test_conflicting_multiple_players_or_canonicals_are_unknown():
    html = player_page(VIDEO, False)
    assert shorts.classify_page(VIDEO, html + html) is None


def test_network_failures_and_invalid_ids_are_unknown(monkeypatch):
    fetch = Mock(side_effect=TimeoutError)
    monkeypatch.setattr(shorts, "urlopen", fetch)
    assert shorts.YouTubeShortsClassifier().classify(VIDEO) is None
    fetch.assert_called_once()
    fetch.reset_mock()
    assert shorts.YouTubeShortsClassifier().classify("../bad") is None
    fetch.assert_not_called()


@pytest.mark.parametrize(
    "status,url,payload",
    [
        (429, f"https://www.youtube.com/watch?v={VIDEO}", b"limited"),
        (200, "https://consent.youtube.com/", b"consent"),
        (200, f"https://www.youtube.com/watch?v={VIDEO}", b"\xff"),
        (200, f"https://www.youtube.com/watch?v={VIDEO}", b"a" * (shorts._MAX_PAGE_BYTES + 1)),
    ],
)
def test_http_failure_challenge_encoding_and_size_limits(monkeypatch, status, url, payload):
    response = BytesIO(payload)
    response.status = status
    response.geturl = lambda: url
    monkeypatch.setattr(shorts, "urlopen", lambda *args, **kwargs: response)
    assert shorts.YouTubeShortsClassifier().classify(VIDEO) is None


def test_unknown_does_not_block_other_videos_and_retries_after_restart(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("youtube_strataread.workbench.workspace.time.time", lambda: now[0])
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate("unknown0001"))
    workspace.add_candidate(candidate(VIDEO))
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=Mock(side_effect=[None, False]))
    acquire = Mock(wraps=service.captions.acquire)
    service.captions = SimpleNamespace(acquire=acquire)
    assert service.run_next()
    assert workspace.activity()["awaiting_classification"] == 1
    acquire.assert_not_called()
    assert service.run_next()
    assert workspace.activity()["ready"] == 1
    assert not service.run_next()
    assert service.shorts.classify.call_count == 2
    workspace = LocalWorkspace.open(tmp_path)
    workspace.recover_interrupted_preparations()
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=Mock(return_value=True))
    assert not service.run_next()
    now[0] += shorts.CLASSIFICATION_RETRY_SECONDS
    workspace.set_meta("drain_paused", "1")
    assert not service.run_next()
    workspace.set_meta("drain_paused", "0")
    workspace.set_excluded_channels(["channel"])
    assert not service.run_next()
    workspace.set_excluded_channels([])
    assert service.run_next()
    assert workspace.activity()["filtered"] == 1
    assert workspace.activity()["awaiting_classification"] == 0
    assert workspace.assets()[0]["video_id"] == VIDEO
    assert len(workspace.assets()) == 1


def test_short_exclusion_survives_refresh_backfill_and_retry(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    video = candidate(VIDEO)
    workspace.replace_subscription_sources(
        [SubscriptionSource(channel_id="channel", title="Channel")]
    )
    discovery = SubscriptionDiscovery(
        workspace=workspace, feeds=SimpleNamespace(fetch=lambda source: [video])
    )
    discovery.refresh()
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=Mock(return_value=True))
    service.captions = SimpleNamespace(acquire=Mock(side_effect=AssertionError("no captions")))
    assert service.run_next()
    assert not service.run_next()
    assert discovery.refresh().discovered == 0
    assert discovery.backfill(days=3650).discovered == 0
    assert workspace.retry_failed() == 0
    assert workspace.change_queue([VIDEO], restore=True)["changed"] == []
    with pytest.raises(ValueError, match="Shorts"):
        workspace.queue_regeneration(VIDEO)
    service.shorts.classify.assert_called_once_with(VIDEO)
    service.captions.acquire.assert_not_called()
    assert workspace.snapshot().as_result()["inbox"] == []
    assert workspace.snapshot().as_result()["counts"]["inbox"] == 0
    assert workspace.assets() == []
    assert workspace.activity_items("filtered")["total"] == 1
    assert workspace.generation_records(VIDEO) == []
    assert [event["stage"] for event in workspace.activity()["events"]] == ["filtered", "checking"]


def test_existing_manuscripts_and_regeneration_are_retained(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    workspace.save_manuscript(
        VIDEO, "# Existing manuscript", generator="legacy", transcript_characters=0
    )
    workspace.set_preparation_state(VIDEO, "ready")
    original = workspace.document(VIDEO)
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(
        classify=Mock(side_effect=AssertionError("do not reclassify retained assets"))
    )
    assert not service.run_next()
    assert workspace.document(VIDEO) == original
    workspace.queue_regeneration(VIDEO)
    assert service.run_next()
    assert workspace.document(VIDEO)["version"] == 2
    service.shorts.classify.assert_not_called()


def test_unknown_can_be_cancelled_and_does_not_reappear_automatically(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=lambda video_id: None)
    service.run_next()
    assert workspace.change_queue([VIDEO])["changed"] == [VIDEO]
    assert not workspace.add_candidate(candidate(VIDEO))
    assert not service.run_next()
    assert workspace.change_queue([VIDEO], restore=True)["changed"] == [VIDEO]
    service.shorts = SimpleNamespace(classify=lambda video_id: False)
    assert service.run_next()
    assert workspace.activity()["ready"] == 1


def test_detector_exception_defers_without_model_or_caption_work(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=Mock(side_effect=RuntimeError("unavailable")))
    service.captions = SimpleNamespace(acquire=Mock())
    service.manuscripts = SimpleNamespace(generate=Mock())
    assert service.run_next()
    assert workspace.activity()["awaiting_classification"] == 1
    service.captions.acquire.assert_not_called()
    service.manuscripts.generate.assert_not_called()


def test_interrupted_classification_recovers_to_deferred_not_failed(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    workspace.claim_next_queued_asset()
    workspace = LocalWorkspace.open(tmp_path)
    workspace.recover_interrupted_preparations()
    assert workspace.activity()["awaiting_classification"] == 1
    assert workspace.activity()["failed"] == 0
    assert not workspace.claim_next_queued_asset()


def test_cached_ordinary_classification_is_reused_after_caption_failure(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    service = ready_service(workspace)
    service.shorts = SimpleNamespace(classify=Mock(return_value=False))
    acquire = service.captions.acquire
    service.captions = SimpleNamespace(
        acquire=Mock(side_effect=RuntimeError("network unavailable"))
    )
    service.run_next()
    assert workspace.activity()["failed"] == 1
    workspace.retry_failed()
    service.captions = SimpleNamespace(acquire=acquire)
    service.run_next()
    assert workspace.activity()["ready"] == 1
    service.shorts.classify.assert_called_once()


def test_existing_database_migrates_without_discarding_pending_or_ready_assets(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.add_candidate(candidate(VIDEO))
    workspace.add_candidate(candidate("saved000001"))
    workspace.save_manuscript(
        "saved000001", "# Retained", generator="legacy", transcript_characters=0
    )
    with sqlite3.connect(workspace.database_path) as db:
        for column in ["shorts_status", "shorts_checked_at", "shorts_retry_at"]:
            db.execute(f"ALTER TABLE candidates DROP COLUMN {column}")
    workspace = LocalWorkspace.open(tmp_path)
    assert len(workspace.assets()) == 2
    assert workspace.document("saved000001")["markdown"] == "# Retained\n"
    assert workspace.claim_next_queued_asset()["shorts_status"] == "unknown"
