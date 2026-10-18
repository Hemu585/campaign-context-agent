"""T02: deterministic, idempotent seeding with an explicit dataset version."""

import pytest
from helpers.graphq import cypher, edge_counts, label_counts, scalar

from app.db.dataset import load_dataset
from app.db.seed import SeedVersionMismatch, seed

EXPECTED_NODES = {
    "Agreement": 3, "Audit": 13, "Availability": 13, "Brand": 5, "Campaign": 8, "Creator": 12,
    "Offer": 12, "Source": 49, "Workspace": 1,
}
EXPECTED_EDGES = {
    "COMPETES_WITH": 1, "HAS_AGREEMENT": 3, "HAS_AUDIT": 13, "HAS_AVAILABILITY": 13, "HAS_BRAND": 5,
    "HAS_CREATOR": 12, "OFFERS": 12, "PARTICIPATED_IN": 8, "RUNS": 8, "SUPPORTED_BY": 49, "WITH_BRAND": 3,
}


async def _all_ids(client):
    rows = await cypher(client, "MATCH (n) RETURN n.id AS id ORDER BY id")
    return [r["id"] for r in rows]


async def test_first_seed_loads_every_record_and_starts_revision_at_one(graph):
    assert await seed(graph, load_dataset("demo_v1")) == "seeded"
    assert await label_counts(graph) == EXPECTED_NODES
    assert await edge_counts(graph) == EXPECTED_EDGES
    ws = (await cypher(graph, "MATCH (w:Workspace) RETURN w.context_revision AS rev, w.seed_status AS st, "
                              "w.dataset_version AS v"))[0]
    assert ws == {"rev": 1, "st": "complete", "v": "demo_v1"}


async def test_seeding_twice_changes_nothing(graph):
    ds = load_dataset("demo_v1")
    await seed(graph, ds)
    ids, nodes, edges = await _all_ids(graph), await label_counts(graph), await edge_counts(graph)
    assert await seed(graph, ds) == "already seeded"
    assert await _all_ids(graph) == ids
    assert await label_counts(graph) == nodes
    assert await edge_counts(graph) == edges


async def test_reseed_does_not_undo_an_edit(graph):
    ds = load_dataset("demo_v1")
    await seed(graph, ds)
    await cypher(graph, "MATCH (a:Agreement {id: 'agr_cr03'}) SET a.end_ms = 42", write=True)
    await seed(graph, ds)
    assert await scalar(graph, "MATCH (a:Agreement {id: 'agr_cr03'}) RETURN a.end_ms") == 42


async def test_interrupted_load_resumes_without_duplicates(graph):
    ds = load_dataset("demo_v1")
    await seed(graph, ds)
    await cypher(graph, "MATCH (w:Workspace) SET w.seed_status = 'loading'", write=True)
    assert await seed(graph, ds) == "seeded"
    assert await label_counts(graph) == EXPECTED_NODES
    assert await edge_counts(graph) == EXPECTED_EDGES


async def test_a_different_dataset_version_is_refused(graph):
    ds = load_dataset("demo_v1")
    await seed(graph, ds)
    ds.version = "demo_v2"
    with pytest.raises(SeedVersionMismatch):
        await seed(graph, ds)


async def test_every_edge_source_id_resolves(graph):
    await seed(graph, load_dataset("demo_v1"))
    assert await scalar(graph, "MATCH ()-[e]->() WHERE e.source_id IS NOT NULL "
                               "OPTIONAL MATCH (s:Source {id: e.source_id}) WITH e, s WHERE s IS NULL "
                               "RETURN count(e)") == 0


async def test_stored_source_text_matches_its_checksum(graph):
    import hashlib

    await seed(graph, load_dataset("demo_v1"))
    rows = await cypher(graph, "MATCH (s:Source) RETURN s.text AS text, s.checksum AS checksum")
    assert len(rows) == 49
    for r in rows:
        assert hashlib.sha256(r["text"].encode("utf-8")).hexdigest() == r["checksum"]
