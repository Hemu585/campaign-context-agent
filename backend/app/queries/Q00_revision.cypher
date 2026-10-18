// Q00: current workspace revision and seed state (read-only).
MATCH (w:Workspace)
RETURN w.id AS workspace_id, w.context_revision AS revision,
       w.dataset_version AS dataset_version, w.seed_status AS seed_status
