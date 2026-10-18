// Q13: agreements the demo editor may change, with current values and source version (read-only).
MATCH (r:Creator)-[:HAS_AGREEMENT]->(a:Agreement)-[:SUPPORTED_BY]->(s:Source)
OPTIONAL MATCH (a)-[:WITH_BRAND]->(b:Brand)
RETURN a.id AS id, r.id AS creator_id, r.name AS creator_name, b.id AS counterparty_brand_id,
       b.name AS counterparty_name, a.exclusive AS exclusive, a.channel AS channel, a.category AS category,
       a.start_ms AS start_ms, a.end_ms AS end_ms, a.status AS status, s.id AS source_id,
       s.version AS version, s.synthetic AS synthetic
ORDER BY creator_id, id
