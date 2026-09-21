"""Conservative platform-format detection; no duration or title heuristics."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

from youtube_strataread.downloader.request_policy import YouTubeRequestPolicy, rate_limit_error

CLASSIFICATION_RETRY_SECONDS = 15 * 60
_MAX_PAGE_BYTES = 4 * 1024 * 1024
_PLAYER_ASSIGNMENT = re.compile(
    r'(?:var\s+ytInitialPlayerResponse|window\["ytInitialPlayerResponse"\]|ytInitialPlayerResponse)\s*=\s*'
)


class ShortsClassifier(Protocol):
    def classify(self, video_id: str) -> bool | None:
        """True = Short, False = ordinary video, None = cannot establish format."""
        ...


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.scripts: list[str] = []
        self._script: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "link" and "canonical" in (attributes.get("rel") or "").lower().split():
            self.canonicals.append(attributes.get("href") or "")
        if tag == "script":
            self._script = []

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script))
            self._script = None


def classify_page(video_id: str, html: str) -> bool | None:
    """Require a playable, identity-matched player and matching canonical format.

    isShortsEligible is an observed YouTube web signal, not a public API contract.
    In particular, a broken Shorts URL can serve a different recommended video.
    Missing or contradictory evidence therefore never admits an ordinary video.
    """
    page = _Page()
    page.feed(html)
    if len(page.canonicals) != 1:
        return None
    canonical = urlsplit(page.canonicals[0])
    if canonical.scheme != "https" or canonical.netloc not in {"www.youtube.com", "youtube.com"}:
        return None
    if canonical.path == f"/shorts/{video_id}":
        canonical_short = True
    elif canonical.path == "/watch" and parse_qs(canonical.query).get("v") == [video_id]:
        canonical_short = False
    else:
        return None
    players = []
    for script in page.scripts:
        for match in _PLAYER_ASSIGNMENT.finditer(script):
            try:
                player, _ = json.JSONDecoder().raw_decode(script[match.end() :])
            except ValueError:
                return None
            players.append(player)
    if len(players) != 1 or not isinstance(players[0], dict):
        return None
    player = players[0]
    status = player.get("playabilityStatus")
    details = player.get("videoDetails")
    microformat = player.get("microformat")
    if not isinstance(status, dict) or status.get("status") != "OK":
        return None
    if not isinstance(details, dict) or details.get("videoId") != video_id:
        return None
    if not isinstance(microformat, dict):
        return None
    renderer = microformat.get("playerMicroformatRenderer")
    if not isinstance(renderer, dict) or renderer.get("externalVideoId", video_id) != video_id:
        return None
    signal = renderer.get("isShortsEligible")
    return signal if type(signal) is bool and signal == canonical_short else None


class YouTubeShortsClassifier:
    def __init__(self, requests: YouTubeRequestPolicy | None = None) -> None:
        self.requests = requests

    def classify(self, video_id: str) -> bool | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            return None
        request = Request(
            f"https://www.youtube.com/watch?v={video_id}&hl=en",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        try:
            if self.requests:
                self.requests.before_request()
            with urlopen(request, timeout=15) as response:
                if response.status != 200:
                    return None
                final_url = urlsplit(response.geturl())
                if final_url.netloc not in {"www.youtube.com", "youtube.com"}:
                    return None
                data = response.read(_MAX_PAGE_BYTES + 1)
            if len(data) > _MAX_PAGE_BYTES:
                return None
            return classify_page(video_id, data.decode("utf-8"))
        except (OSError, ValueError) as error:
            limited = rate_limit_error(error)
            if limited:
                raise (self.requests.limit(limited) if self.requests else limited) from error
            return None
