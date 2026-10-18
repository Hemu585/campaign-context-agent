// Seed step 8: agreement-completeness audits owned by creators.
UNWIND $rows AS r
MATCH (cr:Creator {id: r.subject_id})
MATCH (s:Source {id: r.source_id})
MERGE (a:Audit {id: r.id})
ON CREATE SET a.kind = r.kind, a.coverage_start_ms = r.coverage_start_ms,
              a.coverage_end_ms = r.coverage_end_ms, a.complete = r.complete, a.listed_ids = r.listed_ids
MERGE (cr)-[:HAS_AUDIT]->(a)
MERGE (a)-[:SUPPORTED_BY]->(s)
RETURN count(a) AS n
