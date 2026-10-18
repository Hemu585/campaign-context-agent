// Q12: current availability window with its current source, before a versioned demo edit (read-only).
MATCH (r:Creator)-[:HAS_AVAILABILITY]->(v:Availability {id: $fact_id})-[:SUPPORTED_BY]->(s:Source)
RETURN r.id AS creator_id, r.name AS creator_name, v.id AS id, v.start_ms AS start_ms, v.end_ms AS end_ms,
       v.status AS status, s.id AS source_id, s.document_id AS document_id, s.version AS version,
       s.synthetic AS synthetic
