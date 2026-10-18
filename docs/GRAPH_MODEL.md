# Graph model

Graph names are selected by the server: `campaign_context_demo` for development and isolated generated names beginning `campaign_context_test_` for tests. A client or model cannot supply a graph name. Stable string application IDs are authoritative; never expose FalkorDB internal node IDs as durable identifiers.

## Nodes

| Label | Required fields | Notes |
| --- | --- | --- |
| Workspace | id, schema_version, dataset_version, context_revision | One per graph |
| Brand | id, name, category | Fictional |
| Campaign | id, title, channel, deliverable, language, category, currency, budget_paise, start_ms, end_ms, status | Optional approved_proposal_id; owns one replacement slot |
| Creator | id, name, active | Fictional names; no contact details |
| Offer | id, channel, deliverable, language, category, fee_paise, currency, valid_from_ms, valid_to_ms | One exact quote, not a generic creator-wide rate |
| Availability | id, start_ms, end_ms, status | status available or unavailable |
| Agreement | id, exclusive, channel, category, start_ms, end_ms, status | status active or cancelled; missing dates cause unknown when relevant |
| Audit | id, kind, coverage_start_ms, coverage_end_ms, complete | kind agreements or competitors |
| Source | id, document_id, version, title, text, observed_at_ms, verified, checksum, synthetic | Immutable content; links to superseded version |
| Session | id, created_at_ms, title | Actual creation time; one workspace |
| Message | id, role, text, created_at_ms | User/assistant display text only; no hidden reasoning |
| Run | id, status, campaign_id, as_of_ms, context_revision, model, model_digest, started_at_ms, finished_at_ms | Bounded trace/evaluation snapshots serialized as JSON strings |
| Proposal | id, status, created_at_ms, context_revision, snapshot_json, request_id, payload_hash | status draft or approved; approval adds approved_at_ms and approved_revision |
| Decision | id, action, scope_type, scope_id, reason, as_of_ms, created_at_ms, request_id, payload_hash | action approved, rejected, or revoked; optional expires_at_ms |
| MutationReceipt | id, operation, payload_hash, result_type, result_id, created_at_ms | id is the workspace-unique idempotency key; written atomically with the action |

Use primitive fields supported by the selected FalkorDB version. Serialize bounded nested evidence/trace objects to strings rather than assuming nested map properties are supported. Parse them with schema validation at the API boundary.

## Relationships

| Start | Relationship | End | Properties / constraints |
| --- | --- | --- | --- |
| Workspace | HAS_BRAND / HAS_CREATOR / HAS_SESSION | Brand / Creator / Session | Membership |
| Workspace | HAS_RECEIPT | MutationReceipt | Persistent deduplication for sessions, runs and other writes |
| Brand | RUNS | Campaign | Exactly one client per campaign |
| Brand | COMPETES_WITH | Brand | One stored edge per pair, `source_id`; query undirected |
| Brand | HAS_AUDIT | Audit | Competitor-map coverage |
| Creator | OFFERS | Offer | Many supported offers |
| Creator | HAS_AVAILABILITY | Availability | Positive and negative windows |
| Creator | HAS_AGREEMENT | Agreement | Each agreement belongs to one creator |
| Agreement | WITH_BRAND | Brand | Exactly one counterparty |
| Creator | HAS_AUDIT | Audit | Agreement completeness coverage |
| Creator | PARTICIPATED_IN | Campaign | `status` completed, assigned, or dropped_out; `source_id` |
| Campaign / Offer / Availability / Agreement / Audit | SUPPORTED_BY | Source | Current factual provenance |
| Source | SUPERSEDES | Source | New immutable source version points to previous |
| Session | HAS_MESSAGE / HAS_RUN | Message / Run | Persistent interaction |
| Run | FOR_CAMPAIGN | Campaign | Explicit context |
| Run | CONSIDERED | Creator | `status`, bounded reason codes |
| Run | USED_SOURCE | Source | Sources used by the run |
| Proposal | FOR_CAMPAIGN / SELECTS / FROM_RUN | Campaign / Creator / Run | Exactly one of each |
| Proposal | SUPPORTED_BY | Source | Sources of immutable snapshot |
| Decision | FOR_CAMPAIGN / CONSIDERED / IN_SESSION | Campaign / Creator / Session | Explicit associations |
| Decision | APPROVES | Proposal | For approval only |
| Decision | SUPPORTED_BY | Source | User feedback source or approval evidence |
| Decision | REVOKES | Decision | Revoke event points to rejection event |

Source IDs on edges must resolve to real Source nodes. Fact checks combine a current node value with its current supporting source version. Old Source nodes and old run snapshots remain available after edits.

## Decision scopes

- Rejected decisions store `scope_type=campaign`, `scope_id=camp_01`, or `scope_type=brand`, `scope_id=brand_01`.
- A campaign link records where the rejection was made even when the rejection applies to the whole brand.
- A rejection is active at `as_of_ms` when its own `as_of_ms <= current_as_of_ms`, it is not expired, and there is no effective REVOKES event at or before current_as_of_ms.
- Expiry is exclusive: at `as_of_ms >= expires_at_ms` the rejection no longer applies. This is intentionally different from inclusive agreement intervals.
- Rejection reasons are remembered instructions from the operator about selection scope, not general facts about a real creator.
- Revocation appends a new decision; it does not delete or rewrite the original event.

## Provenance and immutable snapshots

Use IDs such as `src_agreement_cr03_v1`. On a synthetic edit create `src_agreement_cr03_v2`, connect SUPERSEDES, update the current fact and its SUPPORTED_BY edge, and increment context revision atomically. The new source records editor type `local_demo_operator` in its text. Do not falsely retain the old source's verification timestamp for new content.

Every persistence-bearing request writes its MutationReceipt in the same atomic statement as its result. Draft tools use a stable server-derived key for run/candidate/revision, not arbitrary model strings. Retrying receipt-backed actions after a backend restart returns the original result. Receipts and transcript-only writes do not themselves advance context revision.

Run/proposal snapshot format contains: campaign constraints, candidate check values, ranking inputs, reason codes, source IDs and versions, source excerpts, relationship paths, as-of time, and context revision. The snapshot is immutable after approval. Live views can show that a later source exists, but must preserve the original basis for the decision.

The competitor relation's `source_id` and its brand Audit source can be the same document. Absence of competitor edges is meaningful only when this audit explicitly states the map is complete for the fictional scenario.

## Schema and ingestion invariants

- Validate unique IDs, positive monetary values, expected currency, known enums and referenced endpoints before any seed mutation.
- Validate `start_ms <= end_ms`; intentionally missing-date test fixtures must be explicitly marked as incomplete evidence, not silently repaired.
- Seed membership, then sources/facts, then relationships in a controlled initial load. Use idempotent MERGE by stable ID; re-seeding the same dataset leaves memory and run records untouched.
- An incompatible schema/data version requires an explicit migration or a separate graph, never automatic deletion.
- Create indexes for frequent IDs only with syntax verified against the installed release. Verify uniqueness in application validation and mutation tests; do not assume an index is a uniqueness constraint.
- Keep sources and graph strings within reasonable documented size limits; no binary files or model weights in the graph.

## Proof that the graph is essential

Conflict detection follows Creator → Agreement → Brand ↔ competing Brand → Campaign. Memory retrieval follows campaign ownership and the explicit decision scope. The executable workflow must use these connections, not a precomputed eligibility list in a JSON file. Stop FalkorDB and the agent must report unavailable context; it cannot invent the same answer from the fixture.
