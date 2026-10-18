"""Draft staging and revalidated approval: T12, T13 (R14, R15, R24; S09)."""

import asyncio

import pytest
from helpers import scenario
from helpers.graphq import cypher, scalar
from helpers.workflow import key, running_run, services_for, staged_draft

from app.errors import AppError


@pytest.fixture
def s(seeded):
    return services_for(seeded)


async def revision(client):
    return await scalar(client, "MATCH (w:Workspace) RETURN w.context_revision")


# staging -------------------------------------------------------------------------------------

async def test_staging_creates_a_draft_with_an_immutable_evidence_snapshot(s, seeded):
    run, proposal = await staged_draft(s, complete=False)
    assert proposal["status"] == "draft" and proposal["creator_id"] == "cr_02"
    assert proposal["approvable"] is False and proposal["unusable_reason"] == "run_not_completed"
    snap = proposal["snapshot"]
    assert snap["context_revision"] == 1 and snap["as_of_ms"] == 1792065600000
    assert snap["candidate"]["status"] == "eligible" and snap["ranking_inputs"]["fee_paise"] == 1800000
    assert {src["id"] for src in snap["sources"]} >= {"src_offer_cr02_v1", "src_avail_cr02_v1", "src_audit_cr02_v1"}
    assert all("FICTIONAL DEMO DATA" in src["excerpt"] for src in snap["sources"])
    history = {h["source_id"] for h in snap["candidate"]["completed_campaigns"]}
    assert len(history) == 2 and history <= {src["id"] for src in snap["sources"]}  # Review fix C7
    linked = await scalar(seeded, "MATCH (:Proposal {id: $id})-[:SUPPORTED_BY]->(s) RETURN count(s)",
                          {"id": proposal["id"]})
    assert linked == len(snap["sources"])
    assert await revision(seeded) == 1  # drafts never change the revision
    assert (await s.sessions.get_run(run["id"]))["proposal_id"] == proposal["id"]


async def test_staging_is_idempotent_per_run_candidate_and_revision(s, seeded):
    run = await running_run(s)
    evaluation, ctx = await s.evaluation.evaluate("camp_01")
    a = await s.proposals.stage(run_id=run["id"], creator_id="cr_02", evaluation=evaluation, campaign=ctx.campaign)
    b = await s.proposals.stage(run_id=run["id"], creator_id="cr_02", evaluation=evaluation, campaign=ctx.campaign)
    assert a["id"] == b["id"]
    assert await scalar(seeded, "MATCH (p:Proposal) RETURN count(p)") == 1


async def test_ineligible_candidate_cannot_be_staged(s):
    run = await running_run(s)
    evaluation, ctx = await s.evaluation.evaluate("camp_01")
    with pytest.raises(AppError) as info:
        await s.proposals.stage(run_id=run["id"], creator_id="cr_03", evaluation=evaluation, campaign=ctx.campaign)
    assert info.value.code == "CANDIDATE_NOT_ELIGIBLE"


async def test_no_draft_after_the_run_stops(s, seeded):
    run = await running_run(s)
    evaluation, ctx = await s.evaluation.evaluate("camp_01")
    await s.sessions.update_run(run["id"], status="cancelled")
    with pytest.raises(AppError) as info:
        await s.proposals.stage(run_id=run["id"], creator_id="cr_02", evaluation=evaluation, campaign=ctx.campaign)
    assert info.value.code == "RUN_NOT_ACTIVE"
    assert await scalar(seeded, "MATCH (p:Proposal) RETURN count(p)") == 0


async def test_staging_from_an_old_evaluation_is_stale(s):
    run = await running_run(s)
    evaluation, ctx = await s.evaluation.evaluate("camp_01")
    await s.decisions.reject(campaign_id="camp_01", creator_id="cr_09", scope_type="campaign", reason="x",
                             expires_at_ms=None, expected_revision=1, session_id=None, key=key())
    with pytest.raises(AppError) as info:
        await s.proposals.stage(run_id=run["id"], creator_id="cr_02", evaluation=evaluation, campaign=ctx.campaign)
    assert info.value.code == "STALE_CONTEXT"


async def test_draft_becomes_stale_after_an_unrelated_change(s):
    _, proposal = await staged_draft(s)
    await s.decisions.reject(campaign_id="camp_01", creator_id="cr_09", scope_type="campaign", reason="x",
                             expires_at_ms=None, expected_revision=1, session_id=None, key=key())
    fresh = await s.proposals.get(proposal["id"])
    assert fresh["is_stale"] is True and fresh["approvable"] is False and fresh["unusable_reason"] == "stale"


# approval ------------------------------------------------------------------------------------

async def test_successful_approval_writes_every_link_and_fills_one_slot(s, seeded):
    run, proposal = await staged_draft(s)
    result = await s.proposals.approve(proposal["id"], 1, key())
    p = result["proposal"]
    assert p["status"] == "approved" and p["approved_revision"] == 2 and p["is_stale"] is False
    assert result["context_revision"] == 2
    assert await scalar(seeded, "MATCH (c:Campaign {id: 'camp_01'}) RETURN c.approved_proposal_id") == proposal["id"]
    links = await cypher(seeded, "MATCH (d:Decision {id: $id})-[e]->(x) RETURN type(e) AS t, count(x) AS n "
                                 "ORDER BY t", {"id": result["decision_id"]})
    by_type = {r["t"]: r["n"] for r in links}
    assert by_type["APPROVES"] == by_type["FOR_CAMPAIGN"] == by_type["CONSIDERED"] == by_type["IN_SESSION"] == 1
    assert by_type["SUPPORTED_BY"] == len(proposal["snapshot"]["sources"])
    # The approved proposal's own revision increment does not make it stale.
    assert (await s.proposals.get(proposal["id"]))["is_stale"] is False


async def test_s09_stale_approval_is_refused_and_writes_nothing(s, seeded):
    _, proposal = await staged_draft(s)
    await s.edits.edit("availability", "avail_cr02", {"status": "unavailable"}, "Mira unavailable", 1, key())
    for expected in (1, 2):
        with pytest.raises(AppError) as info:
            await s.proposals.approve(proposal["id"], expected, key())
        assert info.value.code == "STALE_CONTEXT"
    assert await scalar(seeded, "MATCH (d:Decision) RETURN count(d)") == 0
    assert await scalar(seeded, "MATCH (c:Campaign {id: 'camp_01'}) RETURN c.approved_proposal_id") is None
    assert await revision(seeded) == 2


async def test_approval_rechecks_rules_not_just_the_revision(s, seeded):
    _, proposal = await staged_draft(s)
    # A change that bypasses the app (unsupported, but approval must still catch it).
    await scenario.set_fact(seeded, "Offer", "off_cr02", fee_paise=3000000)
    with pytest.raises(AppError) as info:
        await s.proposals.approve(proposal["id"], 1, key())
    assert info.value.code == "CANDIDATE_NOT_ELIGIBLE"
    assert info.value.details["failed_checks"] == ["budget"]
    assert await scalar(seeded, "MATCH (d:Decision) RETURN count(d)") == 0


async def test_approval_respects_memory_added_after_staging(s, seeded):
    _, proposal = await staged_draft(s)
    await s.decisions.reject(campaign_id="camp_01", creator_id="cr_02", scope_type="campaign", reason="No",
                             expires_at_ms=None, expected_revision=1, session_id=None, key=key())
    with pytest.raises(AppError) as info:
        await s.proposals.approve(proposal["id"], 2, key())
    assert info.value.code == "STALE_CONTEXT"  # revision moved: a new run is required


async def test_draft_from_an_unsuccessful_run_cannot_be_approved(s, seeded):
    run, proposal = await staged_draft(s, complete=False)
    await s.sessions.update_run(run["id"], status="failed")
    with pytest.raises(AppError) as info:
        await s.proposals.approve(proposal["id"], 1, key())
    assert info.value.code == "PROPOSAL_NOT_USABLE"


async def test_second_approval_for_the_same_slot_is_refused(s, seeded):
    _, first = await staged_draft(s, "cr_02")
    _, second = await staged_draft(s, "cr_04")
    await s.proposals.approve(first["id"], 1, key())
    with pytest.raises(AppError) as info:
        await s.proposals.approve(second["id"], 2, key())
    assert info.value.code == "SLOT_FILLED"
    assert await scalar(seeded, "MATCH (d:Decision {action: 'approved'}) RETURN count(d)") == 1


async def test_retry_with_the_same_key_returns_the_original_approval(s, seeded):
    _, proposal = await staged_draft(s)
    k = key()
    first = await s.proposals.approve(proposal["id"], 1, k)
    second = await s.proposals.approve(proposal["id"], 1, k)
    assert first["decision_id"] == second["decision_id"] and second["replayed"] is True
    assert await revision(seeded) == 2


async def test_same_key_with_a_changed_payload_is_a_conflict(s):
    _, proposal = await staged_draft(s)
    k = key()
    await s.proposals.approve(proposal["id"], 1, k)
    with pytest.raises(AppError) as info:
        await s.proposals.approve(proposal["id"], 2, k)
    assert (info.value.code, info.value.status) == ("IDEMPOTENCY_CONFLICT", 409)


async def test_simultaneous_approvals_produce_exactly_one_winner(s, seeded):
    _, proposal = await staged_draft(s)
    results = await asyncio.gather(*(s.proposals.approve(proposal["id"], 1, key()) for _ in range(3)),
                                   return_exceptions=True)
    wins = [r for r in results if isinstance(r, dict)]
    losses = [r for r in results if isinstance(r, AppError)]
    assert len(wins) == 1 and len(losses) == 2
    assert {e.code for e in losses} <= {"SLOT_FILLED", "STALE_CONTEXT"}
    assert await scalar(seeded, "MATCH (d:Decision {action: 'approved'}) RETURN count(d)") == 1


async def test_failure_before_the_write_leaves_no_partial_state(s, seeded, monkeypatch):
    _, proposal = await staged_draft(s)
    original = seeded.query

    async def failing(query_id, params=None):
        if query_id == "Q10_approve":
            raise RuntimeError("simulated crash before the approval statement")
        return await original(query_id, params)

    monkeypatch.setattr(seeded, "query", failing)
    with pytest.raises(RuntimeError):
        await s.proposals.approve(proposal["id"], 1, key())
    assert await scalar(seeded, "MATCH (d:Decision) RETURN count(d)") == 0
    assert (await s.proposals.get(proposal["id"]))["status"] == "draft"
    assert await revision(seeded) == 1
    assert await scalar(seeded, "MATCH (r:MutationReceipt {operation: 'approve'}) RETURN count(r)") == 0


async def test_old_approval_survives_later_fact_changes_unrewritten(s, seeded):
    _, proposal = await staged_draft(s)
    await s.proposals.approve(proposal["id"], 1, key())
    await s.edits.edit("availability", "avail_cr02", {"status": "unavailable"}, "later change", 2, key())
    p = await s.proposals.get(proposal["id"])
    assert p["status"] == "approved" and p["is_stale"] is False
    assert p["snapshot"]["candidate"]["status"] == "eligible"  # the decision's original basis is preserved
