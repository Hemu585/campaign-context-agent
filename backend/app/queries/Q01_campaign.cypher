// Q01: campaign constraints, client brand, roster participants and brief sources (read-only).
MATCH (w:Workspace)-[:HAS_BRAND]->(b:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:Source)
WITH w, b, c, collect(DISTINCT s.id) AS source_ids
OPTIONAL MATCH (p:Creator)-[pe:PARTICIPATED_IN]->(c)
RETURN w.context_revision AS revision,
       c.id AS id, c.title AS title, c.channel AS channel, c.deliverable AS deliverable,
       c.language AS language, c.category AS category, c.currency AS currency,
       c.budget_paise AS budget_paise, c.start_ms AS start_ms, c.end_ms AS end_ms,
       c.status AS status, c.approved_proposal_id AS approved_proposal_id,
       b.id AS brand_id, b.name AS brand_name, source_ids,
       collect(CASE WHEN p IS NULL THEN NULL
                    ELSE {creator_id: p.id, creator_name: p.name, status: pe.status, source_id: pe.source_id}
               END) AS participants
