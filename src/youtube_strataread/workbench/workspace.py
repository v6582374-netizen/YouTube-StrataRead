"""Sidecar-owned local workspace for the personal reading workbench."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_data_dir

from youtube_strataread.downloader.request_policy import (
    MAX_RATE_LIMIT_ATTEMPTS,
    YouTubeRequestPolicy,
)
from youtube_strataread.workbench.shorts import CLASSIFICATION_RETRY_SECONDS

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
        self.youtube_requests = YouTubeRequestPolicy(self.database_path)

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
                SELECT video_id, channel_title, title, url, published_at, preparation_state, failure_reason,
                       duration_seconds
                FROM candidates
                WHERE preparation_state != 'filtered' OR manuscript_version IS NOT NULL
                ORDER BY COALESCE(published_ts, 0) DESC, discovered_at DESC
                """
            ).fetchall()
            state_rows = connection.execute(
                "SELECT reading_state, COUNT(*) FROM candidates "
                "WHERE preparation_state != 'filtered' OR manuscript_version IS NOT NULL "
                "GROUP BY reading_state"
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
                "duration_seconds": row[7],
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
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, 'queued', NULL
                WHERE NOT EXISTS (SELECT 1 FROM excluded_channels WHERE channel_id = ?)
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
                    candidate.channel_id,
                ),
            )
        return cursor.rowcount > 0

    def excluded_channels(self) -> list[str]:
        with sqlite3.connect(self.database_path) as connection:
            return [
                str(row[0])
                for row in connection.execute(
                    "SELECT channel_id FROM excluded_channels ORDER BY channel_id"
                )
            ]

    def set_excluded_channels(self, channels: list[str]) -> None:
        # Share SQLite's write ordering with queue claims. Already-claimed work
        # completes; existing documents are never removed by subscription settings.
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM excluded_channels")
            connection.executemany(
                "INSERT INTO excluded_channels (channel_id) VALUES (?)",
                [(channel,) for channel in sorted(set(channels))],
            )

    def claim_next_queued_asset(self) -> dict[str, object] | None:
        """Atomically honour drain pause and claim exactly one queued asset."""
        with sqlite3.connect(self.database_path, isolation_level=None) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            paused = connection.execute(
                "SELECT value FROM workspace_meta WHERE key = 'drain_paused'"
            ).fetchone()
            if paused is not None and paused[0] == "1":
                connection.execute("COMMIT")
                return None
            if self.youtube_requests._read(connection)["cooldown_until"] > self.youtube_requests.now():
                connection.execute("COMMIT")
                return None
            row = connection.execute(
                """
                SELECT video_id, channel_id, channel_title, title, url, published_at,
                       manuscript_version, shorts_status
                FROM candidates WHERE (preparation_state IN ('queued', 'rate_limited') OR
                    (preparation_state = 'awaiting_classification' AND shorts_retry_at <= ?))
                  AND channel_id NOT IN (SELECT channel_id FROM excluded_channels)
                  AND (shorts_status != 'short' OR manuscript_version IS NOT NULL)
                ORDER BY discovered_at ASC LIMIT 1
                """,
                (time.time(),),
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            stage = (
                "checking"
                if row["manuscript_version"] is None and row["shorts_status"] != "video"
                else "acquiring"
            )
            connection.execute(
                """
                UPDATE candidates SET preparation_state = 'acquiring', failure_reason = NULL,
                    preparation_started_at = ?, preparation_completed_at = NULL,
                    preparation_stage = ?, stage_updated_at = ?
                WHERE video_id = ?
                """,
                (time.time(), stage, time.time(), row["video_id"]),
            )
            self._activity_event(connection, row["video_id"], stage)
            connection.execute("COMMIT")
        return dict(row)

    def defer_rate_limited(self, video_id: str, *, attempted: bool = True) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT rate_limit_attempts FROM candidates WHERE video_id = ? AND preparation_state = 'acquiring'",
                (video_id,),
            ).fetchone()
            if row is None:
                return
            attempts = row[0] + int(attempted)
            exhausted = attempts >= MAX_RATE_LIMIT_ATTEMPTS
            state = "failed" if exhausted else "rate_limited"
            reason = (
                "YouTube 多次限流，已停止自动重试此视频。冷却结束后可手动重试。"
                if exhausted else "YouTube 请求限流，冷却结束后自动重试。"
            )
            connection.execute(
                """UPDATE candidates SET preparation_state = ?, preparation_stage = ?,
                   failure_reason = ?, rate_limit_attempts = ?, stage_updated_at = ?,
                   preparation_completed_at = ? WHERE video_id = ?""",
                (state, state, reason, attempts, time.time(), time.time() if exhausted else None, video_id),
            )
            self._activity_event(connection, video_id, state, reason)

    def record_shorts_classification(self, video_id: str, is_short: bool | None) -> None:
        if is_short is not None and type(is_short) is not bool:
            raise ValueError("classification must be True, False or None")
        now = time.time()
        if is_short is None:
            status, state = "unknown", "awaiting_classification"
        elif is_short:
            status, state = "short", "filtered"
        else:
            status, state = "video", "acquiring"
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE candidates SET shorts_status = ?, shorts_checked_at = ?,
                   shorts_retry_at = ?, preparation_state = ?, preparation_stage = ?,
                   stage_updated_at = ?, preparation_completed_at = ?, failure_reason = NULL
                   WHERE video_id = ? AND preparation_state = 'acquiring'
                     AND manuscript_version IS NULL""",
                (
                    status, now,
                    now + CLASSIFICATION_RETRY_SECONDS if is_short is None else None,
                    state, state, now, now if is_short is True else None, video_id,
                ),
            )
            if cursor.rowcount:
                self._activity_event(connection, video_id, state)

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
                    preparation_completed_at = ?, preparation_stage = ?, stage_updated_at = ?
                WHERE video_id = ?
                """,
                (
                    state,
                    failure_reason,
                    state,
                    time.time(),
                    completed_at,
                    state,
                    time.time(),
                    video_id,
                ),
            )
            if cursor.rowcount:
                self._activity_event(connection, video_id, state)
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")

    def queue_regeneration(self, video_id: str) -> None:
        # Serialize with automatic claims: never erase the checkpoint of a job
        # which became active between the user's inspection and this request.
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT preparation_state FROM candidates WHERE video_id = ?", (video_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown asset: {video_id}")
            if row[0] in {"acquiring", "generating"}:
                raise ValueError("资料正在生成，请等待本次处理完成。")
            if row[0] == "cancelled":
                raise ValueError("此视频已取消处理，请先在处理进度中恢复。")
            if row[0] == "filtered":
                raise ValueError("此视频是 YouTube Shorts，已排除自动处理。")
            self.translation_checkpoint(video_id).unlink(missing_ok=True)
            connection.execute(
                """
                UPDATE candidates
                SET preparation_state = 'queued', failure_reason = NULL,
                    rate_limit_attempts = 0,
                    preparation_started_at = NULL, preparation_completed_at = NULL
                WHERE video_id = ?
                """,
                (video_id,),
            )

    def retry_failed(self, video_id: str | None = None) -> int:
        statement = """
            UPDATE candidates SET preparation_state = 'queued', failure_reason = NULL,
                rate_limit_attempts = 0,
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

    @staticmethod
    def _console_entry(connection, video_id: str, message: str) -> None:
        connection.execute(
            "INSERT INTO preparation_console (video_id, message, occurred_at) VALUES (?, ?, ?)",
            (video_id, message[:4000], time.time()),
        )
        connection.execute(
            "DELETE FROM preparation_console WHERE sequence <= "
            "(SELECT MAX(sequence) - 500 FROM preparation_console)"
        )

    def report_console(self, video_id: str, message: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            self._console_entry(connection, video_id, message)

    @staticmethod
    def _activity_event(connection, video_id: str, stage: str, detail: str = "") -> None:
        connection.execute(
            "INSERT INTO preparation_events (video_id, stage, detail, occurred_at) VALUES (?, ?, ?, ?)",
            (video_id, stage, detail, time.time()),
        )
        LocalWorkspace._console_entry(connection, video_id, f"[{stage}] {detail}".rstrip())

    def change_queue(self, video_ids: list[str], *, restore: bool = False) -> dict[str, object]:
        """Serialize cancellation with worker claims; report races per item."""
        expected = ("cancelled", "cancelled", "cancelled") if restore else ("queued", "awaiting_classification", "rate_limited")
        target = "queued" if restore else "cancelled"
        changed, skipped = [], []
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for video_id in dict.fromkeys(video_ids):
                cursor = connection.execute(
                    """UPDATE candidates SET preparation_state = ?, preparation_stage = NULL,
                        stage_updated_at = ?, preparation_started_at = NULL,
                        preparation_completed_at = NULL, failure_reason = NULL
                        WHERE video_id = ? AND preparation_state IN (?, ?, ?)""",
                    (target, time.time(), video_id, *expected),
                )
                if cursor.rowcount:
                    changed.append(video_id)
                    self._activity_event(
                        connection, video_id, "restored" if restore else "cancelled"
                    )
                else:
                    row = connection.execute(
                        "SELECT preparation_state FROM candidates WHERE video_id = ?", (video_id,)
                    ).fetchone()
                    skipped.append({"video_id": video_id, "state": row[0] if row else "missing"})
        return {"changed": changed, "skipped": skipped}

    def report_stage(self, video_id: str, stage: str, detail: str = "") -> None:
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """UPDATE candidates SET preparation_stage = ?, stage_updated_at = ?
                   WHERE video_id = ? AND preparation_state IN ('acquiring', 'generating')""",
                (stage, time.time(), video_id),
            )
            if cursor.rowcount:
                self._activity_event(connection, video_id, stage, detail)

    def activity_items(
        self, state: str = "queued", offset: int = 0, limit: int = 50
    ) -> dict[str, object]:
        if state not in {"queued", "cancelled", "failed", "unavailable", "ready", "awaiting_classification", "filtered", "rate_limited"}:
            raise ValueError("无效的处理状态。")
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
            raise ValueError("无效的分页范围。")
        where = "preparation_state = ?"
        if state in {"queued", "awaiting_classification", "rate_limited"}:
            where += " AND channel_id NOT IN (SELECT channel_id FROM excluded_channels)"
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            total = connection.execute(
                f"SELECT COUNT(*) FROM candidates WHERE {where}", (state,)
            ).fetchone()[0]
            rows = connection.execute(
                f"""SELECT video_id, title, channel_title, preparation_state, failure_reason,
                    manuscript_version, published_at, duration_seconds FROM candidates WHERE {where}
                    ORDER BY discovered_at ASC, video_id ASC LIMIT ? OFFSET ?""",
                (state, limit, offset),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total}

    def set_reading_state(self, video_id: str, state: str) -> None:
        if state not in {"inbox", "to-read", "reading", "read"}:
            raise ValueError(f"unknown reading state: {state}")
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE candidates SET reading_state = ? WHERE video_id = ?", (state, video_id)
            )
        if cursor.rowcount != 1:
            raise KeyError(f"unknown asset: {video_id}")

    def record_video_duration(self, video_id: str, duration_seconds: float | None) -> None:
        """Retain source duration independently of subtitle and manuscript success."""
        if (isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float))
                or not math.isfinite(duration_seconds) or duration_seconds <= 0):
            return
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "UPDATE candidates SET duration_seconds = ? WHERE video_id = ?",
                (duration_seconds, video_id),
            )

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
        translation: str | None = None,
        provenance: dict | None = None,
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
        if translation is not None:
            (directory / "translation.md").write_text(translation.rstrip() + "\n", encoding="utf-8")
        if provenance is not None:
            (directory / "translation-run.json").write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
                       c.manuscript_path, c.preparation_completed_at, c.duration_seconds,
                       t.path AS transcript_path
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
        documents_only: bool = False,
        unread_only: bool = False,
        reading_state: str | None = None,
        channel_id: str | None = None,
        preparation_state: str | None = None,
        published_after: float | None = None,
        published_before: float | None = None,
    ) -> list[dict[str, object]]:
        clauses: list[str] = ["(c.preparation_state != 'filtered' OR c.manuscript_version IS NOT NULL)"]
        values: list[object] = []
        if documents_only:
            clauses.append("c.manuscript_version IS NOT NULL")
        if unread_only:
            clauses.append("c.reading_state != 'read'")
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
                       c.manuscript_path, c.preparation_completed_at, c.duration_seconds,
                       SUBSTR(m.markdown, 1, 400) AS excerpt,
                       LENGTH(m.markdown) AS manuscript_characters,
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
                [
                    *values,
                    query.strip(),
                    f"%{query.strip()}%",
                    f"%{query.strip()}%",
                    f"%{query.strip()}%",
                ],
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
        return {
            "path": str(row["path"]),
            "markdown": str(row["markdown"]),
            "version": row["version"],
            "translation_path": str(Path(row["path"]).with_name("translation.md"))
            if Path(row["path"]).with_name("translation.md").exists()
            else None,
        }

    def recover_interrupted_preparations(self) -> None:
        """Called once by the owning host on startup, not on every workspace read."""
        with sqlite3.connect(self.database_path) as connection:
            if self.youtube_requests._read(connection)["cooldown_until"] > self.youtube_requests.now():
                connection.execute(
                    """UPDATE candidates SET preparation_state = 'rate_limited',
                       preparation_stage = 'rate_limited', stage_updated_at = ?,
                       failure_reason = 'YouTube 请求处于冷却中，结束后自动重试。'
                       WHERE preparation_state = 'acquiring'""",
                    (time.time(),),
                )
            connection.execute(
                """UPDATE candidates SET preparation_state = 'awaiting_classification',
                   preparation_stage = 'awaiting_classification', shorts_retry_at = ?,
                   stage_updated_at = ?, failure_reason = NULL
                   WHERE preparation_state = 'acquiring' AND preparation_stage = 'checking'
                     AND shorts_status = 'unknown' AND manuscript_version IS NULL""",
                (time.time() + CLASSIFICATION_RETRY_SECONDS, time.time()),
            )
            connection.execute(
                "UPDATE candidates SET preparation_state = 'failed', failure_reason = ?, "
                "preparation_completed_at = ? WHERE preparation_state IN ('acquiring', 'generating')",
                ("上次处理被中断，已完成阶段保留，可重试。", time.time()),
            )

    def translation_checkpoint(self, video_id: str) -> Path:
        return self._asset_directory(video_id) / "translation-attempt.json"

    def retained_transcript(self, video_id: str) -> dict[str, str] | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT language, content FROM transcripts WHERE video_id = ?", (video_id,)
            ).fetchone()
        return {"language": row[0], "content": row[1]} if row else None

    def delete_asset(self, video_id: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM preparation_events WHERE video_id = ?", (video_id,))
            connection.execute("DELETE FROM preparation_console WHERE video_id = ?", (video_id,))
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
                """SELECT preparation_state, COUNT(*) FROM candidates
                WHERE preparation_state NOT IN ('queued', 'awaiting_classification', 'rate_limited') OR channel_id NOT IN
                    (SELECT channel_id FROM excluded_channels)
                GROUP BY preparation_state"""
            ).fetchall()
            document_count = connection.execute(
                "SELECT COUNT(*) FROM candidates WHERE manuscript_version IS NOT NULL"
            ).fetchone()[0]
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
            connection.row_factory = sqlite3.Row
            current = [
                dict(row)
                for row in connection.execute(
                    """SELECT video_id, title, channel_title, preparation_state, preparation_stage,
                   preparation_started_at, stage_updated_at, published_at, duration_seconds FROM candidates
                   WHERE preparation_state IN ('acquiring', 'generating')
                   ORDER BY preparation_started_at"""
                )
            ]
            for item in current:
                item["observed_stages"] = [
                    row[0]
                    for row in connection.execute(
                        """SELECT DISTINCT stage FROM preparation_events
                       WHERE video_id = ? AND occurred_at >= ?""",
                        (item["video_id"], item["preparation_started_at"] or 0),
                    )
                ]
            events = [
                dict(row)
                for row in connection.execute(
                    """SELECT e.sequence, e.video_id, c.title, e.stage, e.detail, e.occurred_at
                   FROM preparation_events e JOIN candidates c ON c.video_id = e.video_id
                   ORDER BY e.sequence DESC LIMIT 60"""
                )
            ]
            console = [dict(row) for row in connection.execute(
                "SELECT sequence, video_id, message, occurred_at FROM preparation_console ORDER BY sequence"
            )]
        counts = {str(state): int(count) for state, count in rows}
        return {
            "document_count": document_count,
            "cancelled": counts.get("cancelled", 0),
            "filtered": counts.get("filtered", 0),
            "awaiting_classification": counts.get("awaiting_classification", 0),
            "rate_limited": counts.get("rate_limited", 0),
            "youtube_requests": self.youtube_requests.snapshot(),
            "current": current,
            "events": events,
            "console": console,
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
                {
                    "video_id": str(row[0]),
                    "title": str(row[1]),
                    "state": str(row[2]),
                    "reason": row[3],
                }
                for row in failure_rows
            ],
            "batch": {
                "limit": int(self.meta("batch_limit") or 100),
                "completed": int(self.meta("batch_completed") or 0),
            },
        }

    def set_batch_progress(self, *, limit: int, completed: int) -> None:
        self.set_meta("batch_limit", str(limit))
        self.set_meta("batch_completed", str(completed))

    def set_meta(self, key: str, value: str) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO workspace_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def meta(self, key: str) -> str | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT value FROM workspace_meta WHERE key = ?", (key,)
            ).fetchone()
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
                CREATE TABLE IF NOT EXISTS preparation_console (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL REFERENCES candidates(video_id) ON DELETE CASCADE,
                    message TEXT NOT NULL,
                    occurred_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preparation_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL REFERENCES candidates(video_id) ON DELETE CASCADE,
                    stage TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    occurred_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS excluded_channels (
                    channel_id TEXT PRIMARY KEY
                );
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
                CREATE INDEX IF NOT EXISTS preparation_events_video ON preparation_events(video_id, occurred_at);
                CREATE INDEX IF NOT EXISTS candidates_preparation_state ON candidates(preparation_state);
                CREATE INDEX IF NOT EXISTS candidates_reading_state ON candidates(reading_state);
                """
            )
            existing = {row[1] for row in connection.execute("PRAGMA table_info(candidates)")}
            for name, definition in {
                "duration_seconds": "REAL",
                "preparation_stage": "TEXT",
                "stage_updated_at": "REAL",
                "reading_state": "TEXT NOT NULL DEFAULT 'inbox'",
                "preparation_started_at": "REAL",
                "preparation_completed_at": "REAL",
                "manuscript_version": "INTEGER",
                "manuscript_path": "TEXT",
                "shorts_status": "TEXT NOT NULL DEFAULT 'unknown'",
                "shorts_checked_at": "REAL",
                "shorts_retry_at": "REAL",
                "rate_limit_attempts": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE candidates ADD COLUMN {name} {definition}")
            if not connection.execute(
                "SELECT 1 FROM workspace_meta WHERE key = 'youtube_rate_limit_migration_v1'"
            ).fetchone():
                # Recover only legacy subtitle throttles, never cancellations or genuinely absent captions.
                connection.execute(
                    """UPDATE candidates SET preparation_state = 'rate_limited',
                       preparation_stage = 'rate_limited', rate_limit_attempts = 0,
                       preparation_completed_at = NULL, stage_updated_at = ?
                       WHERE preparation_state = 'unavailable'
                       AND failure_reason LIKE '%download video subtitles%'
                       AND (failure_reason LIKE '%HTTP Error 429%' OR failure_reason LIKE '%Too Many Requests%')""",
                    (time.time(),),
                )
                connection.execute(
                    "INSERT INTO workspace_meta(key, value) VALUES ('youtube_rate_limit_migration_v1', '1')"
                )


def workspace_root() -> Path:
    configured = os.environ.get("YOUTUBE_WORKBENCH_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(user_data_dir("youtube-reading-workbench")) / "workspace"
