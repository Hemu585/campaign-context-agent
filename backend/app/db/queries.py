"""Named, versioned Cypher templates loaded from app/queries/*.cypher.

The file stem is the query ID (e.g. ``Q04_agreements``). Only these templates
can reach the database; values travel as bound parameters, never by string
interpolation, and no route or model can supply Cypher.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

QUERY_DIR = Path(__file__).resolve().parents[1] / "queries"


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//")).strip()


@lru_cache
def catalog() -> dict[str, str]:
    queries = {p.stem: _strip_comments(p.read_text(encoding="utf-8")) for p in sorted(QUERY_DIR.glob("*.cypher"))}
    if not queries:
        raise RuntimeError(f"no Cypher templates found in {QUERY_DIR}")
    return queries


def get(query_id: str) -> str:
    try:
        return catalog()[query_id]
    except KeyError:
        raise KeyError(f"unknown query id {query_id!r}") from None
