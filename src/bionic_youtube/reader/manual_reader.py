"""Mode A: manual Tab-to-advance sentence reader.

Given a leaf :class:`Node`, this loop:
- prints the leaf's title
- each Tab press reveals the next sentence (typed out character-by-character)
- Shift+Tab shows the previous sentence (re-typed)
- Space skips to the last sentence
- Esc / b / q returns control to the caller
"""
from __future__ import annotations

import time

from rich.console import Console

from bionic_youtube.reader.bionic_render import iter_bionic_chars, render_str
from bionic_youtube.reader.doc_tree import Node
from bionic_youtube.reader.keys import key_reader

CHAR_TYPE_DELAY = 0.02  # seconds between characters when "typing"
_ANSI_BOLD = "\x1b[1m"
_ANSI_RESET = "\x1b[0m"


def read_leaf_manual(leaf: Node, console: Console) -> str:
    """Blocking loop. Returns the *exit reason* string ('done' | 'back' | 'quit')."""
    console.clear()
    console.print(f"[bold cyan]{leaf.title}[/]")
    console.print("[dim]Tab 下一句  Shift+Tab 上一句  Space 跳到末句  Esc 返回  q 退出[/]")
    console.print()

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        console.print("[yellow]（本小节暂无正文。按 Esc 返回。）[/]")
        return _wait_for_back()

    shown: list[int] = []  # indices of sentences already revealed
    idx = 0  # the "current sentence"
    _type_out(console, sentences[idx])
    shown.append(idx)

    with key_reader() as read:
        while True:
            key = read()
            if key is None:
                continue
            k = key.key
            if k in ("q", "ctrl-c"):
                return "quit"
            if k in ("escape", "b"):
                return "back"
            if k == "tab":
                if idx + 1 >= len(sentences):
                    console.print("[dim]— 本小节已读完，按 Esc 返回 —[/]")
                    return "done"
                idx += 1
                _type_out(console, sentences[idx])
                shown.append(idx)
            elif k == "shift-tab":
                if idx == 0:
                    continue
                idx -= 1
                console.print(f"[dim]↑ 上一句 ({idx + 1}/{len(sentences)})：[/]")
                console.print(render_str(sentences[idx]))
            elif k == "space":
                while idx + 1 < len(sentences):
                    idx += 1
                    _type_out(console, sentences[idx], instant=True)
                console.print("[dim]— 已跳到末句，Esc 返回 —[/]")


def _type_out(console: Console, sentence: str, instant: bool = False) -> None:
    """Print a sentence once, with Bionic Reading emphasis applied inline.

    ``instant=True`` skips the per-character typing animation (used by Space to
    jump to the end of a leaf).
    """
    out = console.file
    if instant:
        # one-shot render via rich (handles markup + styles cleanly).
        console.print(render_str(sentence))
        console.print()
        return

    bold_open = False
    for ch, is_bold in iter_bionic_chars(sentence):
        if is_bold and not bold_open:
            out.write(_ANSI_BOLD)
            bold_open = True
        elif not is_bold and bold_open:
            out.write(_ANSI_RESET)
            bold_open = False
        out.write(ch)
        out.flush()
        time.sleep(CHAR_TYPE_DELAY)
    if bold_open:
        out.write(_ANSI_RESET)
    out.write("\n\n")
    out.flush()


def _wait_for_back() -> str:
    with key_reader() as read:
        while True:
            k = read()
            if k is None:
                continue
            if k.key in ("escape", "b", "q", "ctrl-c"):
                return "back" if k.key != "q" else "quit"
