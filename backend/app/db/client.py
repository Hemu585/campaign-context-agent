"""Async FalkorDB adapter: named queries only, read-only path, timeouts, error mapping.

There is deliberately no fallback: if the graph is down, callers get
GRAPH_UNAVAILABLE instead of an answer built from the fixture file (R02, T15).
"""

from __future__ import annotations

from typing import Any

from falkordb.asyncio.graph import AsyncGraph
from redis import exceptions as redis_errors
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.config import Settings
from app.db import queries
from app.errors import AppError, graph_unavailable

TEST_GRAPH_PREFIX = "campaign_context_test_"
# Graphs a human may reset explicitly (never automatically) via `app.cli reset-demo`.
RESETTABLE_GRAPHS = {"campaign_context_demo", "campaign_context_e2e", "campaign_context_persist"}
_UNREACHABLE = (redis_errors.ConnectionError, redis_errors.TimeoutError, ConnectionError, OSError)


def _rows(result) -> list[dict[str, Any]]:
    names = [col[1] for col in (result.header or [])]
    return [dict(zip(names, row, strict=True)) for row in (result.result_set or [])]


def no_seed_data() -> AppError:
    return AppError("NO_SEED_DATA",
                    "The graph has no data yet. Run `python -m app.cli seed --dataset demo_v1` first.", 503)


class GraphClient:
    def __init__(self, settings: Settings, graph_name: str | None = None):
        self.settings = settings
        self.graph_name = graph_name or settings.falkordb_graph
        # A plain async Redis connection: falkordb's FalkorDB() constructor runs a blocking
        # synchronous INFO probe for cluster mode, which fails (and blocks) whenever the
        # database is down. This app talks to one local node, so the probe is skipped.
        self._conn = Redis(
            host=settings.falkordb_host,
            port=settings.falkordb_port,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=15,
            # One immediate retry re-dials a pooled connection that died with a FalkorDB
            # restart; more retries with backoff only delay an honest GRAPH_UNAVAILABLE.
            retry=Retry(NoBackoff(), 1),
        )
        self._graph = AsyncGraph(self._conn, self.graph_name)

    async def query(self, query_id: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Run a named write (or read/write) template."""
        return _rows(await self._execute(queries.get(query_id), params, read_only=False))

    async def ro_query(self, query_id: str, params: dict | None = None) -> list[dict[str, Any]]:
        """Run a named template through GRAPH.RO_QUERY; the server refuses any write in it."""
        return _rows(await self._execute(queries.get(query_id), params, read_only=True))

    async def query_stats(self, query_id: str, params: dict | None = None):
        """Like query() but returns the raw result (rows plus write counters)."""
        result = await self._execute(queries.get(query_id), params, read_only=False)
        return _rows(result), result

    async def _execute(self, cypher: str, params: dict | None, *, read_only: bool):
        try:
            if read_only:
                return await self._graph.ro_query(cypher, params or {}, timeout=self.settings.query_timeout_ms)
            return await self._graph.query(cypher, params or {})
        except _UNREACHABLE as exc:
            raise graph_unavailable() from exc
        except redis_errors.ResponseError as exc:
            text = str(exc).lower()
            if "timed out" in text:
                raise AppError("QUERY_TIMEOUT", "A graph query took too long and was stopped.", 503,
                               retryable=True) from exc
            if "empty key" in text:
                raise no_seed_data() from exc
            raise

    async def run_catalog_script(self, query_id: str, *, tolerate: tuple[str, ...] = ()) -> int:
        """Run a ';'-separated catalog file (index setup). Errors containing a tolerated phrase are skipped."""
        executed = 0
        for statement in (s.strip() for s in queries.get(query_id).split(";")):
            if not statement:
                continue
            try:
                await self._execute(statement, None, read_only=False)
                executed += 1
            except redis_errors.ResponseError as exc:
                if not any(phrase in str(exc) for phrase in tolerate):
                    raise
        return executed

    async def server_config(self, *names: str) -> dict[str, str]:
        """Redis CONFIG GET values (persistence checks in `app.cli preflight`)."""
        out: dict[str, str] = {}
        try:
            for name in names:
                out.update(await self._conn.config_get(name))
        except _UNREACHABLE as exc:
            raise graph_unavailable() from exc
        return out

    async def ping(self) -> bool:
        try:
            return bool(await self._conn.ping())
        except _UNREACHABLE:
            return False

    async def graph_exists(self) -> bool:
        try:
            return self.graph_name in (await self._conn.execute_command("GRAPH.LIST") or [])
        except _UNREACHABLE as exc:
            raise graph_unavailable() from exc

    async def delete_graph(self, *, missing_ok: bool = True) -> None:
        """Delete this client's graph. Only disposable test graphs may be deleted here."""
        if not self.graph_name.startswith(TEST_GRAPH_PREFIX):
            raise PermissionError(f"refusing to delete non-test graph {self.graph_name!r}")
        try:
            await self._graph.delete()
        except redis_errors.ResponseError:
            if not missing_ok:
                raise

    async def reset_graph_with_confirmation(self, confirm: str) -> bool:
        """Explicit human reset of the demo/e2e/persist graph. Returns False if it did not exist."""
        if self.graph_name not in RESETTABLE_GRAPHS or confirm != self.graph_name:
            raise PermissionError(f"reset of {self.graph_name!r} needs --confirm {self.graph_name}")
        if not await self.graph_exists():
            return False
        await self._graph.delete()
        return True

    async def close(self) -> None:
        await self._conn.aclose()
