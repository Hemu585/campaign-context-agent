# Acceptance tests and verification gates

Status at handoff: NOT RUN. The specification is not evidence of test execution.

Use small unit tests for temporal/status logic, real-FalkorDB integration tests for relationship-dependent outcomes and writes, one browser workflow, and a real-local-model smoke suite. Mock inference only in deterministic automation; label it as mocked. Never mock FalkorDB in tests that claim graph integration or persistence.

## Test catalog

| ID | Test and setup | Expected result |
| --- | --- | --- |
| T01 | Fresh dependency install, health and preflight | Actual versions reported; missing services clearly identified; no billing setup |
| T02 | Seed twice, inspect nodes/edges, stop graph | Stable counts and IDs; no duplicate facts; graph-down requests fail instead of using JSON fallback |
| T03 | S01 baseline with real Cypher | Five eligible; top three cr_02/cr_04/cr_09; all twelve evaluated; exact exclusions shown |
| T04 | Budget boundary, wrong currency, missing offer, current participant, expired quote | Exact paise comparisons; equal budget allowed; wrong/unknown evidence distinguished; no premature LIMIT |
| T05 | S05/S06/S12/S13 and channel/category scope | Expired agreement stops blocking; exact start overlap blocks; reversed edge works; no transitive inference; nonexclusive/unrelated scope doesn't block |
| T06 | S08 plus stale/future/unverified/conflicting sources and null agreement dates | Unknown unless an independent verified hard failure exists; no unsupported “clear” result |
| T07 | S11 and equal ranking inputs | Fee, history, then ID order; no stochastic order or fabricated score |
| T08 | Real model baseline/repeat, memory, change, no-candidate; malformed tool/loop caps using test double | Real required tools and valid final results; rejected illegal calls; bounded attempts; no fake completion |
| T09 | Open each recommended/excluded claim's source and path; inject invented source ID in model output | Valid graph path/source provenance; invented IDs rejected; snapshot text matches source version |
| T10 | S02/S03/S04 across new sessions | Correct campaign/brand scope; revocation and expiry take effect; history remains |
| T11 | Edit agreement through app and compare old/new run evidence | Revision increments; source versions preserved; old result stale; historical snapshot unchanged |
| T12 | S09, noneligible candidate, already-filled slot, forged chat approval | No unauthorized or stale approval; successful approval creates all links and fills one slot |
| T13 | Same idempotency key twice, changed payload, simultaneous approvals, interrupted write error | One outcome for retry; 409 on reuse with new payload; one winning approval; no partial state |
| T14 | Save feedback/approval, restart backend and database, recreate DB container keeping volume | Sessions/decisions/snapshots survive; approval and memory behavior unchanged; pending run marked interrupted |
| T15 | Remove qualifying relationship or stop graph during run | Result changes or explicit failure; no memorized model/fixture answer accepted |
| T16 | S14, unknown tool, arbitrary Cypher payload, cross-origin POST, invalid nonce, cancel/timeout | No unauthorized mutation; bounded failure; escaped source text; no new tools after cancellation |
| T17 | Inspect endpoint validation, offline runtime, disabled cloud, missing model | Remote endpoint/cloud tag refused; no provider fallback; demo works after downloads without external API |
| T18 | Browser: campaign→request→evidence→reject→new session→changed result→proposal→approve | Working controls and final state; stale action disabled; keyboard and target viewport checked |
| T19 | Reproduce README, inspect final source tree, participant walkthrough and submission artifacts | Exact setup works; no keys/data leaks; disclosure accurate; participant can explain implementation |

## Additional edge expectations

- A positive availability window must individually cover the delivery interval; the MVP does not merge partial adjacent windows. Negative overlap wins.
- Missing fee does not sort to zero. Unknown creators cannot be staged or approved.
- A self-brand agreement is not a competitor agreement. Record-source freshness still matters.
- A rejected creator who also has a known hard failure is ineligible with the memory reason also shown; do not hide failures behind memory status.
- Approval rechecks every rule, not just revision equality. Revision mismatch always demands rerun even if the candidate might still qualify.
- A rejected creator outside the relevant scope is unaffected. Revoking a rejection twice with different request IDs does not erase or duplicate its effect; return an explicit already-revoked state or conflict.
- An old approved proposal remains visible after facts change; its snapshot is not rewritten to look retrospectively correct.
- Invalid model prose cannot override machine-validated fields or source IDs.

## Requirement-to-test matrix

| Requirements | Primary verification |
| --- | --- |
| R01, R18 | T01, T17 |
| R02, R03 | T02, T15 |
| R04, R05, R08 | T03, T04, T07, T18 |
| R06, R07, R23 | T04, T05, T06 |
| R09, R17 | T08, T16 |
| R10, R24 | T09, T11, T14 |
| R11, R12 | T10 |
| R13 | T11 |
| R14, R15 | T12, T13 |
| R16 | T14 |
| R19 | T16 |
| R20 | T18 |
| R21, R22 | T19 |

## Gates and evidence

1. Graph gate: T02–T07 and graph-dependency behavior pass against actual FalkorDB.
2. Mutation gate: memory, source versioning, idempotency, stale and duplicate approvals pass.
3. Agent gate: real model completes each named normal scenario plus one baseline repeat; no invalid recommendation accepted.
4. Persistence gate: explicit stop/start and recreate-with-volume check passes, not just browser refresh.
5. Demo gate: functional browser flow, honest error states, no runtime cloud/API dependency, reproducible README.

For each gate record command, commit (if available), tool/service versions, model digest, machine summary, observed timing, pass/fail/blocked, and relevant output. Do not paste secrets, model reasoning, or entire logs. Fix concrete failures; do not broaden optional testing once these gates are sufficiently verified.

## Performance records

Measure cold model load separately from a warm run. Record at least three warm graph evaluations and two complete baseline model runs. Report observations and hardware rather than claiming the prototype meets universal latency targets. A timeout is a visible failure, not a shortened invented answer.

## Destructive test boundary

Tests may create/delete only their own uniquely named test graphs. Container recreation tests must target the project-specific service and named test volume. Never run `docker system prune`, delete unrelated databases, or erase the demo graph to make a test pass. A human demo reset is separate and explicit.
