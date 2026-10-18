// Seed step 5: exact fee quotes per creator, each with its supporting source.
UNWIND $rows AS r
MATCH (cr:Creator {id: r.creator_id})
MATCH (s:Source {id: r.source_id})
MERGE (o:Offer {id: r.id})
ON CREATE SET o.channel = r.channel, o.deliverable = r.deliverable, o.language = r.language,
              o.category = r.category, o.fee_paise = r.fee_paise, o.currency = r.currency,
              o.valid_from_ms = r.valid_from_ms, o.valid_to_ms = r.valid_to_ms
MERGE (cr)-[:OFFERS]->(o)
MERGE (o)-[:SUPPORTED_BY]->(s)
RETURN count(o) AS n
