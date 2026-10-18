// VERIFY only (disposable campaign_context_test_verify_* graphs, enforced in code): plant
// instruction-like text inside a fictional source document for scenario S14. Never used by routes.
MATCH (s:Source {id: $source_id})
SET s.text = $text
RETURN s.id AS id
