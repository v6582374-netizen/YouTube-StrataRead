"""Sidecar-owned local workspace for the personal reading workbench."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir


@dataclass(frozen=True)
class LibrarySnapshot:
    """The minimum library state available before subscription import exists."""

    label: str = "Local Library"
    status: str = "ready"
    inbox: int = 0
    to_read: int = 0
    reading: int = 0
    read: int = 0

    def as_result(self) -> dict[str, object]:
        return {
            "workspace": {"label": self.label, "status": self.status},
            "counts": {
                "inbox": self.inbox,
                "to_read": self.to_read,
                "reading": self.reading,
                "read": self.read,
            },
            "inbox": [],
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
        return LibrarySnapshot()

    def _initialize_database(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )


def workspace_root() -> Path:
    configured = os.environ.get("YOUTUBE_WORKBENCH_WORKSPACE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(user_data_dir("youtube-reading-workbench")) / "workspace"
