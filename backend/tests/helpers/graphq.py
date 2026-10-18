"""Raw Cypher for test assertions and fixture-only scenario setup."""

from __future__ import annotations

from app.db.client import GraphClient, _rows


async def cypher(client: GraphClient, text: str, params: dict | None = None, *, write: bool = False) -> list[dict]:
    return _rows(await client._execute(text, params, read_only=not write))


async def scalar(client: GraphClient, text: str, params: dict | None = None):
    rows = await cypher(client, text, params)
    return next(iter(rows[0].values())) if rows else None


async def label_counts(client: GraphClient) -> dict[str, int]:
    rows = await cypher(client, "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY label")
    return {r["label"]: r["n"] for r in rows}


async def edge_counts(client: GraphClient) -> dict[str, int]:
    rows = await cypher(client, "MATCH ()-[e]->() RETURN type(e) AS type, count(e) AS n ORDER BY type")
    return {r["type"]: r["n"] for r in rows}
