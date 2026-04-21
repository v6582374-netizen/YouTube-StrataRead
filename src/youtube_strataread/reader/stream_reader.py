"""Mode B: auto-stream a leaf's body at a fixed CPM, with pause / speed control.

Control keys during streaming:
- ``Space``           toggles pause
- ``+`` / ``-``       next/previous speed tier (x0.5, x0.75, x1, x1.5, x2)
- ``Tab``             skips immediately to the end of the current sentence
- ``h``               toggles highlight on the hovered sentence (keyboard)
- mouse move          hovers a sentence (grey)
- mouse left-click    toggles champagne-gold highlight on the hovered sentence
- ``Esc`` / ``b``     terminate streaming and return to the parent menu
- ``q``               quit the reader

On the last sentence we ``return "done"`` *immediately* instead of waiting
for an Enter press, so chapter-to-chapter transitions are seamless.
"""
from __future__ import annotations

import time

from rich.console import Console

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import Key, key_reader
from youtube_strataread.reader.mouse import parse as parse_mouse
from youtube_strataread.reader.session import ReadingSession

SPEED_TIERS = [0.5, 0.75, 1.0, 1.5, 2.0]
DEFAULT_TIER_INDEX = 2  # x1


def read_leaf_stream(
    leaf: Node,
    console: Console,
    session: ReadingSession,
    cpm: int = 300,
) -> str:
    """Return 'done' | 'back' | 'quit'."""
    console.clear()
    console.print(f"[bold cyan]{leaf.title}[/]")
    console.print(
        "[dim]Space \u6682\u505c  +/- \u8c03\u901f  Tab \u4e0b\u4e00\u53e5  h \u9ad8\u4eae  Esc \u8fd4\u56de  q \u9000\u51fa[/]"
    )
    console.print()
    session.begin_leaf(leaf, header_rows=3)

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        console.print("[yellow]\uff08\u672c\u5c0f\u8282\u6682\u65e0\u6b63\u6587\u3002\u6309 Esc \u8fd4\u56de\u3002\uff09[/]")
        with key_reader(with_mouse=True) as read:
            while True:
                k = read()
                if k is None:
                    continue
                if k.key in ("escape", "b"):
                    session.finish_leaf()
                    return "back"
                if k.key in ("q", "ctrl-c"):
                    session.finish_leaf()
                    return "quit"
                if k.key == "mouse":
                    _handle_mouse(k, session)

    base_delay = max(60.0 / cpm, 0.01)
    tier_idx = DEFAULT_TIER_INDEX

    with key_reader(with_mouse=True) as read:
        for s_idx, sentence in enumerate(sentences):
            paused = False
            session.begin_sentence(s_idx, sentence)
            pieces = list(iter_bionic_chars(sentence))
            skipped = False
            for idx, (ch, is_bold) in enumerate(pieces):
                # Drain any pending input (keyboard + mouse) non-blockingly.
                done_action: str | None = None
                while True:
                    ev = read(timeout=0)
                    if ev is None:
                        break
                    action = _handle_event(ev, session)
                    if action == "quit":
                        done_action = "quit"
                        break
                    if action == "back":
                        done_action = "back"
                        break
                    if action == "skip":
                        for rch, rb in pieces[idx:]:
                            session.write_char(rch, rb)
                        skipped = True
                        break
                    if action == "pause":
                        paused = not paused
                    elif action == "speed_up":
                        tier_idx = min(tier_idx + 1, len(SPEED_TIERS) - 1)
                    elif action == "speed_down":
                        tier_idx = max(tier_idx - 1, 0)
                if done_action:
                    session.write_char("\n", False, count_for_progress=False)
                    session.end_sentence()
                    session.finish_leaf()
                    return done_action
                if skipped:
                    break
                while paused:
                    ev = read(timeout=0.1)
                    if ev is None:
                        continue
                    action = _handle_event(ev, session)
                    if action == "quit":
                        session.end_sentence()
                        session.finish_leaf()
                        return "quit"
                    if action == "back":
                        session.end_sentence()
                        session.finish_leaf()
                        return "back"
                    if action == "pause":
                        paused = False
                session.write_char(ch, is_bold)
                time.sleep(base_delay / SPEED_TIERS[tier_idx])
            session.write_char("\n", False, count_for_progress=False)
            session.end_sentence()
        session.finish_leaf()
    return "done"


def _handle_event(key: Key, session: ReadingSession) -> str:
    k = key.key
    if k in ("q", "ctrl-c"):
        return "quit"
    if k in ("escape", "b"):
        return "back"
    if k == "tab":
        return "skip"
    if k == "space":
        return "pause"
    if k == "+":
        return "speed_up"
    if k == "-":
        return "speed_down"
    if k == "h":
        session.toggle_highlight()
        return "noop"
    if k == "mouse":
        _handle_mouse(key, session)
        return "noop"
    return "noop"


def _handle_mouse(key: Key, session: ReadingSession) -> None:
    ev = parse_mouse(key.raw)
    if ev is None:
        return
    abs_row = ev.row + session.scroll_offset
    span = session.span_at(abs_row, ev.col)
    if ev.kind == "move":
        session.hover(span)
    elif ev.kind == "press" and ev.button == 0 and span is not None:
        session.toggle_highlight(span)
