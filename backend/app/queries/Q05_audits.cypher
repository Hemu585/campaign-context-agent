// Q05: agreement-completeness audits owned by creators and the competitor-map audit owned by
// the campaign's client brand. Missing coverage is never proof of "no conflict" (read-only).
MATCH (client:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (subject)-[:HAS_AUDIT]->(au:Audit)
WHERE (subject:Creator AND au.kind = 'agreements')
   OR (subject:Brand AND subject.id = client.id AND au.kind = 'competitors')
OPTIONAL MATCH (au)-[:SUPPORTED_BY]->(s:Source)
RETURN subject.id AS subject_id, au.id AS id, au.kind AS kind,
       au.coverage_start_ms AS coverage_start_ms, au.coverage_end_ms AS coverage_end_ms,
       au.complete AS complete, au.listed_ids AS listed_ids, collect(DISTINCT s.id) AS source_ids
ORDER BY subject_id, id
