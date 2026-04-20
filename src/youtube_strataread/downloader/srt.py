"""SRT parsing and normalization.

Converts raw SRT subtitles into a list of :class:`Cue` objects and further into
line-format strings consumable by the AI pipeline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import srt as srtlib

from youtube_strataread.utils.text import strip_bom

_HTML_TAG = re.compile(r"<[^>]+>")
_NOISE_MARKERS = re.compile(r"\[[^\]]+\]|\([^)]+\)")  # [Music], (applause)
_SPEAKER_PREFIX = re.compile(r"^\s*(?:>>|-)\s*")
_MULTI_WS = re.compile(r"\s+")


@dataclass
class Cue:
    start: timedelta
    end: timedelta
    speaker: str | None
    text: str


def load_cues(srt_text: str) -> list[Cue]:
    """Parse raw SRT text into a normalized list of cues.

    - strips HTML tags
    - removes bracketed noise markers
    - normalises speaker prefixes (``>>``, ``-``) to ``speaker=None`` placeholder
    - drops empty cues after cleanup
    - merges consecutive sub-1s cues from the same speaker
    """
    text = strip_bom(srt_text)
    try:
        parsed = list(srtlib.parse(text))
    except Exception as e:  # pragma: no cover - defensive
        raise ValueError(f"failed to parse SRT: {e}") from e

    cues: list[Cue] = []
    for sub in parsed:
        content = _HTML_TAG.sub("", sub.content)
        content = _NOISE_MARKERS.sub(" ", content)
        content = content.replace("\n", " ")
        # speaker prefix is only consumed for *cleanup*; we do not try to
        # infer individual speakers from raw captions.
        content = _SPEAKER_PREFIX.sub("", content)
        content = _MULTI_WS.sub(" ", content).strip()
        if not content:
            continue
        cues.append(Cue(start=sub.start, end=sub.end, speaker=None, text=content))
    return _merge_short_cues(cues)


def _merge_short_cues(cues: list[Cue], min_gap: float = 0.5) -> list[Cue]:
    if not cues:
        return []
    merged: list[Cue] = [cues[0]]
    for c in cues[1:]:
        prev = merged[-1]
        gap = (c.start - prev.end).total_seconds()
        same_speaker = c.speaker == prev.speaker
        if same_speaker and gap <= min_gap and len(prev.text) + len(c.text) < 200:
            merged[-1] = Cue(
                start=prev.start,
                end=c.end,
                speaker=prev.speaker,
                text=f"{prev.text} {c.text}".strip(),
            )
        else:
            merged.append(c)
    return merged


def cues_to_lines(cues: list[Cue]) -> list[str]:
    """Render cues as plain content lines, one cue per line.

    We intentionally do *not* prefix each line with ``讲话人:``. YouTube
    captions are fragmented on timing, not on speaker turns; forcing a speaker
    prefix on every fragment caused the LLM to preserve that prefix even when
    a sentence spanned two fragments, producing mid-sentence breaks like::

        不过我很多年前确实和
        讲话人: 我那位极繁主义时尚博主朋友...

    If the original cue *already* came with a speaker label (parsed in
    ``load_cues``) we preserve it verbatim.
    """
    lines: list[str] = []
    for c in cues:
        if c.speaker:
            lines.append(f"{c.speaker}: {c.text}")
        else:
            lines.append(c.text)
    return lines


def read_srt_file(path: Path) -> list[Cue]:
    return load_cues(path.read_text(encoding="utf-8"))
