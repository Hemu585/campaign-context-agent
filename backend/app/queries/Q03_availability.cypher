// Q03: all positive and negative availability windows with their sources (read-only).
MATCH (w:Workspace)-[:HAS_CREATOR]->(r:Creator)-[:HAS_AVAILABILITY]->(a:Availability)
OPTIONAL MATCH (a)-[:SUPPORTED_BY]->(s:Source)
RETURN r.id AS creator_id, a.id AS id, a.start_ms AS start_ms, a.end_ms AS end_ms, a.status AS status,
       collect(DISTINCT s.id) AS source_ids
ORDER BY creator_id, id
