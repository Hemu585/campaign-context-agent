"""Campaign picker, campaign detail and the diagnostic rule check (no AI)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict

from app.models.api import Evaluation
from app.routes.errors import ERROR_RESPONSES
from app.security import write_guard
from app.services.campaigns import CampaignDetail, CampaignSummary, campaign_detail, list_campaigns

router = APIRouter(prefix="/api", tags=["campaigns"], responses=ERROR_RESPONSES)
CampaignId = Path(pattern=r"^[a-z0-9_]{1,64}$")


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.get("/campaigns", response_model=list[CampaignSummary])
async def get_campaigns(request: Request):
    return await list_campaigns(request.app.state.graph)


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(request: Request, campaign_id: str = CampaignId):
    return await campaign_detail(request.app.state.graph, campaign_id)


@router.post("/campaigns/{campaign_id}/evaluate", response_model=Evaluation)
async def evaluate_campaign(request: Request, body: EmptyBody, campaign_id: str = CampaignId,
                            _key: uuid.UUID = Depends(write_guard)):
    """Deterministic rule check over graph evidence, clearly labelled as not an AI run.

    Read-only: a repeated Idempotency-Key simply returns a freshly calculated result
    (documented exception in API_CONTRACTS).
    """
    evaluation, _ = await request.app.state.evaluation.evaluate(campaign_id)
    return evaluation
