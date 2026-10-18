"""T11: versioned synthetic edits change the next result and preserve history (R13, R24; S05, S09 setup)."""

import uuid

import pytest
from helpers.graphq import cypher, scalar

from app.config import Settings
from app.errors import AppError
from app.services.demo_edits import DemoEditService
from app.services.evaluation import EvaluationService
from app.services.mutations import MutationService
from app.services.sessions import SessionService

AS_OF = 1792065600000


@pytest.fixture
def editor(seeded):
    return DemoEditService(seeded, MutationService(seeded, seeded.settings))


async def edit(editor, fact_type="agreement", fact_id="agr_cr03", changes=None, revision=1, key=None,
               reason="Noro Glow contract ended early (fictional)"):
    if changes is None:
        changes = {"end_at": "2026-10-19T23:59:59+05:30"}
    return await editor.edit(fact_type, fact_id, changes, reason, revision, key or str(uuid.uuid4()))


async def evaluate(client):
    evaluation, _ = await EvaluationService(client, client.settings).evaluate("camp_01")
    return evaluation, {c.creator_id: c for c in evaluation.candidates}


async def test_s05_agreement_edit_versions_sources_and_changes_the_result(editor, seeded):
    result = await edit(editor)
    assert result["source_id"] == "src_agreement_cr03_v2"
    assert result["supersedes"] == ["src_agreement_cr03_v1"]
    assert result["context_revision"] == 2
    links = await cypher(seeded, "MATCH (n:Source)-[:SUPERSEDES]->(o:Source) RETURN n.id AS n, o.id AS o ORDER BY n")
    assert links == [{"n": "src_agreement_cr03_v2", "o": "src_agreement_cr03_v1"},
                     {"n": "src_audit_cr03_v2", "o": "src_audit_cr03_v1"}]
    assert await scalar(seeded, "MATCH (:Agreement {id: 'agr_cr03'})-[:SUPPORTED_BY]->(s) RETURN s.id") == \
        "src_agreement_cr03_v2"
    evaluation, by_id = await evaluate(seeded)
    assert by_id["cr_03"].status == "eligible" and by_id["cr_03"].rank == 1
    assert evaluation.recommended_creator_ids == ["cr_03", "cr_02", "cr_04"]
    assert evaluation.context_revision == 2


async def test_new_source_is_operator_attested_at_the_business_clock(editor, seeded):
    await edit(editor)
    src = (await cypher(seeded, "MATCH (s:Source {id: 'src_agreement_cr03_v2'}) RETURN properties(s) AS p"))[0]["p"]
    assert src["observed_at_ms"] == AS_OF and src["verified"] is True and src["synthetic"] is True
    assert src["editor"] == "local_demo_operator" and src["version"] == 2
    assert "Operator text (untrusted, shown as data): Noro Glow contract ended early" in src["text"]
    assert "19 Oct 2026, 23:59:59 IST" in src["text"]
    old = (await cypher(seeded, "MATCH (s:Source {id: 'src_agreement_cr03_v1'}) RETURN s.text AS t"))[0]["t"]
    assert "31 Oct 2026, 23:59:59 IST" in old  # the old version is kept unchanged


async def test_saved_snapshot_is_not_rewritten_by_a_later_edit(editor, seeded):
    sessions = SessionService(seeded, editor.mutations)
    session = await sessions.create_session("S", str(uuid.uuid4()))
    run = await sessions.create_run(session["id"], "camp_01", "find", str(uuid.uuid4()), model="m", model_digest=None)
    before, _ = await evaluate(seeded)
    await sessions.update_run(run["id"], status="completed", evaluation=before.model_dump(mode="json"))
    await edit(editor)
    saved = (await sessions.get_run(run["id"]))["evaluation"]
    assert saved["recommended_creator_ids"] == ["cr_02", "cr_04", "cr_09"]
    assert saved["context_revision"] == 1


async def test_s09_setup_availability_edit_makes_mira_unavailable(editor, seeded):
    result = await edit(editor, "availability", "avail_cr02", {"status": "unavailable"},
                        reason="Mira is travelling (fictional)")
    assert result["source_id"] == "src_avail_cr02_v2" and result["fact"]["status"] == "unavailable"
    _, by_id = await evaluate(seeded)
    assert by_id["cr_02"].status == "ineligible"
    assert by_id["cr_02"].failed_checks == ["availability"]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"end_at": "2026-12-15T23:59:59+05:30"}, "INVALID_INTERVAL"),  # outside audit coverage
        ({"start_at": "2026-10-25T00:00:00+05:30", "end_at": "2026-10-24T00:00:00+05:30"}, "INVALID_INTERVAL"),
        ({"end_at": "2026-10-19T23:59:59"}, "INVALID_INTERVAL"),  # naive time
        ({"status": "paused"}, "INVALID_INPUT"),
        ({"verified": False}, "UNKNOWN_TOOL_ARGUMENT"),
        ({"source_id": "src_fake_v9"}, "UNKNOWN_TOOL_ARGUMENT"),
        ({}, "INVALID_INPUT"),
        ({"end_at": "2026-10-31T23:59:59+05:30"}, "INVALID_INPUT"),  # no actual change
    ],
)
async def test_invalid_edits_write_nothing(editor, seeded, changes, code):
    with pytest.raises(AppError) as info:
        await edit(editor, changes=changes)
    assert info.value.code == code
    assert await scalar(seeded, "MATCH (w:Workspace) RETURN w.context_revision") == 1
    assert await scalar(seeded, "MATCH (s:Source) RETURN count(s)") == 49


async def test_demo_mode_off_disables_editing(seeded):
    settings = Settings(_env_file=None, falkordb_graph=seeded.graph_name, demo_mode=False)
    service = DemoEditService(seeded, MutationService(seeded, settings))
    with pytest.raises(AppError) as info:
        await edit(service)
    assert (info.value.code, info.value.status) == ("DEMO_EDIT_DISABLED", 403)


async def test_stale_revision_and_replay(editor, seeded):
    with pytest.raises(AppError) as info:
        await edit(editor, revision=5)
    assert info.value.code == "STALE_CONTEXT"
    key = str(uuid.uuid4())
    first = await edit(editor, key=key)
    second = await edit(editor, key=key)
    assert first["source_id"] == second["source_id"]
    assert await scalar(seeded, "MATCH (w:Workspace) RETURN w.context_revision") == 2


async def test_editor_lists_only_agreements_and_windows(editor):
    facts = await editor.list_facts()
    assert [a["id"] for a in facts["agreements"]] == ["agr_cr03", "agr_cr09", "agr_cr10"]
    assert len(facts["availability"]) == 13 and facts["demo_mode"] is True
