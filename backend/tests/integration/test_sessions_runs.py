"""Mutation core (receipts, replay, conflicts, lock) and persistent sessions/runs (R15, R16, T13 part)."""

import asyncio
import uuid

import pytest
from helpers.graphq import scalar

from app.errors import AppError
from app.services.mutations import MutationService
from app.services.sessions import SessionService


@pytest.fixture
def services(seeded):
    mutations = MutationService(seeded, seeded.settings)
    return mutations, SessionService(seeded, mutations)


async def revision(client):
    return await scalar(client, "MATCH (w:Workspace) RETURN w.context_revision")


async def test_same_key_same_payload_replays_without_a_second_write(services, seeded):
    _, sessions = services
    key = str(uuid.uuid4())
    first = await sessions.create_session("Replacement for Luma", key)
    second = await sessions.create_session("Replacement for Luma", key)
    assert first["id"] == second["id"]
    assert await scalar(seeded, "MATCH (s:Session) RETURN count(s)") == 1
    assert await scalar(seeded, "MATCH (r:MutationReceipt) RETURN count(r)") == 1


async def test_same_key_different_payload_is_a_conflict(services):
    _, sessions = services
    key = str(uuid.uuid4())
    await sessions.create_session("A", key)
    with pytest.raises(AppError) as info:
        await sessions.create_session("B", key)
    assert (info.value.code, info.value.status) == ("IDEMPOTENCY_CONFLICT", 409)


async def test_same_key_for_a_different_operation_is_a_conflict(services):
    _, sessions = services
    key = str(uuid.uuid4())
    session = await sessions.create_session("A", key)
    with pytest.raises(AppError) as info:
        await sessions.create_run(session["id"], "camp_01", "Find a replacement", key,
                                  model="m", model_digest=None)
    assert info.value.code == "IDEMPOTENCY_CONFLICT"


async def test_failed_perform_stores_no_receipt(services, seeded):
    mutations, _ = services

    async def perform(_digest):
        raise AppError("STALE_CONTEXT", "nope", 409)

    with pytest.raises(AppError):
        await mutations.run("noop", "k-1", {}, perform)
    assert await mutations.receipt("k-1") is None


async def test_the_lock_serializes_mutations(services):
    mutations, _ = services
    order = []

    def make(name):
        async def perform(_digest):
            order.append(f"{name}-start")
            await asyncio.sleep(0.05)
            order.append(f"{name}-end")
            raise AppError("STALE_CONTEXT", "test", 409)
        return perform

    results = await asyncio.gather(mutations.run("a", "ka", {}, make("a")), mutations.run("b", "kb", {}, make("b")),
                                   return_exceptions=True)
    assert all(isinstance(r, AppError) for r in results)
    assert order in (["a-start", "a-end", "b-start", "b-end"], ["b-start", "b-end", "a-start", "a-end"])


async def test_sessions_list_newest_first_and_survive_reads(services):
    _, sessions = services
    s1 = await sessions.create_session("First", str(uuid.uuid4()))
    await asyncio.sleep(0.01)
    s2 = await sessions.create_session("Second", str(uuid.uuid4()))
    listed = await sessions.list_sessions()
    assert [s["id"] for s in listed] == [s2["id"], s1["id"]]


async def test_run_and_user_message_are_created_together_without_changing_revision(services, seeded):
    _, sessions = services
    session = await sessions.create_session("S", str(uuid.uuid4()))
    run = await sessions.create_run(session["id"], "camp_01", "  Find a replacement  ", str(uuid.uuid4()),
                                    model="qwen3:4b-instruct-2507-q4_K_M", model_digest="0edcdef34593")
    assert run["status"] == "queued" and run["campaign_id"] == "camp_01"
    assert run["context_revision"] == 1 and run["as_of_ms"] == 1792065600000
    detail = await sessions.get_session(session["id"])
    assert [(m["role"], m["text"]) for m in detail["messages"]] == [("user", "Find a replacement")]
    assert [r["id"] for r in detail["runs"]] == [run["id"]]
    assert await revision(seeded) == 1


@pytest.mark.parametrize("message", ["", "   ", "x" * 4001])
async def test_run_message_length_is_validated(services, message):
    _, sessions = services
    session = await sessions.create_session("S", str(uuid.uuid4()))
    with pytest.raises(AppError) as info:
        await sessions.create_run(session["id"], "camp_01", message, str(uuid.uuid4()), model="m", model_digest=None)
    assert info.value.code == "INVALID_INPUT"


async def test_run_for_unknown_campaign_or_session_is_404(services):
    _, sessions = services
    session = await sessions.create_session("S", str(uuid.uuid4()))
    with pytest.raises(AppError) as info:
        await sessions.create_run(session["id"], "camp_99", "hi", str(uuid.uuid4()), model="m", model_digest=None)
    assert info.value.code == "CAMPAIGN_NOT_FOUND"
    with pytest.raises(AppError) as info:
        await sessions.create_run("ses_missing", "camp_01", "hi", str(uuid.uuid4()), model="m", model_digest=None)
    assert info.value.code == "SESSION_NOT_FOUND"


async def test_trace_and_evaluation_round_trip_as_bounded_json(services):
    _, sessions = services
    session = await sessions.create_session("S", str(uuid.uuid4()))
    run = await sessions.create_run(session["id"], "camp_01", "hi", str(uuid.uuid4()), model="m", model_digest=None)
    trace = [{"tool": "evaluate_candidates", "status": "ok", "elapsed_ms": 31, "record_ids": ["cr_02"]}]
    await sessions.update_run(run["id"], status="running", phase="checking_candidates", trace=trace,
                              evaluation={"recommended_creator_ids": ["cr_02"]})
    loaded = await sessions.get_run(run["id"])
    assert loaded["status"] == "running" and loaded["trace"] == trace
    assert loaded["evaluation"] == {"recommended_creator_ids": ["cr_02"]}


async def test_unfinished_runs_become_interrupted_on_startup(services):
    _, sessions = services
    session = await sessions.create_session("S", str(uuid.uuid4()))
    queued = await sessions.create_run(session["id"], "camp_01", "a", str(uuid.uuid4()), model="m", model_digest=None)
    running = await sessions.create_run(session["id"], "camp_01", "b", str(uuid.uuid4()), model="m", model_digest=None)
    done = await sessions.create_run(session["id"], "camp_01", "c", str(uuid.uuid4()), model="m", model_digest=None)
    await sessions.update_run(running["id"], status="running")
    await sessions.update_run(done["id"], status="completed")
    assert await sessions.mark_interrupted_on_startup() == 2
    assert (await sessions.get_run(queued["id"]))["status"] == "interrupted"
    assert (await sessions.get_run(running["id"]))["error"]["code"] == "RUN_INTERRUPTED"
    assert (await sessions.get_run(done["id"]))["status"] == "completed"
    detail = await sessions.get_session(session["id"])
    assert len(detail["messages"]) == 3  # transcript kept
