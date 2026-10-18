"""The five allowlisted agent tools (AGENT_WORKFLOW "Tool registry").

The server injects workspace, run, campaign, as_of and revision; the model can pass at most a
``creator_id``. Unknown tools or arguments are rejected before execution and returned to the
model as structured errors. Every tool re-checks the run's revision first, so tool calls in
one run never mix revisions. Results are compact; source text is bounded and labelled as
untrusted data. No tool can approve anything or run Cypher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.client import GraphClient
from app.errors import AppError
from app.models.api import Evaluation
from app.models.domain import CampaignRec
from app.money import format_inr
from app.services.campaigns import campaign_detail
from app.services.decisions import DecisionService
from app.services.evaluation import EvaluationService
from app.services.graph_reads import load_sources, read_revision
from app.services.proposals import ProposalService
from app.timeutil import ms_to_ist

CREATOR_ID = re.compile(r"^cr_\d{2}$")
EXCERPT_CHARS = 300
MAX_EVIDENCE_SOURCES = 4

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": "get_campaign_requirements",
        "description": "Read the selected campaign's requirements, client brand, budget, delivery window and the "
                       "dropped-out creator from the graph.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "evaluate_candidates",
        "description": "Check every creator against all hard rules using graph evidence. Returns statuses, the "
                       "ranking and reason codes. Remembered rejections are already applied.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_candidate_evidence",
        "description": "Get the check results, graph paths and short source excerpts for one creator.",
        "parameters": {"type": "object", "properties": {
            "creator_id": {"type": "string", "description": "A creator id exactly as returned by evaluate_candidates"}},
            "required": ["creator_id"]}}},
    {"type": "function", "function": {
        "name": "get_previous_decisions",
        "description": "List remembered operator rejections and revocations for this campaign or its brand.",
        "parameters": {"type": "object", "properties": {
            "creator_id": {"type": "string", "description": "Optional creator id to filter by"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "stage_replacement_proposal",
        "description": "Stage an internal DRAFT replacement proposal for one eligible creator after reading their "
                       "evidence. Only the operator can approve it in the app; nothing is booked or sent.",
        "parameters": {"type": "object", "properties": {
            "creator_id": {"type": "string", "description": "Creator id of the eligible creator to propose"}},
            "required": ["creator_id"]}}},
]
TOOL_NAMES = [t["function"]["name"] for t in TOOL_SCHEMAS]
ALLOWED_ARGS = {"get_campaign_requirements": set(), "evaluate_candidates": set(),
                "get_candidate_evidence": {"creator_id"}, "get_previous_decisions": {"creator_id"},
                "stage_replacement_proposal": {"creator_id"}}
REQUIRED_ARGS = {"get_candidate_evidence": {"creator_id"}, "stage_replacement_proposal": {"creator_id"}}
PHASES = {"get_campaign_requirements": "reading_campaign", "evaluate_candidates": "checking_candidates",
          "get_previous_decisions": "reviewing_memory", "get_candidate_evidence": "inspecting_evidence",
          "stage_replacement_proposal": "preparing_proposal"}
EVALUATION_QUERIES = ["Q00_revision", "Q01_campaign", "Q02_creators", "Q03_availability", "Q04_agreements",
                      "Q04b_client_competitors", "Q05_audits", "Q06_decisions", "Q07a_source_meta"]
FATAL_CODES = {"GRAPH_UNAVAILABLE", "QUERY_TIMEOUT", "STALE_CONTEXT", "NO_SEED_DATA", "RUN_NOT_ACTIVE"}


@dataclass
class AgentServices:
    client: GraphClient
    evaluation: EvaluationService
    decisions: DecisionService
    proposals: ProposalService


@dataclass
class RunContext:
    run_id: str
    session_id: str
    campaign_id: str
    revision: int
    as_of_ms: int
    evaluation: Evaluation | None = None
    campaign: CampaignRec | None = None
    requirements_read: bool = False
    decisions_read: bool = False
    evidence_seen: set[str] = field(default_factory=set)
    staged: dict | None = None
    tool_calls: int = 0


@dataclass
class ToolOutcome:
    ok: bool
    content: dict
    error_code: str | None = None
    fatal: AppError | None = None
    record_ids: list[str] = field(default_factory=list)
    query_ids: list[str] = field(default_factory=list)


def _error(code: str, message: str) -> ToolOutcome:
    return ToolOutcome(False, {"error": {"code": code, "message": message}}, code)


def excerpt(text: str | None) -> str:
    body = text or ""
    if "## Record" in body:
        body = body.split("## Record", 1)[1]
    return " ".join(body.split())[:EXCERPT_CHARS]


def compact_evaluation(evaluation: Evaluation) -> dict:
    groups: dict[str, list] = {"eligible": [], "excluded_by_memory": [], "needs_information": [], "ineligible": []}
    for c in evaluation.candidates:
        codes = [ch.reason_code for ch in c.checks if ch.result in ("fail", "unknown") and ch.reason_code]
        if c.status == "eligible":
            groups["eligible"].append({"creator_id": c.creator_id, "name": c.name, "rank": c.rank,
                                       "fee": format_inr(c.fee_paise), "completed_campaigns": c.completed_campaign_count})
        else:
            key = "needs_information" if c.status == "unknown" else c.status
            groups[key].append({"creator_id": c.creator_id, "name": c.name, "reason_codes": codes})
    return {"context_revision": evaluation.context_revision, "as_of": ms_to_ist(evaluation.as_of_ms),
            "recommended_creator_ids": evaluation.recommended_creator_ids, **groups,
            "note": "Statuses and ranking are final rule results. Do not change them."}


def _validate(name: str, raw_args) -> tuple[dict | None, ToolOutcome | None]:
    if name not in TOOL_NAMES:
        return None, _error("UNKNOWN_TOOL", f"Unknown tool. Allowed tools: {', '.join(TOOL_NAMES)}.")
    args = {} if raw_args is None else raw_args
    if not isinstance(args, dict):
        return None, _error("INVALID_INPUT", "Tool arguments must be a JSON object.")
    extra = set(args) - ALLOWED_ARGS[name]
    if extra:
        return None, _error("UNKNOWN_TOOL_ARGUMENT", f"Unexpected argument(s): {', '.join(sorted(extra))}.")
    missing = REQUIRED_ARGS.get(name, set()) - set(args)
    if missing:
        return None, _error("INVALID_INPUT", f"Missing argument(s): {', '.join(sorted(missing))}.")
    creator = args.get("creator_id")
    if creator is not None and (not isinstance(creator, str) or not CREATOR_ID.match(creator)):
        return None, _error("INVALID_INPUT", "creator_id must be an id returned by evaluate_candidates (cr_ and two digits).")
    return args, None


async def execute_tool(name: str, raw_args, ctx: RunContext, services: AgentServices) -> ToolOutcome:
    args, problem = _validate(name, raw_args)
    if problem:
        return problem
    try:
        current = await read_revision(services.client)
        if current != ctx.revision:
            raise AppError("STALE_CONTEXT", "The campaign information changed during this run. Run it again.", 409,
                           details={"run_revision": ctx.revision, "current_revision": current})
        return await HANDLERS[name](args, ctx, services)
    except AppError as exc:
        if exc.code in FATAL_CODES:
            return ToolOutcome(False, {"error": {"code": exc.code, "message": exc.message}}, exc.code, fatal=exc)
        return _error(exc.code, exc.message)


async def _requirements(_args, ctx: RunContext, s: AgentServices) -> ToolOutcome:
    detail = await campaign_detail(s.client, ctx.campaign_id)
    c = detail.campaign
    ctx.requirements_read = True
    return ToolOutcome(True, {
        "campaign_id": c.id, "title": c.title, "client_brand": f"{c.client_brand_name} ({c.client_brand_id})",
        "channel": c.channel, "deliverable": c.deliverable, "language": c.language, "category": c.category,
        "currency": c.currency, "replacement_budget": format_inr(c.budget_paise),
        "delivery_window": f"{ms_to_ist(c.start_ms)} – {ms_to_ist(c.end_ms)}",
        "dropped_out_creator": f"{c.dropped_creator_name} ({c.dropped_creator_id})",
        "replacement_slot": "open" if not c.approved_proposal_id else f"already filled by {c.approved_proposal_id}",
        "brief_source_ids": [b.id for b in detail.brief_sources], "context_revision": detail.current_revision,
    }, record_ids=[c.id, c.client_brand_id, c.dropped_creator_id],
        query_ids=["Q13_campaign_list", "Q01_campaign", "Q07_sources_by_id"])


async def _evaluate(_args, ctx: RunContext, s: AgentServices) -> ToolOutcome:
    evaluation, gctx = await s.evaluation.consistent_evaluate(ctx.campaign_id, ctx.revision)
    ctx.evaluation, ctx.campaign = evaluation, gctx.campaign
    return ToolOutcome(True, compact_evaluation(evaluation), record_ids=[c.creator_id for c in evaluation.candidates],
                       query_ids=EVALUATION_QUERIES)


def _candidate(ctx: RunContext, creator_id: str):
    if ctx.evaluation is None:
        raise AppError("PREREQUISITE_MISSING", "Call evaluate_candidates first.", 409)
    cand = next((c for c in ctx.evaluation.candidates if c.creator_id == creator_id), None)
    if cand is None:
        raise AppError("INVALID_INPUT", f"{creator_id} is not in this evaluation.", 422)
    return cand


async def _evidence(args, ctx: RunContext, s: AgentServices) -> ToolOutcome:
    cand = _candidate(ctx, args["creator_id"])
    problem_checks = {ch.name for ch in cand.checks if ch.result in ("fail", "unknown")}
    paths = [p for p in ctx.evaluation.evidence_paths if p.id in cand.evidence_path_ids]
    # Paths that explain a failure or an unknown come first, so the cap never hides them.
    paths.sort(key=lambda p: p.check not in problem_checks)
    priority = [sid for ch in cand.checks if ch.result in ("fail", "unknown") for sid in ch.source_ids]
    rest = [sid for ch in cand.checks for sid in ch.source_ids] + [sid for p in paths for sid in p.source_ids]
    ordered = list(dict.fromkeys(priority + rest))[:MAX_EVIDENCE_SOURCES]
    docs = {d["id"]: d for d in await load_sources(s.client, ordered)}
    ctx.evidence_seen.add(cand.creator_id)
    return ToolOutcome(True, {
        "creator_id": cand.creator_id, "name": cand.name, "status": cand.status, "rank": cand.rank,
        "fee": format_inr(cand.fee_paise) if cand.fee_paise is not None else None,
        "checks": [{"check": ch.name, "result": ch.result,
                    **({"reason_code": ch.reason_code, "detail": ch.detail}
                       if ch.result in ("fail", "unknown") else {})} for ch in cand.checks],
        "paths": [{"id": p.id, "nodes": [n.name for n in p.nodes], "relationships": [e.type for e in p.edges]}
                  for p in paths[:4]],
        "sources": [{"id": sid, "title": docs[sid]["title"], "version": docs[sid]["version"],
                     "observed": ms_to_ist(docs[sid]["observed_at_ms"]) if docs[sid]["observed_at_ms"] else None,
                     "untrusted_source_text": excerpt(docs[sid]["text"])} for sid in ordered if sid in docs],
    }, record_ids=[cand.creator_id] + [n for p in paths for n in p.node_ids], query_ids=["Q07_sources_by_id"])


async def _decisions(args, ctx: RunContext, s: AgentServices) -> ToolOutcome:
    rows = await s.decisions.list(campaign_id=ctx.campaign_id, creator_id=args.get("creator_id"))
    ctx.decisions_read = True

    def scope(d):
        if d["scope_type"] == "campaign" and d["scope_id"] == ctx.campaign_id:
            return "this campaign"
        return f"{d['scope_type']} {d['scope_id']}"

    return ToolOutcome(True, {
        "decisions": [{"decision_id": d["id"], "action": d["action"], "creator": f"{d['creator_name']} ({d['creator_id']})",
                       "scope": scope(d), "state": d["state"], "untrusted_reason": (d["reason"] or "")[:160]}
                      for d in rows[:10]],
        "note": "Active rejections are already applied by evaluate_candidates.",
    }, record_ids=[d["id"] for d in rows[:10]], query_ids=["Q13_decisions"])


async def _stage(args, ctx: RunContext, s: AgentServices) -> ToolOutcome:
    cand = _candidate(ctx, args["creator_id"])
    if cand.status != "eligible":
        raise AppError("CANDIDATE_NOT_ELIGIBLE", f"{cand.name} is {cand.status}; only eligible creators can be "
                       "proposed.", 409)
    if cand.creator_id not in ctx.evidence_seen:
        raise AppError("EVIDENCE_REQUIRED", f"Call get_candidate_evidence for {cand.creator_id} first.", 409)
    if ctx.staged and ctx.staged["creator_id"] != cand.creator_id:
        raise AppError("ALREADY_STAGED", f"This run already staged {ctx.staged['id']}; a campaign has one "
                       "replacement slot.", 409)
    proposal = await s.proposals.stage(run_id=ctx.run_id, creator_id=cand.creator_id, evaluation=ctx.evaluation,
                                       campaign=ctx.campaign)
    ctx.staged = proposal
    return ToolOutcome(True, {
        "proposal_id": proposal["id"], "creator_id": cand.creator_id, "status": "draft_pending_human_approval",
        "note": "Only the operator can approve this draft in the app. Nothing was booked, paid or sent.",
    }, record_ids=[proposal["id"], cand.creator_id], query_ids=["Q09_stage_draft"])


HANDLERS = {"get_campaign_requirements": _requirements, "evaluate_candidates": _evaluate,
            "get_candidate_evidence": _evidence, "get_previous_decisions": _decisions,
            "stage_replacement_proposal": _stage}
