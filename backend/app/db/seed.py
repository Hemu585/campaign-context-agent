"""Guarded, idempotent initial load of a validated fixture (SYNTHETIC_DATA "Safe seeding").

- New graph: load membership, then sources and facts, then relationships, then mark
  the workspace complete at context revision 1.
- Same dataset already complete: no-op, so operator memory, edits, runs and
  approvals are never overwritten.
- Interrupted load ('loading'): resume; every statement MERGEs by stable id with
  ON CREATE only.
- Different dataset_version: stop with an explicit migration message.
Never called automatically at API startup.
"""

from __future__ import annotations

from app.clock import wall_now_ms
from app.db.client import GraphClient
from app.db.dataset import Dataset
from app.errors import AppError


class SeedVersionMismatch(RuntimeError):
    pass


class SeedIntegrityError(RuntimeError):
    pass


async def workspace_state(client: GraphClient) -> dict | None:
    try:
        rows = await client.ro_query("Q00_revision")
    except AppError as exc:
        if exc.code == "NO_SEED_DATA":
            return None
        raise
    return rows[0] if rows else None


def _pick(rec: dict, *keys: str) -> dict:
    return {k: rec.get(k) for k in keys}


async def seed(client: GraphClient, ds: Dataset, *, now_ms: int | None = None) -> str:
    now_ms = now_ms or wall_now_ms()
    state = await workspace_state(client)
    if state is not None:
        if state["dataset_version"] != ds.version:
            raise SeedVersionMismatch(
                f"graph {client.graph_name!r} holds dataset {state['dataset_version']!r}, not {ds.version!r}. "
                "Migrate explicitly or seed a separate graph; nothing was changed."
            )
        if state["seed_status"] == "complete":
            return "already seeded"

    await client.run_catalog_script("SEED_indexes", tolerate=("already indexed",))
    ws = {"workspace_id": ds.workspace["id"]}
    await client.query("SEED_00_workspace", {
        **ws, "name": ds.workspace.get("name", ""), "schema_version": ds.schema_version,
        "dataset_version": ds.version, "now_ms": now_ms,
    })
    await client.query("SEED_01_brands", {**ws, "rows": [_pick(b, "id", "name", "category") for b in ds.brands]})
    await client.query("SEED_02_creators", {**ws, "rows": [_pick(c, "id", "name", "active") for c in ds.creators]})
    await client.query("SEED_03_sources", {"rows": [
        {"id": s.id, "document_id": s.document_id, "version": s.version, "kind": s.kind, "title": s.title,
         "subject_id": s.subject_id, "text": s.text, "checksum": s.checksum, "fact_hash": s.fact_hash,
         "observed_at_ms": s.observed_at_ms, "verified": s.verified, "synthetic": s.synthetic,
         "created_at_ms": now_ms}
        for s in ds.sources
    ]})
    await client.query("SEED_04_campaigns", {"rows": [
        _pick(c, "id", "brand_id", "title", "channel", "deliverable", "language", "category", "currency",
              "budget_paise", "start_ms", "end_ms", "status", "source_id") for c in ds.campaigns
    ]})
    await client.query("SEED_05_offers", {"rows": [
        _pick(o, "id", "creator_id", "channel", "deliverable", "language", "category", "fee_paise", "currency",
              "valid_from_ms", "valid_to_ms", "source_id") for o in ds.offers
    ]})
    await client.query("SEED_06_availability", {"rows": [
        _pick(a, "id", "creator_id", "start_ms", "end_ms", "status", "source_id") for a in ds.availability
    ]})
    await client.query("SEED_07_agreements", {"rows": [
        _pick(a, "id", "creator_id", "counterparty_brand_id", "exclusive", "channel", "category", "start_ms",
              "end_ms", "status", "source_id") for a in ds.agreements
    ]})
    audit_keys = ("id", "kind", "subject_id", "coverage_start_ms", "coverage_end_ms", "complete", "listed_ids",
                  "source_id")
    await client.query("SEED_08_creator_audits", {"rows": [
        _pick(a, *audit_keys) for a in ds.audits if a["kind"] == "agreements"
    ]})
    await client.query("SEED_09_brand_audits", {"rows": [
        _pick(a, *audit_keys) for a in ds.audits if a["kind"] == "competitors"
    ]})
    await client.query("SEED_10_participation", {"rows": [
        _pick(p, "creator_id", "campaign_id", "status", "source_id") for p in ds.participation
    ]})
    await client.query("SEED_11_competitors", {"rows": [
        _pick(e, "a", "b", "source_id") for e in ds.competitor_edges
    ]})

    dangling = (await client.ro_query("SEED_98_dangling_sources"))[0]["dangling"]
    if dangling:
        raise SeedIntegrityError(f"{dangling} relationship(s) cite a source_id with no Source node")
    await client.query("SEED_99_complete", {**ws, "now_ms": now_ms})
    return "seeded"
