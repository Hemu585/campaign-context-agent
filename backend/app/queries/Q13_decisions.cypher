// Q13: every decision event (rejections, revocations, approvals) with its explicit links (read-only).
MATCH (d:Decision)
OPTIONAL MATCH (d)-[:CONSIDERED]->(r:Creator)
OPTIONAL MATCH (d)-[:FOR_CAMPAIGN]->(c:Campaign)
OPTIONAL MATCH (d)-[:REVOKES]->(target:Decision)
OPTIONAL MATCH (d)-[:APPROVES]->(p:Proposal)
OPTIONAL MATCH (d)-[:IN_SESSION]->(sess:Session)
WITH d, r, c, target, p, sess
OPTIONAL MATCH (rev:Decision)-[:REVOKES]->(d)
WITH d, r, c, target, p, sess,
     collect(CASE WHEN rev IS NULL THEN NULL ELSE {id: rev.id, as_of_ms: rev.as_of_ms} END) AS revocations
OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(s:Source)
RETURN d.id AS id, d.action AS action, d.scope_type AS scope_type, d.scope_id AS scope_id,
       d.reason AS reason, d.as_of_ms AS as_of_ms, d.created_at_ms AS created_at_ms,
       d.expires_at_ms AS expires_at_ms, r.id AS creator_id, r.name AS creator_name,
       c.id AS campaign_id, c.title AS campaign_title, target.id AS revokes_id, p.id AS proposal_id,
       sess.id AS session_id, revocations, collect(DISTINCT s.id) AS source_ids
ORDER BY created_at_ms DESC, id DESC
