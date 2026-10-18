"""Load and validate the versioned fictional fixture before any graph write.

JSON is only a seed input: the running app never answers from this file
(design decision D08). Validation covers unique IDs, positive integer paise, INR only,
known enums, start <= end, resolvable references and present source documents
(GRAPH_MODEL "Schema and ingestion invariants").
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.db.factsig import SOURCE_KIND_TO_FACT, fact_hash, text_checksum
from app.db.sourcedocs import (
    agreement_rows,
    audit_rows,
    availability_rows,
    campaign_rows,
    offer_rows,
    render_source,
    source_title,
)
from app.timeutil import parse_iso_ms

DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "synthetic"

CHANNELS = {"instagram", "youtube"}
DELIVERABLES = {"instagram_reel", "instagram_story", "youtube_short", "youtube_video"}
LANGUAGES = {"hi", "en"}
CATEGORIES = {"beauty", "fitness", "home", "technology"}
CAMPAIGN_STATUS = {"open", "completed"}
AVAILABILITY_STATUS = {"available", "unavailable"}
AGREEMENT_STATUS = {"active", "cancelled"}
PARTICIPATION_STATUS = {"completed", "assigned", "dropped_out"}
AUDIT_KINDS = {"agreements", "competitors"}
CURRENCY = "INR"


class DatasetError(ValueError):
    """The fixture is invalid; nothing has been written to the graph."""


def source_id_for(document_id: str, version: int = 1) -> str:
    return f"src_{document_id}_v{version}"


@dataclass
class SourceSeed:
    id: str
    document_id: str
    version: int
    kind: str
    title: str
    subject_id: str
    observed_at_ms: int
    verified: bool
    synthetic: bool
    fact_hash: str | None
    text: str
    checksum: str


@dataclass
class Dataset:
    version: str
    schema_version: int
    workspace: dict
    brands: list[dict]
    creators: list[dict]
    campaigns: list[dict]
    participation: list[dict]
    competitor_edges: list[dict]
    offers: list[dict]
    availability: list[dict]
    agreements: list[dict]
    audits: list[dict]
    sources: list[SourceSeed] = field(default_factory=list)
    root: Path | None = None


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise DatasetError(message)


def _positive_int(value, where: str) -> None:
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
             f"{where} must be a positive integer number of paise, got {value!r}")


def _time(value, where: str) -> int:
    try:
        return parse_iso_ms(value)
    except (TypeError, ValueError) as exc:
        raise DatasetError(f"{where} is not a timezone-aware ISO timestamp: {value!r}") from exc


def _interval(rec: dict, start_key: str, end_key: str, where: str) -> tuple[int | None, int | None]:
    start = rec.get(start_key)
    end = rec.get(end_key)
    if rec.get("incomplete") and (start is None or end is None):
        # Explicitly marked incomplete evidence: keep the gap, never repair it.
        return (None if start is None else _time(start, where), None if end is None else _time(end, where))
    s, e = _time(start, f"{where}.{start_key}"), _time(end, f"{where}.{end_key}")
    _require(s <= e, f"{where} has {start_key} after {end_key}")
    return s, e


def validate_raw(raw: dict) -> Dataset:
    """Validate a raw fixture dict and return a converted Dataset (no source texts yet)."""
    _require(isinstance(raw.get("dataset_version"), str), "dataset_version is required")
    ids: set[str] = set()

    def claim(entity_id, where):
        _require(isinstance(entity_id, str) and entity_id, f"{where} needs a string id")
        _require(entity_id not in ids, f"duplicate id {entity_id!r} ({where})")
        ids.add(entity_id)

    brands = copy.deepcopy(raw.get("brands", []))
    for b in brands:
        claim(b.get("id"), "brand")
        _require(b.get("category") in CATEGORIES, f"brand {b['id']} has unknown category {b.get('category')!r}")
    brand_ids = {b["id"] for b in brands}

    creators = copy.deepcopy(raw.get("creators", []))
    for c in creators:
        claim(c.get("id"), "creator")
        _require(isinstance(c.get("name"), str) and c["name"], f"creator {c['id']} needs a name")
        _require(isinstance(c.get("active"), bool), f"creator {c['id']} needs a boolean active flag")
    creator_ids = {c["id"] for c in creators}

    campaigns = copy.deepcopy(raw.get("campaigns", []))
    for c in campaigns:
        where = f"campaign {c.get('id')}"
        claim(c.get("id"), "campaign")
        _require(c.get("brand_id") in brand_ids, f"{where} references unknown brand {c.get('brand_id')!r}")
        _require(c.get("channel") in CHANNELS, f"{where} has unknown channel {c.get('channel')!r}")
        _require(c.get("deliverable") in DELIVERABLES, f"{where} has unknown deliverable")
        _require(c.get("language") in LANGUAGES, f"{where} has unknown language")
        _require(c.get("category") in CATEGORIES, f"{where} has unknown category")
        _require(c.get("currency") == CURRENCY, f"{where} must use {CURRENCY}")
        _require(c.get("status") in CAMPAIGN_STATUS, f"{where} has unknown status {c.get('status')!r}")
        _positive_int(c.get("budget_paise"), f"{where}.budget_paise")
        c["start_ms"], c["end_ms"] = _interval(c, "start", "end", where)
    campaign_ids = {c["id"] for c in campaigns}

    participation = copy.deepcopy(raw.get("participation", []))
    for p in participation:
        where = f"participation {p.get('creator_id')}->{p.get('campaign_id')}"
        _require(p.get("creator_id") in creator_ids, f"{where} references unknown creator")
        _require(p.get("campaign_id") in campaign_ids, f"{where} references unknown campaign")
        _require(p.get("status") in PARTICIPATION_STATUS, f"{where} has unknown status {p.get('status')!r}")

    edges = copy.deepcopy(raw.get("competitor_edges", []))
    for e in edges:
        _require(e.get("a") in brand_ids and e.get("b") in brand_ids, f"competitor edge {e} references unknown brand")
        _require(e["a"] != e["b"], "a brand cannot compete with itself")

    offers = copy.deepcopy(raw.get("offers", []))
    for o in offers:
        where = f"offer {o.get('id')}"
        claim(o.get("id"), "offer")
        _require(o.get("creator_id") in creator_ids, f"{where} references unknown creator {o.get('creator_id')!r}")
        _require(o.get("channel") in CHANNELS, f"{where} has unknown channel")
        _require(o.get("deliverable") in DELIVERABLES, f"{where} has unknown deliverable")
        _require(o.get("language") in LANGUAGES, f"{where} has unknown language")
        _require(o.get("category") in CATEGORIES, f"{where} has unknown category")
        _require(o.get("currency") == CURRENCY, f"{where} must use {CURRENCY}")
        _positive_int(o.get("fee_paise"), f"{where}.fee_paise")
        o["valid_from_ms"], o["valid_to_ms"] = _interval(o, "valid_from", "valid_to", where)

    availability = copy.deepcopy(raw.get("availability", []))
    for a in availability:
        where = f"availability {a.get('id')}"
        claim(a.get("id"), "availability")
        _require(a.get("creator_id") in creator_ids, f"{where} references unknown creator")
        _require(a.get("status") in AVAILABILITY_STATUS, f"{where} has unknown status {a.get('status')!r}")
        a["start_ms"], a["end_ms"] = _interval(a, "start", "end", where)

    agreements = copy.deepcopy(raw.get("agreements", []))
    for a in agreements:
        where = f"agreement {a.get('id')}"
        claim(a.get("id"), "agreement")
        _require(a.get("creator_id") in creator_ids, f"{where} references unknown creator")
        _require(a.get("counterparty_brand_id") in brand_ids, f"{where} references unknown brand")
        _require(isinstance(a.get("exclusive"), bool), f"{where} needs a boolean exclusive flag")
        _require(a.get("channel") in CHANNELS | {"all"}, f"{where} has unknown channel scope")
        _require(a.get("category") in CATEGORIES | {"all"}, f"{where} has unknown category scope")
        _require(a.get("status") in AGREEMENT_STATUS, f"{where} has unknown status {a.get('status')!r}")
        a["start_ms"], a["end_ms"] = _interval(a, "start", "end", where)
    agreements_by_creator: dict[str, set[str]] = {}
    for a in agreements:
        agreements_by_creator.setdefault(a["creator_id"], set()).add(a["id"])

    audits = copy.deepcopy(raw.get("audits", []))
    for a in audits:
        where = f"audit {a.get('id')}"
        claim(a.get("id"), "audit")
        _require(a.get("kind") in AUDIT_KINDS, f"{where} has unknown kind {a.get('kind')!r}")
        _require(isinstance(a.get("complete"), bool), f"{where} needs a boolean complete flag")
        listed = a.get("listed_ids")
        _require(isinstance(listed, list), f"{where} needs listed_ids")
        if a["kind"] == "agreements":
            _require(a.get("subject_id") in creator_ids, f"{where} subject must be a creator")
            allowed = agreements_by_creator.get(a["subject_id"], set())
            _require(set(listed) <= allowed, f"{where} lists agreements that are not this creator's")
        else:
            _require(a.get("subject_id") in brand_ids, f"{where} subject must be a brand")
            _require(set(listed) <= brand_ids, f"{where} lists unknown brands")
        a["coverage_start_ms"], a["coverage_end_ms"] = _interval(a, "coverage_start", "coverage_end", where)

    for group in (campaigns, participation, edges, offers, availability, agreements, audits):
        for rec in group:
            _require(isinstance(rec.get("source_doc"), str) and rec["source_doc"], f"record {rec} needs source_doc")
            rec["source_id"] = source_id_for(rec["source_doc"])

    return Dataset(
        version=raw["dataset_version"],
        schema_version=int(raw.get("schema_version", 1)),
        workspace=copy.deepcopy(raw.get("workspace") or {"id": "ws_demo"}),
        brands=brands, creators=creators, campaigns=campaigns, participation=participation,
        competitor_edges=edges, offers=offers, availability=availability, agreements=agreements,
        audits=audits,
    )


def _observed(rec: dict, default_ms: int) -> int:
    override = rec.get("source_observed_at")
    return default_ms if override is None else _time(override, f"{rec.get('id')}.source_observed_at")


def build_sources(ds: Dataset, default_observed_ms: int) -> list[SourceSeed]:
    """Derive one Source per fact record, rendering its document text."""
    brand_name = {b["id"]: b["name"] for b in ds.brands}
    creator_name = {c["id"]: c["name"] for c in ds.creators}
    seeds: dict[str, SourceSeed] = {}

    def add(kind, doc, subject_id, subject_label, observed_ms, rows, statement, hashed):
        sid = source_id_for(doc)
        text = render_source(kind=kind, document_id=doc, version=1, subject_id=subject_id,
                             subject_label=subject_label, observed_at_ms=observed_ms,
                             record_rows=rows, statement=statement)
        fact_kind = SOURCE_KIND_TO_FACT.get(kind)
        seeds[sid] = SourceSeed(
            id=sid, document_id=doc, version=1, kind=kind, title=source_title(kind, subject_label),
            subject_id=subject_id, observed_at_ms=observed_ms, verified=True, synthetic=True,
            fact_hash=fact_hash(fact_kind, hashed) if fact_kind else None,
            text=text, checksum=text_checksum(text),
        )

    for c in ds.campaigns:
        roster = [p for p in ds.participation if p["campaign_id"] == c["id"]]
        if c["status"] == "open":
            kind = "campaign_brief"
            parts = [f"{creator_name[p['creator_id']]} ({p['creator_id']}) {p['status'].replace('_', ' ')}"
                     for p in roster]
            statement = ("Roster for the single replacement slot: " + ("; ".join(parts) or "none")
                         + ". No other creator is currently assigned.")
        else:
            kind = "campaign_record"
            parts = [f"{creator_name[p['creator_id']]} ({p['creator_id']})" for p in roster
                     if p["status"] == "completed"]
            statement = "Completed deliverables recorded for: " + (", ".join(parts) or "no fixture creator") + "."
        add(kind, c["source_doc"], c["id"], f"{c['title']} ({c['id']})", _observed(c, default_observed_ms),
            campaign_rows(c, brand_name[c["brand_id"]]), statement, c)

    # Competitor edges cite the competitor-map document, which is rendered with the brand audit below.
    for o in ds.offers:
        add("offer", o["source_doc"], o["id"], f"{creator_name[o['creator_id']]} ({o['creator_id']})",
            _observed(o, default_observed_ms), offer_rows(o),
            "The quote applies only to the exact channel, deliverable, language and category listed.", o)

    for a in ds.availability:
        label = f"{creator_name[a['creator_id']]} ({a['creator_id']}), {a['status']}"
        statement = ("The creator confirmed availability for the whole window above."
                     if a["status"] == "available"
                     else "The creator is unavailable for the whole window above.")
        add("availability", a["source_doc"], a["id"], label, _observed(a, default_observed_ms),
            availability_rows(a), statement, a)

    for a in ds.agreements:
        label = f"{creator_name[a['creator_id']]} ({a['creator_id']}) with {brand_name[a['counterparty_brand_id']]}"
        add("agreement", a["source_doc"], a["id"], label, _observed(a, default_observed_ms),
            agreement_rows(a, brand_name[a["counterparty_brand_id"]]),
            "Exclusivity, when present, applies only within the channel and category scope and the dated term above.",
            a)

    for a in ds.audits:
        if a["kind"] == "agreements":
            label = f"{creator_name[a['subject_id']]} ({a['subject_id']})"
            listed = ", ".join(sorted(a["listed_ids"])) or "none"
            statement = ("Audit statement: every agreement involving this creator in the fictional scenario "
                         f"is represented for the coverage period. Represented agreements: {listed}.")
            kind = "agreement_audit"
        else:
            label = f"{brand_name[a['subject_id']]} ({a['subject_id']})"
            listed = ", ".join(f"{brand_name[b]} ({b})" for b in sorted(a["listed_ids"])) or "none"
            statement = ("Complete competitor map for the fictional scenario during the coverage period. "
                         f"Direct competitors: {listed}. Competition is never inferred from category alone.")
            kind = "competitor_map"
        add(kind, a["source_doc"], a["id"], label, _observed(a, default_observed_ms), audit_rows(a), statement, a)

    referenced = {r["source_id"] for g in (ds.campaigns, ds.participation, ds.competitor_edges, ds.offers,
                                            ds.availability, ds.agreements, ds.audits) for r in g}
    missing = sorted(referenced - set(seeds))
    _require(not missing, f"records cite source documents that no fact record defines: {missing}")
    return [seeds[k] for k in sorted(seeds)]


def source_file(root: Path, seed: SourceSeed) -> Path:
    return root / "sources" / f"{seed.document_id}_v{seed.version}.md"


def load_dataset(name: str = "demo_v1", *, check_files: bool = True, root: Path | None = None) -> Dataset:
    root = root or (DATA_ROOT / name)
    raw = json.loads((root / "dataset.json").read_text(encoding="utf-8"))
    ds = validate_raw(raw)
    ds.root = root
    default_ms = _time(raw.get("default_observed_at", "2026-10-15T12:00:00Z"), "default_observed_at")
    ds.sources = build_sources(ds, default_ms)
    if check_files:
        for seed in ds.sources:
            path = source_file(root, seed)
            _require(path.exists(), f"source document missing on disk: {path.name}")
            on_disk = path.read_text(encoding="utf-8")
            _require(on_disk == seed.text, f"source document {path.name} differs from the dataset; "
                                           "regenerate with scripts/generate_sources.py")
    return ds
