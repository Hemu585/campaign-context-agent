"""Command line: seed, reset-demo (explicit), preflight and verify-model.

    .venv/Scripts/python.exe -m app.cli seed --dataset demo_v1
    .venv/Scripts/python.exe -m app.cli reset-demo --confirm campaign_context_demo
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.agent.ollama import probe_model
from app.agent.verify import verify_model
from app.config import Settings
from app.db.client import GraphClient
from app.db.dataset import load_dataset
from app.db.seed import SeedVersionMismatch, seed, workspace_state

SCENARIOS = ["baseline", "baseline_repeat", "memory", "agreement_change", "no_candidate", "injection"]


async def _preflight(settings: Settings) -> int:
    """Read-only checks of services, persistence settings, seed state and local model."""
    rows: list[tuple[str, bool, str]] = [
        ("Config is local-only", True,
         f"graph {settings.falkordb_host}:{settings.falkordb_port}, model {settings.ollama_base_url}"),
    ]
    client = GraphClient(settings)
    try:
        reachable = await client.ping()
        rows.append(("FalkorDB reachable", reachable, f"{settings.falkordb_host}:{settings.falkordb_port}"))
        if reachable:
            cfg = await client.server_config("dir", "appendonly", "appendfsync")
            rows.append(("FalkorDB data dir on the volume", cfg.get("dir") == "/data", f"dir={cfg.get('dir')}"))
            rows.append(("FalkorDB AOF persistence", cfg.get("appendonly") == "yes",
                         f"appendonly={cfg.get('appendonly')} appendfsync={cfg.get('appendfsync')}"))
            state = await workspace_state(client)
            seeded = bool(state and state["seed_status"] == "complete")
            rows.append(("Graph seeded", seeded,
                         f"{settings.falkordb_graph}: " + (f"{state['dataset_version']} revision {state['revision']}"
                                                           if state else "empty (run app.cli seed)")))
    finally:
        await client.close()
    model = await probe_model(settings)
    rows.append(("Ollama reachable on loopback", model.reachable,
                 f"{settings.ollama_base_url} version {model.server_version or '?'}"))
    rows.append(("Local model installed", model.installed,
                 f"{model.tag} digest {model.digest[:12] if model.digest else '-'}"))
    width = max(len(r[0]) for r in rows)
    for name, ok, detail in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    return 0 if all(ok for _, ok, _ in rows) else 1


async def _seed(settings: Settings, dataset: str) -> int:
    ds = load_dataset(dataset)
    client = GraphClient(settings)
    try:
        if not await client.ping():
            print("FalkorDB is not reachable on "
                  f"{settings.falkordb_host}:{settings.falkordb_port}. Run `docker compose up -d`.")
            return 2
        try:
            outcome = await seed(client, ds)
        except SeedVersionMismatch as exc:
            print(f"refused: {exc}")
            return 3
        print(f"{outcome}: dataset {ds.version} in graph {settings.falkordb_graph} "
              f"({len(ds.creators)} creators, {len(ds.campaigns)} campaigns, {len(ds.sources)} sources)")
        return 0
    finally:
        await client.close()


async def _reset(settings: Settings, confirm: str) -> int:
    client = GraphClient(settings)
    try:
        try:
            existed = await client.reset_graph_with_confirmation(confirm)
        except PermissionError as exc:
            print(f"refused: {exc}")
            return 3
        print(f"{'deleted' if existed else 'nothing to delete for'} graph {settings.falkordb_graph}. "
              "Run `app.cli seed` to load the fixture again.")
        return 0
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_seed = sub.add_parser("seed", help="load a fictional dataset into an empty graph (never overwrites)")
    p_seed.add_argument("--dataset", default="demo_v1")
    p_seed.add_argument("--graph", help="graph name (defaults to FALKORDB_GRAPH)")
    p_reset = sub.add_parser("reset-demo", help="explicitly delete the demo/e2e graph so it can be re-seeded")
    p_reset.add_argument("--graph", help="graph name (defaults to FALKORDB_GRAPH)")
    p_reset.add_argument("--confirm", required=True, help="must repeat the exact graph name")
    p_pre = sub.add_parser("preflight", help="read-only check of FalkorDB, persistence, seed and local model")
    p_pre.add_argument("--graph", help="graph name (defaults to FALKORDB_GRAPH)")
    p_vm = sub.add_parser("verify-model", help="run the REAL local model through the acceptance scenarios")
    p_vm.add_argument("--scenarios", default=",".join(SCENARIOS),
                      help=f"comma-separated subset of: {', '.join(SCENARIOS)}")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles cannot print "₹" otherwise

    overrides = {"falkordb_graph": args.graph} if getattr(args, "graph", None) else {}
    settings = Settings(**overrides)
    if args.command == "seed":
        return asyncio.run(_seed(settings, args.dataset))
    if args.command == "reset-demo":
        return asyncio.run(_reset(settings, args.confirm))
    if args.command == "preflight":
        return asyncio.run(_preflight(settings))
    if args.command == "verify-model":
        chosen = [s.strip() for s in args.scenarios.split(",") if s.strip()]
        unknown = set(chosen) - set(SCENARIOS)
        if unknown:
            parser.error(f"unknown scenario(s): {', '.join(sorted(unknown))}")
        passed, report = asyncio.run(verify_model(settings, chosen))
        print(f"{'ALL PASS' if passed else 'SOME FAILED'}; report: {report}")
        return 0 if passed else 1
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
