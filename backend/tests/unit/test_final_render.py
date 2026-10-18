"""The backend-rendered final result states facts the backend knows, whatever the model labels them."""

from helpers.ctxfactory import AS_OF, Ctx

from app.agent.final import FinalAnswer, render_final
from app.models.api import Evaluation
from app.services.rules import evaluate_context, recommended_ids


def evaluation_for(ctx: Ctx) -> Evaluation:
    candidates, paths = evaluate_context(ctx.build(), AS_OF)
    return Evaluation(campaign_id="camp_01", context_revision=1, as_of_ms=AS_OF, mode="agent_run",
                      candidates=candidates, recommended_creator_ids=recommended_ids(candidates),
                      unknowns=[], sources=[], evidence_paths=paths)


def explanation() -> FinalAnswer:
    return FinalAnswer(outcome="explanation", recommended_creator_ids=[], highlighted_reasons=[],
                       clarification_code="none")


def test_an_explanation_with_nobody_eligible_says_that_nothing_qualifies():
    # Seen in verify-model (no_candidate): the model called its answer an "explanation" and the
    # operator's summary never said that no creator qualified.
    result = render_final(explanation(), evaluation_for(Ctx().creator("cr_a", fee=9_000_000)), None,
                          campaign_id="camp_01", title="Luma Autumn Launch")
    assert result["outcome"] == "no_eligible_candidate"
    assert result["summary"].startswith("No creator passes every check for Luma Autumn Launch")
    assert result["recommended_creator_ids"] == [] and result["proposal_id"] is None


def test_an_explanation_stays_an_explanation_when_someone_is_eligible():
    result = render_final(explanation(), evaluation_for(Ctx().creator("cr_a")), None,
                          campaign_id="camp_01", title="Luma Autumn Launch")
    assert result["outcome"] == "explanation"
    assert "No creator passes every check" not in result["summary"]
