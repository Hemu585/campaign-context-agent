// Q11: append a revocation event pointing at an unrevoked rejection, with its feedback source
// and receipt, and advance the revision. The original rejection is never edited or deleted.
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $expected_revision
MATCH (orig:Decision {id: $decision_id})-[:CONSIDERED]->(r:Creator)
WHERE orig.action = 'rejected'
MATCH (orig)-[:FOR_CAMPAIGN]->(c:Campaign)
OPTIONAL MATCH (earlier:Decision)-[:REVOKES]->(orig)
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, orig, r, c, earlier, rc
WHERE earlier IS NULL AND rc IS NULL
CREATE (fb:Source {id: $source_id, document_id: $source_document_id, version: 1, kind: 'operator_feedback',
                   title: $source_title, subject_id: $revocation_id, text: $source_text, checksum: $source_checksum,
                   observed_at_ms: $as_of_ms, verified: true, synthetic: true, editor: 'local_demo_operator',
                   created_at_ms: $now_ms})
CREATE (d:Decision {id: $revocation_id, action: 'revoked', scope_type: orig.scope_type, scope_id: orig.scope_id,
                    reason: $reason, as_of_ms: $as_of_ms, created_at_ms: $now_ms, request_id: $key,
                    payload_hash: $payload_hash})
CREATE (d)-[:REVOKES]->(orig), (d)-[:CONSIDERED]->(r), (d)-[:FOR_CAMPAIGN]->(c), (d)-[:SUPPORTED_BY]->(fb)
SET w.context_revision = $new_revision
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'revoke', payload_hash: $payload_hash,
                                               result_type: 'decision', result_id: $revocation_id,
                                               created_at_ms: $now_ms})
RETURN d.id AS id, w.context_revision AS revision
