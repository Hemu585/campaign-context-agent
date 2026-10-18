"""Decision history, scoped rejections and revocations (journey C)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.models.responses import Decision
from app.routes.errors import ERROR_RESPONSES
from app.security import write_guard

router = APIRouter(prefix="/api", tags=["decisions"], responses=ERROR_RESPONSES)
DecisionId = Path(pattern=r"^dec_[a-f0-9]{16}$")
ID = r"^[a-z0-9_]{1,64}$"


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(pattern=ID)
    creator_id: str = Field(pattern=ID)
    scope_type: Literal["campaign", "brand"] = "campaign"
    reason: str = Field(min_length=1, max_length=500)
    expires_at_ms: int | None = Field(default=None, gt=0)
    expected_revision: int = Field(ge=1)
    session_id: str | None = Field(default=None, pattern=r"^ses_[a-f0-9]{16}$")


class RevokeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)
    expected_revision: int = Field(ge=1)


@router.get("/decisions", response_model=list[Decision])
async def list_decisions(request: Request, campaign_id: str | None = Query(default=None, pattern=ID),
                         creator_id: str | None = Query(default=None, pattern=ID)):
    return await request.app.state.decisions.list(campaign_id=campaign_id, creator_id=creator_id)


@router.post("/decisions/rejections", status_code=201, response_model=Decision)
async def reject(request: Request, body: RejectBody, key: uuid.UUID = Depends(write_guard)):
    return await request.app.state.decisions.reject(
        campaign_id=body.campaign_id, creator_id=body.creator_id, scope_type=body.scope_type, reason=body.reason,
        expires_at_ms=body.expires_at_ms, expected_revision=body.expected_revision, session_id=body.session_id,
        key=str(key))


@router.post("/decisions/{decision_id}/revoke", response_model=Decision)
async def revoke(request: Request, body: RevokeBody, decision_id: str = DecisionId,
                 key: uuid.UUID = Depends(write_guard)):
    return await request.app.state.decisions.revoke(decision_id=decision_id, reason=body.reason,
                                                    expected_revision=body.expected_revision, key=str(key))
