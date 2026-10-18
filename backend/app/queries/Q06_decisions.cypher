// Q06: operator rejection events whose explicit scope is this campaign or its client brand,
// with any revocation events. Relevance comes from graph ownership and stored scope, never
// from model inference (read-only).
MATCH (client:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (d:Decision)-[:CONSIDERED]->(r:Creator)
WHERE d.action = 'rejected'
  AND ((d.scope_type = 'campaign' AND d.scope_id = c.id)
    OR (d.scope_type = 'brand' AND d.scope_id = client.id))
OPTIONAL MATCH (d)-[:FOR_CAMPAIGN]->(made_in:Campaign)
OPTIONAL MATCH (rev:Decision)-[:REVOKES]->(d)
OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(s:Source)
RETURN d.id AS id, r.id AS creator_id, d.scope_type AS scope_type, d.scope_id AS scope_id,
       d.reason AS reason, d.as_of_ms AS as_of_ms, d.created_at_ms AS created_at_ms,
       d.expires_at_ms AS expires_at_ms, made_in.id AS made_in_campaign_id,
       collect(DISTINCT CASE WHEN rev IS NULL THEN NULL ELSE {id: rev.id, as_of_ms: rev.as_of_ms} END)
         AS revocations,
       collect(DISTINCT s.id) AS source_ids
ORDER BY as_of_ms, id
