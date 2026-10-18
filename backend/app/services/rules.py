"""Deterministic eligibility, status precedence and ranking (spec section 5).

Pure functions over a CampaignContext read from FalkorDB. Nothing here reads the
fixture file or model output, and the model cannot override a result. Every check
reports pass, fail, unknown or not_applicable with evidence source IDs; paths are
built only from graph rows.

Status precedence: ineligible > unknown > excluded_by_memory > eligible.
Ranking (eligible only): fee ascending, verified completed campaigns descending,
creator ID ascending. No engagement, ROI or confidence scores are invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.db.factsig import fact_hash
from app.models.api import CandidateEvaluation, Check, CompletedCampaign, EvidencePath, PathEdge, PathNode
from app.models.domain import (
    AgreementRec,
    AuditRec,
    AvailabilityRec,
    CampaignContext,
    CreatorRec,
    OfferRec,
)
from app.money import format_inr
from app.services.evidence import DAY_MS, Support, fact_support
from app.services.memory import decision_is_active
from app.timeutil import covers, ms_to_ist, overlaps

HARD_CHECKS = ("participation", "offer_match", "quote_validity", "budget", "availability",
               "agreement_audit", "competitor_audit", "exclusivity")
STATUS_ORDER = {"eligible": 0, "excluded_by_memory": 1, "unknown": 2, "ineligible": 3}
MAX_RECOMMENDATIONS = 3


def _window(start: int | None, end: int | None) -> str:
    left = "?" if start is None else ms_to_ist(start)
    right = "?" if end is None else ms_to_ist(end)
    return f"{left} – {right}"


def overlap_tristate(a_start: int | None, a_end: int | None, b_start: int, b_end: int) -> bool | None:
    """Inclusive overlap that stays unknown when a missing date could matter."""
    if a_start is not None and a_start > b_end:
        return False
    if a_end is not None and a_end < b_start:
        return False
    if a_start is None or a_end is None:
        return None  # a missing end date is never read as "expired"
    return overlaps(a_start, a_end, b_start, b_end)


@dataclass
class _Ctx:
    ctx: CampaignContext
    as_of_ms: int
    freshness_ms: int
    paths: list[EvidencePath] = field(default_factory=list)

    @property
    def camp(self):
        return self.ctx.campaign

    def support(self, kind: str | None, record: dict | None, source_ids, *, fresh: bool = True) -> Support:
        node_hash = fact_hash(kind, record) if kind else None
        return fact_support(node_hash, source_ids, self.ctx.sources, self.as_of_ms, self.freshness_ms,
                            require_fresh=fresh)

    def brand(self, brand_id: str | None) -> str:
        return self.ctx.brand_names.get(brand_id or "", brand_id or "unknown brand")

    def add_path(self, pid: str, check: str, creator_id: str, nodes: list[tuple[str, str, str]],
                 edges: list[tuple[str, str, str, tuple[str, ...]]]) -> str:
        sources = sorted({s for *_, src in edges for s in src})
        self.paths.append(EvidencePath(
            id=pid, check=check, creator_id=creator_id, node_ids=[n[0] for n in nodes],
            nodes=[PathNode(id=i, label=lbl, name=name) for i, lbl, name in nodes],
            edges=[PathEdge(from_=a, type=t, to=b, source_ids=list(src)) for a, t, b, src in edges],
            source_ids=sources,
        ))
        return pid


def _campaign_record(camp) -> dict:
    return {"brand_id": camp.brand_id, "channel": camp.channel, "deliverable": camp.deliverable,
            "language": camp.language, "category": camp.category, "currency": camp.currency,
            "budget_paise": camp.budget_paise, "start_ms": camp.start_ms, "end_ms": camp.end_ms}


def _offer_record(o: OfferRec) -> dict:
    return {"channel": o.channel, "deliverable": o.deliverable, "language": o.language, "category": o.category,
            "fee_paise": o.fee_paise, "currency": o.currency, "valid_from_ms": o.valid_from_ms,
            "valid_to_ms": o.valid_to_ms}


def _window_record(w: AvailabilityRec) -> dict:
    return {"start_ms": w.start_ms, "end_ms": w.end_ms, "status": w.status}


def _agreement_record(a: AgreementRec) -> dict:
    return {"counterparty_brand_id": a.counterparty_brand_id, "exclusive": a.exclusive, "channel": a.channel,
            "category": a.category, "start_ms": a.start_ms, "end_ms": a.end_ms, "status": a.status}


def _audit_record(a: AuditRec) -> dict:
    return {"kind": a.kind, "coverage_start_ms": a.coverage_start_ms, "coverage_end_ms": a.coverage_end_ms,
            "complete": a.complete, "listed_ids": list(a.listed_ids)}


# --- individual checks -----------------------------------------------------------------------


def check_participation(c: _Ctx, cr: CreatorRec, brief: Support) -> Check:
    camp = c.camp
    if cr.active is False:
        return Check(name="participation", result="fail", reason_code="INACTIVE_CREATOR",
                     detail=f"{cr.name} is marked inactive.")
    if cr.active is None:
        return Check(name="participation", result="unknown", reason_code="CREATOR_STATUS_MISSING",
                     detail=f"{cr.name} has no active flag on record.")
    blocking = [p for p in c.ctx.participants if p.creator_id == cr.id and p.status in ("dropped_out", "assigned")]
    if blocking:
        p = blocking[0]
        code = "DROPPED_OUT" if p.status == "dropped_out" else "CURRENTLY_ASSIGNED"
        verb = "dropped out of" if p.status == "dropped_out" else "is already assigned to"
        sup = c.support(None, None, [p.source_id] if p.source_id else [])
        pid = c.add_path(f"{cr.id}:participation:{camp.id}", "participation", cr.id,
                         [(cr.id, "Creator", cr.name), (camp.id, "Campaign", camp.title)],
                         [(cr.id, "PARTICIPATED_IN", camp.id, sup.source_ids)])
        if sup.ok:
            return Check(name="participation", result="fail", reason_code=code,
                         detail=f"{cr.name} {verb} {camp.title}.", source_ids=list(sup.source_ids),
                         facts={"participation_status": p.status, "path_id": pid})
        return Check(name="participation", result="unknown", reason_code=sup.reason_code,
                     detail=f"A {p.status.replace('_', ' ')} record exists but {sup.detail}.",
                     source_ids=list(sup.source_ids), facts={"path_id": pid})
    if not brief.ok:
        return Check(name="participation", result="unknown", reason_code=brief.reason_code,
                     detail=f"Campaign brief evidence is not usable: {brief.detail}.",
                     source_ids=list(brief.source_ids))
    return Check(name="participation", result="pass", detail="Not the dropped-out or a currently assigned creator.",
                 source_ids=list(brief.source_ids))


def check_offer(c: _Ctx, cr: CreatorRec) -> tuple[Check, OfferRec | None]:
    camp = c.camp
    offers = c.ctx.offers.get(cr.id, ())
    slot = (camp.channel, camp.deliverable, camp.language, camp.category)
    exact = [o for o in offers if (o.channel, o.deliverable, o.language, o.category) == slot]
    want = f"{camp.deliverable} in '{camp.language}' for {camp.category}"
    if not exact:
        have = "; ".join(f"{o.deliverable} in '{o.language}' for {o.category}" for o in offers) or "no offers"
        return Check(name="offer_match", result="fail", reason_code="NO_MATCHING_OFFER",
                     detail=f"No exact offer for {want}. On record: {have}.",
                     source_ids=sorted({s for o in offers for s in o.source_ids})), None
    in_currency = [o for o in exact if o.currency == camp.currency]
    if not in_currency:
        o = exact[0]
        return Check(name="offer_match", result="fail", reason_code="OFFER_CURRENCY_MISMATCH",
                     detail=f"The matching offer {o.id} is quoted in {o.currency}; the budget is in {camp.currency}.",
                     source_ids=list(o.source_ids)), None
    supported = [(o, c.support("offer", _offer_record(o), o.source_ids)) for o in in_currency]
    valid = [(o, s) for o, s in supported if s.ok]
    # Only quotes whose period covers the as-of time compete as "current". An undated quote might be
    # current, so it competes too; an expired or not-yet-valid quote never blocks a current one.
    current = [(o, s) for o, s in valid if _quote_may_cover(o, c.as_of_ms)]
    if len(current) > 1:
        ids = ", ".join(o.id for o, _ in current)
        return Check(name="offer_match", result="unknown", reason_code="MULTIPLE_MATCHING_OFFERS",
                     detail=f"Several current quotes match the slot ({ids}); reconcile them first.",
                     source_ids=sorted({x for _, s in current for x in s.source_ids})), None
    if current:
        o, s = current[0]
    elif valid:  # no usable current quote: the latest one lets quote_validity say why
        o, s = max(valid, key=lambda pair: (pair[0].valid_to_ms or 0, pair[0].id))
    else:
        o, s = supported[0]
    pid = c.add_path(f"{cr.id}:offer:{o.id}", "offer_match", cr.id,
                     [(cr.id, "Creator", cr.name), (o.id, "Offer", f"Quote {o.id}")],
                     [(cr.id, "OFFERS", o.id, s.source_ids)])
    if not s.ok:
        return Check(name="offer_match", result="unknown", reason_code=s.reason_code,
                     detail=f"Offer {o.id} cannot be used: {s.detail}.", source_ids=list(s.source_ids),
                     facts={"offer_id": o.id, "path_id": pid}), o
    return Check(name="offer_match", result="pass", detail=f"Exact offer {o.id}: {want}, in {o.currency}.",
                 source_ids=list(s.source_ids), facts={"offer_id": o.id, "path_id": pid}), o


def _quote_may_cover(o: OfferRec, at_ms: int) -> bool:
    if o.valid_from_ms is None or o.valid_to_ms is None:
        return True
    return o.valid_from_ms <= at_ms <= o.valid_to_ms


def check_quote(c: _Ctx, offer: OfferRec | None, offer_check: Check) -> Check:
    if offer is None or offer_check.result != "pass":
        return Check(name="quote_validity", result="not_applicable",
                     detail="Needs a supported exact offer first.")
    if offer.valid_from_ms is None or offer.valid_to_ms is None:
        return Check(name="quote_validity", result="unknown", reason_code="QUOTE_DATES_MISSING",
                     detail=f"Quote {offer.id} has no complete validity period.", source_ids=offer_check.source_ids)
    period = _window(offer.valid_from_ms, offer.valid_to_ms)
    facts = {"valid_from_ms": offer.valid_from_ms, "valid_to_ms": offer.valid_to_ms}
    if c.as_of_ms < offer.valid_from_ms:
        return Check(name="quote_validity", result="fail", reason_code="QUOTE_NOT_YET_VALID",
                     detail=f"Quote valid only from {period}.", source_ids=offer_check.source_ids, facts=facts)
    if c.as_of_ms > offer.valid_to_ms:
        return Check(name="quote_validity", result="fail", reason_code="QUOTE_EXPIRED",
                     detail=f"Quote expired; it was valid {period}.", source_ids=offer_check.source_ids, facts=facts)
    return Check(name="quote_validity", result="pass", detail=f"Quote valid {period}.",
                 source_ids=offer_check.source_ids, facts=facts)


def check_budget(c: _Ctx, offer: OfferRec | None, quote: Check) -> Check:
    if offer is None or quote.result != "pass":
        return Check(name="budget", result="not_applicable", detail="Needs a current, supported quote first.")
    budget = c.camp.budget_paise
    if offer.fee_paise is None or budget is None:
        return Check(name="budget", result="unknown", reason_code="FEE_MISSING",
                     detail="The quote or the budget has no amount recorded.", source_ids=quote.source_ids)
    facts = {"fee_paise": offer.fee_paise, "budget_paise": budget}
    if offer.fee_paise <= budget:
        return Check(name="budget", result="pass",
                     detail=f"{format_inr(offer.fee_paise)} is within the {format_inr(budget)} replacement budget.",
                     source_ids=quote.source_ids + list(c.camp.source_ids), facts=facts)
    return Check(name="budget", result="fail", reason_code="OVER_BUDGET",
                 detail=(f"{format_inr(offer.fee_paise)} exceeds the {format_inr(budget)} budget "
                         f"by {format_inr(offer.fee_paise - budget)}."),
                 source_ids=quote.source_ids + list(c.camp.source_ids), facts=facts)


def check_availability(c: _Ctx, cr: CreatorRec) -> Check:
    camp = c.camp
    windows = c.ctx.availability.get(cr.id, ())

    def path_for(w: AvailabilityRec, s: Support) -> str:
        return c.add_path(f"{cr.id}:availability:{w.id}", "availability", cr.id,
                          [(cr.id, "Creator", cr.name), (w.id, "Availability", f"{w.status} {_window(w.start_ms, w.end_ms)}")],
                          [(cr.id, "HAS_AVAILABILITY", w.id, s.source_ids)])

    unknown_blockers: list[tuple[AvailabilityRec, Support]] = []
    for w in windows:
        if w.status != "unavailable":
            continue
        s = c.support("availability", _window_record(w), w.source_ids)
        ov = overlap_tristate(w.start_ms, w.end_ms, camp.start_ms, camp.end_ms)
        if ov is False:
            continue
        if ov and s.ok:
            pid = path_for(w, s)
            return Check(name="availability", result="fail", reason_code="UNAVAILABLE_OVERLAP",
                         detail=f"Unavailable {_window(w.start_ms, w.end_ms)}, which overlaps the delivery window.",
                         source_ids=list(s.source_ids), facts={"window_id": w.id, "path_id": pid})
        unknown_blockers.append((w, s))

    covering = [w for w in windows if w.status == "available" and w.start_ms is not None and w.end_ms is not None
                and covers(w.start_ms, w.end_ms, camp.start_ms, camp.end_ms)]
    supported = [(w, c.support("availability", _window_record(w), w.source_ids)) for w in covering]
    good = [(w, s) for w, s in supported if s.ok]
    if unknown_blockers:
        w, s = unknown_blockers[0]
        pid = path_for(w, s)
        reason = s.reason_code if not s.ok else "AVAILABILITY_DATES_MISSING"
        why = s.detail if not s.ok else "the window has no complete dates"
        return Check(name="availability", result="unknown", reason_code=reason,
                     detail=f"An unavailable window may overlap the delivery window, but {why}.",
                     source_ids=list(s.source_ids), facts={"window_id": w.id, "path_id": pid})
    if good:
        w, s = good[0]
        pid = path_for(w, s)
        return Check(name="availability", result="pass",
                     detail=f"Available {_window(w.start_ms, w.end_ms)}, covering the whole delivery window.",
                     source_ids=list(s.source_ids), facts={"window_id": w.id, "path_id": pid})
    if supported:
        w, s = supported[0]
        pid = path_for(w, s)
        return Check(name="availability", result="unknown", reason_code=s.reason_code,
                     detail=f"A covering window exists but {s.detail}.", source_ids=list(s.source_ids),
                     facts={"window_id": w.id, "path_id": pid})
    partial = [w for w in windows if w.status == "available" and w.start_ms is not None and w.end_ms is not None
               and overlaps(w.start_ms, w.end_ms, camp.start_ms, camp.end_ms)]
    if partial:
        return Check(name="availability", result="unknown", reason_code="NO_COVERING_WINDOW",
                     detail="Recorded windows only partly cover the delivery window (windows are not merged).",
                     source_ids=sorted({s for w in partial for s in w.source_ids}))
    return Check(name="availability", result="unknown", reason_code="NO_AVAILABILITY_RECORD",
                 detail="No availability window on record covers the delivery window.")


def _audit_check(c: _Ctx, name: str, audits: tuple[AuditRec, ...], expected_ids: list[str], owner_id: str,
                 owner_label: str, owner_name: str, what: str, creator_id: str) -> Check:
    camp = c.camp
    if not audits:
        return Check(name=name, result="unknown", reason_code="AUDIT_MISSING",
                     detail=f"No {what} audit on record, so missing records cannot be ruled out.")
    problems: list[Check] = []
    for a in audits:
        s = c.support("audit", _audit_record(a), a.source_ids)
        pid = c.add_path(f"{creator_id}:{name}:{a.id}", name, creator_id,
                         [(owner_id, owner_label, owner_name), (a.id, "Audit", f"{what.capitalize()} audit {a.id}")],
                         [(owner_id, "HAS_AUDIT", a.id, s.source_ids)])
        facts = {"audit_id": a.id, "path_id": pid, "coverage_start_ms": a.coverage_start_ms,
                 "coverage_end_ms": a.coverage_end_ms, "listed_ids": list(a.listed_ids)}
        if not s.ok:
            problems.append(Check(name=name, result="unknown", reason_code=s.reason_code,
                                  detail=f"The {what} audit cannot be used: {s.detail}.",
                                  source_ids=list(s.source_ids), facts=facts))
            continue
        if a.complete is not True:
            problems.append(Check(name=name, result="unknown", reason_code="AUDIT_INCOMPLETE",
                                  detail=f"The {what} audit is not marked complete.", source_ids=list(s.source_ids),
                                  facts=facts))
            continue
        if (a.coverage_start_ms is None or a.coverage_end_ms is None
                or not covers(a.coverage_start_ms, a.coverage_end_ms, camp.start_ms, camp.end_ms)):
            problems.append(Check(name=name, result="unknown", reason_code="AUDIT_COVERAGE",
                                  detail=(f"The {what} audit covers {_window(a.coverage_start_ms, a.coverage_end_ms)}, "
                                          "not the whole delivery window."),
                                  source_ids=list(s.source_ids), facts=facts))
            continue
        if sorted(a.listed_ids) != sorted(expected_ids):
            problems.append(Check(name=name, result="unknown", reason_code="AUDIT_LIST_MISMATCH",
                                  detail=(f"The {what} audit lists {', '.join(a.listed_ids) or 'none'} but the graph "
                                          f"holds {', '.join(expected_ids) or 'none'}."),
                                  source_ids=list(s.source_ids), facts=facts))
            continue
        listed = ", ".join(a.listed_ids) or "none"
        return Check(name=name, result="pass",
                     detail=(f"Verified complete {what} audit covers {_window(a.coverage_start_ms, a.coverage_end_ms)};"
                             f" listed: {listed}."),
                     source_ids=list(s.source_ids), facts=facts)
    return problems[0]


def check_agreement_audit(c: _Ctx, cr: CreatorRec) -> Check:
    expected = sorted(a.id for a in c.ctx.agreements.get(cr.id, ()))
    return _audit_check(c, "agreement_audit", c.ctx.agreement_audits.get(cr.id, ()), expected, cr.id, "Creator",
                        cr.name, "agreement-completeness", cr.id)


def check_competitor_audit(c: _Ctx, cr: CreatorRec) -> Check:
    camp = c.camp
    for comp in c.ctx.client_competitors:
        s = c.support(None, None, [comp.source_id] if comp.source_id else [])
        if not s.ok:
            return Check(name="competitor_audit", result="unknown", reason_code=s.reason_code,
                         detail=f"The competitor link to {comp.name or comp.brand_id} cannot be used: {s.detail}.",
                         source_ids=list(s.source_ids))
    expected = sorted(x.brand_id for x in c.ctx.client_competitors)
    return _audit_check(c, "competitor_audit", c.ctx.competitor_audits, expected, camp.brand_id, "Brand",
                        camp.brand_name, "competitor-map", cr.id)


def check_exclusivity(c: _Ctx, cr: CreatorRec, audits_pass: bool) -> Check:
    camp = c.camp
    client = camp.brand_name
    conflicts, unknowns, cleared = [], [], []
    for a in c.ctx.agreements.get(cr.id, ()):
        other = c.brand(a.counterparty_brand_id)
        s = c.support("agreement", _agreement_record(a), a.source_ids)
        if not s.ok:
            unknowns.append((s.reason_code, f"agreement {a.id} with {other} cannot be used: {s.detail}", a, s, None))
            continue
        if a.counterparty_brand_id is None:
            unknowns.append(("AGREEMENT_COUNTERPARTY_MISSING", f"agreement {a.id} has no counterparty", a, s, None))
            continue
        if a.counterparty_brand_id == camp.brand_id:
            cleared.append(f"{a.id} is with the client brand itself")
            continue
        if not a.is_direct_competitor:
            cleared.append(f"{a.id} is with {other}, not a direct competitor of {client}")
            continue
        edge = c.support(None, None, a.competitor_edge_source_ids)
        if not edge.ok:
            unknowns.append((edge.reason_code, f"the competitor link {other}–{client} cannot be used: {edge.detail}",
                             a, s, edge))
            continue
        if a.status not in ("active", "cancelled") or a.exclusive is None:
            unknowns.append(("AGREEMENT_FIELDS_MISSING", f"agreement {a.id} has no usable status or exclusivity",
                             a, s, edge))
            continue
        if a.status == "cancelled":
            cleared.append(f"{a.id} with {other} is cancelled")
            continue
        if a.exclusive is False:
            cleared.append(f"{a.id} with {other} is not exclusive")
            continue
        if a.channel is None or a.category is None:
            unknowns.append(("AGREEMENT_SCOPE_MISSING", f"agreement {a.id} has no channel/category scope", a, s, edge))
            continue
        if a.channel not in (camp.channel, "all") or a.category not in (camp.category, "all"):
            cleared.append(f"{a.id} with {other} covers {a.channel}/{a.category}, outside this campaign's scope")
            continue
        ov = overlap_tristate(a.start_ms, a.end_ms, camp.start_ms, camp.end_ms)
        if ov is None:
            unknowns.append(("AGREEMENT_DATES_MISSING",
                             f"agreement {a.id} with {other} has missing dates, so it cannot be declared harmless",
                             a, s, edge))
            continue
        if ov:
            conflicts.append((a, s, edge))
        else:
            cleared.append(f"{a.id} with {other} ran {_window(a.start_ms, a.end_ms)}, outside the delivery window")

    def conflict_path(a: AgreementRec, s: Support, edge: Support | None) -> str:
        other_id = a.counterparty_brand_id
        nodes = [(cr.id, "Creator", cr.name), (a.id, "Agreement", f"Exclusive agreement {a.id}")]
        edges = [(cr.id, "HAS_AGREEMENT", a.id, s.source_ids)]
        if other_id:
            nodes.append((other_id, "Brand", c.brand(other_id)))
            edges.append((a.id, "WITH_BRAND", other_id, s.source_ids))
            if edge is not None and a.is_direct_competitor:
                nodes += [(camp.brand_id, "Brand", client), (camp.id, "Campaign", camp.title)]
                edges += [(other_id, "COMPETES_WITH", camp.brand_id, edge.source_ids),
                          (camp.brand_id, "RUNS", camp.id, tuple(camp.source_ids))]
        return c.add_path(f"{cr.id}:exclusivity:{a.id}", "exclusivity", cr.id, nodes, edges)

    if conflicts:
        a, s, edge = conflicts[0]
        pid = conflict_path(a, s, edge)
        others = [x[0].id for x in conflicts[1:]]
        return Check(
            name="exclusivity", result="fail", reason_code="COMPETITOR_EXCLUSIVITY",
            detail=(f"Active exclusive agreement {a.id} with {c.brand(a.counterparty_brand_id)} "
                    f"({a.channel}/{a.category}, {_window(a.start_ms, a.end_ms)}) overlaps the delivery window, "
                    f"and {c.brand(a.counterparty_brand_id)} is a direct competitor of {client}."
                    + (f" Also: {', '.join(others)}." if others else "")),
            source_ids=sorted(set(s.source_ids) | set(edge.source_ids)),
            facts={"agreement_id": a.id, "counterparty_brand_id": a.counterparty_brand_id, "path_id": pid},
        )
    if unknowns:
        code, why, a, s, edge = unknowns[0]
        pid = conflict_path(a, s, edge)
        return Check(name="exclusivity", result="unknown", reason_code=code or "AGREEMENT_EVIDENCE_INVALID",
                     detail=f"Cannot rule out a conflict: {why}.",
                     source_ids=sorted(set(s.source_ids) | set(edge.source_ids if edge else ())),
                     facts={"agreement_id": a.id, "path_id": pid})
    if not audits_pass:
        return Check(name="exclusivity", result="unknown", reason_code="REQUIRES_COMPLETE_AUDITS",
                     detail=("No conflict is visible, but without verified complete agreement and competitor "
                             "audits a hidden conflict cannot be ruled out."))
    for a in c.ctx.agreements.get(cr.id, ()):
        s = c.support("agreement", _agreement_record(a), a.source_ids)
        c.add_path(f"{cr.id}:exclusivity:{a.id}", "exclusivity", cr.id,
                   [(cr.id, "Creator", cr.name), (a.id, "Agreement", f"Agreement {a.id}"),
                    (a.counterparty_brand_id or "?", "Brand", c.brand(a.counterparty_brand_id))],
                   [(cr.id, "HAS_AGREEMENT", a.id, s.source_ids),
                    (a.id, "WITH_BRAND", a.counterparty_brand_id or "?", s.source_ids)])
    agreement_sources = sorted({x for a in c.ctx.agreements.get(cr.id, ()) for x in a.source_ids})
    detail = "No conflict found in verified demo records."
    if cleared:
        detail += " " + "; ".join(cleared) + "."
    return Check(name="exclusivity", result="pass", detail=detail, source_ids=agreement_sources,
                 facts={"cleared": cleared})


def check_memory(c: _Ctx, cr: CreatorRec) -> Check:
    camp = c.camp
    decisions = c.ctx.decisions.get(cr.id, ())
    active = [d for d in decisions if decision_is_active(d, c.as_of_ms)]
    if not active:
        return Check(name="memory", result="pass", detail="No active operator rejection applies here.",
                     facts={"inactive_decision_ids": [d.id for d in decisions]})
    d = active[0]
    scope = "this campaign" if d.scope_type == "campaign" else f"every {camp.brand_name} campaign"
    nodes = [(d.id, "Decision", f"Rejection {d.id}"), (cr.id, "Creator", cr.name)]
    edges = [(d.id, "CONSIDERED", cr.id, d.source_ids)]
    if d.made_in_campaign_id:
        nodes.append((d.made_in_campaign_id, "Campaign", d.made_in_campaign_id))
        edges.append((d.id, "FOR_CAMPAIGN", d.made_in_campaign_id, d.source_ids))
    pid = c.add_path(f"{cr.id}:memory:{d.id}", "memory", cr.id, nodes, edges)
    return Check(name="memory", result="fail", reason_code="REJECTED_BY_OPERATOR",
                 detail=f"The operator rejected {cr.name} for {scope}.",
                 source_ids=list(d.source_ids),
                 facts={"decision_ids": [x.id for x in active], "scope_type": d.scope_type, "scope_id": d.scope_id,
                        "reason": d.reason, "expires_at_ms": d.expires_at_ms, "path_id": pid})


# --- assembly ---------------------------------------------------------------------------------


def status_of(checks: list[Check]) -> str:
    hard = [ch for ch in checks if ch.name in HARD_CHECKS]
    if any(ch.result == "fail" for ch in hard):
        return "ineligible"
    if any(ch.result == "unknown" for ch in hard):
        return "unknown"
    if any(ch.name == "memory" and ch.result == "fail" for ch in checks):
        return "excluded_by_memory"
    return "eligible"


def completed_campaigns(c: _Ctx, creator_id: str) -> list[CompletedCampaign]:
    """Completed campaigns with verified sources. They break fee ties, so they are cited as evidence."""
    counted: dict[str, str] = {}
    for h in c.ctx.completed.get(creator_id, ()):
        s = c.support(None, None, [h.source_id] if h.source_id else [], fresh=False)
        if s.ok and h.campaign_id not in counted:
            counted[h.campaign_id] = h.source_id
    return [CompletedCampaign(campaign_id=k, source_id=v) for k, v in sorted(counted.items())]


def evaluate_context(ctx: CampaignContext, as_of_ms: int, freshness_days: int = 30
                     ) -> tuple[list[CandidateEvaluation], list[EvidencePath]]:
    c = _Ctx(ctx=ctx, as_of_ms=as_of_ms, freshness_ms=freshness_days * DAY_MS)
    brief = c.support("campaign", _campaign_record(ctx.campaign), ctx.campaign.source_ids)
    results: list[CandidateEvaluation] = []
    for cr in ctx.creators:
        before = len(c.paths)
        participation = check_participation(c, cr, brief)
        offer_check, offer = check_offer(c, cr)
        quote = check_quote(c, offer, offer_check)
        budget = check_budget(c, offer, quote)
        availability = check_availability(c, cr)
        agreement_audit = check_agreement_audit(c, cr)
        competitor_audit = check_competitor_audit(c, cr)
        audits_pass = agreement_audit.result == "pass" and competitor_audit.result == "pass"
        exclusivity = check_exclusivity(c, cr, audits_pass)
        memory = check_memory(c, cr)
        checks = [participation, offer_check, quote, budget, availability, agreement_audit, competitor_audit,
                  exclusivity, memory]
        status = status_of(checks)
        history = completed_campaigns(c, cr.id)
        results.append(CandidateEvaluation(
            creator_id=cr.id, name=cr.name, status=status,
            fee_paise=offer.fee_paise if offer is not None else None,
            completed_campaign_count=len(history), completed_campaigns=history, rank=None, checks=checks,
            active_rejection_ids=list(memory.facts.get("decision_ids", [])) if memory.result == "fail" else [],
            evidence_path_ids=[p.id for p in c.paths[before:]],
            failed_checks=[ch.name for ch in checks if ch.result == "fail"],
            unknown_checks=[ch.name for ch in checks if ch.result == "unknown"],
        ))

    eligible = sorted((r for r in results if r.status == "eligible"),
                      key=lambda r: (r.fee_paise, -r.completed_campaign_count, r.creator_id))
    for rank, r in enumerate(eligible, start=1):
        r.rank = rank
    others = sorted((r for r in results if r.status != "eligible"),
                    key=lambda r: (STATUS_ORDER[r.status], r.creator_id))
    return eligible + others, c.paths


def recommended_ids(candidates: list[CandidateEvaluation]) -> list[str]:
    return [r.creator_id for r in candidates if r.status == "eligible"][:MAX_RECOMMENDATIONS]
