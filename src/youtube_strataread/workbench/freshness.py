"""Admission of automatic work, distinct from permission and completion eligibility."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

WINDOW_SECONDS = 72 * 60 * 60


def timestamp(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def event_completion(broadcast: object, details: dict[str, Any], now: float) -> str:
    """Only official actual times establish completion; schedules never do."""
    start = timestamp(details.get('actualStartTime'))
    end = timestamp(details.get('actualEndTime'))
    for key in ('actualStartTime', 'actualEndTime', 'scheduledStartTime'):
        if key in details and timestamp(details[key]) is None:
            return 'unverified'
    if start is not None and start > now:
        return 'unverified'
    if end is not None:
        return ('ended' if broadcast == 'none' and start is not None
                and start <= end <= now else 'unverified')
    if broadcast == 'upcoming' and start is not None:
        return 'unverified'
    return 'waiting' if broadcast in ('live', 'upcoming') else 'unverified'


def preparation_admission(published_at: str, published_ts: float | None, now: float,
                          timing_status: str = 'publication', completion_status: str = 'unverified',
                          actual_end_at: str | None = None, *, age_exempt: bool = False) -> str:
    if timing_status == 'event':
        if completion_status == 'waiting':
            return 'awaiting_completion'
        if completion_status != 'ended':
            return 'awaiting_timing'
        state = admission(actual_end_at or '', timestamp(actual_end_at), now)
    elif timing_status == 'publication':
        state = admission(published_at, published_ts, now)
    else:
        return 'awaiting_timing'
    return 'queued' if age_exempt and state == 'expired' else state


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
    'awaiting_timing': '视频类型、公开时间或实际结束时间尚未可靠核实，等待官方复查。',
    'awaiting_completion': '直播或首映尚未结束，等待结束后核实实际结束时间。',
}
