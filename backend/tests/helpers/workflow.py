"""Backend-only workflow helpers: sessions, runs, staged drafts and services wired to one test graph.

The real agent stages drafts through the same ProposalService (Section 3); these helpers let
the mutation gate be proven without depending on model prose.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.db.client import GraphClient
from app.services.decisions import DecisionService
from app.services.demo_edits import DemoEditService
from app.services.evaluation import EvaluationService
from app.services.mutations import MutationService
from app.services.proposals import ProposalService
from app.services.sessions import SessionService


@dataclass
class Services:
    client: GraphClient
    mutations: MutationService
    evaluation: EvaluationService
    sessions: SessionService
    decisions: DecisionService
    edits: DemoEditService
    proposals: ProposalService


def services_for(client: GraphClient) -> Services:
    mutations = MutationService(client, client.settings)
    evaluation = EvaluationService(client, client.settings)
    return Services(client, mutations, evaluation, SessionService(client, mutations),
                    DecisionService(client, mutations), DemoEditService(client, mutations),
                    ProposalService(client, mutations, evaluation))


def key() -> str:
    return str(uuid.uuid4())


async def running_run(s: Services, campaign_id: str = "camp_01") -> dict:
    session = await s.sessions.create_session("Replacement", key())
    run = await s.sessions.create_run(session["id"], campaign_id, "Find a replacement for this campaign.", key(),
                                      model="qwen3:4b-instruct-2507-q4_K_M", model_digest="0edcdef34593")
    await s.sessions.update_run(run["id"], status="running", phase="checking_candidates")
    return run


async def staged_draft(s: Services, creator_id: str = "cr_02", campaign_id: str = "camp_01",
                       complete: bool = True) -> tuple[dict, dict]:
    run = await running_run(s, campaign_id)
    evaluation, ctx = await s.evaluation.evaluate(campaign_id)
    proposal = await s.proposals.stage(run_id=run["id"], creator_id=creator_id, evaluation=evaluation,
                                       campaign=ctx.campaign)
    if complete:
        await s.sessions.update_run(run["id"], status="completed", phase="done")
    return run, proposal
