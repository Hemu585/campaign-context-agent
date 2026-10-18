// Q08: on backend startup, runs that were queued or running can no longer finish. Mark them
// interrupted and keep their transcript and evidence. They can never be approved.
MATCH (r:Run)
WHERE r.status IN ['queued', 'running']
SET r.status = 'interrupted', r.phase = 'interrupted', r.finished_at_ms = $now_ms, r.error_json = $error_json
RETURN count(r) AS interrupted
