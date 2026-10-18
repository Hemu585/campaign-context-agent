"""Backend for the Playwright demo flow (T18): a freshly seeded e2e graph on its own port.

Resets and re-seeds ONLY the `campaign_context_e2e` graph (never the demo graph), then
serves the API on 127.0.0.1:8001 for the e2e UI origin http://127.0.0.1:5174, so the
normal dev servers on 8000/5173 can keep running. Started by frontend/playwright.config.ts.
"""

from __future__ import annotations

import os
import subprocess
import sys

GRAPH = "campaign_context_e2e"
API_PORT = 8001
UI_ORIGIN = "http://127.0.0.1:5174"

os.environ.update({"FALKORDB_GRAPH": GRAPH, "ALLOWED_ORIGINS": UI_ORIGIN})


def cli(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "app.cli", *args], check=True)


if __name__ == "__main__":
    cli("reset-demo", "--graph", GRAPH, "--confirm", GRAPH)
    cli("seed", "--graph", GRAPH, "--dataset", "demo_v1")
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=API_PORT, workers=1)
