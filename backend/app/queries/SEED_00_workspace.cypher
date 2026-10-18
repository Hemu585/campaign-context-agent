// Seed step 0: create the workspace in 'loading' state (revision 0 until the load completes).
MERGE (w:Workspace {id: $workspace_id})
ON CREATE SET w.name = $name, w.schema_version = $schema_version, w.dataset_version = $dataset_version,
              w.seed_status = 'loading', w.context_revision = 0, w.created_at_ms = $now_ms
RETURN w.seed_status AS seed_status, w.dataset_version AS dataset_version
