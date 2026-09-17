"""Sidecar-owned local workspace for the personal reading workbench."""

from __future__ import annotations

import hashlib
import os
import shutil
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
            state_rows = connection.execute(
                "SELECT reading_state, COUNT(*) FROM candidates GROUP BY reading_state"
            ).fetchall()
        reading_counts = {str(state): int(count) for state, count in state_rows}
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
        return LibrarySnapshot(
            inbox=reading_counts.get("inbox", 0),
            to_read=reading_counts.get("to-read", 0),
            reading=reading_counts.get("reading", 0),
            read=reading_counts.get("read", 0),
            candidates=candidates,
        )

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

    def next_queued_asset(self) -> dict[str, object] | None:
        """Return the oldest queued asset without claiming it.

        The sidecar processes one asset at a time, so this intentionally has no
        general job-queue abstraction. State is claimed immediately afterwards
        by ``set_preparation_state``.
        """
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT video_id, channel_id, channel_title, title, url, published_at
                FROM candidates WHERE preparation_state = 'queued'
                ORDER BY discovered_at ASC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row is not None else None

    def set_preparation_state(
        self, video_id: str, state: str, failure_reason: str | None = None
    ) -> None:
        if state not in {"queued", "acquiring", "generating", "ready", "unavailable", "failed"}:
            raise ValueError(f"unknown preparation state: {state}")
        completed_at = time.time() if state in {"ready", "unavailable", "failed"} else None
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE candidates
                SET preparation_state = ?, failure_reason = ?,
                    preparation_started_at = CASE WHEN ? IN ('acquiring', 'generating')
                        THEN COALESCE(preparation_started_at, ?) ELSE preparation_started_at END,
                    preparation_completed_at = ?
                WHERE video_id = ?
                """,
                (state, failure_reason, state, time.time(), completed_at, video_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")

    def queue_regeneration(self, video_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE candidates
                SET preparation_state = 'queued', failure_reason = NULL,
                    preparation_started_at = NULL, preparation_completed_at = NULL
                WHERE video_id = ?
                """,
                (video_id,),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")

    def retry_failed(self, video_id: str | None = None) -> int:
        statement = """
            UPDATE candidates SET preparation_state = 'queued', failure_reason = NULL,
                preparation_started_at = NULL, preparation_completed_at = NULL
            WHERE preparation_state = 'failed'
        """
        values: tuple[object, ...] = ()
        if video_id is not None:
            statement += " AND video_id = ?"
            values = (video_id,)
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(statement, values)
        return cursor.rowcount

    def set_reading_state(self, video_id: str, state: str) -> None:
        if state not in {"inbox", "to-read", "reading", "read"}:
            raise ValueError(f"unknown reading state: {state}")
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE candidates SET reading_state = ? WHERE video_id = ?", (state, video_id)
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")

    def store_transcript(self, video_id: str, *, language: str, srt_text: str) -> str:
        asset_dir = self._asset_directory(video_id)
        asset_dir.mkdir(parents=True, exist_ok=True)
        path = asset_dir / "transcript.srt"
        path.write_text(srt_text, encoding="utf-8")
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO transcripts (video_id, language, path, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                  language=excluded.language, path=excluded.path, content=excluded.content,
                  created_at=excluded.created_at
                """,
                (video_id, language, str(path), srt_text, time.time()),
            )
        return str(path)

    def save_manuscript(
        self,
        video_id: str,
        markdown: str,
        *,
        generator: str,
        transcript_characters: int,
    ) -> dict[str, object]:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM manuscripts WHERE video_id = ?",
                (video_id,),
            ).fetchone()
            version = int(row[0])
        directory = self._asset_directory(video_id) / f"manuscript-v{version}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "manuscript.md"
        path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        created_at = time.time()
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO manuscripts (video_id, version, path, markdown, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (video_id, version, str(path), markdown.rstrip() + "\n", created_at),
            )
            connection.execute(
                """
                UPDATE candidates SET manuscript_version = ?, manuscript_path = ?
                WHERE video_id = ?
                """,
                (version, str(path), video_id),
            )
            connection.execute(
                """
                INSERT INTO generation_records
                    (video_id, manuscript_version, generator, transcript_characters,
                     manuscript_characters, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    video_id,
                    version,
                    generator,
                    transcript_characters,
                    len(markdown.rstrip() + "\n"),
                    created_at,
                ),
            )
        return {"version": version, "path": str(path), "created_at": created_at}

    def generation_records(self, video_id: str) -> list[dict[str, object]]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT manuscript_version, generator, transcript_characters, manuscript_characters, created_at
                FROM generation_records WHERE video_id = ? ORDER BY manuscript_version
                """,
                (video_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def asset(self, video_id: str) -> dict[str, object]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT c.video_id, c.channel_id, c.channel_title, c.title, c.url, c.published_at,
                       c.preparation_state, c.failure_reason, c.reading_state, c.manuscript_version,
                       c.manuscript_path, c.preparation_completed_at, t.path AS transcript_path
                FROM candidates c LEFT JOIN transcripts t ON t.video_id = c.video_id
                WHERE c.video_id = ?
                """,
                (video_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown asset: {video_id}")
        return dict(row)

    def assets(
        self,
        *,
        query: str = "",
        include_transcript: bool = False,
        reading_state: str | None = None,
        channel_id: str | None = None,
        preparation_state: str | None = None,
        published_after: float | None = None,
        published_before: float | None = None,
    ) -> list[dict[str, object]]:
        clauses: list[str] = []
        values: list[object] = []
        if reading_state:
            clauses.append("c.reading_state = ?")
            values.append(reading_state)
        if channel_id:
            clauses.append("c.channel_id = ?")
            values.append(channel_id)
        if preparation_state:
            clauses.append("c.preparation_state = ?")
            values.append(preparation_state)
        if published_after is not None:
            clauses.append("c.published_ts >= ?")
            values.append(published_after)
        if published_before is not None:
            clauses.append("c.published_ts <= ?")
            values.append(published_before)
        if query.strip():
            escaped = f"%{query.strip()}%"
            text = "c.title LIKE ? COLLATE NOCASE OR c.channel_title LIKE ? COLLATE NOCASE OR m.markdown LIKE ? COLLATE NOCASE"
            values.extend([escaped, escaped, escaped])
            if include_transcript:
                text += " OR t.content LIKE ? COLLATE NOCASE"
                values.append(escaped)
            clauses.append(f"({text})")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT c.video_id, c.channel_id, c.channel_title, c.title, c.url, c.published_at,
                       c.preparation_state, c.failure_reason, c.reading_state, c.manuscript_version,
                       c.manuscript_path, c.preparation_completed_at,
                       CASE WHEN t.video_id IS NULL THEN 0 ELSE 1 END AS transcript_available
                FROM candidates c
                LEFT JOIN manuscripts m ON m.video_id = c.video_id AND m.version = c.manuscript_version
                LEFT JOIN transcripts t ON t.video_id = c.video_id
                {where}
                ORDER BY CASE WHEN ? = '' THEN 0 ELSE
                    (CASE WHEN c.title LIKE ? COLLATE NOCASE THEN 3 ELSE 0 END +
                     CASE WHEN c.channel_title LIKE ? COLLATE NOCASE THEN 2 ELSE 0 END +
                     CASE WHEN m.markdown LIKE ? COLLATE NOCASE THEN 1 ELSE 0 END)
                END DESC, COALESCE(c.published_ts, 0) DESC, c.discovered_at DESC
                """,
                [*values, query.strip(), f"%{query.strip()}%", f"%{query.strip()}%", f"%{query.strip()}%"],
            ).fetchall()
        return [dict(row) for row in rows]

    def document(self, video_id: str) -> dict[str, object]:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT m.path, m.markdown, m.version FROM manuscripts m
                JOIN candidates c ON c.video_id = m.video_id AND c.manuscript_version = m.version
                WHERE m.video_id = ?
                """,
                (video_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"asset has no manuscript: {video_id}")
        return {"path": str(row["path"]), "markdown": str(row["markdown"]), "version": row["version"]}

    def delete_asset(self, video_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM generation_records WHERE video_id = ?", (video_id,))
            connection.execute("DELETE FROM manuscripts WHERE video_id = ?", (video_id,))
            connection.execute("DELETE FROM transcripts WHERE video_id = ?", (video_id,))
            cursor = connection.execute("DELETE FROM candidates WHERE video_id = ?", (video_id,))
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")
        shutil.rmtree(self._asset_directory(video_id), ignore_errors=True)

    def activity(self) -> dict[str, object]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT preparation_state, COUNT(*) FROM candidates GROUP BY preparation_state"
            ).fetchall()
            transcript_characters = connection.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM transcripts"
            ).fetchone()[0]
            manuscript_characters = connection.execute(
                "SELECT COALESCE(SUM(LENGTH(markdown)), 0) FROM manuscripts"
            ).fetchone()[0]
            failure_rows = connection.execute(
                """
                SELECT video_id, title, preparation_state, failure_reason FROM candidates
                WHERE preparation_state IN ('failed', 'unavailable')
                ORDER BY preparation_completed_at DESC LIMIT 10
                """
            ).fetchall()
        counts = {str(state): int(count) for state, count in rows}
        return {
            "queued": counts.get("queued", 0),
            "acquiring": counts.get("acquiring", 0),
            "generating": counts.get("generating", 0),
            "ready": counts.get("ready", 0),
            "unavailable": counts.get("unavailable", 0),
            "failed": counts.get("failed", 0),
            "drain_paused": self.meta("drain_paused") == "1",
            "volume": {
                "transcript_characters": int(transcript_characters),
                "manuscript_characters": int(manuscript_characters),
            },
            # Provider pricing is not stable enough to present an invented estimate.
            "cost_estimate": None,
            "failures": [
                {"video_id": str(row[0]), "title": str(row[1]), "state": str(row[2]), "reason": row[3]}
                for row in failure_rows
            ],
        }

    def set_meta(self, key: str, value: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO workspace_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def meta(self, key: str) -> str | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute("SELECT value FROM workspace_meta WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row is not None else None

    def _asset_directory(self, video_id: str) -> Path:
        return self.root / "assets" / hashlib.sha256(video_id.encode("utf-8")).hexdigest()

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
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
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
                    failure_reason TEXT,
                    reading_state TEXT NOT NULL DEFAULT 'inbox',
                    preparation_started_at REAL,
                    preparation_completed_at REAL,
                    manuscript_version INTEGER,
                    manuscript_path TEXT
                );
                CREATE TABLE IF NOT EXISTS transcripts (
                    video_id TEXT PRIMARY KEY REFERENCES candidates(video_id) ON DELETE CASCADE,
                    language TEXT NOT NULL, path TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS manuscripts (
                    video_id TEXT NOT NULL REFERENCES candidates(video_id) ON DELETE CASCADE,
                    version INTEGER NOT NULL, path TEXT NOT NULL, markdown TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY (video_id, version)
                );
                CREATE TABLE IF NOT EXISTS generation_records (
                    video_id TEXT NOT NULL REFERENCES candidates(video_id) ON DELETE CASCADE,
                    manuscript_version INTEGER NOT NULL,
                    generator TEXT NOT NULL,
                    transcript_characters INTEGER NOT NULL,
                    manuscript_characters INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (video_id, manuscript_version)
                );
                CREATE INDEX IF NOT EXISTS candidates_preparation_state ON candidates(preparation_state);
                CREATE INDEX IF NOT EXISTS candidates_reading_state ON candidates(reading_state);
                """
            )
            existing = {row[1] for row in connection.execute("PRAGMA table_info(candidates)")}
            for name, definition in {
                "reading_state": "TEXT NOT NULL DEFAULT 'inbox'",
                "preparation_started_at": "REAL",
                "preparation_completed_at": "REAL",
                "manuscript_version": "INTEGER",
                "manuscript_path": "TEXT",
            }.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE candidates ADD COLUMN {name} {definition}")


def workspace_root() -> Path:
    configured = os.environ.get("YOUTUBE_WORKBENCH_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(user_data_dir("youtube-reading-workbench")) / "workspace"
