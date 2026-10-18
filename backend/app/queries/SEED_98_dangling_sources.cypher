// Integrity check (read-only): every source_id stored on an edge must resolve to a Source node.
MATCH ()-[e]->()
WHERE e.source_id IS NOT NULL
OPTIONAL MATCH (s:Source {id: e.source_id})
WITH e, s
WHERE s IS NULL
RETURN count(e) AS dangling
