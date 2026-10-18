"""Shared fixtures. Integration tests run against the real FalkorDB on 127.0.0.1:6379.

Each test gets its own disposable graph ``campaign_context_test_<uuid>`` and deletes
only that graph afterwards (ACCEPTANCE_TESTS "Destructive test boundary"). If
FalkorDB is down the tests fail loudly; they never skip, because a skip would hide
missing graph coverage.
"""

from __future__ import annotations

import uuid

import pytest

from app.config import Settings
from app.db.client import GraphClient
from app.db.dataset import load_dataset
from app.db.seed import seed

FALKORDB_DOWN = (
    "FalkorDB is not reachable on 127.0.0.1:6379. Start Docker Desktop, then run "
    "`docker compose up -d`. Integration tests do not skip."
)


def new_test_settings(**overrides) -> Settings:
    name = f"campaign_context_test_{uuid.uuid4().hex[:12]}"
    return Settings(_env_file=None, falkordb_graph=name, **overrides)


@pytest.fixture
def test_settings() -> Settings:
    return new_test_settings()


@pytest.fixture
async def graph(test_settings):
    client = GraphClient(test_settings)
    if not await client.ping():
        await client.close()
        pytest.fail(FALKORDB_DOWN)
    try:
        yield client
    finally:
        await client.delete_graph(missing_ok=True)
        await client.close()


@pytest.fixture
async def seeded(graph):
    """A disposable graph holding the baseline demo_v1 fixture (scenario S01)."""
    await seed(graph, load_dataset("demo_v1"))
    return graph
