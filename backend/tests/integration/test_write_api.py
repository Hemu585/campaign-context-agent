"""HTTP write routes over real FalkorDB: sessions, memory, demo edits, sources and approval (R11-R16, R19)."""

import uuid

import httpx
import pytest
from helpers.workflow import services_for, staged_draft

from app.main import create_app

BASE = "http://127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:5173"


@pytest.fixture
async def api(seeded, test_settings):
    app = create_app(test_settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        nonce = (await client.get("/api/bootstrap")).json()["nonce"]
        client.headers.update({"Origin": ORIGIN})
        client.nonce = nonce
        yield client
    await app.state.graph.close()


def h(api, key=None):
    return {"Content-Type": "application/json", "X-Local-Nonce": api.nonce, "Idempotency-Key": key or str(uuid.uuid4())}


async def test_session_create_replay_and_list(api):
    key = str(uuid.uuid4())
    first = await api.post("/api/sessions", json={"title": "Luma replacement"}, headers=h(api, key))
    second = await api.post("/api/sessions", json={"title": "Luma replacement"}, headers=h(api, key))
    assert first.status_code == 201 and first.json()["id"] == second.json()["id"]
    listed = (await api.get("/api/sessions")).json()
    assert [s["id"] for s in listed] == [first.json()["id"]]
    detail = (await api.get(f"/api/sessions/{first.json()['id']}")).json()
    assert detail["messages"] == [] and detail["runs"] == []


async def test_reject_then_revoke_through_the_api(api):
    res = await api.post("/api/decisions/rejections", headers=h(api), json={
        "campaign_id": "camp_01", "creator_id": "cr_02", "scope_type": "campaign",
        "reason": "Tone does not fit", "expected_revision": 1})
    assert res.status_code == 201, res.text
    decision = res.json()
    assert decision["is_active"] is True and decision["scope_id"] == "camp_01"
    evaluation = (await api.post("/api/campaigns/camp_01/evaluate", json={}, headers=h(api))).json()
    assert evaluation["recommended_creator_ids"] == ["cr_04", "cr_09", "cr_10"]
    revoked = await api.post(f"/api/decisions/{decision['id']}/revoke", headers=h(api),
                             json={"reason": "Changed our mind", "expected_revision": 2})
    assert revoked.status_code == 200, revoked.text
    history = (await api.get("/api/decisions", params={"campaign_id": "camp_01"})).json()
    original = next(d for d in history if d["id"] == decision["id"])
    assert original["state"] == "revoked" and original["revoked_by_id"] == revoked.json()["id"]


async def test_stale_write_returns_the_envelope_with_revisions(api):
    res = await api.post("/api/decisions/rejections", headers=h(api), json={
        "campaign_id": "camp_01", "creator_id": "cr_02", "reason": "x", "expected_revision": 9})
    assert res.status_code == 409
    err = res.json()["error"]
    assert err["code"] == "STALE_CONTEXT" and err["retryable"] is True
    assert err["details"] == {"expected_revision": 9, "current_revision": 1}


@pytest.mark.parametrize(
    "body",
    [
        {"campaign_id": "camp_01", "creator_id": "cr_02", "reason": "x", "expected_revision": 1, "scope_id": "brand_02"},
        {"campaign_id": "camp_01", "creator_id": "cr_02", "reason": "x", "expected_revision": 1, "scope_type": "global"},
        {"campaign_id": "camp_01", "creator_id": "cr_02", "reason": "", "expected_revision": 1},
        {"campaign_id": "camp_01; DROP", "creator_id": "cr_02", "reason": "x", "expected_revision": 1},
    ],
)
async def test_invalid_rejection_bodies_are_refused(api, body):
    res = await api.post("/api/decisions/rejections", headers=h(api), json=body)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_INPUT"


async def test_demo_edit_creates_a_viewable_new_source_version(api):
    res = await api.patch("/api/demo/facts/agreement/agr_cr03", headers=h(api), json={
        "changes": {"end_at": "2026-10-19T23:59:59+05:30"}, "reason": "Contract ended early", "expected_revision": 1})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source_id"] == "src_agreement_cr03_v2" and body["context_revision"] == 2
    doc = (await api.get("/api/sources/src_agreement_cr03_v2")).json()
    assert doc["supersedes"] == ["src_agreement_cr03_v1"] and doc["fictional_label"] == "FICTIONAL DEMO DATA"
    old = (await api.get("/api/sources/src_agreement_cr03_v1")).json()
    assert old["superseded_by"] == ["src_agreement_cr03_v2"]
    evaluation = (await api.post("/api/campaigns/camp_01/evaluate", json={}, headers=h(api))).json()
    assert evaluation["recommended_creator_ids"][0] == "cr_03"


@pytest.mark.parametrize(
    ("path", "changes", "status"),
    [
        ("/api/demo/facts/agreement/agr_cr03", {"verified": False}, 422),
        ("/api/demo/facts/agreement/agr_cr03", {"observed_at": "2026-10-15T00:00:00Z"}, 422),
        ("/api/demo/facts/offer/off_cr02", {"fee_paise": 1}, 422),
        ("/api/demo/facts/availability/avail_cr99", {"status": "unavailable"}, 404),
    ],
)
async def test_editor_only_accepts_allowed_fields_on_existing_facts(api, path, changes, status):
    res = await api.patch(path, headers=h(api), json={"changes": changes, "reason": "x", "expected_revision": 1})
    assert res.status_code == status


async def test_editable_fact_list(api):
    facts = (await api.get("/api/demo/facts")).json()
    assert len(facts["agreements"]) == 3 and len(facts["availability"]) == 13


async def test_unknown_resources_are_404_envelopes(api):
    assert (await api.get("/api/sources/src_missing_v1")).json()["error"]["code"] == "SOURCE_NOT_FOUND"
    assert (await api.get("/api/proposals/prop_0123456789abcdef")).json()["error"]["code"] == "PROPOSAL_NOT_FOUND"
    assert (await api.get("/api/runs/run_0123456789abcdef")).json()["error"]["code"] == "RUN_NOT_FOUND"


async def test_approval_through_the_api_fills_the_slot_once(api, seeded):
    _, proposal = await staged_draft(services_for(seeded))
    listed = (await api.get("/api/proposals", params={"campaign_id": "camp_01"})).json()
    assert [p["id"] for p in listed] == [proposal["id"]] and listed[0]["approvable"] is True
    key = str(uuid.uuid4())
    res = await api.post(f"/api/proposals/{proposal['id']}/approve", headers=h(api, key), json={"expected_revision": 1})
    assert res.status_code == 200, res.text
    again = await api.post(f"/api/proposals/{proposal['id']}/approve", headers=h(api, key),
                           json={"expected_revision": 1})
    assert again.json()["decision_id"] == res.json()["decision_id"]
    campaigns = (await api.get("/api/campaigns")).json()
    assert next(c for c in campaigns if c["id"] == "camp_01")["approved_proposal_id"] == proposal["id"]


async def test_approval_needs_the_human_write_boundary(api, seeded):
    _, proposal = await staged_draft(services_for(seeded))
    no_nonce = {"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    res = await api.post(f"/api/proposals/{proposal['id']}/approve", headers=no_nonce, json={"expected_revision": 1})
    assert res.status_code == 403
    res = await api.post(f"/api/proposals/{proposal['id']}/approve", headers=h(api), json={})
    assert res.status_code == 422  # expected_revision is mandatory
    # There is no route that turns conversation text into an approval or a draft.
    assert (await api.post("/api/proposals", headers=h(api), json={"creator_id": "cr_02"})).status_code == 405
    assert (await api.post("/api/chat/approve", headers=h(api), json={"text": "approve"})).status_code == 404
