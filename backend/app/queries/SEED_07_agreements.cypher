// Seed step 7: brand agreements with exactly one counterparty (WITH_BRAND).
UNWIND $rows AS r
MATCH (cr:Creator {id: r.creator_id})
MATCH (b:Brand {id: r.counterparty_brand_id})
MATCH (s:Source {id: r.source_id})
MERGE (a:Agreement {id: r.id})
ON CREATE SET a.exclusive = r.exclusive, a.channel = r.channel, a.category = r.category,
              a.start_ms = r.start_ms, a.end_ms = r.end_ms, a.status = r.status
MERGE (cr)-[:HAS_AGREEMENT]->(a)
MERGE (a)-[:WITH_BRAND]->(b)
MERGE (a)-[:SUPPORTED_BY]->(s)
RETURN count(a) AS n
