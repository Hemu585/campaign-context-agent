// Q13: proposals with campaign slot, run state and approval decision (read-only).
MATCH (w:Workspace)
MATCH (p:Proposal)-[:FOR_CAMPAIGN]->(c:Campaign)
MATCH (p)-[:SELECTS]->(r:Creator)
MATCH (p)-[:FROM_RUN]->(run:Run)
OPTIONAL MATCH (d:Decision)-[:APPROVES]->(p)
RETURN p.id AS id, p.status AS status, p.created_at_ms AS created_at_ms, p.context_revision AS context_revision,
       p.as_of_ms AS as_of_ms, p.snapshot_json AS snapshot_json, p.approved_at_ms AS approved_at_ms,
       p.approved_revision AS approved_revision, c.id AS campaign_id, c.title AS campaign_title,
       c.approved_proposal_id AS slot_proposal_id, r.id AS creator_id, r.name AS creator_name,
       run.id AS run_id, run.status AS run_status, d.id AS decision_id, w.context_revision AS current_revision
ORDER BY created_at_ms DESC, id DESC
