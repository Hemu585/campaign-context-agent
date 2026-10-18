# Fictional dataset and scenario oracle

Every name and commercial record in this file is invented for the demo. Use no real handles, phone numbers, emails, images, clients, or contracts. This dataset is the specification for fixtures; implementation must create versioned JSON and local Markdown source records from it.

## Fixed environment

- Dataset version: `demo_v1`.
- Demo clock: `2026-10-15T12:00:00Z` (15 October, 5:30 PM IST).
- Display the fixed clock; keep actual creation timestamps separate from business-rule `as_of_ms`.
- Freshness window: 30 days; source observation times below use the demo clock unless specified.
- Primary campaign: `camp_01`, “Luma Autumn Launch”, client `brand_01` Luma Skin.
- Delivery: `2026-10-20T09:00:00+05:30` through `2026-10-23T18:00:00+05:30`, inclusive.
- One `instagram_reel`, channel `instagram`, language `hi`, category `beauty`, currency `INR`.
- Budget: ₹25,000 / 2,500,000 paise; original creator `cr_01` has dropped out.
- All default offer quotes valid from 1 October through 31 October 2026 inclusive, observed on the fixed demo date.
- Default positive availability covers 20 October 00:00 through 24 October 23:59:59 IST.
- All default audits explicitly cover 1 October through 30 November 2026, with complete=true and verified sources.

## Brands

| ID | Name | Category | Relationship |
| --- | --- | --- | --- |
| brand_01 | Luma Skin | beauty | Client of primary campaign |
| brand_02 | Noro Glow | beauty | Direct competitor of brand_01 |
| brand_03 | Alto Fitness | fitness | Not listed as competitor |
| brand_04 | Pavo Home | home | Not listed as competitor |
| brand_05 | Kivo Tech | technology | Not listed as competitor |

The verified competitor-map source explicitly states this is the complete map for the fictional scenario. Store one COMPETES_WITH edge between brand_01 and brand_02 and query it undirected. Do not infer competition solely from category.

## Creator oracle

All rows have a matching active offer, fresh sources, default availability/audits, and no active rejection unless the exception says otherwise. The table's rupee amounts must be converted to integer paise in fixtures.

| ID | Fictional name | Fee INR | Completed history count | Exception | Baseline result |
| --- | --- | ---: | ---: | --- | --- |
| cr_01 | Asha Pine | 17,000 | 1 | Original creator; dropped out of camp_01 | ineligible |
| cr_02 | Mira Vale | 18,000 | 2 | None | eligible, rank 1 |
| cr_03 | Tara Reed | 15,000 | 1 | Active Noro Glow exclusive agreement | ineligible |
| cr_04 | Noor Finch | 21,000 | 1 | None | eligible, rank 2 |
| cr_05 | Elia Stone | 27,000 | 0 | Above budget | ineligible |
| cr_06 | Kavya Moss | 19,000 | 0 | Unavailable 21 Oct 00:00–22 Oct 23:59:59 IST | ineligible |
| cr_07 | Lena Brook | 16,000 | 0 | Only `en` offer; campaign requires `hi` | ineligible |
| cr_08 | Sia North | 17,000 | 0 | Agreement completeness audit missing | unknown |
| cr_09 | Ada Bloom | 23,000 | 0 | Noro Glow exclusivity ended 30 Sep | eligible, rank 3 |
| cr_10 | Rhea Lake | 24,000 | 0 | Active agreement with non-competing Alto Fitness | eligible, rank 4 |
| cr_11 | Dia Fern | 17,500 | 0 | Availability source observed 1 Sep 2026 | unknown |
| cr_12 | Nia Cove | 25,000 | 0 | Exactly at budget | eligible, rank 5 |

Keep all five eligible candidates in the evaluation even when only the top three are recommended. No candidate may be hidden before eligibility evaluation.

## Agreements and source records

- `agr_cr03`: Tara / Noro Glow, active, exclusive=true, category beauty, channel instagram, 1 October 00:00 through 31 October 23:59:59 IST.
- `agr_cr09`: Ada / Noro Glow, active record describing a historical agreement, exclusive=true, beauty/instagram, 1 September 00:00 through 30 September 23:59:59 IST. “Active record” does not make the interval overlap the campaign.
- `agr_cr10`: Rhea / Alto Fitness, active, exclusive=true, fitness/instagram, 1 October through 31 October. It is not a competing-brand beauty agreement.
- Every other complete audit explicitly records no additional represented agreements; absence without an audit remains unknown.
- Suggested source IDs: `src_camp01_brief_v1`, `src_competitors_brand01_v1`, `src_offer_cr02_v1`, `src_avail_cr02_v1`, `src_audit_cr02_v1`, `src_agreement_cr03_v1`.
- Each source is a short Markdown document with a FICTIONAL DEMO DATA label, subject ID, record fields, observation time, and version. The graph stores the corresponding immutable text and checksum.

## Historical campaigns and scope-test campaigns

Use eight campaigns total. `camp_02` is another Luma Skin replacement campaign with the same future constraints; `camp_03` is a Pavo Home replacement campaign with the same supported deliverable/language/category for scope tests. `camp_04`–`camp_08` are completed historical campaigns with dates before the demo clock. Assign counts from the table through distinct PARTICIPATED_IN edges marked completed: cr_01→camp_04; cr_02→camp_04/camp_05; cr_03→camp_06; cr_04→camp_07. Other historical campaigns may have no fixture participant. Source every participation edge.

Do not count dropped-out or assigned edges as completed. The two scope-test campaigns must have their own brief and competitor-map audit coverage. Their copied fictional requirements are intentional test inputs, not real marketing claims.

## Named scenarios

Each test scenario starts with an isolated baseline graph unless it explicitly describes sequential steps. The demonstration sequence is in DEMO_RUNBOOK.

| Scenario | Mutation / action | Required result |
| --- | --- | --- |
| S01 Baseline | None | Top three cr_02, cr_04, cr_09 |
| S02 Campaign memory | Reject cr_02 in camp_01 | New session: cr_04 first; camp_02 still allows cr_02 |
| S03 Brand memory | Reject cr_02 for brand_01 | camp_01 and camp_02 exclude cr_02; camp_03 does not |
| S04 Revoke/expire | Revoke rejection, or test exactly at expiry | cr_02 returns if otherwise eligible; original history retained |
| S05 Agreement change | Change agr_cr03 end to 19 Oct 23:59:59 IST with new source | cr_03 becomes eligible and ranks first at ₹15,000 |
| S06 Inclusive boundary | End agr_cr03 exactly at campaign start | cr_03 still conflicts |
| S07 Negative availability | Positive full coverage plus overlapping unavailable window | cr_06 remains excluded |
| S08 Missing evidence | Remove relevant audit or source in isolated test fixture | Unknown, never clear by absence |
| S09 Stale approval | Stage cr_02 then make cr_02 unavailable | Approval returns conflict; no approval writes |
| S10 Empty result | Add overlapping unavailable windows for all baseline eligible creators | No eligible recommendation; no draft |
| S11 Tie | Set cr_04 fee equal cr_02 | cr_02 wins by completed history; equalize counts and compare IDs |
| S12 Reverse competitor edge | Store competitor relationship in opposite direction | Same conflict result |
| S13 Transitive-only relation | Remove direct edge, add intermediary, and supply explicit verified complete map | No direct-competitor conflict inferred; other rules still apply |
| S14 Suspicious source | Add instruction-like text to fictional source | Text cannot change tools, scope, ranking, or approval |

Scenario-only mutations such as competitor edges, audits and source deletion can be created by test fixtures. They are not arbitrary-write UI endpoints. Production demo editor stays limited to agreement and availability fields.

## Safe seeding

Initial seed may populate a new graph. Re-running the same seed must not undo source edits, proposals, or feedback. If dataset_version differs, stop with an explicit migration message. Destructive reset requires a separate clearly labelled script targeting only the exact demo graph; it must never be an automatic startup action. Tests operate on disposable test graphs and clean up only their own names.
