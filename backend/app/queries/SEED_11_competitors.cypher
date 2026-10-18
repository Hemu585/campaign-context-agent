// Seed step 11: one stored COMPETES_WITH edge per brand pair; queries traverse it undirected.
UNWIND $rows AS r
MATCH (a:Brand {id: r.a})
MATCH (b:Brand {id: r.b})
MERGE (a)-[e:COMPETES_WITH]->(b)
ON CREATE SET e.source_id = r.source_id
RETURN count(e) AS n
