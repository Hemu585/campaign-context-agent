"""UTC-millisecond storage and IST display (requirement R23, eligibility time rules)."""

import pytest

from app.clock import business_now_ms, wall_now_ms
from app.config import Settings
from app.timeutil import covers, ms_to_ist, ms_to_iso_utc, overlaps, parse_iso_ms


def test_offset_and_utc_forms_are_the_same_instant():
    assert parse_iso_ms("2026-10-20T09:00:00+05:30") == parse_iso_ms("2026-10-20T03:30:00Z")


def test_known_epoch_value():
    assert parse_iso_ms("1970-01-01T00:00:01Z") == 1000
    assert parse_iso_ms("2026-10-15T12:00:00Z") == 1792065600000


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError):
        parse_iso_ms("2026-10-20T09:00:00")


def test_ist_display():
    assert ms_to_ist(parse_iso_ms("2026-10-15T12:00:00Z")) == "15 Oct 2026, 17:30 IST"
    assert ms_to_ist(parse_iso_ms("2026-10-19T23:59:59+05:30")) == "19 Oct 2026, 23:59:59 IST"


def test_utc_iso_round_trip():
    ms = parse_iso_ms("2026-10-20T09:00:00+05:30")
    assert ms_to_iso_utc(ms) == "2026-10-20T03:30:00Z"
    assert parse_iso_ms(ms_to_iso_utc(ms)) == ms


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 10), (10, 20), True),   # shared endpoint overlaps (inclusive)
        ((0, 9), (10, 20), False),
        ((15, 16), (10, 20), True),  # contained
        ((21, 30), (10, 20), False),
    ],
)
def test_inclusive_overlap(a, b, expected):
    assert overlaps(*a, *b) is expected
    assert overlaps(*b, *a) is expected


def test_covers_requires_full_containment():
    assert covers(0, 100, 10, 90) is True
    assert covers(0, 100, 0, 100) is True
    assert covers(0, 100, 10, 101) is False
    assert covers(5, 100, 4, 90) is False


def test_demo_clock_is_fixed_and_wall_clock_moves():
    settings = Settings(_env_file=None, demo_mode=True)
    assert business_now_ms(settings) == parse_iso_ms("2026-10-15T12:00:00Z")
    assert wall_now_ms() > parse_iso_ms("2026-01-01T00:00:00Z")


def test_normal_mode_uses_the_server_clock():
    settings = Settings(_env_file=None, demo_mode=False)
    assert abs(business_now_ms(settings) - wall_now_ms()) < 5_000
