// Q12: versioned edit of a fictional availability window in ONE statement (fact, new source
// version superseding the old one, revision, receipt).
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $expected_revision
MATCH (r:Creator)-[:HAS_AVAILABILITY]->(v:Availability {id: $fact_id})-[old_edge:SUPPORTED_BY]->(old:Source {id: $old_source_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, v, old_edge, old, rc
WHERE rc IS NULL
SET v.start_ms = $start_ms, v.end_ms = $end_ms, v.status = $status
DELETE old_edge
CREATE (v)-[:SUPPORTED_BY]->(new:Source {id: $new_source_id, document_id: $document_id, version: $new_version,
         kind: 'availability', title: $title, subject_id: $fact_id, text: $text, checksum: $checksum,
         fact_hash: $fact_hash, observed_at_ms: $as_of_ms, verified: true, synthetic: true,
         editor: 'local_demo_operator', created_at_ms: $now_ms})-[:SUPERSEDES]->(old)
SET w.context_revision = $new_revision
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'edit_fact', payload_hash: $payload_hash,
                                               result_type: 'source', result_id: $new_source_id,
                                               created_at_ms: $now_ms})
RETURN new.id AS source_id, null AS audit_source_id, w.context_revision AS revision
