// Q07a: metadata (no text) for every Source, with any newer version that supersedes it (read-only).
MATCH (s:Source)
OPTIONAL MATCH (newer:Source)-[:SUPERSEDES]->(s)
RETURN s.id AS id, s.document_id AS document_id, s.version AS version, s.kind AS kind,
       s.title AS title, s.subject_id AS subject_id, s.observed_at_ms AS observed_at_ms,
       s.verified AS verified, s.checksum AS checksum, s.fact_hash AS fact_hash,
       s.synthetic AS synthetic, collect(newer.id) AS superseded_by
ORDER BY id
