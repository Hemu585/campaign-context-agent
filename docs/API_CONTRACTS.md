# API contracts

Prefix `/api`. JSON requests/responses, UTF-8, stable application IDs. Validate with Pydantic; reject unknown write fields. Store integer UTC milliseconds and integer paise. Frontend should use generated OpenAPI types or a tested equivalent.

## Core objects

`CampaignSummary`: id, title, client_brand_id, client_brand_name, channel, deliverable, language, category, currency, budget_paise, start_ms, end_ms, dropped_creator_id, approved_proposal_id (nullable).

`Check`: name, result (`pass`, `fail`, `unknown`), reason_code, detail, source_ids. Valid names include participation, offer_match, quote_validity, budget, availability, agreement_audit, competitor_audit, exclusivity, memory.

`CandidateEvaluation`: creator_id, name, status, fee_paise (nullable), completed_campaign_count, rank (nullable), checks, active_rejection_ids, evidence_path_ids. Status enum: eligible, ineligible, unknown, excluded_by_memory; rank exists only for eligible candidates.

`EvidencePath`: id, node_ids, edges as `{from, type, to, source_ids}`, source_ids. All IDs refer to actual application entities. The path is a graph fact, not generated reasoning.

`Evaluation`: campaign_id, context_revision, as_of_ms, candidates, recommended_creator_ids (up to three), unknowns, sources metadata, evidence_paths. Candidate order is deterministic. Included source text is bounded; full text uses the source endpoint.

`Run`: id, session_id, campaign_id, status, phase, model, model_digest, context_revision, as_of_ms, evaluation (nullable), final_answer (nullable), proposal_id (nullable), tool_trace, error (nullable). Status is queued, running, completed, needs_clarification, failed, cancelled, or interrupted. A no-candidate answer is a completed run with an empty recommendation list.

The public final_answer summary is built from validated reason codes and graph facts. Do not display unrestricted model text as verified evidence. Clarification text must stay within the supported campaign/task scope and carry no unsupported creator facts.

`Proposal`: id, campaign_id, creator_id, run_id, status, context_revision, current_revision, is_stale, snapshot, created_at_ms, approved_at_ms (nullable), approved_revision (nullable). Status is draft or approved. `is_stale` is true only for a draft whose context_revision differs from current_revision; it is not a destructive overwrite of the snapshot. An approved proposal remains historical even if later context changes. Its own approval revision increment must not label it stale.

`Decision`: id, action, creator_id, campaign_id, scope_type, scope_id, reason, as_of_ms, created_at_ms, expires_at_ms (nullable), is_active, source_ids, revoked_by_id (nullable).

## Endpoints

| Method and route | Input | Output / behavior |
| --- | --- | --- |
| GET `/health` | none | backend, graph, model installed/reachable, version summary; 200 healthy or 503 degraded |
| GET `/bootstrap` | none | session-local API nonce, workspace ID, context revision, synthetic/demo-clock flags |
| GET `/campaigns` | none | CampaignSummary list |
| GET `/campaigns/{id}` | path ID | Full campaign, brief source, participants, current revision |
| POST `/campaigns/{id}/evaluate` | empty JSON | Diagnostic deterministic Evaluation; clearly not an AI run |
| GET `/sessions` | optional bounded cursor | Persistent sessions, newest first |
| POST `/sessions` | title, max 80 chars | New session ID |
| GET `/sessions/{id}` | path ID | Messages, run references, latest state |
| POST `/sessions/{id}/runs` | campaign_id, message (1–4000 chars) | 202 and Run ID; starts real local agent |
| GET `/runs/{id}` | path ID | Persisted Run; UI polls while active |
| POST `/runs/{id}/cancel` | empty JSON | Cancel request; no further tools after cancellation |
| GET `/runs/{id}/evidence` | path ID | Validated paths and source metadata from the run snapshot |
| GET `/sources/{id}` | path ID | Read-only fictional Source, full escaped text and version |
| GET `/proposals` | optional campaign_id | Proposal list |
| GET `/proposals/{id}` | path ID | Proposal snapshot plus stale state |
| POST `/proposals/{id}/approve` | expected_revision | Revalidated approval Decision and new context revision |
| GET `/decisions` | optional campaign_id, creator_id | History with active scopes |
| POST `/decisions/rejections` | campaign_id, creator_id, scope_type, reason, expires_at_ms?, expected_revision | New rejection Decision; derive scope_id on server |
| POST `/decisions/{id}/revoke` | reason, expected_revision | New revoke Decision linked to original rejection |
| PATCH `/demo/facts/{type}/{id}` | permitted changes, reason, expected_revision | Versioned fictional edit, source ID, new revision |

There is no HTTP route to run arbitrary Cypher, change the model endpoint, mutate arbitrary properties, approve through chat, or load external URLs. Draft staging is an internal agent tool/service. The frontend can approve only a validated persisted draft.

## Mutation headers and idempotency

All POST/PATCH routes require `Content-Type: application/json`, `X-Local-Nonce` from bootstrap, and a validated `Idempotency-Key` UUID. The server binds nonce to the current application process, checks allowed loopback Host/Origin values, and enforces exact CORS allowlists. This is a local-browser write boundary, not multi-user authentication.

For persistence-bearing operations, atomically store key, operation, payload hash and result reference in a MutationReceipt. Same key and payload returns the original result; different payload yields 409. A retry after restart must not duplicate a decision/proposal/session/run. Cancellation can be naturally idempotent by run ID. The read-only diagnostic POST may return a freshly calculated result for a repeated key; document this exception since it has no mutation side effect.

Context-changing mutations require `expected_revision`. Check idempotent replay before revision comparison. Return 409 when new writes use stale context. Return 409 if the campaign slot is already filled or the proposal no longer qualifies. Do not return success based on an HTTP request alone; inspect graph write results.

## Demo fact editing

Enabled only when `DEMO_MODE=true`; all targets must be marked synthetic. Allowed types: `agreement` and `availability`.

- Agreement: start/end times, active/cancelled status, exclusivity flag. Keep creator, brand and scope fixed in MVP.
- Availability: start/end times and available/unavailable status.
- Require a short reason and a current revision. Validate intervals and timezone-aware input before converting to milliseconds.
- Source versions, current fact fields, and revision update must be one mutation. Do not let the client set `verified`, source IDs, audit completeness, or observation time.
- Editing an agreement within the already-covered interval creates a refreshed agreement source and refreshed agreement-audit source for that creator; preserve the audit's coverage and complete list of represented agreements. Edits outside coverage fail validation rather than silently expanding it. Record both sources.
- The demo editor's explicit operator action attests the fictional source. It cannot validate a real-world contract.

## Errors

Common envelope:

```json
{
  "error": {
    "code": "STALE_CONTEXT",
    "message": "The campaign information changed. Run the recommendation again.",
    "retryable": true,
    "details": {"expected_revision": 4, "current_revision": 5}
  }
}
```

| Status | Codes |
| --- | --- |
| 400 / 422 | INVALID_INPUT, UNSUPPORTED_SCOPE, INVALID_INTERVAL, UNKNOWN_TOOL_ARGUMENT |
| 403 | LOCAL_ACCESS_REQUIRED, INVALID_NONCE, DEMO_EDIT_DISABLED |
| 404 | CAMPAIGN_NOT_FOUND, SOURCE_NOT_FOUND, RUN_NOT_FOUND, PROPOSAL_NOT_FOUND |
| 409 | STALE_CONTEXT, RUN_BUSY, IDEMPOTENCY_CONFLICT, SLOT_FILLED, CANDIDATE_NOT_ELIGIBLE |
| 503 | GRAPH_UNAVAILABLE, MODEL_UNAVAILABLE, MODEL_NOT_INSTALLED |
| terminal Run error | MODEL_TIMEOUT, INVALID_MODEL_OUTPUT, TOOL_LIMIT_REACHED, QUERY_TIMEOUT |

Return actionable user messages without raw stack traces, local filesystem secrets, or hidden reasoning. Distinguish no candidates from technical failure. API tests must verify failures cause no unintended writes.
