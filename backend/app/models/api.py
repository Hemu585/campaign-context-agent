"""API objects shared by the rule engine, routes and the generated frontend types.

Field names follow docs/API_CONTRACTS.md. Additive fields (``facts``, ``nodes``,
``not_applicable``) are documented design decisions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CheckName = Literal["participation", "offer_match", "quote_validity", "budget", "availability",
                    "agreement_audit", "competitor_audit", "exclusivity", "memory"]
CheckResult = Literal["pass", "fail", "unknown", "not_applicable"]
CandidateStatus = Literal["eligible", "ineligible", "unknown", "excluded_by_memory"]


class Check(BaseModel):
    name: CheckName
    result: CheckResult
    reason_code: str | None = None
    detail: str
    source_ids: list[str] = []
    facts: dict[str, Any] = {}


class PathNode(BaseModel):
    id: str
    label: str
    name: str


class PathEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: str = Field(alias="from")
    type: str
    to: str
    source_ids: list[str] = []


class EvidencePath(BaseModel):
    id: str
    check: CheckName
    creator_id: str
    node_ids: list[str]
    nodes: list[PathNode]
    edges: list[PathEdge]
    source_ids: list[str]


class CompletedCampaign(BaseModel):
    """A completed campaign counted for ranking ties, with the source that verifies it."""
    campaign_id: str
    source_id: str


class CandidateEvaluation(BaseModel):
    creator_id: str
    name: str
    status: CandidateStatus
    fee_paise: int | None
    completed_campaign_count: int
    completed_campaigns: list[CompletedCampaign] = []
    rank: int | None
    checks: list[Check]
    active_rejection_ids: list[str] = []
    evidence_path_ids: list[str] = []
    failed_checks: list[str] = []
    unknown_checks: list[str] = []


class UnknownItem(BaseModel):
    creator_id: str
    name: str
    check: CheckName
    reason_code: str | None
    detail: str


class SourceMeta(BaseModel):
    id: str
    document_id: str | None
    version: int | None
    title: str | None
    kind: str | None
    observed_at_ms: int | None
    verified: bool
    synthetic: bool
    superseded: bool


class Evaluation(BaseModel):
    campaign_id: str
    context_revision: int
    as_of_ms: int
    mode: Literal["rule_check_no_ai", "agent_run"] = "rule_check_no_ai"
    candidates: list[CandidateEvaluation]
    recommended_creator_ids: list[str]
    unknowns: list[UnknownItem]
    sources: list[SourceMeta]
    evidence_paths: list[EvidencePath]
