// Q09: stage an internal draft proposal for one evaluated, eligible candidate from a RUNNING run.
// Server-derived idempotency key (run, creator, revision). Drafts never change the revision, are
// never approvals, and cannot be created once the run stops running (e.g. after cancellation).
MATCH (w:Workspace {id: $workspace_id})
WHERE w.context_revision = $revision
MATCH (sess:Session)-[:HAS_RUN]->(run:Run {id: $run_id})
WHERE run.status = 'running' AND run.campaign_id = $campaign_id
MATCH (w)-[:HAS_BRAND]->(:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (w)-[:HAS_CREATOR]->(r:Creator {id: $creator_id})
OPTIONAL MATCH (rc:MutationReceipt {id: $key})
WITH w, run, c, r, rc
WHERE rc IS NULL
CREATE (p:Proposal {id: $proposal_id, status: 'draft', created_at_ms: $now_ms, context_revision: $revision,
                    as_of_ms: $as_of_ms, snapshot_json: $snapshot_json, request_id: $key,
                    payload_hash: $payload_hash})
CREATE (p)-[:FOR_CAMPAIGN]->(c), (p)-[:SELECTS]->(r), (p)-[:FROM_RUN]->(run)
SET run.proposal_id = $proposal_id
CREATE (w)-[:HAS_RECEIPT]->(:MutationReceipt {id: $key, operation: 'stage_draft', payload_hash: $payload_hash,
                                               result_type: 'proposal', result_id: $proposal_id,
                                               created_at_ms: $now_ms})
WITH p
OPTIONAL MATCH (s:Source)
WHERE s.id IN $source_ids
WITH p, collect(s) AS sources
FOREACH (x IN sources | CREATE (p)-[:SUPPORTED_BY]->(x))
RETURN p.id AS id, size(sources) AS source_count
