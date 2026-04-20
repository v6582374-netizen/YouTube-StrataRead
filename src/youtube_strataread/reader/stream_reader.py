"""Mode B: auto-stream a leaf's body at a fixed CPM, with pause / speed control.

Control keys during streaming:
- ``Space``       => toggle pause
- ``+`` / ``-``   => next/previous speed tier (×0.5, ×0.75, ×1, ×1.5, ×2)
- ``Tab``         => skip immediately to the start of the next sentence
- ``Esc``/``b``   => terminate streaming and return to the parent menu
- ``q``           => quit the reader
"""
from __future__ import annotations

import time

from rich.console import Console

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import key_reader

SPEED_TIERS = [0.5, 0.75, 1.0, 1.5, 2.0]
DEFAULT_TIER_INDEX = 2  # ×1
_ANSI_BOLD = "\x1b[1m"
_ANSI_RESET = "\x1b[0m"


def read_leaf_stream(leaf: Node, console: Console, cpm: int = 300) -> str:
    """Return 'done' | 'back' | 'quit'."""
    console.clear()
    console.print(f"[bold cyan]{leaf.title}[/]")
    console.print("[dim]Space 暂停  +/- 调速  Tab 下一句  Esc 返回  q 退出[/]")
    console.print()

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        console.print("[yellow]（本小节暂无正文。按 Esc 返回。）[/]")
        with key_reader() as read:
            while True:
                k = read()
                if k is None:
                    continue
                if k.key in ("escape", "b"):
                    return "back"
                if k.key in ("q", "ctrl-c"):
                    return "quit"

    base_delay = max(60.0 / cpm, 0.01)
    tier_idx = DEFAULT_TIER_INDEX

    out = console.file
    with key_reader() as read:
        for s_idx, sentence in enumerate(sentences):
            paused = False
            console.print(f"[dim]({s_idx + 1}/{len(sentences)})[/] ", end="")
            pieces = list(iter_bionic_chars(sentence))
            skipped = False
            bold_open = False
            for idx, (ch, is_bold) in enumerate(pieces):
                # poll keys (non-blocking via small timeout)
                key = read(timeout=0)
                while key is not None:
                    if key.key in ("q", "ctrl-c"):
                        if bold_open:
                            out.write(_ANSI_RESET)
                        out.write("\n")
                        return "quit"
                    if key.key in ("escape", "b"):
                        if bold_open:
                            out.write(_ANSI_RESET)
                        out.write("\n")
                        return "back"
                    if key.key == "tab":
                        for rch, rb in pieces[idx:]:
                            if rb and not bold_open:
                                out.write(_ANSI_BOLD)
                                bold_open = True
                            elif not rb and bold_open:
                                out.write(_ANSI_RESET)
                                bold_open = False
                            out.write(rch)
                        out.flush()
                        skipped = True
                        break
                    if key.key == "space":
                        paused = not paused
                    if key.key == "+":
                        tier_idx = min(tier_idx + 1, len(SPEED_TIERS) - 1)
                    if key.key == "-":
                        tier_idx = max(tier_idx - 1, 0)
                    key = read(timeout=0)
                if skipped:
                    break
                while paused:
                    key = read(timeout=0.1)
                    if key is None:
                        continue
                    if key.key == "space":
                        paused = False
                    elif key.key in ("q", "ctrl-c"):
                        if bold_open:
                            out.write(_ANSI_RESET)
                        return "quit"
                    elif key.key in ("escape", "b"):
                        if bold_open:
                            out.write(_ANSI_RESET)
                        return "back"
                if is_bold and not bold_open:
                    out.write(_ANSI_BOLD)
                    bold_open = True
                elif not is_bold and bold_open:
                    out.write(_ANSI_RESET)
                    bold_open = False
                out.write(ch)
                out.flush()
                time.sleep(base_delay / SPEED_TIERS[tier_idx])
            if bold_open:
                out.write(_ANSI_RESET)
                bold_open = False
            out.write("\n\n")
            out.flush()
    console.print("[dim]— 本小节已读完，按 Esc 返回 —[/]")
    with key_reader() as read:
        while True:
            k = read()
            if k is None:
                continue
            if k.key in ("escape", "b", "enter", "tab"):
                return "done"
            if k.key in ("q", "ctrl-c"):
                return "quit"
