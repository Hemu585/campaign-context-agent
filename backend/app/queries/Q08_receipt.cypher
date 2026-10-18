// Q08: look up an idempotency receipt by key (read-only).
MATCH (r:MutationReceipt {id: $key})
RETURN r.id AS id, r.operation AS operation, r.payload_hash AS payload_hash,
       r.result_type AS result_type, r.result_id AS result_id, r.created_at_ms AS created_at_ms
