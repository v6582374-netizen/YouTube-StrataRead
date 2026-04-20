"""Persisted reading progress, per-document."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_state_dir

from bionic_youtube.config import APP_NAME


@dataclass
class Progress:
    mode: str = "manual"
    current_path: str = ""
    completed: list[str] = field(default_factory=list)
    last_sentence_idx: int = 0
    timestamp: str = ""


def _state_dir() -> Path:
    d = Path(user_state_dir(APP_NAME)) / "progress"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(doc_hash: str) -> Path:
    return _state_dir() / f"{doc_hash}.json"


def load(doc_hash: str) -> Progress | None:
    p = _file(doc_hash)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return Progress(**data)


def save(doc_hash: str, progress: Progress) -> None:
    _file(doc_hash).write_text(
        json.dumps(asdict(progress), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear(doc_hash: str) -> None:
    p = _file(doc_hash)
    if p.exists():
        p.unlink()
