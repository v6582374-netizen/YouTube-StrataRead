"""Text utilities: slug generation, CJK sentence splitting, normalization."""
from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT_TO_DASH = re.compile(r"[\s\u3000]+")
_UNSAFE_CHARS = re.compile(r"[^\w\-\u4e00-\u9fff]", re.UNICODE)
_MULTI_DASH = re.compile(r"-{2,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?…])|(?<=[\.\?\!])\s+")


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
    """Split a paragraph into sentences, preserving CJK/English punctuation.

    Keeps the terminator attached to the preceding sentence.
    """
    text = paragraph.strip()
    if not text:
        return []
    raw = _SENTENCE_SPLIT.split(text)
    return [s.strip() for s in raw if s and s.strip()]
