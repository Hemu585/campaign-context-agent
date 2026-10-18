// Q13: campaigns that own a replacement slot (a dropped-out creator), for the campaign picker (read-only).
MATCH (w:Workspace)-[:HAS_BRAND]->(b:Brand)-[:RUNS]->(c:Campaign)
MATCH (d:Creator)-[p:PARTICIPATED_IN]->(c)
WHERE p.status = 'dropped_out'
RETURN c.id AS id, c.title AS title, b.id AS client_brand_id, b.name AS client_brand_name,
       c.channel AS channel, c.deliverable AS deliverable, c.language AS language,
       c.category AS category, c.currency AS currency, c.budget_paise AS budget_paise,
       c.start_ms AS start_ms, c.end_ms AS end_ms, c.status AS status,
       d.id AS dropped_creator_id, d.name AS dropped_creator_name,
       c.approved_proposal_id AS approved_proposal_id, w.context_revision AS revision
ORDER BY id
