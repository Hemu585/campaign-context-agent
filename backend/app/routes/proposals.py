"""Proposal reads and the explicit human approval action (journey E). Drafts are created only by
the agent's staging tool; there is no route that stages, and chat text can never approve."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.models.responses import ApprovalResult, Proposal
from app.routes.errors import ERROR_RESPONSES
from app.security import write_guard

router = APIRouter(prefix="/api", tags=["proposals"], responses=ERROR_RESPONSES)
ProposalId = Path(pattern=r"^prop_[a-f0-9]{16}$")


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


@router.get("/proposals", response_model=list[Proposal])
async def list_proposals(request: Request, campaign_id: str | None = Query(default=None, pattern=r"^[a-z0-9_]{1,64}$")):
    return await request.app.state.proposals.list(campaign_id)


@router.get("/proposals/{proposal_id}", response_model=Proposal)
async def get_proposal(request: Request, proposal_id: str = ProposalId):
    return await request.app.state.proposals.get(proposal_id)


@router.post("/proposals/{proposal_id}/approve", response_model=ApprovalResult)
async def approve(request: Request, body: ApproveBody, proposal_id: str = ProposalId,
                  key: uuid.UUID = Depends(write_guard)):
    return await request.app.state.proposals.approve(proposal_id, body.expected_revision, str(key))
