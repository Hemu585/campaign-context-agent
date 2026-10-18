"""Fixture-only scenario mutations for SYNTHETIC_DATA S02-S14 and T04-T07 edge cases.

These run raw Cypher on disposable test graphs only. They are not app routes; the
demo editor exposes just agreement/availability edits through versioned services.
Helpers that change an attested fact re-stamp the supporting source's fact hash, so a
scenario tests the intended rule rather than tripping SOURCE_MISMATCH.
"""

from __future__ import annotations

from helpers.graphq import cypher

from app.db.factsig import fact_hash
from app.timeutil import parse_iso_ms

LABEL_KIND = {"Offer": "offer", "Availability": "availability", "Agreement": "agreement",
              "Audit": "audit", "Campaign": "campaign"}


async def _node_fields(client, label: str, node_id: str) -> dict:
    rows = await cypher(client, f"MATCH (n:{label} {{id: $id}}) RETURN properties(n) AS p", {"id": node_id})
    fields = dict(rows[0]["p"])
    if label == "Agreement":
        b = await cypher(client, "MATCH (:Agreement {id: $id})-[:WITH_BRAND]->(b:Brand) RETURN b.id AS b",
                         {"id": node_id})
        fields["counterparty_brand_id"] = b[0]["b"] if b else None
    if label == "Campaign":
        b = await cypher(client, "MATCH (b:Brand)-[:RUNS]->(:Campaign {id: $id}) RETURN b.id AS b", {"id": node_id})
        fields["brand_id"] = b[0]["b"]
    return fields


async def refresh_fact_hash(client, label: str, node_id: str) -> str:
    digest = fact_hash(LABEL_KIND[label], await _node_fields(client, label, node_id))
    await cypher(client, f"MATCH (:{label} {{id: $id}})-[:SUPPORTED_BY]->(s:Source) SET s.fact_hash = $h",
                 {"id": node_id, "h": digest}, write=True)
    return digest


async def set_fact(client, label: str, node_id: str, **props) -> None:
    """Change attested fields on a fact node and re-stamp its source hash (None removes a field)."""
    for key, value in props.items():
        await cypher(client, f"MATCH (n:{label} {{id: $id}}) SET n.{key} = $v", {"id": node_id, "v": value},
                     write=True)
    await refresh_fact_hash(client, label, node_id)


async def set_source(client, source_id: str, **props) -> None:
    for key, value in props.items():
        await cypher(client, f"MATCH (s:Source {{id: $id}}) SET s.{key} = $v", {"id": source_id, "v": value},
                     write=True)


async def delete_node(client, label: str, node_id: str) -> None:
    await cypher(client, f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", {"id": node_id}, write=True)


async def reverse_competitor_edge(client, a: str, b: str) -> None:
    rows = await cypher(client, "MATCH (:Brand {id: $a})-[e:COMPETES_WITH]->(:Brand {id: $b}) "
                                "RETURN e.source_id AS s", {"a": a, "b": b})
    await cypher(client, "MATCH (:Brand {id: $a})-[e:COMPETES_WITH]->(:Brand {id: $b}) DELETE e",
                 {"a": a, "b": b}, write=True)
    await cypher(client, "MATCH (x:Brand {id: $b}), (y:Brand {id: $a}) CREATE (x)-[:COMPETES_WITH {source_id: $s}]->(y)",
                 {"a": a, "b": b, "s": rows[0]["s"]}, write=True)


async def remove_competitor_edge(client, a: str, b: str) -> None:
    await cypher(client, "MATCH (:Brand {id: $a})-[e:COMPETES_WITH]-(:Brand {id: $b}) DELETE e",
                 {"a": a, "b": b}, write=True)


async def add_brand(client, brand_id: str, name: str, category: str) -> None:
    await cypher(client, "MATCH (w:Workspace) CREATE (w)-[:HAS_BRAND]->(:Brand {id: $id, name: $n, category: $c})",
                 {"id": brand_id, "n": name, "c": category}, write=True)


async def add_competitor_edge(client, a: str, b: str, source_id: str) -> None:
    await cypher(client, "MATCH (x:Brand {id: $a}), (y:Brand {id: $b}) CREATE (x)-[:COMPETES_WITH {source_id: $s}]->(y)",
                 {"a": a, "b": b, "s": source_id}, write=True)


async def set_participation(client, creator_id: str, campaign_id: str, status: str, source_id: str) -> None:
    await cypher(client, "MATCH (r:Creator {id: $r}), (c:Campaign {id: $c}) "
                         "MERGE (r)-[p:PARTICIPATED_IN]->(c) SET p.status = $st, p.source_id = $s",
                 {"r": creator_id, "c": campaign_id, "st": status, "s": source_id}, write=True)


async def add_availability(client, creator_id: str, window_id: str, start: str, end: str, status: str,
                           observed_at: str = "2026-10-15T12:00:00Z") -> None:
    """New window with its own verified source (fixture-only; the demo editor cannot add windows)."""
    start_ms, end_ms = parse_iso_ms(start), parse_iso_ms(end)
    digest = fact_hash("availability", {"start_ms": start_ms, "end_ms": end_ms, "status": status})
    await cypher(
        client,
        "MATCH (r:Creator {id: $r}) "
        "CREATE (r)-[:HAS_AVAILABILITY]->(a:Availability {id: $id, start_ms: $s, end_ms: $e, status: $st})"
        "-[:SUPPORTED_BY]->(:Source {id: $sid, document_id: $doc, version: 1, kind: 'availability', "
        "title: 'Test fixture window', subject_id: $id, text: 'FICTIONAL DEMO DATA test fixture', "
        "checksum: 'test', fact_hash: $h, observed_at_ms: $obs, verified: true, synthetic: true})",
        {"r": creator_id, "id": window_id, "s": start_ms, "e": end_ms, "st": status, "sid": f"src_{window_id}_v1",
         "doc": window_id, "h": digest, "obs": parse_iso_ms(observed_at)},
        write=True,
    )


async def add_competing_source(client, label: str, node_id: str, source_id: str, digest: str,
                               observed_at_ms: int) -> None:
    """Attach a second, equally current source to a fact (T06 conflicting sources)."""
    await cypher(
        client,
        f"MATCH (n:{label} {{id: $id}}) CREATE (n)-[:SUPPORTED_BY]->(:Source {{id: $sid, document_id: $sid, "
        "version: 1, kind: 'offer', title: 'Competing test record', subject_id: $id, "
        "text: 'FICTIONAL DEMO DATA competing test record', checksum: 'test', fact_hash: $h, "
        "observed_at_ms: $obs, verified: true, synthetic: true})",
        {"id": node_id, "sid": source_id, "h": digest, "obs": observed_at_ms},
        write=True,
    )
