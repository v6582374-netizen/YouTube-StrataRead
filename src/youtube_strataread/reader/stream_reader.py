"""Mode B: auto-stream a leaf's body at a fixed CPM."""
from __future__ import annotations

import time

from rich.console import Console

from youtube_strataread.reader.bionic_render import iter_bionic_chars
from youtube_strataread.reader.doc_tree import Node
from youtube_strataread.reader.keys import Key, key_reader
from youtube_strataread.reader.session import ReadingSession

SPEED_TIERS = [0.5, 0.75, 1.0, 1.5, 2.0]
DEFAULT_TIER_INDEX = 2


def read_leaf_stream(
    leaf: Node,
    console: Console,
    session: ReadingSession,
    cpm: int = 300,
) -> str:
    """Return 'done' | 'back' | 'quit'."""
    del console
    session.begin_leaf(leaf)

    sentences = leaf.sentences or ([leaf.body] if leaf.body else [])
    if not sentences:
        _show_placeholder(session)
        with key_reader() as read:
            while True:
                key = read()
                if key is None:
                    continue
                if key.key in ("escape", "b"):
                    session.finish_leaf()
                    return "back"
                if key.key in ("q", "ctrl-c"):
                    session.finish_leaf()
                    return "quit"

    base_delay = max(60.0 / cpm, 0.01)
    tier_idx = DEFAULT_TIER_INDEX

    with key_reader() as read:
        for sent_idx, sentence in enumerate(sentences):
            paused = False
            session.begin_sentence(sent_idx, sentence)
            pieces = list(iter_bionic_chars(sentence))
            skipped = False
            for idx, (ch, is_bold) in enumerate(pieces):
                done_action: str | None = None
                while True:
                    event = read(timeout=0)
                    if event is None:
                        break
                    action = _handle_event(event)
                    if action in {"quit", "back"}:
                        done_action = action
                        break
                    if action == "skip":
                        session.write_chars(pieces[idx:], count_for_progress=True)
                        skipped = True
                        break
                    if action == "pause":
                        paused = not paused
                    elif action == "speed_up":
                        tier_idx = min(tier_idx + 1, len(SPEED_TIERS) - 1)
                    elif action == "speed_down":
                        tier_idx = max(tier_idx - 1, 0)
                if done_action is not None:
                    session.end_sentence()
                    session.finish_leaf()
                    return done_action
                if skipped:
                    break
                while paused:
                    event = read(timeout=0.1)
                    if event is None:
                        continue
                    action = _handle_event(event)
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
                    elif action == "speed_up":
                        tier_idx = min(tier_idx + 1, len(SPEED_TIERS) - 1)
                    elif action == "speed_down":
                        tier_idx = max(tier_idx - 1, 0)
                session.write_char(ch, is_bold)
                time.sleep(base_delay / SPEED_TIERS[tier_idx])
            session.end_sentence()
        session.finish_leaf()
    return "done"


def _handle_event(key: Key) -> str:
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
    return "noop"


def _show_placeholder(session: ReadingSession) -> None:
    message = "（本小节暂无正文。按 Esc 返回。）"
    session.begin_sentence(0, message)
    session.write_chars([(ch, False) for ch in message], count_for_progress=False)
    session.end_sentence()
