// Q10: atomic human approval (ARCHITECTURE "Mutation integrity"). Runs only after the service has
// re-evaluated the candidate under the mutation lock. ONE statement re-checks the expected revision,
// the unfilled slot, the current draft and its completed run, then creates the approval Decision
// with explicit links and evidence, approves the proposal, fills the slot, advances the revision and
// writes the receipt. No returned row means conflict; nothing partial is written.
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $expected_revision
MATCH (w)-[:HAS_BRAND]->(:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
WHERE c.approved_proposal_id IS NULL
MATCH (p:Proposal {id: $proposal_id})-[:FOR_CAMPAIGN]->(c)
WHERE p.status = 'draft' AND p.context_revision = $expected_revision
MATCH (p)-[:SELECTS]->(r:Creator {id: $creator_id})
MATCH (p)-[:FROM_RUN]->(run:Run)<-[:HAS_RUN]-(sess:Session)
WHERE run.status = 'completed'
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, c, p, r, sess, rc
WHERE rc IS NULL
OPTIONAL MATCH (p)-[:SUPPORTED_BY]->(s:Source)
WITH w, c, p, r, sess, collect(s) AS sources
CREATE (d:Decision {id: $decision_id, action: 'approved', scope_type: 'campaign', scope_id: c.id,
                    reason: $reason, as_of_ms: $as_of_ms, created_at_ms: $now_ms, request_id: $key,
                    payload_hash: $payload_hash})
CREATE (d)-[:APPROVES]->(p), (d)-[:FOR_CAMPAIGN]->(c), (d)-[:CONSIDERED]->(r), (d)-[:IN_SESSION]->(sess)
FOREACH (x IN sources | CREATE (d)-[:SUPPORTED_BY]->(x))
SET p.status = 'approved', p.approved_at_ms = $now_ms, p.approved_revision = $new_revision,
    c.approved_proposal_id = p.id, w.context_revision = $new_revision
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'approve', payload_hash: $payload_hash,
                                               result_type: 'decision', result_id: $decision_id,
                                               created_at_ms: $now_ms})
RETURN d.id AS decision_id, w.context_revision AS revision
