"""Read-only fictional source viewer and the limited synthetic-data editor (journeys B and D)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError
from app.models.responses import EditableFacts, EditResult, SourceDoc
from app.routes.errors import ERROR_RESPONSES
from app.security import write_guard
from app.services.graph_reads import load_sources

router = APIRouter(prefix="/api", tags=["sources", "demo"], responses=ERROR_RESPONSES)


class AgreementChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_at: str | None = None
    end_at: str | None = None
    status: Literal["active", "cancelled"] | None = None
    exclusive: bool | None = None


class AvailabilityChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_at: str | None = None
    end_at: str | None = None
    status: Literal["available", "unavailable"] | None = None


class EditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changes: dict
    reason: str = Field(min_length=1, max_length=300)
    expected_revision: int = Field(ge=1)


@router.get("/sources/{source_id}", response_model=SourceDoc)
async def get_source(request: Request, source_id: str = Path(pattern=r"^src_[a-z0-9_]{1,80}$")):
    rows = await load_sources(request.app.state.graph, [source_id])
    if not rows:
        raise AppError("SOURCE_NOT_FOUND", f"Source {source_id!r} does not exist.", 404)
    doc = rows[0]
    doc["verified"], doc["synthetic"] = bool(doc["verified"]), bool(doc["synthetic"])
    doc["fictional_label"] = "FICTIONAL DEMO DATA"
    return doc


@router.get("/demo/facts", response_model=EditableFacts)
async def editable_facts(request: Request):
    return await request.app.state.edits.list_facts()


@router.patch("/demo/facts/{fact_type}/{fact_id}", response_model=EditResult)
async def edit_fact(request: Request, body: EditBody, fact_type: Literal["agreement", "availability"],
                    fact_id: str = Path(pattern=r"^[a-z0-9_]{1,64}$"), key: uuid.UUID = Depends(write_guard)):
    model = AgreementChanges if fact_type == "agreement" else AvailabilityChanges
    try:
        changes = model.model_validate(body.changes).model_dump(exclude_none=True)
    except ValueError:
        raise AppError("INVALID_INPUT", f"Only these {fact_type} fields can be edited: "
                       f"{', '.join(model.model_fields)}.", 422) from None
    return await request.app.state.edits.edit(fact_type, fact_id, changes, body.reason, body.expected_revision,
                                              str(key))
