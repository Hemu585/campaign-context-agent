// Seed step 6: positive and negative availability windows.
UNWIND $rows AS r
MATCH (cr:Creator {id: r.creator_id})
MATCH (s:Source {id: r.source_id})
MERGE (a:Availability {id: r.id})
ON CREATE SET a.start_ms = r.start_ms, a.end_ms = r.end_ms, a.status = r.status
MERGE (cr)-[:HAS_AVAILABILITY]->(a)
MERGE (a)-[:SUPPORTED_BY]->(s)
RETURN count(a) AS n
