"""Shared, durable pacing and cooldown for the workbench's YouTube traffic."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

REQUEST_INTERVAL = 2.0
VIDEO_INTERVAL = 15.0
INITIAL_COOLDOWN = 15 * 60
MAX_COOLDOWN = 6 * 60 * 60
MAX_RATE_LIMIT_ATTEMPTS = 4
_STATE_KEY = "youtube_request_policy"


class YouTubeError(RuntimeError):
    """Public acquisition error shared by the CLI and the workbench."""


class YouTubeRateLimited(YouTubeError):
    def __init__(
        self,
        retry_at: float | None = None,
        *,
        recorded: bool = False,
        response_received: bool = True,
    ) -> None:
        super().__init__("YouTube 请求限流，正在冷却，稍后自动重试。")
        self.retry_at = retry_at
        self.recorded = recorded
        self.response_received = response_received


class YouTubeRequestsStopped(RuntimeError):
    pass


def rate_limit_error(
    error: BaseException, *, now: float | None = None
) -> YouTubeRateLimited | None:
    """Preserve Retry-After through urllib/yt-dlp exception wrappers."""
    now = time.time() if now is None else now
    pending, seen = [error], set()
    found, retry_at = False, None
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, YouTubeRateLimited):
            return item
        response = getattr(item, "response", None)
        status = (
            getattr(item, "status", None)
            or getattr(item, "code", None)
            or getattr(response, "status", None)
        )
        if status == 429 or re.search(
            r"HTTP(?: Error)?[ :]+429\b|Too Many Requests", str(item), re.I
        ):
            found = True
            headers = getattr(item, "headers", None) or getattr(response, "headers", None)
            value = headers.get("Retry-After") if headers else None
            if value:
                try:
                    deadline = now + max(0, int(value.strip()))
                except (ValueError, AttributeError):
                    try:
                        deadline = parsedate_to_datetime(value).timestamp()
                    except (ValueError, TypeError, OverflowError):
                        deadline = now
                retry_at = max(retry_at or now, deadline)
        pending.extend(cause for cause in (item.__cause__, item.__context__) if cause is not None)
        exc_info = getattr(item, "exc_info", None)
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) > 1
            and isinstance(exc_info[1], BaseException)
        ):
            pending.append(exc_info[1])
    return YouTubeRateLimited(retry_at) if found else None


class YouTubeRequestPolicy:
    """SQLite serializes reservations across workers and survives application restarts.

    These conservative intervals are product defaults, not published YouTube limits.
    Only successful caption acquisition resets the exponential cooldown streak;
    a successful RSS or watch page must not undo repeated subtitle rate limits.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.now = time.time
        self.stopped = threading.Event()

    @staticmethod
    def _read(connection) -> dict:
        row = connection.execute(
            "SELECT value FROM workspace_meta WHERE key = ?", (_STATE_KEY,)
        ).fetchone()
        return (
            json.loads(row[0])
            if row
            else {
                "cooldown_until": 0,
                "strikes": 0,
                "next_request_at": 0,
                "next_video_at": 0,
            }
        )

    @staticmethod
    def _write(connection, state: dict) -> None:
        connection.execute(
            "INSERT INTO workspace_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_STATE_KEY, json.dumps(state)),
        )

    def snapshot(self) -> dict:
        with sqlite3.connect(self.database_path) as connection:
            return self._read(connection)

    def cooling_down(self) -> bool:
        return self.snapshot()["cooldown_until"] > self.now()

    def _take_slot(self, field: str, interval: float) -> None:
        while True:
            if self.stopped.is_set():
                raise YouTubeRequestsStopped("YouTube requests stopped")
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                state, now = self._read(connection), self.now()
                if state["cooldown_until"] > now:
                    raise YouTubeRateLimited(
                        state["cooldown_until"], recorded=True, response_received=False
                    )
                delay = state[field] - now
                if delay <= 0:
                    state[field] = now + interval
                    self._write(connection, state)
                    return
            # Never hold the database while waiting, and remain interruptible on quit.
            self.stopped.wait(min(delay, 0.5))

    def before_request(self) -> None:
        self._take_slot("next_request_at", REQUEST_INTERVAL)

    def before_video(self) -> None:
        self._take_slot("next_video_at", VIDEO_INTERVAL)

    def limit(self, error: YouTubeRateLimited) -> YouTubeRateLimited:
        if error.recorded:
            return error
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            state, now = self._read(connection), self.now()
            state["strikes"] += 1
            delay = min(MAX_COOLDOWN, INITIAL_COOLDOWN * 2 ** min(state["strikes"] - 1, 8))
            state["cooldown_until"] = max(state["cooldown_until"], now + delay, error.retry_at or 0)
            self._write(connection, state)
        return YouTubeRateLimited(state["cooldown_until"], recorded=True)

    def caption_succeeded(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = self._read(connection)
            # Another in-flight request may have just imposed a cooldown.
            if state["cooldown_until"] <= self.now():
                state["strikes"] = 0
                self._write(connection, state)
