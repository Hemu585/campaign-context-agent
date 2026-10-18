# UI requirements

## Visual direction

Build a clean desktop operations interface: white/off-white background, dark readable text, restrained burgundy action accent, rounded cards, thin borders, clear spacing. Use system fonts and local assets. Use initials or simple locally generated avatars for fictional creators; no actual influencer photos or externally fetched images. Display “Synthetic demo data” and the demo as-of date persistently.

Avoid a generic chat-only page. The task, candidate comparison, supporting evidence and saved outcome must be visible.

## Layout

1. Header: product name, campaign selector, new-session action, local service status.
2. Main left area: selected campaign summary and agent conversation with current progress.
3. Main right area: ranked replacement cards/table with status and reason chips.
4. Evidence drawer: facts, sources, relationship paths, tool activity.
5. Secondary tabs: decision history and synthetic data editor.

At 1280×720 preserve readable tables and functional controls; use drawers or tabs instead of squeezing every panel. On narrow screens stack content and provide horizontal table scrolling with labels intact.

## Campaign summary

Show client, deliverable, channel, language, category, delivery interval, replacement budget, dropped-out creator, and whether the slot already has an approved proposal. Use ₹ formatting from integer paise and Indian date/time display. A draft must not make the slot look filled.

## Conversation

- Suggested prompt: “Find a replacement for this campaign and explain any conflicts.”
- Show real phases such as reading campaign, checking candidates, reviewing memory, and preparing proposal. Derive phases from actual tool execution.
- Let the user cancel; show interruption/failure with a retry action.
- Disable new run while one is active. Never fake typing or progress that implies a tool ran when it did not.
- A model outage leaves a clear incomplete state. Diagnostic candidate checks remain labelled “Rule check — no AI run.”

## Candidate comparison

Show name, fee, availability result, conflict result, memory status, final status, rank where applicable, and “View evidence.” Group eligible first, then excluded/unknown rows. Explicit text must accompany colors.

Use phrases such as “No conflict found in verified demo records” instead of an absolute legal guarantee. Unknown evidence must be labelled “Needs information.” Do not invent engagement statistics or use star ratings as an unexplained confidence signal.

Actions:

- Eligible draft candidate: “Review proposal.”
- Candidate rejection: open scope and reason dialog; campaign scope selected by default.
- Excluded-by-memory: show applicable reason and a deliberate “Revoke rejection” action in history.
- Stale result: “Information changed — run again”; disable approval.

## Evidence

For the competitor case show the actual path: creator, agreement, competing brand, client brand, campaign. Label every relationship. Other checks show offer and availability paths with local source links. A simple SVG or a small existing graph library is sufficient; do not spend time on a full graph editor.

The sources panel shows document title, version, verification observation date, fictional label, excerpt, and full text. Provide a keyboard-accessible list of the same paths so the diagram is not the only way to inspect evidence. Render strings as text, not raw HTML.

“Tool activity” shows tool name, status, elapsed time and relevant record IDs/query IDs. It is an operational trace, not model chain-of-thought. Raw Cypher can remain in developer documentation.

## Proposal confirmation

Display chosen creator, quoted fee, brief constraints, evidence summary and whether information is current. State: “Approves an internal replacement proposal. Does not contact or book the creator.” The user clicks “Approve proposal.” The UI renders the backend's saved approval and updated slot state; it never shows success optimistically before the write completes.

On 409 show the reason and refresh; do not silently approve another creator. Double clicks reuse the same idempotency key until the action resolves.

## Decision history and memory

Show actual operator actions, scope, reason, event time, expiry/revocation state, source link and campaign. New Session preserves these records. Explain that a campaign rejection applies only here, while a brand rejection applies across that brand's campaigns. Do not call conversation text itself a persistent preference.

## Synthetic data editor

Expose only the limited agreement/availability fields in API_CONTRACTS. Show old and new value, require an edit reason, and display changed-source feedback. This panel is for the demo; no file upload or real-data import. Editing marks affected displayed results stale through the revision response.

## Required empty/error states

No seed data, missing campaign, no eligible candidates, unknown evidence, model missing, graph down, run busy, timeout, stale result, slot filled, validation error, cancellation, and interrupted run after restart. Each state gives a relevant next step and preserves readable existing evidence.

## Accessibility and verification

Keyboard navigation, visible focus, dialog focus handling, labelled inputs, non-color status indicators, readable contrast, and an aria-live region for run status. Test a full workflow and inspect the app at the target viewport. Keep decorative animation optional and respect reduced-motion preferences.
