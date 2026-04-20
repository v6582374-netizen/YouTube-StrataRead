"""Reader entrypoint. Wires the navigator to the chosen body-reader mode."""
from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

from rich.console import Console

from youtube_strataread.reader import progress_store
from youtube_strataread.reader.doc_tree import parse_file
from youtube_strataread.reader.manual_reader import read_leaf_manual
from youtube_strataread.reader.navigator import Navigator
from youtube_strataread.reader.stream_reader import read_leaf_stream
from youtube_strataread.utils.logging import stdout


def run_reader(*, md_path: Path, mode: str = "manual", cpm: int | None = None) -> None:
    if mode not in {"manual", "stream"}:
        raise ValueError(f"unknown mode '{mode}'. Use 'manual' or 'stream'.")
    root, doc_hash = parse_file(md_path)
    if not root.children:
        stdout().print(f"[yellow]{md_path} 不包含任何标题，无法阅读。[/]")
        return

    console = Console()
    saved = progress_store.load(doc_hash)
    completed: set[str] = set(saved.completed) if saved else set()
    if saved and saved.mode != mode:
        completed.clear()

    nav = Navigator(root=root, console=console, completed=completed)
    cpm_value = cpm or 300
    gen = nav.loop()
    try:
        leaf = next(gen)
        while True:
            reason = _read_leaf(leaf, console, mode, cpm_value)
            if reason == "quit":
                with contextlib.suppress(StopIteration):
                    gen.send("quit")
                break
            try:
                leaf = gen.send(reason)
            except StopIteration:
                break
    except StopIteration:
        pass
    finally:
        progress_store.save(
            doc_hash,
            progress_store.Progress(
                mode=mode,
                current_path="",
                completed=sorted(nav.completed),
                last_sentence_idx=0,
                timestamp=datetime.utcnow().isoformat(),
            ),
        )


def _read_leaf(leaf, console: Console, mode: str, cpm: int) -> str:
    if mode == "manual":
        return read_leaf_manual(leaf, console)
    return read_leaf_stream(leaf, console, cpm=cpm)
