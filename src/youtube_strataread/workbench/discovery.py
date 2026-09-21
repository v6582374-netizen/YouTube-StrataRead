"""Bounded Atom feed discovery for local Subscription sources."""

from __future__ import annotations

import html
import time
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from youtube_strataread.downloader.request_policy import YouTubeRequestPolicy, rate_limit_error
from youtube_strataread.workbench.connection import ConnectionError, SubscriptionSource
from youtube_strataread.workbench.workspace import LocalWorkspace

_RSS_URL = "https://www.youtube.com/feeds/videos.xml"
_MAX_REFRESH_CANDIDATES = 100


@dataclass(frozen=True)
class Candidate:
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    url: str
    published_at: str
    published_ts: float | None


@dataclass(frozen=True)
class DiscoveryResult:
    discovered: int
    scanned_sources: int
    truncated: bool

    def as_result(self) -> dict[str, object]:
        return {
            "discovered": self.discovered,
            "scanned_sources": self.scanned_sources,
            "truncated": self.truncated,
        }


class AtomFeeds(Protocol):
    def fetch(self, source: SubscriptionSource) -> list[Candidate]: ...


class YouTubeAtomFeeds:
    """Reads the public Atom update feed for a single channel."""

    def __init__(self, requests: YouTubeRequestPolicy | None = None) -> None:
        self.requests = requests

    def fetch(self, source: SubscriptionSource) -> list[Candidate]:
        try:
            if self.requests:
                self.requests.before_request()
            with urlopen(
                f"{_RSS_URL}?{urlencode({'channel_id': source.channel_id})}", timeout=30
            ) as response:
                payload = response.read()
            root = element_tree.fromstring(payload)
        except (OSError, element_tree.ParseError) as error:
            limited = rate_limit_error(error)
            if limited:
                raise (self.requests.limit(limited) if self.requests else limited) from error
            raise ConnectionError("YouTube update feed could not be read") from error
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        candidates: list[Candidate] = []
        for entry in root.findall("atom:entry", namespaces):
            video_id = (
                entry.findtext("yt:videoId", default="", namespaces=namespaces) or ""
            ).strip()
            if not video_id:
                continue
            published_at = entry.findtext("atom:published", default="", namespaces=namespaces) or ""
            candidates.append(
                Candidate(
                    video_id=video_id,
                    channel_id=source.channel_id,
                    channel_title=(
                        entry.findtext(
                            "atom:author/atom:name", default=source.title, namespaces=namespaces
                        )
                        or source.title
                    ),
                    title=html.unescape(
                        entry.findtext("atom:title", default=video_id, namespaces=namespaces)
                        or video_id
                    ),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                    published_ts=_published_timestamp(published_at),
                )
            )
        return candidates


class SubscriptionDiscovery:
    """Adds new feed entries to Inbox without fetching subtitles or manuscripts."""

    def __init__(self, *, workspace: LocalWorkspace, feeds: AtomFeeds) -> None:
        self.workspace = workspace
        self.feeds = feeds

    def refresh(self, *, limit: int = _MAX_REFRESH_CANDIDATES) -> DiscoveryResult:
        return self._discover(limit=limit, since=None)

    def backfill(self, *, days: int = 7, limit: int = _MAX_REFRESH_CANDIDATES) -> DiscoveryResult:
        if days <= 0:
            raise ConnectionError("Backfill days must be positive")
        return self._discover(limit=limit, since=time.time() - days * 24 * 60 * 60)

    def _discover(self, *, limit: int, since: float | None) -> DiscoveryResult:
        if limit <= 0 or limit > _MAX_REFRESH_CANDIDATES:
            raise ConnectionError("Discovery limit must be between 1 and 100")
        discovered = 0
        scanned_sources = 0
        excluded = set(self.workspace.excluded_channels())
        for source_data in self.workspace.subscription_sources():
            if source_data["channel_id"] in excluded:
                continue
            source = SubscriptionSource(
                channel_id=str(source_data["channel_id"]),
                title=str(source_data["title"]),
                description=str(source_data["description"] or ""),
                thumbnail_url=source_data["thumbnail_url"],
                subscribed_at=source_data["subscribed_at"],
            )
            scanned_sources += 1
            for candidate in self.feeds.fetch(source):
                if since is not None and (
                    candidate.published_ts is None or candidate.published_ts < since
                ):
                    continue
                if discovered >= limit:
                    return DiscoveryResult(discovered, scanned_sources, truncated=True)
                if self.workspace.add_candidate(candidate):
                    discovered += 1
        return DiscoveryResult(discovered, scanned_sources, truncated=False)


def _published_timestamp(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
