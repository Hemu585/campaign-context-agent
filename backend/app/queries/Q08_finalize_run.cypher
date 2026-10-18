// Q08: finish a still-running run: store its bounded result and evaluation snapshot, add the
// backend-rendered assistant message, and link the creators it considered and the sources it
// used. A run already cancelled (or otherwise no longer running) is left untouched.
MATCH (s:Session)-[:HAS_RUN]->(r:Run {id: $run_id})
WHERE r.status = 'running'
SET r += $props
CREATE (s)-[:HAS_MESSAGE]->(:Message {id: $message_id, role: 'assistant', text: $text, created_at_ms: $now_ms,
                                       run_id: $run_id})
WITH r
OPTIONAL MATCH (src:Source)
WHERE src.id IN $source_ids
WITH r, collect(src) AS sources
FOREACH (x IN sources | CREATE (r)-[:USED_SOURCE]->(x))
WITH r
UNWIND $considered AS row
MATCH (c:Creator {id: row.creator_id})
CREATE (r)-[:CONSIDERED {status: row.status, reason_codes: row.reason_codes}]->(c)
RETURN count(c) AS considered
