// Q13: persistent sessions, newest first (read-only).
MATCH (w:Workspace)-[:HAS_SESSION]->(s:Session)
OPTIONAL MATCH (s)-[:HAS_RUN]->(r:Run)
RETURN s.id AS id, s.title AS title, s.created_at_ms AS created_at_ms, count(r) AS run_count
ORDER BY created_at_ms DESC, id DESC
LIMIT $limit
