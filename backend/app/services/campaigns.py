"""Campaign summaries and detail for the picker and the campaign panel (R04)."""

from __future__ import annotations

from pydantic import BaseModel

from app.db.client import GraphClient
from app.errors import AppError
from app.services.graph_reads import load_sources


class CampaignSummary(BaseModel):
    id: str
    title: str
    client_brand_id: str
    client_brand_name: str
    channel: str
    deliverable: str
    language: str
    category: str
    currency: str
    budget_paise: int
    start_ms: int
    end_ms: int
    status: str
    dropped_creator_id: str
    dropped_creator_name: str
    approved_proposal_id: str | None = None


class Participant(BaseModel):
    creator_id: str
    creator_name: str | None
    status: str | None
    source_id: str | None


class BriefSource(BaseModel):
    id: str
    title: str | None
    version: int | None
    observed_at_ms: int | None
    verified: bool
    synthetic: bool


class CampaignDetail(BaseModel):
    campaign: CampaignSummary
    participants: list[Participant]
    brief_sources: list[BriefSource]
    current_revision: int


async def list_campaigns(client: GraphClient) -> list[CampaignSummary]:
    rows = await client.ro_query("Q13_campaign_list")
    return [CampaignSummary(**{k: v for k, v in r.items() if k != "revision"}) for r in rows]


async def campaign_detail(client: GraphClient, campaign_id: str) -> CampaignDetail:
    summaries = {c.id: c for c in await list_campaigns(client)}
    if campaign_id not in summaries:
        raise AppError("CAMPAIGN_NOT_FOUND", f"Campaign {campaign_id!r} has no open replacement slot.", 404)
    rows = await client.ro_query("Q01_campaign", {"campaign_id": campaign_id})
    row = rows[0]
    sources = await load_sources(client, row["source_ids"])
    return CampaignDetail(
        campaign=summaries[campaign_id],
        participants=[Participant(**p) for p in row["participants"]],
        brief_sources=[BriefSource(id=s["id"], title=s["title"], version=s["version"],
                                   observed_at_ms=s["observed_at_ms"], verified=bool(s["verified"]),
                                   synthetic=bool(s["synthetic"])) for s in sources],
        current_revision=int(row["revision"]),
    )
