# Security, privacy and spending boundaries

This is a trusted single-user local demonstration using fictional records. These requirements protect the workflow; they are not a claim of production security or enterprise access control.

## Spending boundary

- No paid model API, cloud inference, hosting, observability service, database plan, API credits, subscription upgrade, or automatic billing retry.
- No cloud model fallback if local inference fails. Disable Ollama cloud features in its server, validate local model installation, and reject remote model endpoints and redirect escapes.
- No external fonts, image CDNs, analytics or runtime web search. Package downloads can use the internet during initial setup.

## Data boundary

All dataset contents and displayed creator identities are invented. Do not import actual contracts, creator contact details, company chats, customer records, social profiles, login-protected data, paywalled material or uploads. The approved MVP needs none of them.

Label generated source documents and UI data as fictional. Record source versions and validation status. No performance numbers or past campaign success metrics may be invented and presented as real observations.

## Local request boundary

Bind all exposed services to loopback. Browser writes need exact allowed Origin/Host, JSON content type, and the nonce issued by bootstrap. Validate IDs and scopes server-side. Do not rely only on a disabled button. There is no remote sharing or public tunnel under this brief.

The nonce prevents unintended browser-origin writes; it is not multi-user login. A compromised local machine can access local processes and the database, which is outside this MVP's threat model. Do not expose this configuration publicly.

## Model and source boundary

Source documents, user messages and tool outputs are untrusted data. They cannot grant permission, add a tool, change a graph, execute a shell command, or approve a proposal. Reject unknown tool names and arguments. Execute only predefined parameterized queries.

The model may stage an internal draft based on validated evidence. Approval, rejection scope changes, rejection revocation and synthetic fact edits require distinct human UI/API actions. Never accept model text as a substitute for that action.

Do not put raw model reasoning into the graph or UI. Store concise user-visible explanations, selected tools, status, timings, IDs, result summaries and evidence paths. Escape all source and model strings on rendering.

## Mutation and evidence boundary

Use idempotency keys, expected revision, pre-write revalidation and atomic statements. Keep original decision snapshots and sources after changes. Refuse unknown evidence and stale approvals. Limit run duration and tool count, and stop new work on cancellation.

Administrative direct DB writes are unsupported during the demo. App-controlled synthetic updates maintain source versions and revision integrity. Separate fixture-only test utilities from human-facing routes.

## Repository hygiene

Exclude `.env`, venvs, node_modules, model weights, database volumes, local process logs, browser captures containing personal information, and credentials. Include `.env.example` with non-secret local values, dependency locks, synthetic sources and setup commands. Check the actual diff before any user-authorized public push. Do not claim automated secret scanning unless it was performed.

## Failure behavior

Missing graph context: return GRAPH_UNAVAILABLE. Missing or invalid model: fail the AI run. Missing evidence: unknown. Stale write: conflict. No candidates: explain the empty result. No condition above authorizes a paid fallback, invented fact, real-world outreach, or silent loss of history.
