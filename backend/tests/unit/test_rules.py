"""Rule engine unit tests: every check, status precedence and ranking (spec section 5, T04-T07)."""

import pytest
from helpers.ctxfactory import AS_OF, C_END, C_START, OCT_1, OCT_31, Ctx

from app.models.domain import ParticipationRec
from app.services.rules import evaluate_context, overlap_tristate, recommended_ids


def run(ctx: Ctx):
    candidates, paths = evaluate_context(ctx.build(), AS_OF)
    return {c.creator_id: c for c in candidates}, candidates, paths


def check(cand, name):
    return next(ch for ch in cand.checks if ch.name == name)


def test_fully_evidenced_creator_is_eligible():
    by_id, _, _ = run(Ctx().creator("cr_a"))
    c = by_id["cr_a"]
    assert c.status == "eligible" and c.rank == 1
    assert all(ch.result == "pass" for ch in c.checks)
    assert "No conflict found in verified demo records" in check(c, "exclusivity").detail


# participation -------------------------------------------------------------------------------

def test_dropped_out_and_assigned_creators_fail():
    ctx = Ctx().creator("cr_a").creator("cr_b").creator("cr_c", active=False)
    ctx.participants = [ParticipationRec("cr_a", "A", "dropped_out", "src_brief"),
                        ParticipationRec("cr_b", "B", "assigned", "src_brief")]
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "participation").reason_code == "DROPPED_OUT"
    assert check(by_id["cr_b"], "participation").reason_code == "CURRENTLY_ASSIGNED"
    assert check(by_id["cr_c"], "participation").reason_code == "INACTIVE_CREATOR"
    assert {by_id[x].status for x in ("cr_a", "cr_b", "cr_c")} == {"ineligible"}


# offers, quote, budget -----------------------------------------------------------------------

def test_wrong_language_is_no_matching_offer_and_budget_is_not_applicable():
    by_id, _, _ = run(Ctx().creator("cr_a", language="en"))
    c = by_id["cr_a"]
    assert check(c, "offer_match").reason_code == "NO_MATCHING_OFFER"
    assert check(c, "quote_validity").result == "not_applicable"
    assert check(c, "budget").result == "not_applicable"
    assert c.status == "ineligible" and c.fee_paise is None


def test_wrong_currency_is_distinguished_from_missing_offer():
    by_id, _, _ = run(Ctx().creator("cr_a", currency="USD"))
    assert check(by_id["cr_a"], "offer_match").reason_code == "OFFER_CURRENCY_MISMATCH"


def test_two_current_matching_quotes_are_unknown():
    ctx = Ctx().creator("cr_a")
    ctx.add_offer("cr_a", "off_cr_a_2", fee=1700000)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "offer_match").reason_code == "MULTIPLE_MATCHING_OFFERS"
    assert by_id["cr_a"].status == "unknown"


def test_an_expired_quote_beside_a_current_one_does_not_block_the_current_one():
    # Review fix C6: only quotes whose period covers the as-of time compete as "current".
    ctx = Ctx().creator("cr_a", fee=1800000)
    ctx.add_offer("cr_a", "off_cr_a_old", fee=1500000, valid_from=OCT_1 - 40 * 86_400_000, valid_to=OCT_1 - 1)
    by_id, _, _ = run(ctx)
    offer = check(by_id["cr_a"], "offer_match")
    assert (offer.result, offer.facts["offer_id"]) == ("pass", "off_cr_a")
    assert check(by_id["cr_a"], "quote_validity").result == "pass"
    assert by_id["cr_a"].fee_paise == 1800000 and by_id["cr_a"].status == "eligible"


def test_an_undated_quote_beside_a_current_one_stays_unknown():
    # An undated quote might be current, so it cannot be ignored.
    ctx = Ctx().creator("cr_a")
    ctx.add_offer("cr_a", "off_cr_a_undated", fee=1500000, valid_from=None, valid_to=None)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "offer_match").reason_code == "MULTIPLE_MATCHING_OFFERS"
    assert by_id["cr_a"].status == "unknown"


def test_with_no_current_quote_the_latest_one_explains_the_failure():
    ctx = Ctx().creator("cr_a", valid_from=OCT_1 - 60 * 86_400_000, valid_to=OCT_1 - 30 * 86_400_000)
    ctx.add_offer("cr_a", "off_cr_a_later", valid_from=OCT_1 - 20 * 86_400_000, valid_to=OCT_1 - 1)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "offer_match").facts["offer_id"] == "off_cr_a_later"
    q = check(by_id["cr_a"], "quote_validity")
    assert (q.result, q.reason_code) == ("fail", "QUOTE_EXPIRED")
    assert by_id["cr_a"].status == "ineligible"


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "result", "code"),
    [
        (OCT_1, AS_OF, "pass", None),                       # valid_to == as_of is inclusive
        (OCT_1, AS_OF - 1, "fail", "QUOTE_EXPIRED"),
        (AS_OF + 1, OCT_31, "fail", "QUOTE_NOT_YET_VALID"),
        (None, OCT_31, "unknown", "QUOTE_DATES_MISSING"),
    ],
)
def test_quote_validity_window(valid_from, valid_to, result, code):
    by_id, _, _ = run(Ctx().creator("cr_a", valid_from=valid_from, valid_to=valid_to))
    q = check(by_id["cr_a"], "quote_validity")
    assert (q.result, q.reason_code) == (result, code)


@pytest.mark.parametrize(("fee", "result"), [(2500000, "pass"), (2500001, "fail"), (2499999, "pass")])
def test_budget_is_compared_in_exact_paise(fee, result):
    by_id, _, _ = run(Ctx().creator("cr_a", fee=fee))
    assert check(by_id["cr_a"], "budget").result == result


def test_stale_offer_source_is_unknown_not_ineligible():
    by_id, _, _ = run(Ctx().creator("cr_a", offer_observed=AS_OF - 31 * 86_400_000))
    assert check(by_id["cr_a"], "offer_match").reason_code == "STALE_SOURCE"
    assert by_id["cr_a"].status == "unknown"


# availability --------------------------------------------------------------------------------

def test_window_exactly_matching_delivery_passes():
    ctx = Ctx().creator("cr_a", window=False)
    ctx.add_window("cr_a", "w1", C_START, C_END, "available")
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "availability").result == "pass"


def test_unavailable_overlap_beats_full_positive_coverage():
    ctx = Ctx().creator("cr_a")
    ctx.add_window("cr_a", "w_off", C_START + 3600_000, C_START + 7200_000, "unavailable")
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "availability").reason_code == "UNAVAILABLE_OVERLAP"


def test_unavailable_window_touching_the_start_still_overlaps():
    ctx = Ctx().creator("cr_a")
    ctx.add_window("cr_a", "w_off", C_START - 86_400_000, C_START, "unavailable")
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "availability").result == "fail"


def test_partial_windows_are_not_merged():
    ctx = Ctx().creator("cr_a", window=False)
    ctx.add_window("cr_a", "w1", C_START, C_START + 86_400_000, "available")
    ctx.add_window("cr_a", "w2", C_START + 86_400_000, C_END, "available")
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "availability").reason_code == "NO_COVERING_WINDOW"
    assert by_id["cr_a"].status == "unknown"


def test_no_availability_record_is_unknown():
    by_id, _, _ = run(Ctx().creator("cr_a", window=False))
    assert check(by_id["cr_a"], "availability").reason_code == "NO_AVAILABILITY_RECORD"


def test_stale_covering_window_is_unknown():
    ctx = Ctx().creator("cr_a", window=False)
    ctx.add_window("cr_a", "w1", C_START, C_END, "available", observed=AS_OF - 44 * 86_400_000)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "availability").reason_code == "STALE_SOURCE"


# audits --------------------------------------------------------------------------------------

def test_missing_agreement_audit_is_unknown_never_clear():
    by_id, _, _ = run(Ctx().creator("cr_a", audit=False))
    c = by_id["cr_a"]
    assert check(c, "agreement_audit").reason_code == "AUDIT_MISSING"
    assert check(c, "exclusivity").reason_code == "REQUIRES_COMPLETE_AUDITS"
    assert c.status == "unknown"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"complete": False}, "AUDIT_INCOMPLETE"),
        ({"end": C_END - 1}, "AUDIT_COVERAGE"),
        ({"listed": ["agr_ghost"]}, "AUDIT_LIST_MISMATCH"),
    ],
)
def test_agreement_audit_problems(kwargs, code):
    ctx = Ctx().creator("cr_a")
    ctx.add_agreement_audit("cr_a", **kwargs)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "agreement_audit").reason_code == code


def test_missing_competitor_audit_makes_everyone_unknown():
    ctx = Ctx().creator("cr_a")
    ctx.competitor_audits = []
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_a"], "competitor_audit").reason_code == "AUDIT_MISSING"
    assert by_id["cr_a"].status == "unknown"


# exclusivity ---------------------------------------------------------------------------------

def test_active_competitor_exclusive_overlapping_fails_with_full_path():
    ctx = Ctx().creator("cr_t", fee=1500000).add_agreement("cr_t", "agr_t")
    by_id, _, paths = run(ctx)
    ex = check(by_id["cr_t"], "exclusivity")
    assert (ex.result, ex.reason_code) == ("fail", "COMPETITOR_EXCLUSIVITY")
    path = next(p for p in paths if p.id == ex.facts["path_id"])
    assert path.node_ids == ["cr_t", "agr_t", "brand_02", "brand_01", "camp_01"]
    assert [e.type for e in path.edges] == ["HAS_AGREEMENT", "WITH_BRAND", "COMPETES_WITH", "RUNS"]
    assert "src_comp" in ex.source_ids


@pytest.mark.parametrize(
    ("kwargs", "result"),
    [
        ({"end": C_START - 1}, "pass"),                # ended before delivery (S05)
        ({"end": C_START}, "fail"),                    # inclusive boundary (S06)
        ({"start": C_END}, "fail"),
        ({"start": C_END + 1}, "pass"),
        ({"channel": "all"}, "fail"),
        ({"category": "all"}, "fail"),
        ({"channel": "youtube"}, "pass"),
        ({"category": "fitness"}, "pass"),
        ({"exclusive": False}, "pass"),
        ({"status": "cancelled"}, "pass"),
        ({"competitor": False}, "pass"),               # no direct COMPETES_WITH edge (S13)
        ({"counterparty": "brand_01", "competitor": False}, "pass"),  # self-brand agreement
        ({"end": None}, "unknown"),                    # missing end is never read as expired
        ({"start": None, "end": C_START - 1}, "pass"),  # ended before delivery regardless of start
        ({"start": C_END + 1, "end": None}, "pass"),   # starts after delivery regardless of end
    ],
)
def test_exclusivity_rules(kwargs, result):
    ctx = Ctx().creator("cr_t").add_agreement("cr_t", "agr_t", **kwargs)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_t"], "exclusivity").result == result


def test_non_competitor_agreement_with_stale_source_is_unknown():
    ctx = Ctx().creator("cr_r").add_agreement("cr_r", "agr_r", counterparty="brand_03", competitor=False,
                                              observed=AS_OF - 40 * 86_400_000)
    by_id, _, _ = run(ctx)
    assert check(by_id["cr_r"], "exclusivity").result == "unknown"


def test_overlap_tristate():
    assert overlap_tristate(None, None, 10, 20) is None
    assert overlap_tristate(None, 5, 10, 20) is False
    assert overlap_tristate(25, None, 10, 20) is False
    assert overlap_tristate(5, None, 10, 20) is None
    assert overlap_tristate(5, 10, 10, 20) is True


# memory --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({}, "excluded_by_memory"),
        ({"expires": AS_OF}, "eligible"),               # expiry is exclusive
        ({"expires": AS_OF + 1}, "excluded_by_memory"),
        ({"revoked_at": AS_OF}, "eligible"),
        ({"revoked_at": AS_OF + 1}, "excluded_by_memory"),  # future revocation not yet effective
        ({"as_of": AS_OF + 1}, "eligible"),             # rejection made after the as-of time
    ],
)
def test_memory_activity(kwargs, status):
    by_id, _, _ = run(Ctx().creator("cr_a").reject("cr_a", "d1", **kwargs))
    assert by_id["cr_a"].status == status


def test_status_precedence_shows_every_reason():
    ctx = Ctx().creator("cr_a", fee=2600000, audit=False).reject("cr_a", "d1")
    by_id, _, _ = run(ctx)
    c = by_id["cr_a"]
    assert c.status == "ineligible"
    assert "budget" in c.failed_checks and "memory" in c.failed_checks
    assert "agreement_audit" in c.unknown_checks
    assert c.active_rejection_ids == ["d1"]


def test_unknown_outranks_memory():
    ctx = Ctx().creator("cr_a", audit=False).reject("cr_a", "d1")
    by_id, _, _ = run(ctx)
    assert by_id["cr_a"].status == "unknown"


# ranking -------------------------------------------------------------------------------------

def test_ranking_fee_then_history_then_id():
    ctx = (Ctx().creator("cr_b", fee=1800000, completed=1).creator("cr_a", fee=1800000, completed=2)
           .creator("cr_c", fee=1800000, completed=2).creator("cr_d", fee=1700000))
    _, candidates, _ = run(ctx)
    assert [c.creator_id for c in candidates] == ["cr_d", "cr_a", "cr_c", "cr_b"]
    assert [c.rank for c in candidates] == [1, 2, 3, 4]
    assert recommended_ids(candidates) == ["cr_d", "cr_a", "cr_c"]


def test_counted_completed_campaigns_carry_their_sources():
    # Review fix C7: history breaks fee ties, so each counted campaign is cited with its source.
    ctx = Ctx().creator("cr_a", completed=2)
    ctx.source("src_hist_cr_a_1", observed=AS_OF - 90 * 86_400_000, verified=False)  # not counted
    by_id, _, _ = run(ctx)
    cand = by_id["cr_a"]
    assert cand.completed_campaign_count == 1
    assert [(h.campaign_id, h.source_id) for h in cand.completed_campaigns] == [("camp_hist_cr_a_0", "src_hist_cr_a_0")]


def test_evaluation_is_deterministic():
    ctx = Ctx().creator("cr_a").creator("cr_b", fee=1700000).add_agreement("cr_b", "agr_b", end=C_START - 1)
    first = [c.model_dump() for c in run(ctx)[1]]
    second = [c.model_dump() for c in run(ctx)[1]]
    assert first == second
