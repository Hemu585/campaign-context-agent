"""Q01-Q07 return the real graph context for one campaign (R02, R05, R06)."""

import pytest
from helpers import scenario

from app.errors import AppError
from app.services.graph_reads import load_campaign_context, load_sources, read_revision
from app.timeutil import parse_iso_ms


async def test_campaign_context_matches_the_fixture(seeded):
    ctx = await load_campaign_context(seeded, "camp_01")
    assert ctx.revision == 1 == await read_revision(seeded)
    c = ctx.campaign
    assert (c.brand_id, c.brand_name, c.language, c.category, c.budget_paise) == (
        "brand_01", "Luma Skin", "hi", "beauty", 2500000)
    assert c.start_ms == parse_iso_ms("2026-10-20T09:00:00+05:30")
    assert c.source_ids == ("src_camp01_brief_v1",)
    assert [(p.creator_id, p.status) for p in ctx.participants] == [("cr_01", "dropped_out")]


async def test_every_creator_is_loaded_with_offers_and_history(seeded):
    ctx = await load_campaign_context(seeded, "camp_01")
    assert [c.id for c in ctx.creators] == [f"cr_{i:02d}" for i in range(1, 13)]
    assert sum(len(v) for v in ctx.offers.values()) == 12
    assert ctx.offers["cr_07"][0].language == "en"
    assert {k: len(v) for k, v in ctx.completed.items()} == {"cr_01": 1, "cr_02": 2, "cr_03": 1, "cr_04": 1}


async def test_windows_agreements_audits_and_sources(seeded):
    ctx = await load_campaign_context(seeded, "camp_01")
    assert sum(len(v) for v in ctx.availability.values()) == 13
    assert {w.status for w in ctx.availability["cr_06"]} == {"available", "unavailable"}
    agreements = {a.id: a for v in ctx.agreements.values() for a in v}
    assert agreements["agr_cr03"].is_direct_competitor is True
    assert agreements["agr_cr03"].competitor_edge_source_ids == ("src_competitors_brand01_v1",)
    assert agreements["agr_cr09"].is_direct_competitor is True
    assert agreements["agr_cr10"].is_direct_competitor is False
    assert [(x.brand_id, x.source_id) for x in ctx.client_competitors] == [("brand_02", "src_competitors_brand01_v1")]
    assert sorted(ctx.agreement_audits) == [f"cr_{i:02d}" for i in range(1, 13) if i != 8]
    assert [a.id for a in ctx.competitor_audits] == ["audit_competitors_brand01"]
    assert ctx.decisions == {}
    assert len(ctx.sources) == 49
    assert not any(s.superseded for s in ctx.sources.values())
    assert ctx.sources["src_avail_cr11_v1"].observed_at_ms == parse_iso_ms("2026-09-01T12:00:00+05:30")


async def test_reversed_competitor_edge_is_still_direct_competition(seeded):
    """S12: COMPETES_WITH is stored once per pair and traversed undirected."""
    await scenario.reverse_competitor_edge(seeded, "brand_01", "brand_02")
    ctx = await load_campaign_context(seeded, "camp_01")
    agreements = {a.id: a for v in ctx.agreements.values() for a in v}
    assert agreements["agr_cr03"].is_direct_competitor is True


async def test_competition_is_relative_to_the_campaign_client(seeded):
    """camp_03 belongs to Pavo Home, which has no listed competitors."""
    ctx = await load_campaign_context(seeded, "camp_03")
    agreements = {a.id: a for v in ctx.agreements.values() for a in v}
    assert agreements["agr_cr03"].is_direct_competitor is False
    assert [a.id for a in ctx.competitor_audits] == ["audit_competitors_brand04"]
    assert ctx.client_competitors == ()


async def test_unknown_campaign_is_a_404(seeded):
    with pytest.raises(AppError) as info:
        await load_campaign_context(seeded, "camp_99")
    assert (info.value.code, info.value.status) == ("CAMPAIGN_NOT_FOUND", 404)


async def test_full_source_text_is_available_for_the_viewer(seeded):
    rows = await load_sources(seeded, ["src_agreement_cr03_v1"])
    assert len(rows) == 1
    assert "FICTIONAL DEMO DATA" in rows[0]["text"] and rows[0]["version"] == 1
