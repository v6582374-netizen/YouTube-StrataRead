"""Reader entrypoint. Wires the navigator to the chosen body-reader mode."""
from __future__ import annotations

import contextlib
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console

from youtube_strataread.reader import progress_store
from youtube_strataread.reader.doc_tree import Node, parse_file
from youtube_strataread.reader.manual_reader import read_leaf_manual
from youtube_strataread.reader.navigator import Navigator
from youtube_strataread.reader.session import ReadingSession
from youtube_strataread.reader.status_bar import NullStatusBar, StatusBar
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

    # Pre-compute the total visible character budget for the progress bar.
    total_chars = _total_chars(root)
    try:
        status_bar: StatusBar | NullStatusBar = StatusBar(total_chars)
    except Exception:
        status_bar = NullStatusBar()
    session = ReadingSession(
        root=root,
        total_chars=max(total_chars, 1),
        status_bar=status_bar,
    )
    status_bar.setup()
    session.setup()

    nav = Navigator(
        root=root,
        console=console,
        completed=completed,
        menu_screen=lambda: _menu_screen(status_bar, session),
    )
    cpm_value = cpm or 300
    gen = nav.loop()
    try:
        leaf = next(gen)
        while True:
            reason = _read_leaf(leaf, console, mode, cpm_value, session)
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
        status_bar.teardown()
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


def _read_leaf(leaf, console: Console, mode: str, cpm: int, session: ReadingSession) -> str:
    if mode == "manual":
        return read_leaf_manual(leaf, console, session)
    return read_leaf_stream(leaf, console, session, cpm=cpm)


def _total_chars(root: Node) -> int:
    total = 0
    for node in root.walk():
        if node.level > 0:
            total += len(_heading_text(node))
        if node.body:
            total += len(node.body)
    return total


def _heading_text(node: Node) -> str:
    hashes = "#" * max(node.level, 1)
    return f"{hashes} {node.title}".rstrip()


@contextlib.contextmanager
def _menu_screen(status_bar: StatusBar | NullStatusBar, session: ReadingSession):
    try:
        tty_ok = sys.stdout.isatty()
    except Exception:
        tty_ok = False
    if not tty_ok:
        yield
        return
    sys.stdout.write("\x1b[?1049h\x1b[2J\x1b[H")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
        status_bar.refresh()
        session.restore_cursor()
