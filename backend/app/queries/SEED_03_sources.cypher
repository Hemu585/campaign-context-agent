// Seed step 3: immutable fictional source documents with checksum and attested fact hash.
UNWIND $rows AS r
MERGE (s:Source {id: r.id})
ON CREATE SET s.document_id = r.document_id, s.version = r.version, s.kind = r.kind, s.title = r.title,
              s.subject_id = r.subject_id, s.text = r.text, s.checksum = r.checksum,
              s.fact_hash = r.fact_hash, s.observed_at_ms = r.observed_at_ms, s.verified = r.verified,
              s.synthetic = r.synthetic, s.created_at_ms = r.created_at_ms
RETURN count(s) AS n
