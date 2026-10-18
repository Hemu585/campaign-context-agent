// Seed step 4: campaigns, their client brand (RUNS) and brief/record source.
UNWIND $rows AS r
MATCH (b:Brand {id: r.brand_id})
MATCH (s:Source {id: r.source_id})
MERGE (c:Campaign {id: r.id})
ON CREATE SET c.title = r.title, c.channel = r.channel, c.deliverable = r.deliverable,
              c.language = r.language, c.category = r.category, c.currency = r.currency,
              c.budget_paise = r.budget_paise, c.start_ms = r.start_ms, c.end_ms = r.end_ms,
              c.status = r.status
MERGE (b)-[:RUNS]->(c)
MERGE (c)-[:SUPPORTED_BY]->(s)
RETURN count(c) AS n
