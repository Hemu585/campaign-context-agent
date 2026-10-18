# Query catalog and implementation contracts

These are proposed query shapes and contracts. They have not been run by the author of this package. Validate every executable query against the selected FalkorDB image before declaring it implemented. Use the official client and its parameter binding; do not interpolate user or model text into Cypher.

## Catalog

| ID | Query responsibility | Returned evidence |
| --- | --- | --- |
| Q01 | Get campaign, client brand, current participants, brief source and revision | Full constraints and ownership |
| Q02 | Enumerate all active creators, their exact offers, supported sources and history counts | Offer matches and ranking inputs |
| Q03 | Get positive/negative availability with source metadata | Window coverage and conflicts |
| Q04 | Traverse agreements, counterparties, and direct competitor edges | Candidate conflict paths |
| Q05 | Retrieve agreement and competitor-map audits | Completeness, freshness, and coverage |
| Q06 | Retrieve scope-matching rejection/revocation events | Active memory and reason sources |
| Q07 | Fetch allowed source IDs and evidence paths | Provenance and focused visualization |
| Q08 | Save run/messages/considered creators and immutable evidence | Persistent session and result |
| Q09 | Stage an idempotent draft from a verified run/candidate | Internal proposed action |
| Q10 | Atomically approve with expected revision and unfilled slot | One approval + proposal + campaign update |
| Q11 | Atomically reject or revoke with revision update | Persistent scoped feedback |
| Q12 | Atomically edit a permitted synthetic fact and version its source | Updated context and audit trail |
| Q13 | Load sessions/runs/proposals and prior snapshots | Restart continuity |

Queries must enumerate all twelve fixture creators before ranking. Do not use a top-N limit on offers before conflict checks, which could incorrectly report no available replacement.

## Illustrative read queries

### Campaign and owner

```cypher
MATCH (b:Brand)-[:RUNS]->(c:Campaign {id: $campaign_id})
MATCH (c)-[:SUPPORTED_BY]->(s:Source)
RETURN c, b, s
```

### Direct competing-brand path

```cypher
MATCH p = (r:Creator {id: $creator_id})-[:HAS_AGREEMENT]->(a:Agreement)
          -[:WITH_BRAND]->(other:Brand)-[:COMPETES_WITH]-(client:Brand)
          -[:RUNS]->(c:Campaign {id: $campaign_id})
WHERE a.exclusive = true
  AND a.status = 'active'
  AND a.start_ms <= c.end_ms
  AND a.end_ms >= c.start_ms
  AND (a.channel = c.channel OR a.channel = 'all')
  AND (a.category = c.category OR a.category = 'all')
RETURN p, r.id AS creator_id, a.id AS agreement_id
```

This query finds known conflicts. It does not prove their absence. Q04 must also fetch all potentially relevant agreements, including incomplete records, and Q05 must validate audit coverage. Null dates omitted by the WHERE clause are an unknown condition evaluated separately. Cancelled status requires valid supporting evidence too.

### Offer evidence

```cypher
MATCH (r:Creator)-[:OFFERS]->(o:Offer)-[:SUPPORTED_BY]->(s:Source)
WHERE r.active = true
RETURN r.id AS creator_id, o, s
```

Retrieve all bounded fixture offers to distinguish a mismatch from missing records. The rule service applies exact offer matching, quote validity/freshness and budget checks. Current participation and completed history come from Q01/Q02 relationships.

### Relevant rejection episodes with revocations

```cypher
MATCH (d:Decision)-[:CONSIDERED]->(r:Creator {id: $creator_id})
WHERE d.action = 'rejected'
  AND ((d.scope_type = 'campaign' AND d.scope_id = $campaign_id)
    OR (d.scope_type = 'brand' AND d.scope_id = $brand_id))
OPTIONAL MATCH (rev:Decision)-[:REVOKES]->(d)
RETURN d, rev
```

Deduplicate returned decisions. Apply event time and expiry rules in the rule service using server-owned as-of time. Relevance is determined by graph ownership and explicit scope, not by model inference.

### Source lookup

```cypher
MATCH (s:Source)
WHERE s.id IN $source_ids
RETURN s.id AS id, s.document_id AS document_id, s.version AS version,
       s.title AS title, s.text AS text, s.observed_at_ms AS observed_at_ms,
       s.verified AS verified, s.synthetic AS synthetic
```

The application checks that requested source IDs belong to this run's evidence when an agent asks for them. A human evidence viewer may inspect any source in this single workspace through a separate validated endpoint.

## Atomic approval contract

Do not treat this pseudo-sequence as runnable Cypher:

```text
under the application's mutation lock:
  resolve existing request_id; verify matching payload hash; return existing result if found
  read draft, candidate, campaign, workspace revision and current evidence
  reject if stale, ineligible, unknown, rejected by memory, or slot already filled
  execute ONE parameterized graph statement:
    match Workspace where revision = expected_revision
    match Campaign where approved_proposal_id is absent
    match Proposal where status = draft and revision = expected_revision
    match its candidate and originating successful Run
    create approval Decision, explicit links, and immutable snapshot
    update Proposal status, approved_at_ms and approved_revision
    set Campaign approved_proposal_id
    increment Workspace context_revision and create MutationReceipt
    return saved IDs
  if no row was written, respond with a conflict
```

Use a server-generated decision ID and a caller-supplied validated idempotency key. Keys are unique across mutation operations within the workspace. Store a canonical payload hash. If the same key is reused for a different operation/payload, return `IDEMPOTENCY_CONFLICT`. A retry with identical payload returns the original success even if the graph revision has since moved.

Ensure a graph write failure cannot leave a partially approved proposal. Verify the pinned release's atomic statement behavior and test failure handling; do not claim database guarantees from untested assumptions.

## Limits and serialization

- Read-only operations use the read-only client path where supported; mutations use only dedicated services.
- Configure and test graph query timeout; target five seconds per query on this bounded dataset.
- Serialize nodes/edges/paths to stable application IDs. Sort and deduplicate deterministically.
- Avoid unbounded variable-length traversals, model-written query fragments, and fetching entire source corpora into the model context.
- Keep test fixture sources short. The model gets structured facts plus excerpts; the UI can inspect full sources.
- The compact model-facing candidate summary can omit repeated source text, but the persisted/API Evaluation retains every check and evidence reference. Never truncate eligible candidates before evaluating the full fixture.
- Save executable queries in `.cypher` files and reference their IDs in tool logs and README.
