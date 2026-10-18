// Q08: create a conversation session with its idempotency receipt (no revision change).
MATCH (w:Workspace {id: $workspace_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, rc
WHERE rc IS NULL
CREATE (w)-[:HAS_SESSION]->(s:Session {id: $session_id, title: $title, created_at_ms: $now_ms})
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'create_session', payload_hash: $payload_hash,
                                               result_type: 'session', result_id: $session_id,
                                               created_at_ms: $now_ms})
RETURN s.id AS id
