"""Bounded subscription discovery using only the official YouTube Data API."""
from __future__ import annotations

import html
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from youtube_strataread.workbench.connection import ConnectionService, SubscriptionSource
from youtube_strataread.workbench.freshness import WINDOW_SECONDS
from youtube_strataread.workbench.workspace import LocalWorkspace
from youtube_strataread.workbench.youtube_api import (
    MAX_PAGE_ITEMS,
    MAX_SCAN_CHANNELS,
    POLL_SECONDS,
    AuthorizationRequired,
    ConnectionError,
    YouTubeAPIError,
)

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
    timing_status: str = 'publication'
    playlist_added_at: str | None = None
    source_observed_at: float | None = None
    source_observed_from: float | None = None
    source_observed_until: float | None = None


@dataclass(frozen=True)
class SourcePage:
    candidates: list[Candidate]
    complete: bool = True
    reason: str = ''


@dataclass(frozen=True)
class DiscoveryResult:
    discovered: int
    scanned_sources: int
    truncated: bool
    status: str = 'healthy'
    error: str | None = None

    def as_result(self) -> dict[str, object]:
        return dict(discovered=self.discovered, scanned_sources=self.scanned_sources,
                    truncated=self.truncated, status=self.status, error=self.error)


class UploadsSource(Protocol):
    def fetch(self, source: SubscriptionSource) -> SourcePage: ...


class YouTubeUploadsAPI:
    def __init__(self, *, workspace: LocalWorkspace, connection: ConnectionService) -> None:
        self.workspace, self.connection = workspace, connection

    def fetch(self, source: SubscriptionSource) -> SourcePage:
        scan = self.workspace.source_scan(source.channel_id)
        uploads = scan.get('uploads_playlist_id')
        if not uploads or time.time() - (scan.get('uploads_checked_at') or 0) >= 86400:
            payload = self.connection.youtube_get('channels', {'part':'contentDetails', 'id':source.channel_id})
            channels = [item for item in payload['items'] if isinstance(item, dict) and item.get('id') == source.channel_id]
            uploads = _object(_object(channels[0].get('contentDetails')).get('relatedPlaylists')).get('uploads') if channels else None
            if not isinstance(uploads, str) or not uploads:
                raise YouTubeAPIError('channel')
            self.workspace.record_source_scan(source.channel_id, uploads_playlist_id=uploads, uploads_checked_at=time.time())
        observed_from = time.time()
        listing = self.connection.youtube_get('playlistItems', {
            'part':'snippet,contentDetails', 'playlistId':uploads, 'maxResults':str(MAX_PAGE_ITEMS),
        })
        observed_until = time.time()
        entries: dict[str, dict] = {}
        complete = not bool(listing.get('nextPageToken')) and len(listing['items']) <= MAX_PAGE_ITEMS
        for item in listing['items'][:MAX_PAGE_ITEMS]:
            if not isinstance(item, dict) or not isinstance(item.get('contentDetails'), dict):
                complete = False
                continue
            video_id = item['contentDetails'].get('videoId')
            if not isinstance(video_id, str) or not video_id:
                complete = False
                continue
            entries[video_id] = item
        observations = self.workspace.observe_uploads(list(entries), observed_from, observed_until)
        known: dict[str, dict] = {}
        for video_id in entries:
            try:
                asset = self.workspace.asset(video_id)
                # Uncertain timing and legacy feed facts still require authoritative details.
                if asset.get('source_observed_at') and asset['preparation_state'] != 'awaiting_timing':
                    known[video_id] = asset
            except KeyError:
                pass
        needed = [video_id for video_id in entries if video_id not in known]
        details: dict[str, dict] = {}
        if needed:
            payload = self.connection.youtube_get('videos', {
                'part':'snippet,contentDetails,status,liveStreamingDetails', 'id':','.join(needed),
            })
            details = {item['id']:item for item in payload['items'] if isinstance(item,dict) and isinstance(item.get('id'),str)}
        candidates = []
        for video_id, entry in entries.items():
            added = _object(entry.get('snippet')).get('publishedAt')
            if video_id in known:
                asset = known[video_id]
                published_at = str(asset['published_at'])
                title = str(asset['title'])
                published_ts = _published_timestamp(published_at)
                timing_status = str(asset.get('timing_status') or 'unverified')
            else:
                video = details.get(video_id, {})
                snippet = video.get('snippet') if isinstance(video.get('snippet'), dict) else {}
                status = video.get('status') if isinstance(video.get('status'), dict) else {}
                published_at = str(snippet.get('publishedAt') or '')
                published_ts = _published_timestamp(published_at)
                playlist_publication = entry['contentDetails'].get('videoPublishedAt')
                if playlist_publication and _published_timestamp(str(playlist_publication)) != published_ts:
                    published_ts = None
                ordinary = (snippet.get('channelId') == source.channel_id
                            and snippet.get('liveBroadcastContent') == 'none'
                            and not video.get('liveStreamingDetails')
                            and status.get('privacyStatus') == 'public'
                            and status.get('uploadStatus') == 'processed')
                timing_status = 'publication' if ordinary else 'unverified'
                if snippet.get('liveBroadcastContent') in ('live','upcoming') or video.get('liveStreamingDetails'):
                    timing_status = 'event'
                if not video or not ordinary or published_ts is None:
                    complete = False
                title = str(snippet.get('title') or _object(entry.get('snippet')).get('title') or video_id)
            candidates.append(Candidate(
                video_id, source.channel_id, source.title, html.unescape(title),
                'https://www.youtube.com/watch?v=' + video_id, published_at, published_ts,
                timing_status=timing_status, playlist_added_at=str(added) if added else None,
                source_observed_at=observations[video_id]['observed_until'],
                source_observed_from=observations[video_id]['observed_from'],
                source_observed_until=observations[video_id]['observed_until'],
            ))
        reason = '' if complete else '补查未完成：本轮仅检查一页上传列表，或仍有视频详情待核实。'
        return SourcePage(candidates, complete, reason)


class SubscriptionDiscovery:
    """One bounded pass; discovery never waits for captions or model processing."""
    def __init__(self, *, workspace: LocalWorkspace, source: UploadsSource) -> None:
        self.workspace, self.source = workspace, source
        self._lock = threading.Lock()
        self._stopping = threading.Event()

    @staticmethod
    def now() -> float:
        return time.time()

    def run(self, stop: threading.Event, wake: threading.Event | None = None) -> None:
        """Independent local scheduler; no subtitle/model work runs on this loop."""
        while not stop.wait(.5):
            if self.workspace.meta('drain_paused') == '1':
                continue
            previous = json.loads(self.workspace.meta('youtube_discovery') or '{}')
            due = previous.get('next_scan_at', 0)
            if isinstance(self.source, YouTubeUploadsAPI):
                gate = self.source.connection.api.gate()
                # Retry transient/global failures only when their own deadline permits.
                if gate.get('retry_at'):
                    due = gate['retry_at']
                elif gate.get('kind') == 'authorization':
                    continue
            if time.time() < due and not (wake and wake.is_set()):
                continue
            if wake:
                wake.clear()
            self.refresh(automatic=True)

    def stop(self) -> None:
        self._stopping.set()

    def refresh(self, *, limit: int = _MAX_REFRESH_CANDIDATES, automatic: bool = False) -> DiscoveryResult:
        if not 1 <= limit <= _MAX_REFRESH_CANDIDATES:
            raise ConnectionError('Discovery limit must be between 1 and 100')
        with self._lock:
            return self._discover(limit, automatic=automatic)

    def backfill(self, *, days: int = 3, limit: int = _MAX_REFRESH_CANDIDATES) -> DiscoveryResult:
        if days <= 0:
            raise ConnectionError('Backfill days must be positive')
        # The basic pass remains bounded; requested history cannot bypass the start window.
        return self.refresh(limit=limit)

    def _discover(self, limit: int, *, automatic: bool) -> DiscoveryResult:
        started = time.time()
        discovered = scanned = 0
        truncated = False
        errors: list[str] = []
        status, error = 'healthy', None
        excluded = set(self.workspace.excluded_channels())
        sources = [source for source in self.workspace.subscription_sources() if source['channel_id'] not in excluded]
        self.workspace.set_meta('youtube_discovery_scanning', '1')
        try:
            if isinstance(self.source, YouTubeUploadsAPI) and not self.source.connection.status().authorized:
                raise AuthorizationRequired('YouTube 授权失效，请重新连接。')
            for data in sources[:MAX_SCAN_CHANNELS]:
                if self._stopping.is_set() or (automatic and self.workspace.meta('drain_paused') == '1'):
                    truncated, status = True, 'paused'
                    break
                if discovered >= limit:
                    truncated = True
                    break
                source = SubscriptionSource(**data)
                source_started = time.time()
                scanned += 1
                try:
                    page = self.source.fetch(source)
                    page_truncated = False
                    for candidate in page.candidates:
                        if discovered >= limit:
                            page_truncated = True
                            break
                        if self.workspace.add_candidate(candidate):
                            discovered += 1
                    complete = page.complete and not page_truncated
                    truncated = truncated or not complete
                    self.workspace.record_source_scan(source.channel_id,
                        last_started_at=source_started, last_finished_at=time.time(), last_success_at=time.time(),
                        valid_from=started-WINDOW_SECONDS if complete else None,
                        valid_until=started if complete else None, complete=int(complete),
                        error='', coverage_reason=page.reason or ('补查未完成：本轮新增数量达到上限。' if not complete else ''))
                except YouTubeAPIError as failure:
                    self.workspace.record_source_scan(source.channel_id, last_started_at=source_started,
                        last_finished_at=time.time(), complete=0, error=str(failure), coverage_reason='补查未完成')
                    if failure.global_failure:
                        raise
                    self.workspace.record_source_scan(source.channel_id, uploads_checked_at=0)
                    errors.append(source.title)
                    truncated = True
            if len(sources) > MAX_SCAN_CHANNELS:
                truncated = True
            if truncated and status == 'healthy':
                status = 'partial'
            if errors:
                error = '部分频道不可用，其他频道继续检查。'
        except AuthorizationRequired as failure:
            status, error, truncated = 'authorization', str(failure), True
        except YouTubeAPIError as failure:
            status, error, truncated = failure.kind, str(failure), True
        except ConnectionError:
            status, error, truncated = 'service', 'YouTube 官方 API 暂不可用，稍后重试。', True
        finally:
            self.workspace.set_meta('youtube_discovery_scanning', '0')
        self.workspace.set_meta('youtube_discovery_finished_at', str(time.time()))
        result = DiscoveryResult(discovered, scanned, truncated, status, error)
        self.workspace.set_meta('youtube_discovery', json.dumps({
            **result.as_result(), 'started_at':started, 'finished_at':time.time(),
            'next_scan_at':max(started + POLL_SECONDS, time.time()), 'source_count':len(sources),
        }))
        return result

    def snapshot(self) -> dict[str, object]:
        result = json.loads(self.workspace.meta('youtube_discovery') or '{}')
        result['scanning'] = self.workspace.meta('youtube_discovery_scanning') == '1'
        result['sources'] = self.workspace.source_scans()
        if isinstance(self.source, YouTubeUploadsAPI):
            excluded = set(self.workspace.excluded_channels())
            sources = self.workspace.subscription_sources()
            result['budget'] = self.source.connection.api.snapshot(
                channels=sum(s['channel_id'] not in excluded for s in sources), subscriptions=len(sources))
        return result


def _published_timestamp(value: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}
