"""Import + reconcile pipeline.

Import flow:  parse → classify (with saved overrides) → dedupe-upsert
Reconcile:    load everything → re-detect recurring → re-match transfers &
              pass-through → write match state back.

Matching always runs over the whole table, not just the new batch, so a newly
imported transfer can pair with an old deposit and vice-versa.
"""
from __future__ import annotations

from . import config, db
from .classify import match, rules
from .ingest import loader


def run_import(uploaded, account: str) -> dict:
    rows, warnings = loader.parse_file(uploaded, account)
    overrides = db.load_overrides()

    for r in rows:
        rules.classify_txn(r, overrides)
        r["id"] = db.make_id(r["account"], r["txn_date"],
                             r["description"], r["amount"])

    inserted, skipped = db.upsert_many(rows)
    reconciled = reconcile()
    return {"inserted": inserted, "skipped": skipped, "warnings": warnings,
            "rows_parsed": len(rows), "reconciled_rows": reconciled}


def reconcile() -> int:
    df = db.load_all()
    rows = df.to_dict("records")
    rules.detect_recurring(rows)
    match.match_all(rows)

    updated = 0
    conn = db.connect()
    try:
        with conn:
            for r in rows:
                cur = conn.execute(
                    """UPDATE transactions
                       SET match_status=?, matched_with=?, flags=?
                       WHERE id=?""",
                    (r.get("match_status"), r.get("matched_with"),
                     r.get("flags"), r["id"]))
                updated += cur.rowcount
    finally:
        conn.close()
    return updated


def reclassify(txn_id: str, classification: str, category: str,
               counterparty: str | None = None) -> int:
    """Apply a manual reclassify and, if keyed by counterparty, remember it as
    an override so future imports (and existing rows) auto-fill. Re-runs
    matching afterwards so a re-labelled transfer/CC payment gets paired."""
    db.reclassify(txn_id, classification, category)
    updated = 0
    if counterparty:
        db.save_override(counterparty, classification, category)
        updated = db.apply_override_to_rows(counterparty, classification, category)
    reconcile()
    return updated


def import_overrides_from_config() -> None:
    """Not used yet — reserved for rules auto-derived from config in future."""
    return None
