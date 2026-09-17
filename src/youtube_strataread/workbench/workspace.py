"""Sidecar-owned local workspace for the personal reading workbench."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_data_dir

if TYPE_CHECKING:
    from youtube_strataread.workbench.connection import SubscriptionSource
    from youtube_strataread.workbench.discovery import Candidate


@dataclass(frozen=True)
class LibrarySnapshot:
    """The minimum library state available before subscription import exists."""

    label: str = "Local Library"
    status: str = "ready"
    inbox: int = 0
    to_read: int = 0
    reading: int = 0
    read: int = 0
    candidates: list[dict[str, object]] | None = None

    def as_result(self) -> dict[str, object]:
        return {
            "workspace": {"label": self.label, "status": self.status},
            "counts": {
                "inbox": self.inbox,
                "to_read": self.to_read,
                "reading": self.reading,
                "read": self.read,
            },
            "inbox": self.candidates or [],
        }


class LocalWorkspace:
    """Owns the durable local boundary that the desktop host cannot access directly."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.database_path = root / "workspace.sqlite3"

    @classmethod
    def open(cls, root: Path) -> LocalWorkspace:
        root.mkdir(parents=True, exist_ok=True)
        workspace = cls(root)
        workspace._initialize_database()
        return workspace

    def snapshot(self) -> LibrarySnapshot:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT video_id, channel_title, title, url, published_at, preparation_state, failure_reason
                FROM candidates
                ORDER BY COALESCE(published_ts, 0) DESC, discovered_at DESC
                """
            ).fetchall()
        candidates = [
            {
                "video_id": str(row[0]),
                "channel_title": str(row[1]),
                "title": str(row[2]),
                "url": str(row[3]),
                "published_at": str(row[4]),
                "preparation_state": str(row[5]),
                "failure_reason": row[6],
            }
            for row in rows
        ]
        return LibrarySnapshot(inbox=len(candidates), candidates=candidates)

    def add_candidate(self, candidate: Candidate) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO candidates
                    (video_id, channel_id, channel_title, title, url, published_at, published_ts,
                     discovered_at, preparation_state, failure_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', NULL)
                """,
                (
                    candidate.video_id,
                    candidate.channel_id,
                    candidate.channel_title,
                    candidate.title,
                    candidate.url,
                    candidate.published_at,
                    candidate.published_ts,
                    time.time(),
                ),
            )
        return cursor.rowcount > 0

    def replace_subscription_sources(self, sources: Iterable[SubscriptionSource]) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM subscription_sources")
            connection.executemany(
                """
                INSERT OR REPLACE INTO subscription_sources
                    (channel_id, title, description, thumbnail_url, subscribed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        source.channel_id,
                        source.title,
                        source.description,
                        source.thumbnail_url,
                        source.subscribed_at,
                    )
                    for source in sources
                ],
            )

    def subscription_source_count(self) -> int:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT COUNT(*) FROM subscription_sources").fetchone()
        return int(row[0]) if row is not None else 0

    def subscription_sources(self) -> list[dict[str, str | None]]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT channel_id, title, description, thumbnail_url, subscribed_at
                FROM subscription_sources
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()
        return [
            {
                "channel_id": str(row[0]),
                "title": str(row[1]),
                "description": str(row[2]),
                "thumbnail_url": row[3],
                "subscribed_at": row[4],
            }
            for row in rows
        ]

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscription_sources (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    thumbnail_url TEXT,
                    subscribed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_title TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    published_ts REAL,
                    discovered_at REAL NOT NULL,
                    preparation_state TEXT NOT NULL DEFAULT 'queued',
                    failure_reason TEXT
                )
                """
            )


def workspace_root() -> Path:
    configured = os.environ.get("YOUTUBE_WORKBENCH_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(user_data_dir("youtube-reading-workbench")) / "workspace"
