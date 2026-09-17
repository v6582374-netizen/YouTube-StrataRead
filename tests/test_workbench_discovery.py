from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from youtube_strataread.workbench.connection import SubscriptionSource
from youtube_strataread.workbench.discovery import Candidate, SubscriptionDiscovery
from youtube_strataread.workbench.workspace import LocalWorkspace


@dataclass
class FakeAtomFeed:
    entries: dict[str, list[Candidate]]

    def fetch(self, source: SubscriptionSource) -> list[Candidate]:
        return self.entries[source.channel_id]


def test_discovery_creates_idempotent_queued_inbox_candidates(tmp_path: Path) -> None:
    workspace = LocalWorkspace.open(tmp_path / "workspace")
    workspace.replace_subscription_sources([SubscriptionSource(channel_id="alpha", title="Alpha")])
    discovery = SubscriptionDiscovery(
        workspace=workspace,
        feeds=FakeAtomFeed(
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
            "preparation_state": "queued",
            "failure_reason": None,
        }
    ]
