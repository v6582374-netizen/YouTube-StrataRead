"""Text utilities: slug generation, CJK sentence splitting, normalization."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT_TO_DASH = re.compile(r"[\s\u3000]+")
_UNSAFE_CHARS = re.compile(r"[^\w\-\u4e00-\u9fff]", re.UNICODE)
_MULTI_DASH = re.compile(r"-{2,}")

# Sentence-terminator taxonomy for the interactive reader.
# * HARD terminators always end a sentence (both halfwidth and fullwidth
#   Chinese punctuation count here).
# * SOFT terminator (English '.') only ends a sentence when followed by
#   whitespace / EOL so that "U.S.A.", "3.14" etc. stay intact.
# * CLOSING punctuation that trails a terminator stays glued to the
#   preceding clause (e.g. the closing quote after “你好。”).
# Enumeration comma 、, colons, brackets and quote-open/close characters are
# intentionally NOT terminators — they keep sub-clauses stitched together.
_HARD_TERMINATORS = frozenset("，。；！？…,;!?")
_SOFT_TERMINATOR = "."
_ALL_TERMINATORS = _HARD_TERMINATORS | frozenset(_SOFT_TERMINATOR)
_CLOSING = frozenset("”’》」』〕〗〙〉)]}\"'»›")


def slugify(title: str, max_len: int = 64) -> str:
    """Turn a video title into a filesystem-friendly slug.

    - NFKC normalize
    - strip emoji / punctuation
    - collapse whitespace to '-'
    - trim and cap at ``max_len`` chars
    - if result would be empty, fall back to a short hash of the title
    """
    if not title:
        return _hash_fallback(title)
    norm = unicodedata.normalize("NFKC", title).strip()
    norm = _PUNCT_TO_DASH.sub("-", norm)
    cleaned = _UNSAFE_CHARS.sub("-", norm)
    cleaned = _MULTI_DASH.sub("-", cleaned).strip("-")
    if not cleaned:
        return _hash_fallback(title)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-")
    return cleaned or _hash_fallback(title)


def short_hash(value: str, length: int = 6) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _hash_fallback(value: str) -> str:
    return f"video-{short_hash(value or 'unknown')}"


def strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def split_sentences(paragraph: str) -> list[str]:
    """Split a paragraph into clause-sized sentences for the reader.

    Rules:
    * Hard terminators ``，。；！？…,;!?`` always end a sentence.
    * The soft terminator ``.`` only ends a sentence when followed by
      whitespace or end-of-string (keeps ``U.S.A.``, ``3.14`` intact).
    * Consecutive terminators (``?!``, ``。。``) are coalesced onto the same
      boundary.
    * Closing punctuation (”。 ”, ``)`` etc.) glues to the preceding clause.
    * Enumeration commas ``、``, colons ``：:`` and quote openers keep
      sub-clauses joined.
    """
    text = paragraph.strip()
    if not text:
        return []
    out: list[str] = []
    buf: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch in _ALL_TERMINATORS:
            j = i + 1
            # Glue trailing closing punctuation to this clause.
            while j < n and text[j] in _CLOSING:
                buf.append(text[j])
                j += 1
            # Absorb runs of additional terminators ("?!", "。。").
            while j < n and text[j] in _ALL_TERMINATORS:
                buf.append(text[j])
                j += 1
            should_split = True
            if ch == _SOFT_TERMINATOR and j < n and not text[j].isspace():
                # e.g. "U.S.A." — keep going without splitting.
                should_split = False
            if should_split:
                sent = "".join(buf).strip()
                if sent:
                    out.append(sent)
                buf = []
                i = j
                while i < n and text[i].isspace():
                    i += 1
                continue
            i = j
            continue
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out
