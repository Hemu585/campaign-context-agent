// Q13: one session with its display messages and run references (read-only).
MATCH (s:Session {id: $session_id})
OPTIONAL MATCH (s)-[:HAS_MESSAGE]->(m:Message)
WITH s, collect(CASE WHEN m IS NULL THEN NULL ELSE {id: m.id, role: m.role, text: m.text,
                                                    created_at_ms: m.created_at_ms, run_id: m.run_id} END)
       AS messages
OPTIONAL MATCH (s)-[:HAS_RUN]->(r:Run)
RETURN s.id AS id, s.title AS title, s.created_at_ms AS created_at_ms, messages,
       collect(CASE WHEN r IS NULL THEN NULL ELSE {id: r.id, status: r.status, phase: r.phase,
                                                   campaign_id: r.campaign_id, created_at_ms: r.created_at_ms,
                                                   proposal_id: r.proposal_id} END) AS runs
