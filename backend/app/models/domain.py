"""Immutable records parsed from graph query rows. The rule engine consumes only these."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceRec:
    id: str
    document_id: str | None
    version: int | None
    kind: str | None
    title: str | None
    subject_id: str | None
    observed_at_ms: int | None
    verified: bool
    checksum: str | None
    fact_hash: str | None
    synthetic: bool
    superseded_by: tuple[str, ...] = ()

    @property
    def superseded(self) -> bool:
        return bool(self.superseded_by)


@dataclass(frozen=True)
class CampaignRec:
    id: str
    title: str
    brand_id: str
    brand_name: str
    channel: str | None
    deliverable: str | None
    language: str | None
    category: str | None
    currency: str | None
    budget_paise: int | None
    start_ms: int | None
    end_ms: int | None
    status: str | None
    approved_proposal_id: str | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ParticipationRec:
    creator_id: str
    creator_name: str | None
    status: str | None
    source_id: str | None


@dataclass(frozen=True)
class CreatorRec:
    id: str
    name: str
    active: bool | None


@dataclass(frozen=True)
class OfferRec:
    id: str
    creator_id: str
    channel: str | None
    deliverable: str | None
    language: str | None
    category: str | None
    fee_paise: int | None
    currency: str | None
    valid_from_ms: int | None
    valid_to_ms: int | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class AvailabilityRec:
    id: str
    creator_id: str
    start_ms: int | None
    end_ms: int | None
    status: str | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgreementRec:
    id: str
    creator_id: str
    counterparty_brand_id: str | None
    counterparty_name: str | None
    exclusive: bool | None
    channel: str | None
    category: str | None
    start_ms: int | None
    end_ms: int | None
    status: str | None
    is_direct_competitor: bool
    competitor_edge_source_ids: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class AuditRec:
    id: str
    kind: str | None
    subject_id: str
    coverage_start_ms: int | None
    coverage_end_ms: int | None
    complete: bool | None
    listed_ids: tuple[str, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompetitorRec:
    brand_id: str
    name: str | None
    source_id: str | None


@dataclass(frozen=True)
class RevocationRec:
    id: str
    as_of_ms: int | None


@dataclass(frozen=True)
class DecisionRec:
    id: str
    creator_id: str
    scope_type: str
    scope_id: str
    reason: str | None
    as_of_ms: int | None
    created_at_ms: int | None
    expires_at_ms: int | None
    made_in_campaign_id: str | None
    revocations: tuple[RevocationRec, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class CompletedRec:
    campaign_id: str
    source_id: str | None


@dataclass(frozen=True)
class CampaignContext:
    """Everything the rules need for one campaign, read at one workspace revision."""

    revision: int
    campaign: CampaignRec
    participants: tuple[ParticipationRec, ...]
    creators: tuple[CreatorRec, ...]
    offers: dict[str, tuple[OfferRec, ...]]
    completed: dict[str, tuple[CompletedRec, ...]]
    availability: dict[str, tuple[AvailabilityRec, ...]]
    agreements: dict[str, tuple[AgreementRec, ...]]
    client_competitors: tuple[CompetitorRec, ...]
    agreement_audits: dict[str, tuple[AuditRec, ...]]
    competitor_audits: tuple[AuditRec, ...]
    decisions: dict[str, tuple[DecisionRec, ...]]
    sources: dict[str, SourceRec]
    brand_names: dict[str, str] = field(default_factory=dict)
