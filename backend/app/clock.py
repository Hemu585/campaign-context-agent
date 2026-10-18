"""Two clocks: the business clock drives eligibility, the wall clock records events.

In demo mode the business clock is fixed (DEMO_AS_OF) so scenarios repeat; real
creation timestamps still use the wall clock (design decision D13, design gap G3).
Clients can never supply either value.
"""

from __future__ import annotations

import time

from app.config import Settings
from app.timeutil import _EPOCH, _MS


def wall_now_ms() -> int:
    return time.time_ns() // 1_000_000


def business_now_ms(settings: Settings) -> int:
    if settings.demo_mode:
        return (settings.demo_as_of - _EPOCH) // _MS
    return wall_now_ms()


def clock_label(settings: Settings) -> str:
    return "fixed demo clock" if settings.demo_mode else "server clock"
