"""Admission of automatic work, distinct from permission and completion eligibility."""
from __future__ import annotations

import math
from datetime import datetime

WINDOW_SECONDS = 72 * 60 * 60


def admission(published_at: str, published_ts: float | None, now: float) -> str:
    """Use corroborated, timezone-aware public time; equality belongs to the window."""
    try:
        parsed = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        if parsed.tzinfo is None or published_ts is None:
            return 'awaiting_timing'
        timestamp = parsed.timestamp()
        if not math.isfinite(published_ts) or abs(timestamp - published_ts) > .001:
            return 'awaiting_timing'
        if timestamp > now:
            return 'awaiting_timing'
        return 'queued' if now - timestamp <= WINDOW_SECONDS else 'expired'
    except (ValueError, TypeError, OverflowError):
        return 'awaiting_timing'


WAITING_REASONS = {
    'expired': '首次开工前已超过 72 小时自动处理窗口；已有资料保留。',
    'awaiting_timing': '发布时间缺失、矛盾或晚于当前时间，等待核实；尚未取得续办资格。',
}
