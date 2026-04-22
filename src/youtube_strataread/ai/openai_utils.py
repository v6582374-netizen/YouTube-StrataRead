"""Helpers for OpenAI-compatible chat-completions providers."""
from __future__ import annotations


def content_to_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part
            for item in content
            for part in (
                item
                if isinstance(item, str)
                else getattr(item, "text", None) or getattr(item, "value", None) or ""
                ,
            )
            if isinstance(part, str)
        )
    text = getattr(content, "text", None) or getattr(content, "value", None)
    return text if isinstance(text, str) else ""


def snapshot_suffix(previous: str, current: str) -> tuple[str, str]:
    """Return (new_buffer, new_text) for cumulative-snapshot style streams."""
    if not current:
        return previous, ""
    if current.startswith(previous):
        return current, current[len(previous) :]
    return previous + current, current
