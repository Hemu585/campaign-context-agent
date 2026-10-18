"""Export the backend's OpenAPI schema to frontend/openapi.json (input for TypeScript type generation).

    .venv/Scripts/python.exe scripts/export_openapi.py
    npm --prefix frontend run gen:api

A unit test fails if the committed file drifts from the running app's schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def current_schema() -> dict:
    return create_app(Settings(_env_file=None)).openapi()


def render(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render(current_schema()), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
