"""Print the deterministic rule-check result for a campaign from the live graph, with timings.

    .venv/Scripts/python.exe scripts/show_evaluation.py --campaign camp_01 --runs 4

Diagnostic only (no AI run). Times one cold and several warm evaluations, which
include all graph reads (Q00-Q07) plus the rule engine.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from app.config import Settings
from app.db.client import GraphClient
from app.money import format_inr
from app.services.evaluation import EvaluationService


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console code page cannot print "₹"
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", default="camp_01")
    parser.add_argument("--runs", type=int, default=4)
    args = parser.parse_args()
    settings = Settings()
    client = GraphClient(settings)
    service = EvaluationService(client, settings)
    timings = []
    try:
        for _ in range(args.runs):
            started = time.perf_counter()
            evaluation, _ = await service.evaluate(args.campaign)
            timings.append((time.perf_counter() - started) * 1000)
    finally:
        await client.close()
    print(f"graph {settings.falkordb_graph} | campaign {args.campaign} | revision {evaluation.context_revision}")
    print(f"recommended: {evaluation.recommended_creator_ids}")
    for c in evaluation.candidates:
        problems = [ch for ch in c.checks if ch.result in ("fail", "unknown")]
        why = "; ".join(f"{ch.name}={ch.reason_code}" for ch in problems) or "all checks pass"
        fee = format_inr(c.fee_paise) if c.fee_paise is not None else "-"
        rank = c.rank if c.rank is not None else "-"
        print(f"  {c.creator_id} {c.name:<11} {c.status:<18} rank {rank!s:<2} fee {fee:<8} {why}")
    print("evaluation ms: cold {:.1f}; warm {}".format(timings[0], ", ".join(f"{t:.1f}" for t in timings[1:])))


if __name__ == "__main__":
    asyncio.run(main())
