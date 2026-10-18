"""HTTP layer over real FalkorDB: read routes, diagnostic evaluation and the write guard (R04, R19, T16 part)."""

import uuid

import httpx
import pytest

from app.config import Settings
from app.main import create_app

BASE = "http://127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:5173"


@pytest.fixture
async def api(seeded, test_settings):
    app = create_app(test_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        client.app = app
        yield client
    await app.state.graph.close()


async def write_headers(api, **overrides):
    nonce = (await api.get("/api/bootstrap")).json()["nonce"]
    headers = {"Content-Type": "application/json", "X-Local-Nonce": nonce, "Idempotency-Key": str(uuid.uuid4()),
               "Origin": ORIGIN}
    headers.update(overrides)
    return headers


async def test_bootstrap_reports_synthetic_demo_clock_and_nonce(api):
    body = (await api.get("/api/bootstrap")).json()
    assert body["synthetic_data"] is True and body["demo_mode"] is True
    assert body["context_revision"] == 1 and len(body["nonce"]) >= 32
    assert body["clock"] == "fixed demo clock"


async def test_campaign_list_shows_only_replacement_slots(api):
    rows = (await api.get("/api/campaigns")).json()
    assert [r["id"] for r in rows] == ["camp_01", "camp_02", "camp_03"]
    first = rows[0]
    assert (first["client_brand_name"], first["budget_paise"], first["dropped_creator_name"]) == (
        "Luma Skin", 2500000, "Asha Pine")
    assert first["approved_proposal_id"] is None


async def test_campaign_detail_includes_the_brief_source(api):
    body = (await api.get("/api/campaigns/camp_01")).json()
    assert body["current_revision"] == 1
    assert body["brief_sources"][0]["id"] == "src_camp01_brief_v1"
    assert body["participants"] == [{"creator_id": "cr_01", "creator_name": "Asha Pine", "status": "dropped_out",
                                     "source_id": "src_camp01_brief_v1"}]


async def test_unknown_campaign_uses_the_error_envelope(api):
    res = await api.get("/api/campaigns/camp_99")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CAMPAIGN_NOT_FOUND"


async def test_diagnostic_evaluation_is_labelled_not_ai(api):
    res = await api.post("/api/campaigns/camp_01/evaluate", json={}, headers=await write_headers(api))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "rule_check_no_ai"
    assert body["recommended_creator_ids"] == ["cr_02", "cr_04", "cr_09"]
    tara_path = next(p for p in body["evidence_paths"] if p["id"] == "cr_03:exclusivity:agr_cr03")
    assert tara_path["edges"][2] == {"from": "brand_02", "type": "COMPETES_WITH", "to": "brand_01",
                                     "source_ids": ["src_competitors_brand01_v1"]}


@pytest.mark.parametrize(
    ("override", "status", "code"),
    [
        ({"X-Local-Nonce": "wrong"}, 403, "INVALID_NONCE"),
        ({"Origin": "http://evil.test"}, 403, "LOCAL_ACCESS_REQUIRED"),
        ({"Content-Type": "text/plain"}, 415, "INVALID_INPUT"),
        ({"Idempotency-Key": "not-a-uuid"}, 400, "INVALID_INPUT"),
    ],
)
async def test_write_guard_rejects_unsafe_requests(api, override, status, code):
    headers = await write_headers(api, **override)
    res = await api.post("/api/campaigns/camp_01/evaluate", content="{}", headers=headers)
    assert res.status_code == status
    assert res.json()["error"]["code"] == code


async def test_unknown_body_fields_are_rejected(api):
    res = await api.post("/api/campaigns/camp_01/evaluate", json={"cypher": "MATCH (n) DETACH DELETE n"},
                         headers=await write_headers(api))
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_INPUT"


async def test_non_loopback_host_header_is_refused(api):
    res = await api.get("/api/campaigns", headers={"Host": "evil.test"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "LOCAL_ACCESS_REQUIRED"


async def test_cors_allows_only_the_local_ui_origin(api):
    preflight = {"Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,x-local-nonce,idempotency-key"}
    evil = await api.options("/api/campaigns/camp_01/evaluate", headers={"Origin": "http://evil.test", **preflight})
    assert "access-control-allow-origin" not in evil.headers
    good = await api.options("/api/campaigns/camp_01/evaluate", headers={"Origin": ORIGIN, **preflight})
    assert good.headers.get("access-control-allow-origin") == ORIGIN


async def test_health_reports_graph_and_model_state(api):
    res = await api.get("/api/health")
    body = res.json()
    assert body["graph"]["reachable"] is True and body["graph"]["seeded"] is True
    assert body["model"]["tag"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert res.status_code == (200 if body["model"]["installed"] else 503)


async def test_graph_down_returns_503_envelope():
    app = create_app(Settings(_env_file=None, falkordb_port=6399, falkordb_graph="campaign_context_test_down"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        res = await client.get("/api/campaigns")
    await app.state.graph.close()
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "GRAPH_UNAVAILABLE"
