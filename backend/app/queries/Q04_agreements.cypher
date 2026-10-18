// Q04: every creator agreement, including incomplete records, with its counterparty brand and
// whether that brand DIRECTLY competes with the campaign's client. COMPETES_WITH is traversed
// undirected and only one hop: no transitive competitor inference (read-only).
// Finds candidate conflict paths; it does not prove their absence (audits do that, Q05).
MATCH (client:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (w:Workspace)-[:HAS_CREATOR]->(r:Creator)-[:HAS_AGREEMENT]->(a:Agreement)
OPTIONAL MATCH (a)-[:WITH_BRAND]->(other:Brand)
OPTIONAL MATCH (other)-[cw:COMPETES_WITH]-(client)
OPTIONAL MATCH (a)-[:SUPPORTED_BY]->(s:Source)
RETURN r.id AS creator_id, a.id AS id, a.exclusive AS exclusive, a.channel AS channel,
       a.category AS category, a.start_ms AS start_ms, a.end_ms AS end_ms, a.status AS status,
       other.id AS counterparty_brand_id, other.name AS counterparty_name,
       count(DISTINCT cw) AS competitor_edges,
       collect(DISTINCT cw.source_id) AS competitor_edge_source_ids,
       collect(DISTINCT s.id) AS source_ids
ORDER BY creator_id, id
