"""Q01-Q07: read one campaign's full decision context from FalkorDB into typed records.

Every creator in the workspace is loaded before any rule runs (no premature LIMIT).
The JSON fixture is never consulted here: if the graph is down the caller gets
GRAPH_UNAVAILABLE (R02, T15).
"""

from __future__ import annotations

from collections import defaultdict

from app.db.client import GraphClient
from app.errors import AppError
from app.models.domain import (
    AgreementRec,
    AuditRec,
    AvailabilityRec,
    CampaignContext,
    CampaignRec,
    CompetitorRec,
    CompletedRec,
    CreatorRec,
    DecisionRec,
    OfferRec,
    ParticipationRec,
    RevocationRec,
    SourceRec,
)


def _t(values) -> tuple[str, ...]:
    return tuple(sorted(v for v in (values or []) if v is not None))


def source_from_row(r: dict) -> SourceRec:
    return SourceRec(
        id=r["id"], document_id=r.get("document_id"), version=r.get("version"), kind=r.get("kind"),
        title=r.get("title"), subject_id=r.get("subject_id"), observed_at_ms=r.get("observed_at_ms"),
        verified=bool(r.get("verified")), checksum=r.get("checksum"), fact_hash=r.get("fact_hash"),
        synthetic=bool(r.get("synthetic")), superseded_by=_t(r.get("superseded_by")),
    )


async def read_revision(client: GraphClient) -> int:
    rows = await client.ro_query("Q00_revision")
    if not rows or rows[0]["seed_status"] != "complete":
        raise AppError("NO_SEED_DATA", "The graph has no completed seed. Run `python -m app.cli seed` first.", 503)
    return int(rows[0]["revision"])


async def load_campaign_context(client: GraphClient, campaign_id: str) -> CampaignContext:
    params = {"campaign_id": campaign_id}
    q1 = await client.ro_query("Q01_campaign", params)
    if not q1:
        raise AppError("CAMPAIGN_NOT_FOUND", f"Campaign {campaign_id!r} does not exist in this workspace.", 404)
    c = q1[0]
    campaign = CampaignRec(
        id=c["id"], title=c["title"], brand_id=c["brand_id"], brand_name=c["brand_name"],
        channel=c["channel"], deliverable=c["deliverable"], language=c["language"], category=c["category"],
        currency=c["currency"], budget_paise=c["budget_paise"], start_ms=c["start_ms"], end_ms=c["end_ms"],
        status=c["status"], approved_proposal_id=c["approved_proposal_id"], source_ids=_t(c["source_ids"]),
    )
    participants = tuple(sorted(
        (ParticipationRec(p["creator_id"], p.get("creator_name"), p.get("status"), p.get("source_id"))
         for p in c["participants"]),
        key=lambda p: (p.creator_id, p.status or ""),
    ))

    creators, offers, completed = [], defaultdict(list), defaultdict(list)
    for r in await client.ro_query("Q02_creators"):
        creators.append(CreatorRec(r["id"], r["name"], r["active"]))
        for o in r["offers"]:
            offers[r["id"]].append(OfferRec(
                id=o["id"], creator_id=r["id"], channel=o.get("channel"), deliverable=o.get("deliverable"),
                language=o.get("language"), category=o.get("category"), fee_paise=o.get("fee_paise"),
                currency=o.get("currency"), valid_from_ms=o.get("valid_from_ms"), valid_to_ms=o.get("valid_to_ms"),
                source_ids=_t(o.get("source_ids")),
            ))
        for h in r["completed"]:
            completed[r["id"]].append(CompletedRec(h["campaign_id"], h.get("source_id")))

    availability = defaultdict(list)
    for r in await client.ro_query("Q03_availability"):
        availability[r["creator_id"]].append(AvailabilityRec(
            r["id"], r["creator_id"], r["start_ms"], r["end_ms"], r["status"], _t(r["source_ids"])))

    agreements = defaultdict(list)
    brand_names = {campaign.brand_id: campaign.brand_name}
    for r in await client.ro_query("Q04_agreements", params):
        if r["counterparty_brand_id"]:
            brand_names[r["counterparty_brand_id"]] = r["counterparty_name"]
        agreements[r["creator_id"]].append(AgreementRec(
            id=r["id"], creator_id=r["creator_id"], counterparty_brand_id=r["counterparty_brand_id"],
            counterparty_name=r["counterparty_name"], exclusive=r["exclusive"], channel=r["channel"],
            category=r["category"], start_ms=r["start_ms"], end_ms=r["end_ms"], status=r["status"],
            is_direct_competitor=r["competitor_edges"] > 0,
            competitor_edge_source_ids=_t(r["competitor_edge_source_ids"]), source_ids=_t(r["source_ids"]),
        ))

    competitors = []
    for r in await client.ro_query("Q04b_client_competitors", params):
        brand_names[r["competitor_id"]] = r["competitor_name"]
        competitors.append(CompetitorRec(r["competitor_id"], r["competitor_name"], r["source_id"]))

    agreement_audits, competitor_audits = defaultdict(list), []
    for r in await client.ro_query("Q05_audits", params):
        audit = AuditRec(r["id"], r["kind"], r["subject_id"], r["coverage_start_ms"], r["coverage_end_ms"],
                         r["complete"], _t(r["listed_ids"]), _t(r["source_ids"]))
        if r["kind"] == "agreements":
            agreement_audits[r["subject_id"]].append(audit)
        else:
            competitor_audits.append(audit)

    decisions = defaultdict(list)
    for r in await client.ro_query("Q06_decisions", params):
        decisions[r["creator_id"]].append(DecisionRec(
            id=r["id"], creator_id=r["creator_id"], scope_type=r["scope_type"], scope_id=r["scope_id"],
            reason=r["reason"], as_of_ms=r["as_of_ms"], created_at_ms=r["created_at_ms"],
            expires_at_ms=r["expires_at_ms"], made_in_campaign_id=r["made_in_campaign_id"],
            revocations=tuple(sorted((RevocationRec(v["id"], v.get("as_of_ms")) for v in r["revocations"]),
                                     key=lambda v: v.id)),
            source_ids=_t(r["source_ids"]),
        ))

    sources = {r["id"]: source_from_row(r) for r in await client.ro_query("Q07a_source_meta")}

    return CampaignContext(
        revision=int(c["revision"]),
        campaign=campaign,
        participants=participants,
        creators=tuple(creators),
        offers={k: tuple(v) for k, v in offers.items()},
        completed={k: tuple(v) for k, v in completed.items()},
        availability={k: tuple(v) for k, v in availability.items()},
        agreements={k: tuple(v) for k, v in agreements.items()},
        client_competitors=tuple(competitors),
        agreement_audits={k: tuple(v) for k, v in agreement_audits.items()},
        competitor_audits=tuple(competitor_audits),
        decisions={k: tuple(v) for k, v in decisions.items()},
        sources=sources,
        brand_names=brand_names,
    )


async def load_sources(client: GraphClient, source_ids: list[str]) -> list[dict]:
    """Full source documents (text included) for the evidence viewer."""
    if not source_ids:
        return []
    return await client.ro_query("Q07_sources_by_id", {"source_ids": sorted(set(source_ids))})
