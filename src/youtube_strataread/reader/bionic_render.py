"""Render text with Bionic-Reading-style emphasis on word prefixes.

Rules:
- English words (``[A-Za-z]+``): bold the first ``ceil(len(word) * 0.4)`` chars.
- Runs of CJK characters: bold the first ``ceil(len(run) / 2)`` chars.
- Digits, punctuation, and whitespace are left as-is.
"""
from __future__ import annotations

import math
import re

from rich.text import Text

_TOKEN_RE = re.compile(
    r"[A-Za-z]+|[\u4e00-\u9fff]+|[0-9]+|[^\sA-Za-z0-9\u4e00-\u9fff]+|\s+"
)


def render(text: str) -> Text:
    t = Text()
    for tok in _TOKEN_RE.findall(text):
        if not tok:
            continue
        if tok.isspace() or _is_punct(tok) or tok.isdigit():
            t.append(tok)
            continue
        prefix_len = _prefix_len(tok)
        if prefix_len <= 0:
            t.append(tok)
            continue
        t.append(tok[:prefix_len], style="bold")
        if len(tok) > prefix_len:
            t.append(tok[prefix_len:])
    return t


def render_str(text: str) -> str:
    """Return a rich-markup string (for ``rich.print`` / ``console.print``)."""
    parts: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        if tok.isspace() or _is_punct(tok) or tok.isdigit():
            parts.append(tok)
            continue
        prefix_len = _prefix_len(tok)
        if prefix_len <= 0:
            parts.append(tok)
            continue
        head = tok[:prefix_len]
        rest = tok[prefix_len:]
        parts.append(f"[bold]{head}[/]" + rest)
    return "".join(parts)


def iter_bionic_chars(text: str):
    """Yield ``(char, is_bold)`` pairs for streaming/typing output.

    Honours the same rules as :func:`render_str`: English word prefixes and
    CJK run prefixes are bold; punctuation/digits/whitespace are not.
    """
    for tok in _TOKEN_RE.findall(text):
        if not tok:
            continue
        if tok.isspace() or _is_punct(tok) or tok.isdigit():
            for ch in tok:
                yield ch, False
            continue
        prefix_len = _prefix_len(tok)
        for i, ch in enumerate(tok):
            yield ch, i < prefix_len


def _prefix_len(tok: str) -> int:
    if re.fullmatch(r"[A-Za-z]+", tok):
        return max(1, math.ceil(len(tok) * 0.4))
    if re.fullmatch(r"[\u4e00-\u9fff]+", tok):
        if len(tok) == 1:
            return 1
        return math.ceil(len(tok) / 2)
    return 0


def _is_punct(tok: str) -> bool:
    return bool(tok) and not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in tok)
