// Q13: one persisted run with its session (read-only).
MATCH (s:Session)-[:HAS_RUN]->(r:Run {id: $run_id})
RETURN s.id AS session_id, properties(r) AS run
