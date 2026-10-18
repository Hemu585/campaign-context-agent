// Seed step 2: fictional creators and workspace membership (no contact details exist).
MATCH (w:Workspace {id: $workspace_id})
UNWIND $rows AS r
MERGE (c:Creator {id: r.id})
ON CREATE SET c.name = r.name, c.active = r.active
MERGE (w)-[:HAS_CREATOR]->(c)
RETURN count(c) AS n
