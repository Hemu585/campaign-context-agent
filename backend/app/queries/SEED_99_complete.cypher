// Seed final step: mark the load complete and start the decision-context revision at 1.
MATCH (w:Workspace {id: $workspace_id})
WHERE w.seed_status = 'loading'
SET w.seed_status = 'complete', w.context_revision = 1, w.seeded_at_ms = $now_ms
RETURN w.context_revision AS revision
