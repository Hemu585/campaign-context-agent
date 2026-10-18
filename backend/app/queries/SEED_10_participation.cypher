// Seed step 10: creator participation (completed / assigned / dropped_out), each edge sourced.
UNWIND $rows AS r
MATCH (cr:Creator {id: r.creator_id})
MATCH (c:Campaign {id: r.campaign_id})
MERGE (cr)-[p:PARTICIPATED_IN]->(c)
ON CREATE SET p.status = r.status, p.source_id = r.source_id
RETURN count(p) AS n
