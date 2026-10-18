"""Source validity and fact support (spec section 5 evidence rules, T06)."""

import pytest

from app.models.domain import SourceRec
from app.services.evidence import DAY_MS, fact_support, source_state
from app.timeutil import parse_iso_ms

AS_OF = parse_iso_ms("2026-10-15T12:00:00Z")
FRESH = 30 * DAY_MS


def src(sid="s1", observed=AS_OF, verified=True, fact_hash="h", superseded_by=()):
    return SourceRec(id=sid, document_id=sid, version=1, kind="offer", title="t", subject_id="x",
                     observed_at_ms=observed, verified=verified, checksum="c", fact_hash=fact_hash,
                     synthetic=True, superseded_by=superseded_by)


@pytest.mark.parametrize(
    ("source", "state"),
    [
        (src(observed=AS_OF - FRESH), "valid"),            # exactly 30 days old is still fresh
        (src(observed=AS_OF - FRESH - 1), "stale"),
        (src(observed=AS_OF + 1), "future"),
        (src(verified=False), "unverified"),
        (src(observed=None), "unverified"),
        (src(superseded_by=("s2",)), "superseded"),
        (None, "missing"),
    ],
)
def test_source_state(source, state):
    assert source_state(source, AS_OF, FRESH) == state


def test_history_sources_can_skip_freshness():
    old = src(observed=parse_iso_ms("2026-07-10T12:00:00+05:30"))
    assert source_state(old, AS_OF, FRESH) == "stale"
    assert source_state(old, AS_OF, FRESH, require_fresh=False) == "valid"


def test_no_sources_means_missing():
    s = fact_support("h", [], {}, AS_OF, FRESH)
    assert (s.ok, s.reason_code) == (False, "MISSING_SOURCE")


def test_dangling_source_id_means_missing():
    s = fact_support("h", ["ghost"], {}, AS_OF, FRESH)
    assert (s.ok, s.reason_code) == (False, "MISSING_SOURCE")


def test_single_matching_source_supports_the_fact():
    s = fact_support("h", ["s1"], {"s1": src()}, AS_OF, FRESH)
    assert (s.ok, s.source_ids) == (True, ("s1",))


def test_record_that_differs_from_its_source_is_unknown():
    s = fact_support("other", ["s1"], {"s1": src()}, AS_OF, FRESH)
    assert (s.ok, s.reason_code) == (False, "SOURCE_MISMATCH")


def test_equally_recent_disagreeing_sources_are_unknown():
    sources = {"s1": src("s1", fact_hash="a"), "s2": src("s2", fact_hash="b")}
    s = fact_support("a", ["s1", "s2"], sources, AS_OF, FRESH)
    assert (s.ok, s.reason_code) == (False, "CONFLICTING_SOURCES")


def test_equally_recent_agreeing_sources_are_fine():
    sources = {"s1": src("s1"), "s2": src("s2")}
    assert fact_support("h", ["s1", "s2"], sources, AS_OF, FRESH).ok


def test_newer_valid_source_wins_over_a_stale_one():
    sources = {"old": src("old", observed=AS_OF - 40 * DAY_MS, fact_hash="x"), "new": src("new")}
    s = fact_support("h", ["old", "new"], sources, AS_OF, FRESH)
    assert (s.ok, s.source_ids) == (True, ("new",))


def test_the_most_informative_failure_is_reported():
    sources = {"a": src("a", observed=AS_OF - 40 * DAY_MS)}
    s = fact_support("h", ["a", "ghost"], sources, AS_OF, FRESH)
    assert s.reason_code == "STALE_SOURCE"
    assert "more than 30 days" in s.detail
