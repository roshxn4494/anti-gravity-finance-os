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


def run_import(uploaded, account: str, password: str | None = None) -> dict:
    rows, warnings = loader.parse_file(uploaded, account, password=password)
    overrides = db.load_overrides()

    for r in rows:
        rules.classify_txn(r, overrides)
        r["id"] = db.make_id(r["account"], r["txn_date"],
                             r["description"], r["amount"])

    inserted, skipped = db.upsert_many(rows)
    reconciled = reconcile()

    # Automatically sync latest ledger balance into account_balances
    if rows:
        b_rows = [r for r in rows if r.get("balance") is not None]
        if b_rows:
            last_r = b_rows[-1]
            existing_b = db.load_account_balances()
            current_fd = 0.0
            if not existing_b.empty:
                match_acct = existing_b[existing_b["account"] == account]
                if not match_acct.empty:
                    current_fd = float(match_acct.iloc[0].get("smart_fd_balance", 0.0))
            
            db.upsert_account_balance({
                "account": account,
                "label": config.ACCOUNTS.get(account, {}).get("label", account.upper()),
                "total_balance": float(last_r["balance"]) + current_fd,
                "savings_balance": float(last_r["balance"]),
                "smart_fd_balance": current_fd,
                "as_of_date": str(last_r["txn_date"]),
                "notes": f"Auto-synced from statement import as of {last_r['txn_date']}"
            })

    return {"inserted": inserted, "skipped": skipped, "warnings": warnings,
            "rows_parsed": len(rows), "reconciled_rows": reconciled}


import pandas as pd


def reconcile() -> int:
    """Run reconciliation rules and update only transactions whose match state changed."""
    df = db.load_all()
    if df.empty:
        return 0

    orig_state = {}
    for _, row in df.iterrows():
        orig_state[row["id"]] = (
            row.get("match_status"),
            row.get("matched_with"),
            row.get("flags")
        )

    rows = df.to_dict("records")
    rules.detect_recurring(rows)
    match.match_all(rows)

    def _norm(val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return str(val).strip()

    changed_rows = []
    for r in rows:
        tid = r["id"]
        new_tuple = (r.get("match_status"), r.get("matched_with"), r.get("flags"))
        old_tuple = orig_state.get(tid, (None, None, None))
        if tuple(_norm(v) for v in new_tuple) != tuple(_norm(v) for v in old_tuple):
            changed_rows.append((r.get("match_status"), r.get("matched_with"), r.get("flags"), tid))

    if not changed_rows:
        return 0

    updated = 0
    conn = db.connect()
    try:
        with conn:
            cur = conn.executemany(
                """UPDATE transactions
                   SET match_status=?, matched_with=?, flags=?
                   WHERE id=?""",
                changed_rows
            )
            updated = cur.rowcount
    finally:
        conn.close()
    return updated


def reclassify_all_unoverridden() -> int:
    """Re-apply updated keyword rules to all transactions without manual overrides."""
    df = db.load_all()
    if df.empty:
        return 0
    overrides = db.load_overrides()
    rows = df.to_dict("records")
    changed = []
    for r in rows:
        # If user has not manually overridden this counterparty, re-classify
        cp = r.get("counterparty")
        if cp and f"counterparty:{cp}" in overrides:
            continue
        old_class = r.get("classification")
        old_cat = r.get("category")
        rules.classify_txn(r, overrides)
        if r.get("classification") != old_class or r.get("category") != old_cat:
            changed.append((r.get("classification"), r.get("category"), r.get("counterparty"), r["id"]))

    if not changed:
        return 0

    conn = db.connect()
    try:
        with conn:
            conn.executemany(
                "UPDATE transactions SET classification=?, category=?, counterparty=? WHERE id=?",
                changed
            )
    finally:
        conn.close()
    reconcile()
    return len(changed)


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
