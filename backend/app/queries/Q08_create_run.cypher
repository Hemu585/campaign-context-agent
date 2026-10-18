// Q08: persist the operator's message and a new queued Run for an explicit campaign, with its
// receipt, in one statement. The run records the workspace revision it starts from.
MATCH (w:Workspace {id: $workspace_id})-[:HAS_SESSION]->(s:Session {id: $session_id})
MATCH (w)-[:HAS_BRAND]->(:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, s, c, rc
WHERE rc IS NULL
CREATE (s)-[:HAS_MESSAGE]->(:Message {id: $message_id, role: 'user', text: $text, created_at_ms: $now_ms,
                                       run_id: $run_id})
CREATE (s)-[:HAS_RUN]->(r:Run {id: $run_id, status: 'queued', phase: 'queued', campaign_id: $campaign_id,
                               as_of_ms: $as_of_ms, context_revision: w.context_revision, model: $model,
                               model_digest: $model_digest, created_at_ms: $now_ms, message_id: $message_id})
CREATE (r)-[:FOR_CAMPAIGN]->(c)
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'create_run', payload_hash: $payload_hash,
                                               result_type: 'run', result_id: $run_id, created_at_ms: $now_ms})
RETURN r.id AS id, r.context_revision AS context_revision
