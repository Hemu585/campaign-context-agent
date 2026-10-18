"""T14 restart proof: operator records survive a FalkorDB restart and a container recreation on
the same named volume, and unfinished runs become interrupted after a backend restart.

    .venv/Scripts/python.exe scripts/persistence_check.py

Uses ONLY the separate test compose project (compose.test.yaml: port 6380, volume
campaign_context_test_data) and the graph campaign_context_persist. It never touches the demo
container, demo volume or demo graph, and never runs `docker compose down -v`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app.config import Settings
from app.db.client import GraphClient
from app.db.dataset import load_dataset
from app.db.seed import seed
from app.services.decisions import DecisionService
from app.services.evaluation import EvaluationService
from app.services.mutations import MutationService
from app.services.proposals import ProposalService
from app.services.sessions import SessionService

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-p", "campaign_context_test", "-f", "compose.test.yaml"]
CONTAINER = "campaign_context_test-falkordb-test-1"
GRAPH = "campaign_context_persist"


def compose(*args: str) -> None:
    subprocess.run([*COMPOSE, *args], cwd=ROOT, check=True, capture_output=True, text=True)


def wait_healthy(timeout_s: int = 90) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = subprocess.run(["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER],
                             capture_output=True, text=True)
        if out.stdout.strip() == "healthy":
            return
        time.sleep(1)
    raise SystemExit(f"{CONTAINER} did not become healthy")


class Stack:
    def __init__(self, settings: Settings):
        self.client = GraphClient(settings)
        self.mutations = MutationService(self.client, settings)
        self.evaluation = EvaluationService(self.client, settings)
        self.sessions = SessionService(self.client, self.mutations)
        self.decisions = DecisionService(self.client, self.mutations)
        self.proposals = ProposalService(self.client, self.mutations, self.evaluation)


async def snapshot(stack: Stack, run_ids: list[str]) -> dict:
    evaluation, ctx = await stack.evaluation.evaluate("camp_01")
    by_id = {c.creator_id: c.status for c in evaluation.candidates}
    sessions = await stack.sessions.list_sessions()
    messages = 0
    for s in sessions:
        messages += len((await stack.sessions.get_session(s["id"]))["messages"])
    return {
        "revision": evaluation.context_revision,
        "decisions": sorted((d["id"], d["action"], d["state"]) for d in await stack.decisions.list()),
        "proposals": sorted((p["id"], p["status"], p["approved_revision"]) for p in await stack.proposals.list()),
        "slot": ctx.campaign.approved_proposal_id,
        "sessions": len(sessions),
        "messages": messages,
        "runs": {rid: (await stack.sessions.get_run(rid))["status"] for rid in run_ids},
        "mira_status": by_id["cr_02"],
        "recommended": evaluation.recommended_creator_ids,
    }


async def build_records(settings: Settings) -> tuple[dict, list[str], str]:
    stack = Stack(settings)
    try:
        await stack.client.reset_graph_with_confirmation(GRAPH)
        await seed(stack.client, load_dataset("demo_v1"))
        session = await stack.sessions.create_session("Persistence check", str(uuid.uuid4()))
        await stack.decisions.reject(campaign_id="camp_01", creator_id="cr_02", scope_type="campaign",
                                     reason="Persistence check rejection", expires_at_ms=None, expected_revision=1,
                                     session_id=session["id"], key=str(uuid.uuid4()))
        run = await stack.sessions.create_run(session["id"], "camp_01", "Find a replacement", str(uuid.uuid4()),
                                              model="persistence-check", model_digest=None)
        await stack.sessions.update_run(run["id"], status="running")
        evaluation, ctx = await stack.evaluation.evaluate("camp_01")
        proposal = await stack.proposals.stage(run_id=run["id"], creator_id=evaluation.recommended_creator_ids[0],
                                               evaluation=evaluation, campaign=ctx.campaign)
        await stack.sessions.update_run(run["id"], status="completed")
        await stack.proposals.approve(proposal["id"], 2, str(uuid.uuid4()))
        pending = await stack.sessions.create_run(session["id"], "camp_01", "Unfinished run", str(uuid.uuid4()),
                                                  model="persistence-check", model_digest=None)
        await stack.sessions.update_run(pending["id"], status="running")
        run_ids = [run["id"], pending["id"]]
        return await snapshot(stack, run_ids), run_ids, pending["id"]
    finally:
        await stack.client.close()


async def read_state(settings: Settings, run_ids: list[str], *, backend_restart: bool = False) -> tuple[dict, int]:
    stack = Stack(settings)
    try:
        interrupted = await stack.sessions.mark_interrupted_on_startup() if backend_restart else 0
        return await snapshot(stack, run_ids), interrupted
    finally:
        await stack.client.close()


def report(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> int:
    settings = Settings(_env_file=None, falkordb_port=6380, falkordb_graph=GRAPH)
    compose("up", "-d")
    wait_healthy()
    before, run_ids, pending_id = asyncio.run(build_records(settings))
    print("records before restart:", json.dumps(before, default=list))
    results = [report("records created", before["revision"] == 3 and before["slot"] is not None
                      and before["mira_status"] == "excluded_by_memory",
                      f"revision {before['revision']}, slot {before['slot']}")]

    compose("restart", "falkordb-test")
    wait_healthy()
    after_restart, _ = asyncio.run(read_state(settings, run_ids))
    results.append(report("FalkorDB restart keeps sessions, decisions, proposals, slot and memory",
                          after_restart == before))

    after_backend, interrupted = asyncio.run(read_state(settings, run_ids, backend_restart=True))
    results.append(report("backend restart marks the unfinished run interrupted",
                          interrupted == 1 and after_backend["runs"][pending_id] == "interrupted"
                          and after_backend["runs"][run_ids[0]] == "completed"))

    compose("up", "-d", "--force-recreate", "falkordb-test")
    wait_healthy()
    after_recreate, _ = asyncio.run(read_state(settings, run_ids))
    results.append(report("container recreation with the same named volume keeps everything",
                          after_recreate == after_backend))
    results.append(report("memory and approval behaviour unchanged after recreation",
                          after_recreate["mira_status"] == "excluded_by_memory"
                          and after_recreate["recommended"] == before["recommended"]
                          and after_recreate["slot"] == before["slot"]))
    print("records after recreation:", json.dumps(after_recreate, default=list))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
