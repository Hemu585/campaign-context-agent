"""The SYNTHETIC_DATA oracle against real FalkorDB: T03-T07, T09 (graph part) and T15.

Each test starts from a disposable baseline graph and applies only fixture-level
mutations through tests/helpers/scenario.py.
"""

import pytest
from helpers import scenario
from helpers.graphq import cypher

from app.config import Settings
from app.db.client import GraphClient
from app.errors import AppError
from app.services.evaluation import EvaluationService
from app.timeutil import parse_iso_ms

AS_OF = parse_iso_ms("2026-10-15T12:00:00Z")
CAMPAIGN_START = parse_iso_ms("2026-10-20T09:00:00+05:30")

BASELINE = {
    "cr_01": ("ineligible", ["participation"], [], "DROPPED_OUT"),
    "cr_02": ("eligible", [], [], None),
    "cr_03": ("ineligible", ["exclusivity"], [], "COMPETITOR_EXCLUSIVITY"),
    "cr_04": ("eligible", [], [], None),
    "cr_05": ("ineligible", ["budget"], [], "OVER_BUDGET"),
    "cr_06": ("ineligible", ["availability"], [], "UNAVAILABLE_OVERLAP"),
    "cr_07": ("ineligible", ["offer_match"], [], "NO_MATCHING_OFFER"),
    "cr_08": ("unknown", [], ["agreement_audit", "exclusivity"], "AUDIT_MISSING"),
    "cr_09": ("eligible", [], [], None),
    "cr_10": ("eligible", [], [], None),
    "cr_11": ("unknown", [], ["availability"], "STALE_SOURCE"),
    "cr_12": ("eligible", [], [], None),
}


async def evaluate(client, campaign_id="camp_01"):
    evaluation, _ = await EvaluationService(client, client.settings).evaluate(campaign_id)
    return evaluation, {c.creator_id: c for c in evaluation.candidates}


def first_reason(cand):
    for ch in cand.checks:
        if ch.result in ("fail", "unknown"):
            return ch.reason_code
    return None


def check(cand, name):
    return next(ch for ch in cand.checks if ch.name == name)


# T03 / S01 -----------------------------------------------------------------------------------

async def test_baseline_matches_the_oracle_for_all_twelve_creators(seeded):
    evaluation, by_id = await evaluate(seeded)
    assert len(evaluation.candidates) == 12
    assert evaluation.context_revision == 1 and evaluation.as_of_ms == AS_OF
    for cid, (status, failed, unknown, reason) in BASELINE.items():
        cand = by_id[cid]
        assert cand.status == status, cid
        assert cand.failed_checks == failed, cid
        assert cand.unknown_checks == unknown, cid
        assert first_reason(cand) == reason, cid
    assert [c.creator_id for c in evaluation.candidates[:5]] == ["cr_02", "cr_04", "cr_09", "cr_10", "cr_12"]
    assert [c.rank for c in evaluation.candidates[:5]] == [1, 2, 3, 4, 5]
    assert evaluation.recommended_creator_ids == ["cr_02", "cr_04", "cr_09"]
    assert by_id["cr_02"].fee_paise == 1800000 and by_id["cr_02"].completed_campaign_count == 2


async def test_completed_campaign_counts_are_cited_as_sources(seeded):
    # Review fix C7: a count that can break a ranking tie must be traceable to its sources.
    evaluation, by_id = await evaluate(seeded)
    cited = {s.id for s in evaluation.sources}
    for cand in evaluation.candidates:
        assert cand.completed_campaign_count == len(cand.completed_campaigns), cand.creator_id
        assert {h.source_id for h in cand.completed_campaigns} <= cited, cand.creator_id
    assert len({h.campaign_id for h in by_id["cr_02"].completed_campaigns}) == 2


async def test_tara_is_excluded_through_the_multi_hop_competitor_path(seeded):
    evaluation, by_id = await evaluate(seeded)
    ex = check(by_id["cr_03"], "exclusivity")
    path = next(p for p in evaluation.evidence_paths if p.id == ex.facts["path_id"])
    assert path.node_ids == ["cr_03", "agr_cr03", "brand_02", "brand_01", "camp_01"]
    assert [e.type for e in path.edges] == ["HAS_AGREEMENT", "WITH_BRAND", "COMPETES_WITH", "RUNS"]
    assert {"src_agreement_cr03_v1", "src_competitors_brand01_v1"} <= set(ex.source_ids)
    assert "Noro Glow" in ex.detail and "Luma Skin" in ex.detail


async def test_baseline_is_the_same_for_the_second_luma_campaign(seeded):
    evaluation, _ = await evaluate(seeded, "camp_02")
    assert evaluation.recommended_creator_ids == ["cr_02", "cr_04", "cr_09"]


async def test_competition_is_client_relative_for_pavo_home(seeded):
    evaluation, by_id = await evaluate(seeded, "camp_03")
    assert by_id["cr_03"].status == "eligible"
    assert evaluation.recommended_creator_ids == ["cr_03", "cr_02", "cr_04"]


# T04 -----------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("label", "node", "props", "creator", "code"),
    [
        ("Offer", "off_cr12", {"fee_paise": 2500001}, "cr_12", "OVER_BUDGET"),
        ("Offer", "off_cr04", {"currency": "USD"}, "cr_04", "OFFER_CURRENCY_MISMATCH"),
        ("Offer", "off_cr04", {"valid_to_ms": parse_iso_ms("2026-10-14T23:59:59+05:30")}, "cr_04", "QUOTE_EXPIRED"),
    ],
)
async def test_boundaries_and_wrong_evidence(seeded, label, node, props, creator, code):
    await scenario.set_fact(seeded, label, node, **props)
    _, by_id = await evaluate(seeded)
    assert by_id[creator].status == "ineligible"
    assert first_reason(by_id[creator]) == code


async def test_exactly_at_budget_is_allowed(seeded):
    _, by_id = await evaluate(seeded)
    assert by_id["cr_12"].fee_paise == 2500000 and by_id["cr_12"].status == "eligible"


async def test_missing_offer_is_no_matching_offer(seeded):
    await scenario.delete_node(seeded, "Offer", "off_cr04")
    _, by_id = await evaluate(seeded)
    assert first_reason(by_id["cr_04"]) == "NO_MATCHING_OFFER"
    assert by_id["cr_04"].fee_paise is None


async def test_current_participant_is_excluded(seeded):
    await scenario.set_participation(seeded, "cr_02", "camp_01", "assigned", "src_camp01_brief_v1")
    _, by_id = await evaluate(seeded)
    assert first_reason(by_id["cr_02"]) == "CURRENTLY_ASSIGNED"


# T05 -----------------------------------------------------------------------------------------

async def test_s05_agreement_ending_before_delivery_makes_tara_first(seeded):
    await scenario.set_fact(seeded, "Agreement", "agr_cr03", end_ms=parse_iso_ms("2026-10-19T23:59:59+05:30"))
    evaluation, by_id = await evaluate(seeded)
    assert by_id["cr_03"].status == "eligible" and by_id["cr_03"].rank == 1
    assert by_id["cr_03"].fee_paise == 1500000
    assert evaluation.recommended_creator_ids == ["cr_03", "cr_02", "cr_04"]


async def test_s06_agreement_ending_exactly_at_start_still_conflicts(seeded):
    await scenario.set_fact(seeded, "Agreement", "agr_cr03", end_ms=CAMPAIGN_START)
    _, by_id = await evaluate(seeded)
    assert first_reason(by_id["cr_03"]) == "COMPETITOR_EXCLUSIVITY"


async def test_s12_reversed_competitor_edge_gives_the_same_conflict(seeded):
    await scenario.reverse_competitor_edge(seeded, "brand_01", "brand_02")
    _, by_id = await evaluate(seeded)
    assert first_reason(by_id["cr_03"]) == "COMPETITOR_EXCLUSIVITY"


async def test_s13_transitive_relation_is_not_a_direct_conflict(seeded):
    await scenario.remove_competitor_edge(seeded, "brand_01", "brand_02")
    await scenario.add_brand(seeded, "brand_x", "Zeta Labs", "beauty")
    await scenario.add_competitor_edge(seeded, "brand_02", "brand_x", "src_competitors_brand01_v1")
    await scenario.add_competitor_edge(seeded, "brand_x", "brand_01", "src_competitors_brand01_v1")
    await scenario.set_fact(seeded, "Audit", "audit_competitors_brand01", listed_ids=["brand_x"])
    _, by_id = await evaluate(seeded)
    assert check(by_id["cr_03"], "exclusivity").result == "pass"
    assert by_id["cr_03"].status == "eligible"


@pytest.mark.parametrize(
    ("props", "conflict"),
    [({"channel": "youtube"}, False), ({"category": "all"}, True), ({"exclusive": False}, False),
     ({"status": "cancelled"}, False)],
)
async def test_agreement_scope_and_status(seeded, props, conflict):
    await scenario.set_fact(seeded, "Agreement", "agr_cr03", **props)
    _, by_id = await evaluate(seeded)
    assert (check(by_id["cr_03"], "exclusivity").result == "fail") is conflict


# T06 -----------------------------------------------------------------------------------------

async def test_s08_missing_audit_is_unknown_never_clear(seeded):
    await scenario.delete_node(seeded, "Audit", "audit_cr02")
    evaluation, by_id = await evaluate(seeded)
    assert by_id["cr_02"].status == "unknown"
    assert check(by_id["cr_02"], "exclusivity").result == "unknown"
    assert evaluation.recommended_creator_ids == ["cr_04", "cr_09", "cr_10"]


@pytest.mark.parametrize(
    ("props", "code"),
    [
        ({"observed_at_ms": parse_iso_ms("2026-09-14T12:00:00Z")}, "STALE_SOURCE"),
        ({"observed_at_ms": parse_iso_ms("2026-10-16T12:00:00Z")}, "FUTURE_SOURCE"),
        ({"verified": False}, "UNVERIFIED_SOURCE"),
    ],
)
async def test_unusable_offer_evidence_is_unknown(seeded, props, code):
    await scenario.set_source(seeded, "src_offer_cr04_v1", **props)
    _, by_id = await evaluate(seeded)
    assert by_id["cr_04"].status == "unknown"
    assert check(by_id["cr_04"], "offer_match").reason_code == code


async def test_conflicting_equally_current_sources_are_unknown(seeded):
    await scenario.add_competing_source(seeded, "Offer", "off_cr04", "src_offer_cr04_alt_v1", "different", AS_OF)
    _, by_id = await evaluate(seeded)
    assert check(by_id["cr_04"], "offer_match").reason_code == "CONFLICTING_SOURCES"


async def test_edit_that_bypasses_source_versioning_is_detected(seeded):
    await cypher(seeded, "MATCH (o:Offer {id: 'off_cr02'}) SET o.fee_paise = 900000", write=True)
    _, by_id = await evaluate(seeded)
    assert check(by_id["cr_02"], "offer_match").reason_code == "SOURCE_MISMATCH"
    assert by_id["cr_02"].status == "unknown"


async def test_missing_agreement_end_date_is_unknown_not_expired(seeded):
    await scenario.set_fact(seeded, "Agreement", "agr_cr03", end_ms=None)
    _, by_id = await evaluate(seeded)
    assert by_id["cr_03"].status == "unknown"
    assert check(by_id["cr_03"], "exclusivity").reason_code == "AGREEMENT_DATES_MISSING"


async def test_known_failure_stays_ineligible_with_unknowns_listed(seeded):
    await scenario.delete_node(seeded, "Audit", "audit_cr05")
    _, by_id = await evaluate(seeded)
    assert by_id["cr_05"].status == "ineligible"
    assert "agreement_audit" in by_id["cr_05"].unknown_checks


async def test_missing_competitor_map_blocks_every_recommendation(seeded):
    await scenario.delete_node(seeded, "Audit", "audit_competitors_brand01")
    evaluation, by_id = await evaluate(seeded)
    assert evaluation.recommended_creator_ids == []
    for cid in ("cr_02", "cr_04", "cr_09", "cr_10", "cr_12"):
        assert by_id[cid].status == "unknown"


# T07 -----------------------------------------------------------------------------------------

async def test_s11_tie_broken_by_history_then_id(seeded):
    await scenario.set_fact(seeded, "Offer", "off_cr04", fee_paise=1800000)
    evaluation, _ = await evaluate(seeded)
    assert evaluation.recommended_creator_ids[:2] == ["cr_02", "cr_04"]
    await scenario.set_participation(seeded, "cr_04", "camp_08", "completed", "src_camp08_record_v1")
    evaluation, by_id = await evaluate(seeded)
    assert by_id["cr_04"].completed_campaign_count == by_id["cr_02"].completed_campaign_count == 2
    assert evaluation.recommended_creator_ids[:2] == ["cr_02", "cr_04"]


async def test_repeated_evaluations_are_identical(seeded):
    dumps = [(await evaluate(seeded))[0].model_dump() for _ in range(3)]
    assert dumps[0] == dumps[1] == dumps[2]


# T09 (graph part) ----------------------------------------------------------------------------

async def test_every_cited_source_and_path_node_exists_in_the_graph(seeded):
    evaluation, _ = await evaluate(seeded)
    cited = {s for c in evaluation.candidates for ch in c.checks for s in ch.source_ids}
    cited |= {s for p in evaluation.evidence_paths for s in p.source_ids}
    rows = await cypher(seeded, "MATCH (s:Source) WHERE s.id IN $ids RETURN s.id AS id", {"ids": sorted(cited)})
    assert {r["id"] for r in rows} == cited
    node_ids = {n for p in evaluation.evidence_paths for n in p.node_ids}
    rows = await cypher(seeded, "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id", {"ids": sorted(node_ids)})
    assert {r["id"] for r in rows} == node_ids
    allowed = {"HAS_AGREEMENT", "WITH_BRAND", "COMPETES_WITH", "RUNS", "OFFERS", "HAS_AVAILABILITY", "HAS_AUDIT",
               "PARTICIPATED_IN", "CONSIDERED", "FOR_CAMPAIGN"}
    assert {e.type for p in evaluation.evidence_paths for e in p.edges} <= allowed


# T15 -----------------------------------------------------------------------------------------

async def test_removing_the_competitor_relationship_changes_the_answer(seeded):
    await scenario.remove_competitor_edge(seeded, "brand_01", "brand_02")
    await scenario.set_fact(seeded, "Audit", "audit_competitors_brand01", listed_ids=[])
    evaluation, by_id = await evaluate(seeded)
    assert by_id["cr_03"].status == "eligible"
    assert evaluation.recommended_creator_ids[0] == "cr_03"


async def test_graph_down_fails_instead_of_answering_from_the_fixture():
    settings = Settings(_env_file=None, falkordb_port=6399, falkordb_graph="campaign_context_test_down")
    client = GraphClient(settings)
    try:
        with pytest.raises(AppError) as info:
            await EvaluationService(client, settings).evaluate("camp_01")
        assert info.value.code == "GRAPH_UNAVAILABLE"
    finally:
        await client.close()
