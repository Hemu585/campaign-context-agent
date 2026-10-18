// Seed step 1: brands and workspace membership. MERGE by stable id, ON CREATE only.
MATCH (w:Workspace {id: $workspace_id})
UNWIND $rows AS r
MERGE (b:Brand {id: r.id})
ON CREATE SET b.name = r.name, b.category = r.category
MERGE (w)-[:HAS_BRAND]->(b)
RETURN count(b) AS n
