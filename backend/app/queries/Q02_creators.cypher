// Q02: EVERY workspace creator (no LIMIT before evaluation) with exact offers, offer sources
// and completed-campaign history used only for ranking (read-only).
MATCH (w:Workspace)-[:HAS_CREATOR]->(r:Creator)
OPTIONAL MATCH (r)-[:OFFERS]->(o:Offer)
OPTIONAL MATCH (o)-[:SUPPORTED_BY]->(os:Source)
WITH r, o, collect(DISTINCT os.id) AS offer_source_ids
WITH r, collect(CASE WHEN o IS NULL THEN NULL ELSE {
        id: o.id, channel: o.channel, deliverable: o.deliverable, language: o.language,
        category: o.category, fee_paise: o.fee_paise, currency: o.currency,
        valid_from_ms: o.valid_from_ms, valid_to_ms: o.valid_to_ms, source_ids: offer_source_ids
     } END) AS offers
OPTIONAL MATCH (r)-[h:PARTICIPATED_IN]->(done:Campaign)
WHERE h.status = 'completed'
RETURN r.id AS id, r.name AS name, r.active AS active, offers,
       collect(CASE WHEN done IS NULL THEN NULL ELSE {campaign_id: done.id, source_id: h.source_id} END)
         AS completed
ORDER BY id
