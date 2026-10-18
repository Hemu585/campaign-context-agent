"""Time handling: store UTC Unix milliseconds, display Asia/Kolkata (spec section 5).

Intervals are closed: endpoints are inclusive, so two intervals overlap when
a.start <= b.end and a.end >= b.start.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS = timedelta(milliseconds=1)


def parse_iso_ms(value: str) -> int:
    """Parse a timezone-aware ISO 8601 string into UTC Unix milliseconds."""
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        raise ValueError(f"timestamp {value!r} has no timezone offset")
    return (dt - _EPOCH) // _MS


def ms_to_datetime(ms: int) -> datetime:
    return _EPOCH + timedelta(milliseconds=ms)


def ms_to_ist(ms: int) -> str:
    """Display form, e.g. '20 Oct 2026, 09:00 IST' (seconds shown only when non-zero)."""
    dt = ms_to_datetime(ms).astimezone(IST)
    clock = dt.strftime("%H:%M:%S") if dt.second else dt.strftime("%H:%M")
    return f"{dt.day} {dt.strftime('%b %Y')}, {clock} IST"


def ms_to_iso_utc(ms: int) -> str:
    dt = ms_to_datetime(ms)
    text = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if dt.microsecond:
        text += f".{dt.microsecond // 1000:03d}"
    return text + "Z"


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and a_end >= b_start


def covers(outer_start: int, outer_end: int, inner_start: int, inner_end: int) -> bool:
    return outer_start <= inner_start and outer_end >= inner_end
