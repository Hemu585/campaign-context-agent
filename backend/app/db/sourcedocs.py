"""Renders the fictional source documents that back every graph fact.

The same renderer produces the committed seed files (scripts/generate_sources.py)
and new versions written by the demo editor, so a document always shows the exact
record fields its fact hash attests. Output is plain Markdown; the UI renders it
as text, never as HTML.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.money import format_inr
from app.timeutil import ms_to_ist, ms_to_iso_utc

FICTIONAL_LABEL = (
    "> FICTIONAL DEMO DATA. Invented for the Campaign Context Agent demo. "
    "No real person, brand, contract or rate is described."
)

KIND_TITLES = {
    "campaign_brief": "Campaign brief",
    "campaign_record": "Completed campaign record",
    "offer": "Fee quote",
    "availability": "Availability window",
    "agreement": "Brand agreement",
    "agreement_audit": "Agreement completeness audit",
    "competitor_map": "Competitor map",
    "operator_feedback": "Operator feedback",
}


def _when(ms: int | None) -> str:
    return "not recorded" if ms is None else f"{ms_to_ist(ms)} ({ms_to_iso_utc(ms)})"


def _table(rows: Sequence[tuple[str, str]]) -> str:
    lines = ["| Field | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def source_title(kind: str, subject_label: str) -> str:
    return f"{KIND_TITLES[kind]}: {subject_label}"


def render_source(
    *,
    kind: str,
    document_id: str,
    version: int,
    subject_id: str,
    subject_label: str,
    observed_at_ms: int,
    record_rows: Sequence[tuple[str, str]],
    statement: str,
    editor: str | None = None,
    operator_text: str | None = None,
) -> str:
    header = [
        f"# {source_title(kind, subject_label)}",
        "",
        FICTIONAL_LABEL,
        "",
        _table([
            ("Document", f"{document_id} (version {version})"),
            ("Subject", subject_id),
            ("Observed", _when(observed_at_ms)),
            ("Verification", "verified against fictional agency records"
             if editor is None else f"attested by {editor} in the local demo editor"),
        ]),
    ]
    if operator_text:
        # Free text from the operator is data: shown, never executed or turned into rules.
        header += ["", f"Operator text (untrusted, shown as data): {operator_text}"]
    body = ["", "## Record", "", _table(record_rows), "", statement, ""]
    return "\n".join(header + body)


def campaign_rows(c: Mapping, brand_name: str) -> list[tuple[str, str]]:
    return [
        ("campaign", f"{c['title']} ({c['id']})"),
        ("client brand", f"{brand_name} ({c['brand_id']})"),
        ("channel", c["channel"]),
        ("deliverable", c["deliverable"]),
        ("language", c["language"]),
        ("category", c["category"]),
        ("currency", c["currency"]),
        ("replacement budget", f"{format_inr(c['budget_paise'])} ({c['budget_paise']} paise)"),
        ("delivery window start", _when(c["start_ms"])),
        ("delivery window end", _when(c["end_ms"])),
    ]


def offer_rows(o: Mapping) -> list[tuple[str, str]]:
    fee = o.get("fee_paise")
    return [
        ("offer", o["id"]),
        ("channel", o["channel"]),
        ("deliverable", o["deliverable"]),
        ("language", o["language"]),
        ("category", o["category"]),
        ("fee", "not recorded" if fee is None else f"{format_inr(fee)} ({fee} paise)"),
        ("currency", o["currency"]),
        ("valid from", _when(o.get("valid_from_ms"))),
        ("valid to", _when(o.get("valid_to_ms"))),
    ]


def availability_rows(a: Mapping) -> list[tuple[str, str]]:
    return [
        ("window", a["id"]),
        ("status", a["status"]),
        ("start", _when(a.get("start_ms"))),
        ("end", _when(a.get("end_ms"))),
    ]


def agreement_rows(a: Mapping, counterparty_name: str) -> list[tuple[str, str]]:
    return [
        ("agreement", a["id"]),
        ("counterparty brand", f"{counterparty_name} ({a['counterparty_brand_id']})"),
        ("exclusive", "yes" if a.get("exclusive") else "no"),
        ("channel scope", str(a.get("channel"))),
        ("category scope", str(a.get("category"))),
        ("start", _when(a.get("start_ms"))),
        ("end", _when(a.get("end_ms"))),
        ("status", str(a.get("status"))),
    ]


def audit_rows(a: Mapping) -> list[tuple[str, str]]:
    listed = ", ".join(sorted(a.get("listed_ids") or [])) or "none"
    return [
        ("audit", a["id"]),
        ("kind", a["kind"]),
        ("coverage start", _when(a.get("coverage_start_ms"))),
        ("coverage end", _when(a.get("coverage_end_ms"))),
        ("complete", "yes" if a.get("complete") else "no"),
        ("listed records", listed),
    ]
