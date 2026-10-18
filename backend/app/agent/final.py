"""Final answer contract (approach 2A): schema, validation against the server evaluation, and
backend-rendered summary.

The model only SELECTS among server facts: an outcome, a prefix of the server ranking, and
{creator_id, reason_code} pairs that must exist among that creator's actual checks. Every
factual sentence shown to the operator is rendered here from the validated fields and the
evaluation's own check details. Unrestricted model prose is never displayed as evidence.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.api import Evaluation
from app.money import format_inr
from app.timeutil import ms_to_ist

Outcome = Literal["recommendation", "explanation", "no_eligible_candidate", "clarification_needed"]
ClarificationCode = Literal["none", "AMBIGUOUS_CAMPAIGN", "UNSUPPORTED_MULTI_SLOT", "UNSUPPORTED_CURRENCY",
                            "UNSUPPORTED_REQUEST"]

# Written inline (no $ref) so Ollama's grammar conversion handles it directly.
FINAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string",
                    "enum": ["recommendation", "explanation", "no_eligible_candidate", "clarification_needed"]},
        "recommended_creator_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "highlighted_reasons": {
            "type": "array", "maxItems": 6,
            "items": {"type": "object",
                      "properties": {"creator_id": {"type": "string"}, "reason_code": {"type": "string"}},
                      "required": ["creator_id", "reason_code"], "additionalProperties": False}},
        "clarification_code": {"type": "string",
                               "enum": ["none", "AMBIGUOUS_CAMPAIGN", "UNSUPPORTED_MULTI_SLOT",
                                        "UNSUPPORTED_CURRENCY", "UNSUPPORTED_REQUEST"]},
    },
    "required": ["outcome", "recommended_creator_ids", "highlighted_reasons", "clarification_code"],
    "additionalProperties": False,
}

CLARIFICATIONS = {
    "AMBIGUOUS_CAMPAIGN": "Your request seems to be about a different campaign. Select that campaign first, or "
                          "confirm that you mean {title}.",
    "UNSUPPORTED_MULTI_SLOT": "This prototype replaces exactly one creator per campaign. Ask for one replacement.",
    "UNSUPPORTED_CURRENCY": "Budgets and fees in this workspace are in INR only.",
    "UNSUPPORTED_REQUEST": "I can find and propose one replacement creator for {title}, or explain why candidates "
                           "are excluded. Please rephrase within that scope.",
}


class HighlightedReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creator_id: str
    reason_code: str


class FinalAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Outcome
    recommended_creator_ids: list[str] = Field(max_length=3)
    highlighted_reasons: list[HighlightedReason] = Field(max_length=6)
    clarification_code: ClarificationCode


def parse_final(content: str) -> tuple[FinalAnswer | None, list[str]]:
    try:
        return FinalAnswer.model_validate(json.loads(content)), []
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        kind = "MALFORMED_FINAL_JSON" if isinstance(exc, json.JSONDecodeError) else "FINAL_JSON_SCHEMA_MISMATCH"
        return None, [kind]


def _allowed_codes(cand) -> set[str]:
    codes = {ch.reason_code for ch in cand.checks if ch.result in ("fail", "unknown") and ch.reason_code}
    return codes | {ch.name for ch in cand.checks if ch.result == "pass"}


def validate_final(fa: FinalAnswer, evaluation: Evaluation | None, staged: dict | None) -> list[str]:
    problems: list[str] = []
    if fa.outcome == "clarification_needed":
        if fa.clarification_code == "none":
            problems.append("CLARIFICATION_CODE_REQUIRED")
        if fa.recommended_creator_ids:
            problems.append("NO_RECOMMENDATIONS_WITH_CLARIFICATION")
    elif fa.clarification_code != "none":
        problems.append("CLARIFICATION_CODE_MUST_BE_none")
    if evaluation is None:
        if fa.outcome != "clarification_needed":
            problems.append("EVALUATION_REQUIRED")
        if fa.highlighted_reasons:
            problems.append("REASONS_NEED_AN_EVALUATION")
        return problems
    by_id = {c.creator_id: c for c in evaluation.candidates}
    eligible = [c.creator_id for c in evaluation.candidates if c.status == "eligible"]
    server = evaluation.recommended_creator_ids
    rec = fa.recommended_creator_ids
    if rec != server[: len(rec)]:
        problems.append(f"RECOMMENDATIONS_MUST_BE_A_PREFIX_OF {server}")
    if fa.outcome == "recommendation":
        if not eligible:
            problems.append("NO_ELIGIBLE_CREATOR_USE_no_eligible_candidate")
        elif not rec:
            problems.append("RECOMMENDATION_LIST_EMPTY")
        if eligible and staged is None:
            problems.append("STAGE_REQUIRED")
    if fa.outcome == "no_eligible_candidate":
        if eligible:
            problems.append(f"ELIGIBLE_CREATORS_EXIST {eligible}")
        if rec:
            problems.append("NO_RECOMMENDATIONS_WITHOUT_ELIGIBLE_CREATORS")
    for hr in fa.highlighted_reasons:
        cand = by_id.get(hr.creator_id)
        if cand is None:
            problems.append(f"UNKNOWN_CREATOR {hr.creator_id}")
        elif hr.reason_code not in _allowed_codes(cand):
            problems.append(f"UNSUPPORTED_REASON {hr.creator_id} {hr.reason_code}")
    return problems


def render_final(fa: FinalAnswer, evaluation: Evaluation | None, staged: dict | None, *, campaign_id: str,
                 title: str) -> dict:
    """Backend-written result object; numbers and facts come from the evaluation, not model prose."""
    by_id = {c.creator_id: c for c in evaluation.candidates} if evaluation else {}
    unknowns = ([{"creator_id": u.creator_id, "name": u.name, "check": u.check, "reason_code": u.reason_code,
                  "detail": u.detail} for u in evaluation.unknowns] if evaluation else [])
    lines: list[str] = []
    reasons: list[dict] = []
    outcome = fa.outcome
    if outcome == "explanation" and evaluation is not None and not any(
            c.status == "eligible" for c in evaluation.candidates):
        # With nobody eligible, the operator's key fact is that nothing qualifies. The backend states it
        # whatever the model called its answer (validation already stops it recommending anyone).
        outcome = "no_eligible_candidate"
    if outcome == "clarification_needed":
        lines.append(CLARIFICATIONS[fa.clarification_code].format(title=title))
    elif outcome == "no_eligible_candidate":
        lines.append(f"No creator passes every check for {title} on the current evidence, so nothing was proposed.")
    if fa.recommended_creator_ids:
        parts = []
        for i, cid in enumerate(fa.recommended_creator_ids, start=1):
            c = by_id[cid]
            parts.append(f"{i}. {c.name} ({cid}), {format_inr(c.fee_paise)}, "
                         f"{c.completed_campaign_count} completed campaign{'s' if c.completed_campaign_count != 1 else ''}")
        lines.append(f"Recommended for {title} (ranked by fee, then completed campaigns, then ID): "
                     + "; ".join(parts) + ".")
    if staged is not None and fa.outcome != "clarification_needed":
        name = by_id[staged["creator_id"]].name if staged["creator_id"] in by_id else staged["creator_id"]
        lines.append(f"Draft proposal {staged['id']} for {name} is ready for your review. It is not approved, "
                     "and nothing has been booked, paid or sent.")
    for hr in fa.highlighted_reasons:
        c = by_id[hr.creator_id]
        check = next((ch for ch in c.checks if ch.reason_code == hr.reason_code), None) or \
            next(ch for ch in c.checks if ch.name == hr.reason_code)
        reasons.append({"creator_id": c.creator_id, "name": c.name, "check": check.name, "result": check.result,
                        "reason_code": check.reason_code, "detail": check.detail, "source_ids": check.source_ids})
        lines.append(check.detail if check.detail.startswith(c.name) else f"{c.name}: {check.detail}")
    if unknowns and fa.outcome != "clarification_needed":
        names = sorted({f"{u['name']}" for u in unknowns})
        lines.append("Needs information (not cleared): " + ", ".join(names) + ".")
    return {
        "status": "needs_clarification" if fa.outcome == "clarification_needed" else "completed",
        "outcome": outcome,
        "campaign_id": campaign_id,
        "context_revision": evaluation.context_revision if evaluation else None,
        "as_of_ms": evaluation.as_of_ms if evaluation else None,
        "as_of_display": ms_to_ist(evaluation.as_of_ms) if evaluation else None,
        "recommended_creator_ids": fa.recommended_creator_ids,
        "proposal_id": staged["id"] if staged is not None and fa.outcome != "clarification_needed" else None,
        # One statement per line; the UI shows the text with its line breaks.
        "summary": "\n".join(lines),
        "reasons": reasons,
        "unknowns": unknowns,
        "clarification_code": fa.clarification_code,
    }
