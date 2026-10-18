"""Fact hashes tie a graph record to the source version that attests it.

A Source stores the hash of the record fields it attests. The evaluator recomputes
the hash from the current node and compares, so an edit that bypasses source
versioning shows up as SOURCE_MISMATCH, and two equally recent sources that
disagree show up as CONFLICTING_SOURCES (design gap G4).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

FACT_FIELDS: dict[str, tuple[str, ...]] = {
    "campaign": ("brand_id", "channel", "deliverable", "language", "category", "currency",
                 "budget_paise", "start_ms", "end_ms"),
    "offer": ("channel", "deliverable", "language", "category", "fee_paise", "currency",
              "valid_from_ms", "valid_to_ms"),
    "availability": ("start_ms", "end_ms", "status"),
    "agreement": ("counterparty_brand_id", "exclusive", "channel", "category", "start_ms",
                  "end_ms", "status"),
    "audit": ("kind", "coverage_start_ms", "coverage_end_ms", "complete", "listed_ids"),
}

# Which fact kind each source document kind attests.
SOURCE_KIND_TO_FACT = {
    "campaign_brief": "campaign",
    "campaign_record": "campaign",
    "offer": "offer",
    "availability": "availability",
    "agreement": "agreement",
    "agreement_audit": "audit",
    "competitor_map": "audit",
}


def fact_hash(kind: str, record: Mapping) -> str:
    fields = FACT_FIELDS[kind]
    payload = {}
    for field in fields:
        value = record.get(field)
        if field == "listed_ids":
            value = sorted(value or [])
        payload[field] = value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def text_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
