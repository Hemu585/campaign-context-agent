"""Versioned edits of fictional agreement/availability facts (journey D, R13, API_CONTRACTS
"Demo fact editing").

- Enabled only in DEMO_MODE and only for synthetic facts.
- Allowed fields only; clients can never set verified, source IDs, coverage or observation time.
- One statement updates the fact, writes a new source version that SUPERSEDES the old one
  (agreement edits also refresh the creator's agreement-audit source), advances the revision
  and writes the receipt. Older sources and saved run/proposal snapshots stay untouched.
- New sources are observed at the business clock (design gap G3) and attested by the operator.
"""

from __future__ import annotations

from app.clock import business_now_ms, wall_now_ms
from app.db.client import GraphClient
from app.db.factsig import fact_hash, text_checksum
from app.db.sourcedocs import agreement_rows, audit_rows, availability_rows, render_source, source_title
from app.errors import AppError
from app.services.graph_reads import read_revision
from app.services.mutations import WORKSPACE_ID, MutationService, stale
from app.timeutil import ms_to_ist, parse_iso_ms

EDITABLE = {
    "agreement": {"start_at", "end_at", "status", "exclusive"},
    "availability": {"start_at", "end_at", "status"},
}
STATUSES = {"agreement": {"active", "cancelled"}, "availability": {"available", "unavailable"}}
MAX_REASON = 300


def _time(value: str, field: str) -> int:
    try:
        return parse_iso_ms(value)
    except (TypeError, ValueError):
        raise AppError("INVALID_INTERVAL", f"{field} must be an ISO 8601 time with a timezone offset.", 422) from None


class DemoEditService:
    def __init__(self, client: GraphClient, mutations: MutationService):
        self.client = client
        self.mutations = mutations
        self.settings = mutations.settings

    async def list_facts(self) -> dict:
        return {
            "demo_mode": self.settings.demo_mode,
            "agreements": await self.client.ro_query("Q13_editable_agreements"),
            "availability": await self.client.ro_query("Q13_editable_availability"),
        }

    async def edit(self, fact_type: str, fact_id: str, changes: dict, reason: str, expected_revision: int,
                   key: str) -> dict:
        if not self.settings.demo_mode:
            raise AppError("DEMO_EDIT_DISABLED", "Fact editing is only available in demo mode.", 403)
        if fact_type not in EDITABLE:
            raise AppError("UNSUPPORTED_SCOPE", "Only agreement and availability facts can be edited.", 422)
        unknown = set(changes) - EDITABLE[fact_type]
        if unknown or not changes:
            raise AppError("UNKNOWN_TOOL_ARGUMENT" if unknown else "INVALID_INPUT",
                           f"Editable fields for {fact_type}: {', '.join(sorted(EDITABLE[fact_type]))}.", 422)
        reason = " ".join((reason or "").split())
        if not 1 <= len(reason) <= MAX_REASON:
            raise AppError("INVALID_INPUT", f"An edit reason of 1-{MAX_REASON} characters is required.", 422)
        payload = {"fact_type": fact_type, "fact_id": fact_id, "changes": changes, "reason": reason,
                   "expected_revision": expected_revision}

        async def perform(digest: str):
            current = await read_revision(self.client)
            if current != expected_revision:
                raise stale(expected_revision=expected_revision, current_revision=current)
            if fact_type == "agreement":
                return await self._agreement(fact_id, changes, reason, expected_revision, current + 1, key, digest)
            return await self._availability(fact_id, changes, reason, expected_revision, current + 1, key, digest)

        result = await self.mutations.run("edit_fact", key, payload, perform)
        return await self._result(fact_type, fact_id, result.result_id)

    def _merged(self, fact_type: str, row: dict, changes: dict) -> dict:
        start = _time(changes["start_at"], "start_at") if "start_at" in changes else row["start_ms"]
        end = _time(changes["end_at"], "end_at") if "end_at" in changes else row["end_ms"]
        status = changes.get("status", row["status"])
        if status not in STATUSES[fact_type]:
            raise AppError("INVALID_INPUT", f"status must be one of {sorted(STATUSES[fact_type])}.", 422)
        if start is None or end is None or start > end:
            raise AppError("INVALID_INTERVAL", "The start must be on or before the end, and both must be set.", 422)
        merged = {"start_ms": start, "end_ms": end, "status": status}
        if fact_type == "agreement":
            exclusive = changes.get("exclusive", row["exclusive"])
            if not isinstance(exclusive, bool):
                raise AppError("INVALID_INPUT", "exclusive must be true or false.", 422)
            merged["exclusive"] = exclusive
        if all(merged[k] == row[k] for k in merged):
            raise AppError("INVALID_INPUT", "The edit does not change anything.", 422)
        return merged

    async def _read(self, query_id: str, fact_id: str) -> dict:
        rows = await self.client.ro_query(query_id, {"fact_id": fact_id})
        if not rows:
            raise AppError("FACT_NOT_FOUND", f"No editable fact {fact_id!r}.", 404)
        row = rows[0]
        if not row["synthetic"]:
            raise AppError("DEMO_EDIT_DISABLED", "Only synthetic demo facts can be edited.", 403)
        return row

    async def _agreement(self, fact_id, changes, reason, expected, new_revision, key, digest):
        row = await self._read("Q12_read_agreement", fact_id)
        merged = self._merged("agreement", row, changes)
        if row["audit_id"] is None:
            raise AppError("INVALID_INTERVAL", "No agreement audit covers this creator, so it cannot be edited.", 422)
        cov_start, cov_end = row["coverage_start_ms"], row["coverage_end_ms"]
        if not (cov_start <= merged["start_ms"] and merged["end_ms"] <= cov_end):
            raise AppError("INVALID_INTERVAL",
                           (f"Edits must stay inside the audit coverage {ms_to_ist(cov_start)} – {ms_to_ist(cov_end)}; "
                            "coverage is never expanded by an edit."), 422)
        as_of = business_now_ms(self.settings)
        record = {"id": fact_id, "counterparty_brand_id": row["counterparty_brand_id"], "channel": row["channel"],
                  "category": row["category"], **merged}
        label = f"{row['creator_name']} ({row['creator_id']}) with {row['counterparty_name']}"
        version = int(row["version"]) + 1
        text = render_source(kind="agreement", document_id=row["document_id"], version=version, subject_id=fact_id,
                             subject_label=label, observed_at_ms=as_of,
                             record_rows=agreement_rows(record, row["counterparty_name"]),
                             statement=("Exclusivity, when present, applies only within the channel and category "
                                        "scope and the dated term above."),
                             editor="local_demo_operator", operator_text=reason)
        audit = {"id": row["audit_id"], "kind": "agreements", "coverage_start_ms": cov_start, "coverage_end_ms": cov_end,
                 "complete": row["audit_complete"], "listed_ids": list(row["listed_ids"] or [])}
        audit_version = int(row["audit_version"]) + 1
        audit_label = f"{row['creator_name']} ({row['creator_id']})"
        listed = ", ".join(sorted(audit["listed_ids"])) or "none"
        audit_text = render_source(
            kind="agreement_audit", document_id=row["audit_document_id"], version=audit_version,
            subject_id=row["audit_id"], subject_label=audit_label, observed_at_ms=as_of, record_rows=audit_rows(audit),
            statement=("Audit statement: every agreement involving this creator in the fictional scenario is "
                       f"represented for the coverage period. Represented agreements: {listed}. "
                       "Re-attested after an agreement edit."),
            editor="local_demo_operator", operator_text=reason)
        rows = await self.client.query("Q12_edit_agreement", {
            "workspace_id": WORKSPACE_ID, "expected_revision": expected, "new_revision": new_revision, "key": key,
            "payload_hash": digest, "fact_id": fact_id, "old_source_id": row["source_id"],
            "audit_id": row["audit_id"], "old_audit_source_id": row["audit_source_id"], **merged,
            "new_source_id": f"src_{row['document_id']}_v{version}", "document_id": row["document_id"],
            "new_version": version, "title": source_title("agreement", label), "text": text,
            "checksum": text_checksum(text), "fact_hash": fact_hash("agreement", record),
            "new_audit_source_id": f"src_{row['audit_document_id']}_v{audit_version}",
            "audit_document_id": row["audit_document_id"], "new_audit_version": audit_version,
            "audit_title": source_title("agreement_audit", audit_label), "audit_text": audit_text,
            "audit_checksum": text_checksum(audit_text), "audit_fact_hash": fact_hash("audit", audit),
            "as_of_ms": as_of, "now_ms": wall_now_ms()})
        if not rows:
            raise stale()
        return "source", rows[0]["source_id"], rows[0]["revision"]

    async def _availability(self, fact_id, changes, reason, expected, new_revision, key, digest):
        row = await self._read("Q12_read_availability", fact_id)
        merged = self._merged("availability", row, changes)
        as_of = business_now_ms(self.settings)
        record = {"id": fact_id, **merged}
        label = f"{row['creator_name']} ({row['creator_id']}), {merged['status']}"
        version = int(row["version"]) + 1
        statement = ("The creator confirmed availability for the whole window above." if merged["status"] == "available"
                     else "The creator is unavailable for the whole window above.")
        text = render_source(kind="availability", document_id=row["document_id"], version=version, subject_id=fact_id,
                             subject_label=label, observed_at_ms=as_of, record_rows=availability_rows(record),
                             statement=statement, editor="local_demo_operator", operator_text=reason)
        rows = await self.client.query("Q12_edit_availability", {
            "workspace_id": WORKSPACE_ID, "expected_revision": expected, "new_revision": new_revision, "key": key,
            "payload_hash": digest, "fact_id": fact_id, "old_source_id": row["source_id"], **merged,
            "new_source_id": f"src_{row['document_id']}_v{version}", "document_id": row["document_id"],
            "new_version": version, "title": source_title("availability", label), "text": text,
            "checksum": text_checksum(text), "fact_hash": fact_hash("availability", record),
            "as_of_ms": as_of, "now_ms": wall_now_ms()})
        if not rows:
            raise stale()
        return "source", rows[0]["source_id"], rows[0]["revision"]

    async def _result(self, fact_type: str, fact_id: str, source_id: str) -> dict:
        facts = await self.list_facts()
        group = facts["agreements"] if fact_type == "agreement" else facts["availability"]
        fact = next(f for f in group if f["id"] == fact_id)
        sources = await self.client.ro_query("Q07_sources_by_id", {"source_ids": [source_id]})
        return {"fact_type": fact_type, "fact": fact, "source_id": source_id,
                "supersedes": sources[0]["supersedes"] if sources else [],
                "context_revision": await read_revision(self.client)}
