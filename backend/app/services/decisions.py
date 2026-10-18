"""Scoped rejection memory: record, revoke, list (journey C, R11, R12, spec section 6).

- Scope is explicit (campaign or brand) and derived on the server from graph ownership.
- Free-text reasons are stored as data in a feedback Source; they never create rules.
- Revocation and expiry never delete or rewrite the original event.
"""

from __future__ import annotations

from app.clock import business_now_ms, wall_now_ms
from app.db.client import GraphClient
from app.db.factsig import text_checksum
from app.db.sourcedocs import render_source
from app.errors import AppError
from app.models.domain import DecisionRec, RevocationRec
from app.services.graph_reads import load_campaign_context, read_revision
from app.services.memory import decision_state
from app.services.mutations import WORKSPACE_ID, MutationService, stale
from app.services.sessions import new_id
from app.timeutil import ms_to_ist

MAX_REASON = 500
SCOPES = ("campaign", "brand")


def _clean_reason(reason: str) -> str:
    text = " ".join((reason or "").split())
    if not 1 <= len(text) <= MAX_REASON:
        raise AppError("INVALID_INPUT", f"A reason of 1-{MAX_REASON} characters is required.", 422)
    return text


class DecisionService:
    def __init__(self, client: GraphClient, mutations: MutationService):
        self.client = client
        self.mutations = mutations
        self.settings = mutations.settings

    async def _check_revision(self, expected: int) -> int:
        current = await read_revision(self.client)
        if current != expected:
            raise stale("The campaign information changed. Refresh and try again.",
                        expected_revision=expected, current_revision=current)
        return current

    async def reject(self, *, campaign_id: str, creator_id: str, scope_type: str, reason: str,
                     expires_at_ms: int | None, expected_revision: int, session_id: str | None, key: str) -> dict:
        if scope_type not in SCOPES:
            raise AppError("UNSUPPORTED_SCOPE", "Scope must be 'campaign' or 'brand'.", 422)
        reason = _clean_reason(reason)
        payload = {"campaign_id": campaign_id, "creator_id": creator_id, "scope_type": scope_type, "reason": reason,
                   "expires_at_ms": expires_at_ms, "expected_revision": expected_revision, "session_id": session_id}

        async def perform(digest: str):
            current = await self._check_revision(expected_revision)
            ctx = await load_campaign_context(self.client, campaign_id)
            creator = next((c for c in ctx.creators if c.id == creator_id), None)
            if creator is None:
                raise AppError("CREATOR_NOT_FOUND", f"Creator {creator_id!r} does not exist.", 404)
            as_of = business_now_ms(self.settings)
            if expires_at_ms is not None and expires_at_ms <= as_of:
                raise AppError("INVALID_INTERVAL", "The expiry must be after the current business time.", 422)
            scope_id = campaign_id if scope_type == "campaign" else ctx.campaign.brand_id
            decision_id = new_id("dec")
            scope_label = (f"campaign {ctx.campaign.title} ({campaign_id})" if scope_type == "campaign"
                           else f"every campaign of {ctx.campaign.brand_name} ({scope_id})")
            text = render_source(
                kind="operator_feedback", document_id=f"feedback_{decision_id}", version=1, subject_id=decision_id,
                subject_label=f"rejection of {creator.name} ({creator_id})", observed_at_ms=as_of,
                record_rows=[("action", "rejected"), ("creator", f"{creator.name} ({creator_id})"),
                             ("scope", scope_label),
                             ("expires", "no expiry" if expires_at_ms is None else ms_to_ist(expires_at_ms))],
                statement=("Operator selection feedback inside this synthetic workspace. It limits who is "
                           "recommended in the stated scope; it is not a fact about a real person."),
                editor="local_demo_operator", operator_text=reason)
            rows = await self.client.query("Q11_reject", {
                "workspace_id": WORKSPACE_ID, "expected_revision": expected_revision, "new_revision": current + 1,
                "campaign_id": campaign_id, "creator_id": creator_id, "key": key, "scope_type": scope_type,
                "scope_id": scope_id, "session_id": session_id or "", "decision_id": decision_id,
                "reason": reason, "as_of_ms": as_of, "now_ms": wall_now_ms(), "expires_at_ms": expires_at_ms,
                "payload_hash": digest, "source_id": f"src_feedback_{decision_id}_v1",
                "source_document_id": f"feedback_{decision_id}", "source_title": f"Operator feedback: {decision_id}",
                "source_text": text, "source_checksum": text_checksum(text)})
            if not rows:
                raise stale()
            return "decision", rows[0]["id"], rows[0]["revision"]

        result = await self.mutations.run("reject", key, payload, perform)
        return await self.get(result.result_id)

    async def revoke(self, *, decision_id: str, reason: str, expected_revision: int, key: str) -> dict:
        reason = _clean_reason(reason)
        payload = {"decision_id": decision_id, "reason": reason, "expected_revision": expected_revision}

        async def perform(digest: str):
            current = await self._check_revision(expected_revision)
            original = await self.get(decision_id)
            if original["action"] != "rejected":
                raise AppError("INVALID_INPUT", "Only a rejection can be revoked.", 422)
            if original["revoked_by_id"]:
                raise AppError("ALREADY_REVOKED", "This rejection was already revoked.", 409,
                               details={"revoked_by_id": original["revoked_by_id"]})
            as_of = business_now_ms(self.settings)
            revocation_id = new_id("dec")
            text = render_source(
                kind="operator_feedback", document_id=f"feedback_{revocation_id}", version=1,
                subject_id=revocation_id, subject_label=f"revocation of {decision_id}", observed_at_ms=as_of,
                record_rows=[("action", "revoked"), ("revokes", decision_id),
                             ("creator", f"{original['creator_name']} ({original['creator_id']})")],
                statement="The original rejection stays in history but no longer filters candidates.",
                editor="local_demo_operator", operator_text=reason)
            rows = await self.client.query("Q11_revoke", {
                "workspace_id": WORKSPACE_ID, "expected_revision": expected_revision, "new_revision": current + 1,
                "decision_id": decision_id, "revocation_id": revocation_id, "key": key, "reason": reason,
                "as_of_ms": as_of, "now_ms": wall_now_ms(), "payload_hash": digest,
                "source_id": f"src_feedback_{revocation_id}_v1", "source_document_id": f"feedback_{revocation_id}",
                "source_title": f"Operator feedback: {revocation_id}", "source_text": text,
                "source_checksum": text_checksum(text)})
            if not rows:
                raise stale()
            return "decision", rows[0]["id"], rows[0]["revision"]

        result = await self.mutations.run("revoke", key, payload, perform)
        return await self.get(result.result_id)

    def _present(self, row: dict, as_of_ms: int) -> dict:
        revocations = sorted(row["revocations"], key=lambda v: (v["as_of_ms"] or 0, v["id"]))
        state = row["action"]
        if row["action"] == "rejected":
            rec = DecisionRec(
                id=row["id"], creator_id=row["creator_id"], scope_type=row["scope_type"], scope_id=row["scope_id"],
                reason=row["reason"], as_of_ms=row["as_of_ms"], created_at_ms=row["created_at_ms"],
                expires_at_ms=row["expires_at_ms"], made_in_campaign_id=row["campaign_id"],
                revocations=tuple(RevocationRec(v["id"], v["as_of_ms"]) for v in revocations),
                source_ids=tuple(row["source_ids"]))
            state = decision_state(rec, as_of_ms)
        return {
            "id": row["id"], "action": row["action"], "state": state, "is_active": state == "active",
            "creator_id": row["creator_id"], "creator_name": row["creator_name"], "campaign_id": row["campaign_id"],
            "campaign_title": row["campaign_title"], "scope_type": row["scope_type"], "scope_id": row["scope_id"],
            "reason": row["reason"], "as_of_ms": row["as_of_ms"], "created_at_ms": row["created_at_ms"],
            "expires_at_ms": row["expires_at_ms"], "source_ids": sorted(row["source_ids"]),
            "revoked_by_id": revocations[0]["id"] if revocations else None, "revokes_id": row["revokes_id"],
            "proposal_id": row["proposal_id"], "session_id": row["session_id"],
        }

    async def list(self, *, campaign_id: str | None = None, creator_id: str | None = None) -> list[dict]:
        as_of = business_now_ms(self.settings)
        rows = await self.client.ro_query("Q13_decisions")
        out = [self._present(r, as_of) for r in rows]
        if campaign_id:
            brand = (await load_campaign_context(self.client, campaign_id)).campaign.brand_id
            out = [d for d in out if d["campaign_id"] == campaign_id
                   or (d["scope_type"] == "brand" and d["scope_id"] == brand)]
        if creator_id:
            out = [d for d in out if d["creator_id"] == creator_id]
        return out

    async def get(self, decision_id: str) -> dict:
        found = [d for d in await self.list() if d["id"] == decision_id]
        if not found:
            raise AppError("DECISION_NOT_FOUND", f"Decision {decision_id!r} does not exist.", 404)
        return found[0]
