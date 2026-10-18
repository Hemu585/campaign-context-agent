// Q08: end a run that failed or was cancelled, keeping its trace, and add a plain assistant
// message explaining the outcome. Only queued/running runs change.
MATCH (s:Session)-[:HAS_RUN]->(r:Run {id: $run_id})
WHERE r.status IN ['queued', 'running']
SET r += $props
CREATE (s)-[:HAS_MESSAGE]->(:Message {id: $message_id, role: 'assistant', text: $text, created_at_ms: $now_ms,
                                       run_id: $run_id})
RETURN r.id AS id
