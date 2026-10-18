"""Fixture validation runs before any seed write (GRAPH_MODEL ingestion invariants, T02)."""

import copy
import json
import shutil

import pytest

from app.db.dataset import DATA_ROOT, DatasetError, load_dataset, validate_raw
from app.db.factsig import fact_hash
from app.timeutil import parse_iso_ms

RAW = json.loads((DATA_ROOT / "demo_v1" / "dataset.json").read_text(encoding="utf-8"))


def mutated(fn):
    raw = copy.deepcopy(RAW)
    fn(raw)
    return raw


def test_baseline_loads_with_expected_counts():
    ds = load_dataset("demo_v1")
    assert ds.version == "demo_v1"
    assert len(ds.brands) == 5
    assert len(ds.creators) == 12
    assert len(ds.campaigns) == 8
    assert len(ds.offers) == 12
    assert len(ds.availability) == 13
    assert len(ds.agreements) == 3
    assert len(ds.audits) == 13
    assert len(ds.participation) == 8
    assert len(ds.competitor_edges) == 1
    assert len(ds.sources) == 49


def test_times_are_converted_to_utc_ms():
    ds = load_dataset("demo_v1")
    camp = next(c for c in ds.campaigns if c["id"] == "camp_01")
    assert camp["start_ms"] == parse_iso_ms("2026-10-20T03:30:00Z")
    assert camp["end_ms"] == parse_iso_ms("2026-10-23T12:30:00Z")
    assert camp["budget_paise"] == 2500000


def test_stale_availability_source_is_preserved_for_dia():
    ds = load_dataset("demo_v1")
    src = next(s for s in ds.sources if s.document_id == "avail_cr11")
    assert src.observed_at_ms == parse_iso_ms("2026-09-01T12:00:00+05:30")


def test_every_source_document_is_labelled_and_traceable():
    ds = load_dataset("demo_v1")
    for s in ds.sources:
        assert "FICTIONAL DEMO DATA" in s.text
        assert s.subject_id in s.text
        assert f"{s.document_id} (version 1)" in s.text
        assert s.synthetic is True and s.verified is True
        assert len(s.checksum) == 64


def test_committed_documents_match_the_dataset():
    # load_dataset(check_files=True) raises on any drift between JSON and Markdown.
    load_dataset("demo_v1", check_files=True)


def test_missing_source_file_is_rejected(tmp_path):
    shutil.copytree(DATA_ROOT / "demo_v1", tmp_path / "demo_v1")
    (tmp_path / "demo_v1" / "sources" / "offer_cr02_v1.md").unlink()
    with pytest.raises(DatasetError, match="missing"):
        load_dataset("demo_v1", root=tmp_path / "demo_v1")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda r: r["creators"].append({"id": "cr_01", "name": "Copy", "active": True}), "duplicate id"),
        (lambda r: r["offers"][0].update(fee_paise=-5), "positive integer"),
        (lambda r: r["offers"][0].update(fee_paise=17000.5), "positive integer"),
        (lambda r: r["campaigns"][0].update(budget_paise=True), "positive integer"),
        (lambda r: r["offers"][1].update(currency="USD"), "INR"),
        (lambda r: r["availability"][0].update(status="maybe"), "unknown status"),
        (lambda r: r["agreements"][0].update(start="2026-11-01T00:00:00+05:30"), "after"),
        (lambda r: r["offers"][2].update(creator_id="cr_99"), "unknown creator"),
        (lambda r: r["agreements"][0].update(counterparty_brand_id="brand_99"), "unknown brand"),
        (lambda r: r["audits"][0].update(listed_ids=["agr_cr03"]), "not this creator's"),
        (lambda r: r["campaigns"][0].update(start="2026-10-20T09:00:00"), "timezone"),
        (lambda r: r["competitor_edges"].append({"a": "brand_01", "b": "brand_01", "source_doc": "x"}), "itself"),
    ],
)
def test_invalid_fixtures_are_rejected_before_any_write(change, message):
    with pytest.raises(DatasetError, match=message):
        validate_raw(mutated(change))


def test_explicitly_incomplete_records_keep_their_gap():
    def drop_end(raw):
        raw["agreements"][0].pop("end")
        raw["agreements"][0]["incomplete"] = True

    ds = validate_raw(mutated(drop_end))
    agreement = next(a for a in ds.agreements if a["id"] == "agr_cr03")
    assert agreement["end_ms"] is None


def test_fact_hash_is_stable_and_field_sensitive():
    record = {"start_ms": 1, "end_ms": 2, "status": "available"}
    assert fact_hash("availability", record) == fact_hash("availability", dict(record))
    assert fact_hash("availability", record) != fact_hash("availability", {**record, "end_ms": 3})
    audit = {"kind": "agreements", "coverage_start_ms": 1, "coverage_end_ms": 2, "complete": True,
             "listed_ids": ["b", "a"]}
    assert fact_hash("audit", audit) == fact_hash("audit", {**audit, "listed_ids": ["a", "b"]})
