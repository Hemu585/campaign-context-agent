"""Response models for every route. FastAPI validates real responses against them, and the
OpenAPI schema generated from them is the source of the frontend's TypeScript types
(`frontend/openapi.json` -> `src/api/schema.d.ts`). A drift test keeps the two in step.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.api import CandidateEvaluation, Evaluation, EvidencePath, SourceMeta


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Bootstrap(_Out):
    nonce: str
    workspace_id: str | None
    context_revision: int | None
    synthetic_data: bool
    demo_mode: bool
    as_of_ms: int
    clock: str
    model: str


class HealthBackend(_Out):
    version: str
    demo_mode: bool
    clock: str
    as_of_ms: int


class HealthGraph(_Out):
    reachable: bool
    graph: str
    seeded: bool
    seed_status: str | None
    dataset_version: str | None
    revision: int | None


class HealthModel(_Out):
    reachable: bool
    installed: bool
    tag: str
    digest: str | None
    server_version: str | None
    detail: str


class Health(_Out):
    status: Literal["ok", "degraded"]
    backend: HealthBackend
    graph: HealthGraph
    model: HealthModel
    synthetic_data: bool


class SessionSummary(_Out):
    id: str
    title: str
    created_at_ms: int
    run_count: int


class Message(_Out):
    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at_ms: int
    run_id: str | None = None


class RunRef(_Out):
    id: str
    status: str
    phase: str | None = None
    campaign_id: str
    created_at_ms: int
    proposal_id: str | None = None


class SessionDetail(_Out):
    id: str
    title: str
    created_at_ms: int
    messages: list[Message]
    runs: list[RunRef]


class TraceEvent(_Out):
    seq: int
    type: Literal["model", "tool", "validation"]
    tool: str | None = None
    args: dict[str, Any] | None = None
    status: str | None = None
    error_code: str | None = None
    elapsed_ms: int | None = None
    record_ids: list[str] | None = None
    query_ids: list[str] | None = None
    phase: str | None = None
    purpose: str | None = None
    turn: int | None = None
    gen_tokens: int | None = None
    tool_calls: list[str] | None = None
    offered_tools: list[str] | None = None
    problems: list[str] | None = None


class RunError(_Out):
    code: str
    message: str
    details: dict[str, Any] | None = None


class FinalReason(_Out):
    creator_id: str
    name: str
    check: str
    result: str
    reason_code: str | None
    detail: str
    source_ids: list[str]


class FinalUnknown(_Out):
    creator_id: str
    name: str
    check: str
    reason_code: str | None
    detail: str


class FinalResult(_Out):
    status: Literal["completed", "needs_clarification"]
    outcome: Literal["recommendation", "explanation", "no_eligible_candidate", "clarification_needed"]
    campaign_id: str
    context_revision: int | None
    as_of_ms: int | None
    as_of_display: str | None
    recommended_creator_ids: list[str]
    proposal_id: str | None
    summary: str
    reasons: list[FinalReason]
    unknowns: list[FinalUnknown]
    clarification_code: str


class Run(_Out):
    id: str
    session_id: str
    status: Literal["queued", "running", "completed", "needs_clarification", "failed", "cancelled", "interrupted"]
    phase: str | None = None
    campaign_id: str
    as_of_ms: int
    context_revision: int
    model: str | None = None
    model_digest: str | None = None
    created_at_ms: int
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    message_id: str | None = None
    proposal_id: str | None = None
    tool_calls: int | None = None
    trace: list[TraceEvent] | None = None
    evaluation: Evaluation | None = None
    final: FinalResult | None = None
    error: RunError | None = None
    current_revision: int | None = None
    is_stale: bool = False
    active: bool = False


class RunEvidence(_Out):
    run_id: str
    campaign_id: str
    context_revision: int
    as_of_ms: int
    evidence_paths: list[EvidencePath]
    sources: list[SourceMeta]


class SnapshotCampaign(_Out):
    id: str
    title: str
    client_brand_id: str
    client_brand_name: str
    channel: str | None
    deliverable: str | None
    language: str | None
    category: str | None
    currency: str | None
    budget_paise: int | None
    start_ms: int | None
    end_ms: int | None


class SnapshotSource(_Out):
    id: str
    title: str | None
    version: int | None
    observed_at_ms: int | None
    verified: bool
    synthetic: bool
    excerpt: str


class ProposalSnapshot(_Out):
    snapshot_version: int
    campaign: SnapshotCampaign
    candidate: CandidateEvaluation
    ranking_inputs: dict[str, Any]
    recommended_creator_ids: list[str]
    evidence_paths: list[EvidencePath]
    sources: list[SnapshotSource]
    as_of_ms: int
    context_revision: int


class Proposal(_Out):
    id: str
    campaign_id: str
    campaign_title: str
    creator_id: str
    creator_name: str
    run_id: str
    run_status: str
    status: Literal["draft", "approved"]
    context_revision: int
    current_revision: int
    is_stale: bool
    slot_filled: bool
    approvable: bool
    unusable_reason: str | None
    as_of_ms: int
    created_at_ms: int
    approved_at_ms: int | None
    approved_revision: int | None
    decision_id: str | None
    snapshot: ProposalSnapshot | None


class ApprovalResult(_Out):
    decision_id: str
    proposal: Proposal
    replayed: bool
    context_revision: int


class Decision(_Out):
    id: str
    action: Literal["rejected", "revoked", "approved"]
    state: str
    is_active: bool
    creator_id: str | None
    creator_name: str | None
    campaign_id: str | None
    campaign_title: str | None
    scope_type: str | None
    scope_id: str | None
    reason: str | None
    as_of_ms: int | None
    created_at_ms: int | None
    expires_at_ms: int | None
    source_ids: list[str]
    revoked_by_id: str | None
    revokes_id: str | None
    proposal_id: str | None
    session_id: str | None


class SourceDoc(_Out):
    id: str
    document_id: str | None
    version: int | None
    kind: str | None
    title: str | None
    subject_id: str | None
    text: str
    observed_at_ms: int | None
    verified: bool
    synthetic: bool
    checksum: str | None
    editor: str | None
    created_at_ms: int | None
    superseded_by: list[str]
    supersedes: list[str]
    fictional_label: str


class EditableAgreement(_Out):
    id: str
    creator_id: str
    creator_name: str
    counterparty_brand_id: str | None
    counterparty_name: str | None
    exclusive: bool | None
    channel: str | None
    category: str | None
    start_ms: int | None
    end_ms: int | None
    status: str | None
    source_id: str
    version: int
    synthetic: bool


class EditableAvailability(_Out):
    id: str
    creator_id: str
    creator_name: str
    start_ms: int | None
    end_ms: int | None
    status: str | None
    source_id: str
    version: int
    synthetic: bool


class EditableFacts(_Out):
    demo_mode: bool
    agreements: list[EditableAgreement]
    availability: list[EditableAvailability]


class EditResult(_Out):
    fact_type: Literal["agreement", "availability"]
    fact: dict[str, Any]
    source_id: str
    supersedes: list[str]
    context_revision: int


class ErrorBody(_Out):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any]


class ErrorEnvelope(_Out):
    error: ErrorBody
