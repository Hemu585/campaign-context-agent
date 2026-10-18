// Q12: versioned edit of a fictional agreement in ONE statement: update the fact, create a new
// source version that SUPERSEDES the old one, refresh the creator's agreement-audit source the
// same way (coverage and listed agreements unchanged), advance the revision, write the receipt.
// Old sources are kept; only the current SUPPORTED_BY links move.
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $expected_revision
MATCH (r:Creator)-[:HAS_AGREEMENT]->(a:Agreement {id: $fact_id})-[old_edge:SUPPORTED_BY]->(old:Source {id: $old_source_id})
MATCH (r)-[:HAS_AUDIT]->(au:Audit {id: $audit_id})-[old_au_edge:SUPPORTED_BY]->(old_au:Source {id: $old_audit_source_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, a, au, old_edge, old, old_au_edge, old_au, rc
WHERE rc IS NULL
SET a.start_ms = $start_ms, a.end_ms = $end_ms, a.status = $status, a.exclusive = $exclusive
DELETE old_edge, old_au_edge
CREATE (a)-[:SUPPORTED_BY]->(new:Source {id: $new_source_id, document_id: $document_id, version: $new_version,
         kind: 'agreement', title: $title, subject_id: $fact_id, text: $text, checksum: $checksum,
         fact_hash: $fact_hash, observed_at_ms: $as_of_ms, verified: true, synthetic: true,
         editor: 'local_demo_operator', created_at_ms: $now_ms})-[:SUPERSEDES]->(old)
CREATE (au)-[:SUPPORTED_BY]->(new_au:Source {id: $new_audit_source_id, document_id: $audit_document_id,
         version: $new_audit_version, kind: 'agreement_audit', title: $audit_title, subject_id: $audit_id,
         text: $audit_text, checksum: $audit_checksum, fact_hash: $audit_fact_hash, observed_at_ms: $as_of_ms,
         verified: true, synthetic: true, editor: 'local_demo_operator', created_at_ms: $now_ms})-[:SUPERSEDES]->(old_au)
SET w.context_revision = $new_revision
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'edit_fact', payload_hash: $payload_hash,
                                               result_type: 'source', result_id: $new_source_id,
                                               created_at_ms: $now_ms})
RETURN new.id AS source_id, new_au.id AS audit_source_id, w.context_revision AS revision
