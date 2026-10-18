// Q13: availability windows the demo editor may change, with current values and source version (read-only).
MATCH (r:Creator)-[:HAS_AVAILABILITY]->(v:Availability)-[:SUPPORTED_BY]->(s:Source)
RETURN v.id AS id, r.id AS creator_id, r.name AS creator_name, v.start_ms AS start_ms, v.end_ms AS end_ms,
       v.status AS status, s.id AS source_id, s.version AS version, s.synthetic AS synthetic
ORDER BY creator_id, id
