"""Revision-consistent evaluation of one campaign (ARCHITECTURE "Revisions and consistent reads").

Read revision R, read every needed graph fact, read R again. If it moved, retry once,
otherwise fail STALE_CONTEXT. The evaluation records R and the server-owned as_of.
"""

from __future__ import annotations

from app.clock import business_now_ms
from app.config import Settings
from app.db.client import GraphClient
from app.errors import AppError
from app.models.api import Evaluation, SourceMeta, UnknownItem
from app.models.domain import CampaignContext
from app.services.graph_reads import load_campaign_context, read_revision
from app.services.rules import evaluate_context, recommended_ids


class EvaluationService:
    def __init__(self, client: GraphClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def consistent_context(self, campaign_id: str) -> CampaignContext:
        for _ in range(2):
            before = await read_revision(self.client)
            ctx = await load_campaign_context(self.client, campaign_id)
            after = await read_revision(self.client)
            if before == after == ctx.revision:
                return ctx
        raise AppError("STALE_CONTEXT", "The campaign information changed while it was being read. Run it again.",
                       409, retryable=True, details={"campaign_id": campaign_id})

    async def consistent_evaluate(self, campaign_id: str, expected_revision: int
                                  ) -> tuple[Evaluation, CampaignContext]:
        """Evaluate and insist the result was read at the revision the caller is acting on."""
        evaluation, ctx = await self.evaluate(campaign_id)
        if evaluation.context_revision != expected_revision:
            raise AppError("STALE_CONTEXT", "The campaign information changed. Run it again.", 409, retryable=True,
                           details={"expected_revision": expected_revision,
                                    "current_revision": evaluation.context_revision})
        return evaluation, ctx

    async def evaluate(self, campaign_id: str, *, as_of_ms: int | None = None
                       ) -> tuple[Evaluation, CampaignContext]:
        as_of = business_now_ms(self.settings) if as_of_ms is None else as_of_ms
        ctx = await self.consistent_context(campaign_id)
        candidates, paths = evaluate_context(ctx, as_of, self.settings.freshness_days)
        referenced = sorted({s for c in candidates for ch in c.checks for s in ch.source_ids}
                            | {s for p in paths for s in p.source_ids}
                            | {h.source_id for c in candidates for h in c.completed_campaigns})
        sources = [
            SourceMeta(id=s.id, document_id=s.document_id, version=s.version, title=s.title, kind=s.kind,
                       observed_at_ms=s.observed_at_ms, verified=s.verified, synthetic=s.synthetic,
                       superseded=s.superseded)
            for sid in referenced if (s := ctx.sources.get(sid)) is not None
        ]
        unknowns = [
            UnknownItem(creator_id=c.creator_id, name=c.name, check=ch.name, reason_code=ch.reason_code,
                        detail=ch.detail)
            for c in candidates for ch in c.checks if ch.result == "unknown"
        ]
        evaluation = Evaluation(
            campaign_id=campaign_id, context_revision=ctx.revision, as_of_ms=as_of, candidates=candidates,
            recommended_creator_ids=recommended_ids(candidates), unknowns=unknowns, sources=sources,
            evidence_paths=paths,
        )
        return evaluation, ctx
