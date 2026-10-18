// Q04b: the client brand's direct competitors as stored in the graph, compared with the
// competitor-map audit's listed ids (read-only).
MATCH (client:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (client)-[cw:COMPETES_WITH]-(comp:Brand)
RETURN comp.id AS competitor_id, comp.name AS competitor_name, cw.source_id AS source_id
ORDER BY competitor_id
