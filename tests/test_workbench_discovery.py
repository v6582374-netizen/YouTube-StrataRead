from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from youtube_strataread.workbench.connection import SubscriptionSource
from youtube_strataread.workbench.discovery import Candidate, SourcePage, SubscriptionDiscovery
from youtube_strataread.workbench.workspace import LocalWorkspace


@pytest.fixture(autouse=True)
def publication_clock(monkeypatch):
    monkeypatch.setattr("youtube_strataread.workbench.workspace.time", SimpleNamespace(time=lambda: 1789689600.0))



@dataclass
class FakeUploads:
    entries: dict[str, list[Candidate]]

    def fetch(self, source: SubscriptionSource) -> SourcePage:
        return SourcePage(self.entries[source.channel_id])


def test_discovery_creates_idempotent_queued_inbox_candidates(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.set_meta("drain_paused", "0")
    workspace.replace_subscription_sources([SubscriptionSource(channel_id="alpha", title="Alpha")])
    discovery = SubscriptionDiscovery(
        workspace=workspace,
        source=FakeUploads(
            entries={
                "alpha": [
                    Candidate(
                        video_id="video-1",
                        channel_id="alpha",
                        channel_title="Alpha",
                        title="New update",
                        url="https://www.youtube.com/watch?v=video-1",
                        published_at="2026-09-17T00:00:00Z",
                        published_ts=1_789_603_200,
                    )
                ]
            }
        ),
    )

    first = discovery.refresh()
    second = discovery.refresh()

    assert first.discovered == 1
    assert second.discovered == 0
    assert workspace.snapshot().as_result()["counts"]["inbox"] == 1
    assert workspace.snapshot().as_result()["inbox"] == [
        {
            "video_id": "video-1",
            "channel_title": "Alpha",
            "title": "New update",
            "url": "https://www.youtube.com/watch?v=video-1",
            "published_at": "2026-09-17T00:00:00Z",
            "duration_seconds": None,
            "preparation_state": "queued",
            "failure_reason": None,
        }
    ]


def test_excluded_channels_are_not_fetched_and_new_subscriptions_default_on(tmp_path):
    workspace = LocalWorkspace.open(tmp_path)
    workspace.set_meta("drain_paused", "0")
    workspace.replace_subscription_sources(
        [
            SubscriptionSource(channel_id="excluded", title="Excluded"),
            SubscriptionSource(channel_id="new", title="New subscription"),
        ]
    )
    workspace.set_excluded_channels(["excluded"])
    fetched = []

    class Feeds:
        def fetch(self, source):
            fetched.append(source.channel_id)
            return SourcePage([
                Candidate(
                    "new-video",
                    source.channel_id,
                    source.title,
                    "New update",
                    "https://www.youtube.com/watch?v=new-video",
                    "2026-09-18T00:00:00Z",
                    1789689600,
                )
            ])

    result = SubscriptionDiscovery(workspace=workspace, source=Feeds()).refresh()
    assert fetched == ["new"]
    assert result.discovered == 1
    assert result.scanned_sources == 1
    assert workspace.claim_next_queued_asset()["video_id"] == "new-video"
