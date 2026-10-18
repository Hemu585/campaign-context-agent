// Q07: full fictional source documents by id, with version links, for evidence and the
// read-only source viewer (read-only).
MATCH (s:Source)
WHERE s.id IN $source_ids
OPTIONAL MATCH (newer:Source)-[:SUPERSEDES]->(s)
OPTIONAL MATCH (s)-[:SUPERSEDES]->(older:Source)
RETURN s.id AS id, s.document_id AS document_id, s.version AS version, s.kind AS kind,
       s.title AS title, s.subject_id AS subject_id, s.text AS text,
       s.observed_at_ms AS observed_at_ms, s.verified AS verified, s.checksum AS checksum,
       s.fact_hash AS fact_hash, s.synthetic AS synthetic, s.editor AS editor,
       s.created_at_ms AS created_at_ms,
       collect(DISTINCT newer.id) AS superseded_by, collect(DISTINCT older.id) AS supersedes
ORDER BY id
