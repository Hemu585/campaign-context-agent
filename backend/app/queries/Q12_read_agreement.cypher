// Q12: current agreement fact with its current source and the creator's current agreement-audit
// source, before a versioned demo edit (read-only).
MATCH (r:Creator)-[:HAS_AGREEMENT]->(a:Agreement {id: $fact_id})-[:SUPPORTED_BY]->(s:Source)
OPTIONAL MATCH (a)-[:WITH_BRAND]->(b:Brand)
OPTIONAL MATCH (r)-[:HAS_AUDIT]->(au:Audit)-[:SUPPORTED_BY]->(aus:Source)
WHERE au.kind = 'agreements'
RETURN r.id AS creator_id, r.name AS creator_name, a.id AS id, a.exclusive AS exclusive,
       a.channel AS channel, a.category AS category, a.start_ms AS start_ms, a.end_ms AS end_ms,
       a.status AS status, b.id AS counterparty_brand_id, b.name AS counterparty_name,
       s.id AS source_id, s.document_id AS document_id, s.version AS version, s.synthetic AS synthetic,
       au.id AS audit_id, au.kind AS audit_kind, au.coverage_start_ms AS coverage_start_ms,
       au.coverage_end_ms AS coverage_end_ms, au.complete AS audit_complete, au.listed_ids AS listed_ids,
       aus.id AS audit_source_id, aus.document_id AS audit_document_id, aus.version AS audit_version
