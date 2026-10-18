"""When a remembered rejection applies (GRAPH_MODEL "Decision scopes").

A rejection is active at as_of when it was made at or before as_of, it has not
expired (expiry is exclusive: at as_of >= expires_at it no longer applies), and no
revocation event is effective at or before as_of. Revocation and expiry never delete
the original event.
"""

from __future__ import annotations

from app.models.domain import DecisionRec


def is_expired(decision: DecisionRec, as_of_ms: int) -> bool:
    return decision.expires_at_ms is not None and as_of_ms >= decision.expires_at_ms


def effective_revocation(decision: DecisionRec, as_of_ms: int):
    hits = [r for r in decision.revocations if r.as_of_ms is not None and r.as_of_ms <= as_of_ms]
    return min(hits, key=lambda r: (r.as_of_ms, r.id)) if hits else None


def decision_is_active(decision: DecisionRec, as_of_ms: int) -> bool:
    if decision.as_of_ms is None or decision.as_of_ms > as_of_ms:
        return False
    if is_expired(decision, as_of_ms):
        return False
    return effective_revocation(decision, as_of_ms) is None


def decision_state(decision: DecisionRec, as_of_ms: int) -> str:
    if effective_revocation(decision, as_of_ms) is not None:
        return "revoked"
    if is_expired(decision, as_of_ms):
        return "expired"
    if decision.as_of_ms is None or decision.as_of_ms > as_of_ms:
        return "not_yet_effective"
    return "active"
