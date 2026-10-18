"""Evidence rules shared by every check (spec section 5, design gap G4).

A required fact counts only when its supporting source is verified, observed no
more than 30 days before as_of, not dated after as_of, and not superseded. Freshness
measures when the evidence was observed, not when an agreement was signed. Equally
recent sources that disagree make the fact unknown until reconciled, and a record
whose fields no longer match its source's fact hash is unknown too.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.models.domain import SourceRec
from app.timeutil import ms_to_ist

DAY_MS = 86_400_000

STATE_REASON = {
    "missing": "MISSING_SOURCE",
    "unverified": "UNVERIFIED_SOURCE",
    "future": "FUTURE_SOURCE",
    "stale": "STALE_SOURCE",
    "superseded": "SUPERSEDED_SOURCE",
}
# When every source fails, report the most informative problem first.
_REPORT_ORDER = ("stale", "future", "unverified", "superseded", "missing")


def source_state(src: SourceRec | None, as_of_ms: int, freshness_ms: int, *, require_fresh: bool = True) -> str:
    if src is None:
        return "missing"
    if src.superseded:
        return "superseded"
    if not src.verified or src.observed_at_ms is None:
        return "unverified"
    if src.observed_at_ms > as_of_ms:
        return "future"
    if require_fresh and as_of_ms - src.observed_at_ms > freshness_ms:
        return "stale"
    return "valid"


def describe_state(source_id: str, src: SourceRec | None, state: str, freshness_ms: int) -> str:
    if state == "missing":
        return f"source {source_id} is not in the graph"
    if state == "superseded":
        return f"source {source_id} has a newer version"
    if state == "unverified":
        return f"source {source_id} is not verified"
    if state == "future":
        return f"source {source_id} is dated {ms_to_ist(src.observed_at_ms)}, after the as-of time"
    if state == "stale":
        days = freshness_ms // DAY_MS
        return f"source {source_id} was observed {ms_to_ist(src.observed_at_ms)}, more than {days} days before the as-of time"
    return f"source {source_id} is valid"


@dataclass(frozen=True)
class Support:
    ok: bool
    reason_code: str | None
    source_ids: tuple[str, ...]
    detail: str


def fact_support(
    node_hash: str | None,
    source_ids: Iterable[str],
    sources: Mapping[str, SourceRec],
    as_of_ms: int,
    freshness_ms: int,
    *,
    require_fresh: bool = True,
) -> Support:
    ids = sorted({s for s in source_ids if s})
    if not ids:
        return Support(False, "MISSING_SOURCE", (), "no supporting source is recorded")
    states = [(sid, sources.get(sid)) for sid in ids]
    states = [(sid, src, source_state(src, as_of_ms, freshness_ms, require_fresh=require_fresh)) for sid, src in states]
    valid = [(sid, src) for sid, src, state in states if state == "valid"]
    if not valid:
        sid, src, state = min(states, key=lambda item: _REPORT_ORDER.index(item[2]))
        return Support(False, STATE_REASON[state], tuple(ids), describe_state(sid, src, state, freshness_ms))
    latest = max(src.observed_at_ms for _, src in valid)
    top = sorted((sid, src) for sid, src in valid if src.observed_at_ms == latest)
    top_ids = tuple(sid for sid, _ in top)
    hashes = {src.fact_hash for _, src in top}
    if len(hashes) > 1:
        return Support(False, "CONFLICTING_SOURCES", top_ids,
                       f"equally recent sources {', '.join(top_ids)} disagree; reconcile them first")
    if node_hash is not None and hashes != {node_hash}:
        return Support(False, "SOURCE_MISMATCH", top_ids,
                       f"the stored record no longer matches its source {top_ids[0]}")
    return Support(True, None, top_ids, "supported by " + ", ".join(top_ids))
