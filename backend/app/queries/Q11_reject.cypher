// Q11: record an operator rejection with explicit scope, its feedback source and receipt, and
// advance the workspace revision -- all in one compare-and-set statement. The scope row is
// re-derived from graph ownership: campaign scope = this campaign, brand scope = its client.
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $expected_revision
MATCH (w)-[:HAS_BRAND]->(b:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (w)-[:HAS_CREATOR]->(r:Creator {id: $creator_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, b, c, r, rc
WHERE rc IS NULL
  AND (($scope_type = 'campaign' AND $scope_id = c.id) OR ($scope_type = 'brand' AND $scope_id = b.id))
OPTIONAL MATCH (sess:Session {id: $session_id})
CREATE (fb:Source {id: $source_id, document_id: $source_document_id, version: 1, kind: 'operator_feedback',
                   title: $source_title, subject_id: $decision_id, text: $source_text, checksum: $source_checksum,
                   observed_at_ms: $as_of_ms, verified: true, synthetic: true, editor: 'local_demo_operator',
                   created_at_ms: $now_ms})
CREATE (d:Decision {id: $decision_id, action: 'rejected', scope_type: $scope_type, scope_id: $scope_id,
                    reason: $reason, as_of_ms: $as_of_ms, created_at_ms: $now_ms, expires_at_ms: $expires_at_ms,
                    request_id: $key, payload_hash: $payload_hash})
CREATE (d)-[:FOR_CAMPAIGN]->(c), (d)-[:CONSIDERED]->(r), (d)-[:SUPPORTED_BY]->(fb)
FOREACH (x IN CASE WHEN sess IS NULL THEN [] ELSE [sess] END | CREATE (d)-[:IN_SESSION]->(x))
SET w.context_revision = $new_revision
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'reject', payload_hash: $payload_hash,
                                               result_type: 'decision', result_id: $decision_id,
                                               created_at_ms: $now_ms})
RETURN d.id AS id, w.context_revision AS revision
