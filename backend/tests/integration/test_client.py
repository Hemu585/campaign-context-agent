"""Graph client against the real FalkorDB (T02/T15 prerequisites)."""

import pytest

from app.config import Settings
from app.db import queries
from app.db.client import GraphClient
from app.errors import AppError


async def test_unseeded_graph_reports_no_seed_data(graph):
    assert await graph.ping() is True
    assert await graph.graph_exists() is False
    with pytest.raises(AppError) as info:
        await graph.ro_query("Q00_revision")
    assert info.value.code == "NO_SEED_DATA"


async def test_reads_work_once_the_graph_exists(graph):
    await graph._execute("CREATE (:Marker {id: 'm1'})", None, read_only=False)
    assert await graph.graph_exists() is True
    assert await graph.ro_query("Q00_revision") == []  # no Workspace node yet


async def test_read_only_path_refuses_writes(graph):
    from redis.exceptions import ResponseError

    await graph._execute("CREATE (:Marker {id: 'm1'})", None, read_only=False)
    with pytest.raises(ResponseError, match="read-only"):
        await graph._execute("CREATE (:ShouldFail)", None, read_only=True)


async def test_unreachable_database_is_reported_not_faked():
    settings = Settings(_env_file=None, falkordb_port=6399, falkordb_graph="campaign_context_test_down")
    client = GraphClient(settings)
    try:
        assert await client.ping() is False
        with pytest.raises(AppError) as info:
            await client.ro_query("Q00_revision")
        assert info.value.code == "GRAPH_UNAVAILABLE"
        assert info.value.status == 503
    finally:
        await client.close()


def test_unknown_query_ids_are_rejected():
    with pytest.raises(KeyError):
        queries.get("NOPE")


def test_query_catalog_strips_comments():
    text = queries.get("Q00_revision")
    assert "//" not in text and text.startswith("MATCH")


async def test_only_test_graphs_can_be_deleted():
    client = GraphClient(Settings(_env_file=None, falkordb_graph="campaign_context_demo"))
    try:
        with pytest.raises(PermissionError):
            await client.delete_graph()
    finally:
        await client.close()
