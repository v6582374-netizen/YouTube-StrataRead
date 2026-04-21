"""Persist clicked sentences to ``highlights.md`` next to the source markdown.

Nothing is written when the user hasn't highlighted anything, per the
product spec. The order is click-order, grouped by the leaf the sentence
originally came from so the note stays navigable.
"""
from __future__ import annotations

from pathlib import Path

from youtube_strataread.reader.session import ReadingSession, SentenceSpan

HIGHLIGHTS_FILENAME = "highlights.md"


def write_highlights(session: ReadingSession) -> Path | None:
    """Dump ``session.highlights_order`` into ``<folder>/highlights.md``.

    Returns the path written to, or ``None`` when there's nothing to save.
    """
    highlights: list[SentenceSpan] = [s for s in session.highlights_order if s.highlighted]
    if not highlights:
        return None

    grouped: dict[str, list[SentenceSpan]] = {}
    ordered_titles: list[str] = []
    for span in highlights:
        key = f"{span.leaf_path}|{span.leaf_title}"
        if key not in grouped:
            grouped[key] = []
            ordered_titles.append(key)
        grouped[key].append(span)

    lines: list[str] = []
    lines.append("# 高亮摘录")
    if session.doc_title:
        lines.append(f"> 来自：{session.doc_title}")
    lines.append("")
    untitled = "(未命名章节)"
    for key in ordered_titles:
        _, title = key.split("|", 1)
        heading = title if title else untitled
        lines.append(f"## {heading}")
        for span in grouped[key]:
            lines.append(f"- {span.text}")
        lines.append("")
    body = "\n".join(lines).rstrip() + "\n"

    out_path = session.folder / HIGHLIGHTS_FILENAME
    out_path.write_text(body, encoding="utf-8")
    return out_path
