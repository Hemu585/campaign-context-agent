"""Internal draft proposals and revalidated human approval (journey E, R14, R15, R24).

A draft is staged by the agent tool only for a candidate that is eligible in the run's current
evaluation. Approval is a separate human HTTP action that, under the mutation lock, rechecks the
slot, the run, the revision AND every eligibility rule before one atomic write. A proposal's
snapshot is immutable: later edits never rewrite it, and an approved proposal is never "stale".
"""

from __future__ import annotations

import hashlib
import json

from app.clock import business_now_ms, wall_now_ms
from app.db.client import GraphClient
from app.errors import AppError
from app.models.api import Evaluation
from app.models.domain import CampaignRec
from app.services.evaluation import EvaluationService
from app.services.graph_reads import load_sources, read_revision
from app.services.mutations import WORKSPACE_ID, MutationService, stale
from app.services.sessions import new_id

EXCERPT_CHARS = 400
APPROVAL_REASON = "Approved by the operator in the local UI. Internal proposal only; no booking or contact."


def staging_key(run_id: str, creator_id: str, revision: int) -> str:
    digest = hashlib.sha256(f"{run_id}|{creator_id}|{revision}".encode()).hexdigest()
    return f"stage_{digest[:40]}"


def _present(row: dict) -> dict:
    is_draft = row["status"] == "draft"
    is_stale = is_draft and row["context_revision"] != row["current_revision"]
    slot_filled = row["slot_proposal_id"] is not None
    reason = None
    if is_draft:
        if row["run_status"] != "completed":
            reason = "run_not_completed"
        elif slot_filled:
            reason = "slot_filled"
        elif is_stale:
            reason = "stale"
    return {
        "id": row["id"], "campaign_id": row["campaign_id"], "campaign_title": row["campaign_title"],
        "creator_id": row["creator_id"], "creator_name": row["creator_name"], "run_id": row["run_id"],
        "run_status": row["run_status"], "status": row["status"], "context_revision": row["context_revision"],
        "current_revision": row["current_revision"], "is_stale": is_stale, "slot_filled": slot_filled,
        "approvable": is_draft and reason is None, "unusable_reason": reason, "as_of_ms": row["as_of_ms"],
        "created_at_ms": row["created_at_ms"], "approved_at_ms": row["approved_at_ms"],
        "approved_revision": row["approved_revision"], "decision_id": row["decision_id"],
        "snapshot": json.loads(row["snapshot_json"]) if row["snapshot_json"] else None,
    }


class ProposalService:
    def __init__(self, client: GraphClient, mutations: MutationService, evaluation: EvaluationService):
        self.client = client
        self.mutations = mutations
        self.evaluation = evaluation
        self.settings = mutations.settings

    async def _snapshot(self, evaluation: Evaluation, campaign: CampaignRec, creator_id: str) -> tuple[dict, list[str]]:
        cand = next(c for c in evaluation.candidates if c.creator_id == creator_id)
        paths = [p for p in evaluation.evidence_paths if p.id in cand.evidence_path_ids]
        source_ids = sorted({s for ch in cand.checks for s in ch.source_ids} | {s for p in paths for s in p.source_ids}
                            | {h.source_id for h in cand.completed_campaigns})
        docs = await load_sources(self.client, source_ids)
        snapshot = {
            "snapshot_version": 1,
            "campaign": {
                "id": campaign.id, "title": campaign.title, "client_brand_id": campaign.brand_id,
                "client_brand_name": campaign.brand_name, "channel": campaign.channel,
                "deliverable": campaign.deliverable, "language": campaign.language, "category": campaign.category,
                "currency": campaign.currency, "budget_paise": campaign.budget_paise, "start_ms": campaign.start_ms,
                "end_ms": campaign.end_ms,
            },
            "candidate": cand.model_dump(mode="json"),
            "ranking_inputs": {"fee_paise": cand.fee_paise, "completed_campaign_count": cand.completed_campaign_count,
                               "rank": cand.rank},
            "recommended_creator_ids": evaluation.recommended_creator_ids,
            "evidence_paths": [p.model_dump(mode="json", by_alias=True) for p in paths],
            "sources": [{"id": d["id"], "title": d["title"], "version": d["version"],
                         "observed_at_ms": d["observed_at_ms"], "verified": bool(d["verified"]),
                         "synthetic": bool(d["synthetic"]), "excerpt": (d["text"] or "")[:EXCERPT_CHARS]}
                        for d in docs],
            "as_of_ms": evaluation.as_of_ms,
            "context_revision": evaluation.context_revision,
        }
        return snapshot, source_ids

    async def stage(self, *, run_id: str, creator_id: str, evaluation: Evaluation, campaign: CampaignRec) -> dict:
        key = staging_key(run_id, creator_id, evaluation.context_revision)
        payload = {"run_id": run_id, "creator_id": creator_id, "revision": evaluation.context_revision}

        async def perform(digest: str):
            current = await read_revision(self.client)
            if current != evaluation.context_revision:
                raise stale("The information changed after this evaluation. Run again before proposing.",
                            expected_revision=evaluation.context_revision, current_revision=current)
            cand = next((c for c in evaluation.candidates if c.creator_id == creator_id), None)
            if cand is None or cand.status != "eligible":
                raise AppError("CANDIDATE_NOT_ELIGIBLE", "Only an eligible candidate from the current evaluation "
                               "can be proposed.", 409, details={"status": cand.status if cand else "not_evaluated"})
            snapshot, source_ids = await self._snapshot(evaluation, campaign, creator_id)
            proposal_id = new_id("prop")
            rows = await self.client.query("Q09_stage_draft", {
                "workspace_id": WORKSPACE_ID, "revision": evaluation.context_revision, "run_id": run_id,
                "campaign_id": evaluation.campaign_id, "creator_id": creator_id, "key": key,
                "proposal_id": proposal_id, "now_ms": wall_now_ms(), "as_of_ms": evaluation.as_of_ms,
                "snapshot_json": json.dumps(snapshot, separators=(",", ":")), "payload_hash": digest,
                "source_ids": source_ids})
            if not rows:
                raise AppError("RUN_NOT_ACTIVE", "The run is no longer running, so it cannot stage a draft.", 409)
            return "proposal", rows[0]["id"], None

        result = await self.mutations.run("stage_draft", key, payload, perform)
        return await self.get(result.result_id)

    async def list(self, campaign_id: str | None = None) -> list[dict]:
        rows = await self.client.ro_query("Q13_proposals")
        out = [_present(r) for r in rows]
        return [p for p in out if campaign_id is None or p["campaign_id"] == campaign_id]

    async def get(self, proposal_id: str) -> dict:
        found = [p for p in await self.list() if p["id"] == proposal_id]
        if not found:
            raise AppError("PROPOSAL_NOT_FOUND", f"Proposal {proposal_id!r} does not exist.", 404)
        return found[0]

    async def approve(self, proposal_id: str, expected_revision: int, key: str) -> dict:
        payload = {"proposal_id": proposal_id, "expected_revision": expected_revision}

        async def perform(digest: str):
            p = await self.get(proposal_id)
            if p["status"] == "approved" or p["slot_filled"]:
                raise AppError("SLOT_FILLED", "This campaign's replacement slot already has an approved proposal.",
                               409, details={"approved_proposal_id": p["id"] if p["status"] == "approved" else None})
            if p["run_status"] != "completed":
                raise AppError("PROPOSAL_NOT_USABLE", "This draft comes from a run that did not complete "
                               "successfully, so it cannot be approved.", 409, details={"run_status": p["run_status"]})
            current = await read_revision(self.client)
            if expected_revision != current or p["context_revision"] != current:
                raise stale("The information changed since this proposal was drafted. Run the agent again.",
                            expected_revision=expected_revision, proposal_revision=p["context_revision"],
                            current_revision=current)
            evaluation, _ = await self.evaluation.consistent_evaluate(p["campaign_id"], expected_revision)
            cand = next((c for c in evaluation.candidates if c.creator_id == p["creator_id"]), None)
            if cand is None or cand.status != "eligible":
                raise AppError("CANDIDATE_NOT_ELIGIBLE", "The candidate no longer passes every check on current "
                               "evidence.", 409, details={"status": cand.status if cand else "not_evaluated",
                                                           "failed_checks": cand.failed_checks if cand else [],
                                                           "unknown_checks": cand.unknown_checks if cand else []})
            decision_id = new_id("dec")
            rows = await self.client.query("Q10_approve", {
                "workspace_id": WORKSPACE_ID, "expected_revision": expected_revision, "new_revision": current + 1,
                "campaign_id": p["campaign_id"], "proposal_id": proposal_id, "creator_id": p["creator_id"],
                "key": key, "decision_id": decision_id, "reason": APPROVAL_REASON,
                "as_of_ms": business_now_ms(self.settings), "now_ms": wall_now_ms(), "payload_hash": digest})
            if not rows:
                raise stale("The approval could not be saved because the graph changed. Refresh and retry.")
            return "decision", rows[0]["decision_id"], rows[0]["revision"]

        result = await self.mutations.run("approve", key, payload, perform)
        proposal = next(p for p in await self.list() if p["decision_id"] == result.result_id)
        return {"decision_id": result.result_id, "proposal": proposal, "replayed": result.replayed,
                "context_revision": await read_revision(self.client)}
