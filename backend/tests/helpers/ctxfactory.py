"""Build CampaignContext objects in memory for rule unit tests (no database).

Defaults mirror the demo_v1 baseline for camp_01: a fully evidenced, eligible creator.
Integration tests cover the same rules through real FalkorDB.
"""

from __future__ import annotations

from app.db.factsig import fact_hash
from app.models.domain import (
    AgreementRec,
    AuditRec,
    AvailabilityRec,
    CampaignContext,
    CampaignRec,
    CompetitorRec,
    CompletedRec,
    CreatorRec,
    DecisionRec,
    OfferRec,
    ParticipationRec,
    RevocationRec,
    SourceRec,
)
from app.timeutil import parse_iso_ms

AS_OF = parse_iso_ms("2026-10-15T12:00:00Z")
C_START = parse_iso_ms("2026-10-20T09:00:00+05:30")
C_END = parse_iso_ms("2026-10-23T18:00:00+05:30")
OCT_1 = parse_iso_ms("2026-10-01T00:00:00+05:30")
OCT_31 = parse_iso_ms("2026-10-31T23:59:59+05:30")
NOV_30 = parse_iso_ms("2026-11-30T23:59:59+05:30")
AVAIL_START = parse_iso_ms("2026-10-20T00:00:00+05:30")
AVAIL_END = parse_iso_ms("2026-10-24T23:59:59+05:30")


class Ctx:
    def __init__(self):
        self.sources: dict[str, SourceRec] = {}
        self.creators: list[CreatorRec] = []
        self.offers: dict[str, list[OfferRec]] = {}
        self.availability: dict[str, list[AvailabilityRec]] = {}
        self.agreements: dict[str, list[AgreementRec]] = {}
        self.agreement_audits: dict[str, list[AuditRec]] = {}
        self.decisions: dict[str, list[DecisionRec]] = {}
        self.completed: dict[str, list[CompletedRec]] = {}
        self.participants: list[ParticipationRec] = []
        campaign_fields = {"brand_id": "brand_01", "channel": "instagram", "deliverable": "instagram_reel",
                           "language": "hi", "category": "beauty", "currency": "INR", "budget_paise": 2500000,
                           "start_ms": C_START, "end_ms": C_END}
        self.source("src_brief", "campaign", campaign_fields)
        self.campaign = CampaignRec(id="camp_01", title="Luma Autumn Launch", brand_name="Luma Skin", status="open",
                                    approved_proposal_id=None, source_ids=("src_brief",), **campaign_fields)
        self.source("src_comp", "audit", self._audit_fields("competitors", ["brand_02"]))
        self.competitors = [CompetitorRec("brand_02", "Noro Glow", "src_comp")]
        self.competitor_audits = [AuditRec("aud_comp", "competitors", "brand_01", OCT_1, NOV_30, True, ("brand_02",),
                                           ("src_comp",))]
        self.brand_names = {"brand_01": "Luma Skin", "brand_02": "Noro Glow", "brand_03": "Alto Fitness"}

    @staticmethod
    def _audit_fields(kind, listed, start=OCT_1, end=NOV_30, complete=True):
        return {"kind": kind, "coverage_start_ms": start, "coverage_end_ms": end, "complete": complete,
                "listed_ids": list(listed)}

    def source(self, sid, kind=None, record=None, *, observed=AS_OF, verified=True, superseded_by=(), digest=None):
        h = digest if digest is not None else (fact_hash(kind, record) if kind else None)
        self.sources[sid] = SourceRec(id=sid, document_id=sid, version=1, kind=kind, title=sid, subject_id="x",
                                      observed_at_ms=observed, verified=verified, checksum="c", fact_hash=h,
                                      synthetic=True, superseded_by=tuple(superseded_by))
        return sid

    def creator(self, cid, *, name=None, fee=1800000, language="hi", currency="INR", active=True,
                offer=True, window=True, audit=True, completed=0, offer_observed=AS_OF,
                valid_from=OCT_1, valid_to=OCT_31):
        self.creators.append(CreatorRec(cid, name or cid, active))
        if offer:
            self.add_offer(cid, f"off_{cid}", fee=fee, language=language, currency=currency,
                           observed=offer_observed, valid_from=valid_from, valid_to=valid_to)
        if window:
            self.add_window(cid, f"av_{cid}", AVAIL_START, AVAIL_END, "available")
        if audit:
            self.add_agreement_audit(cid)
        for i in range(completed):
            sid = self.source(f"src_hist_{cid}_{i}", observed=AS_OF - 90 * 86_400_000)
            self.completed.setdefault(cid, []).append(CompletedRec(f"camp_hist_{cid}_{i}", sid))
        return self

    def add_offer(self, cid, oid, *, fee=1800000, language="hi", currency="INR", observed=AS_OF,
                  valid_from=OCT_1, valid_to=OCT_31, deliverable="instagram_reel"):
        rec = {"channel": "instagram", "deliverable": deliverable, "language": language, "category": "beauty",
               "fee_paise": fee, "currency": currency, "valid_from_ms": valid_from, "valid_to_ms": valid_to}
        sid = self.source(f"src_{oid}", "offer", rec, observed=observed)
        self.offers.setdefault(cid, []).append(OfferRec(id=oid, creator_id=cid, source_ids=(sid,), **rec))

    def add_window(self, cid, wid, start, end, status, *, observed=AS_OF):
        rec = {"start_ms": start, "end_ms": end, "status": status}
        sid = self.source(f"src_{wid}", "availability", rec, observed=observed)
        self.availability.setdefault(cid, []).append(AvailabilityRec(wid, cid, start, end, status, (sid,)))

    def add_agreement_audit(self, cid, *, listed=None, complete=True, start=OCT_1, end=NOV_30, observed=AS_OF):
        listed = listed if listed is not None else [a.id for a in self.agreements.get(cid, [])]
        rec = self._audit_fields("agreements", listed, start, end, complete)
        sid = self.source(f"src_aud_{cid}", "audit", rec, observed=observed)
        self.agreement_audits[cid] = [AuditRec(f"aud_{cid}", "agreements", cid, start, end, complete, tuple(listed),
                                               (sid,))]

    def add_agreement(self, cid, aid, *, counterparty="brand_02", exclusive=True, channel="instagram",
                      category="beauty", start=OCT_1, end=OCT_31, status="active", competitor=True,
                      observed=AS_OF):
        rec = {"counterparty_brand_id": counterparty, "exclusive": exclusive, "channel": channel,
               "category": category, "start_ms": start, "end_ms": end, "status": status}
        sid = self.source(f"src_{aid}", "agreement", rec, observed=observed)
        self.agreements.setdefault(cid, []).append(AgreementRec(
            id=aid, creator_id=cid, counterparty_brand_id=counterparty,
            counterparty_name=self.brand_names.get(counterparty), exclusive=exclusive, channel=channel,
            category=category, start_ms=start, end_ms=end, status=status, is_direct_competitor=competitor,
            competitor_edge_source_ids=("src_comp",) if competitor else (), source_ids=(sid,)))
        self.add_agreement_audit(cid)  # keep the audit list consistent with the graph
        return self

    def reject(self, cid, did, *, scope_type="campaign", scope_id="camp_01", as_of=AS_OF, expires=None,
               revoked_at=None):
        sid = self.source(f"src_fb_{did}")
        revs = (RevocationRec(f"rev_{did}", revoked_at),) if revoked_at is not None else ()
        self.decisions.setdefault(cid, []).append(DecisionRec(
            id=did, creator_id=cid, scope_type=scope_type, scope_id=scope_id, reason="test reason", as_of_ms=as_of,
            created_at_ms=as_of, expires_at_ms=expires, made_in_campaign_id="camp_01", revocations=revs,
            source_ids=(sid,)))
        return self

    def build(self) -> CampaignContext:
        return CampaignContext(
            revision=1, campaign=self.campaign, participants=tuple(self.participants), creators=tuple(self.creators),
            offers={k: tuple(v) for k, v in self.offers.items()},
            completed={k: tuple(v) for k, v in self.completed.items()},
            availability={k: tuple(v) for k, v in self.availability.items()},
            agreements={k: tuple(v) for k, v in self.agreements.items()},
            client_competitors=tuple(self.competitors),
            agreement_audits={k: tuple(v) for k, v in self.agreement_audits.items()},
            competitor_audits=tuple(self.competitor_audits),
            decisions={k: tuple(v) for k, v in self.decisions.items()},
            sources=dict(self.sources), brand_names=dict(self.brand_names))
