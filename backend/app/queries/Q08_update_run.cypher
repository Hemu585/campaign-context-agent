// Q08: update run status, phase and bounded trace/result fields. Run bookkeeping never
// changes the decision-context revision.
MATCH (r:Run {id: $run_id})
SET r += $props
RETURN r.id AS id, r.status AS status
