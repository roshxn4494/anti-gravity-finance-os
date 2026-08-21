"""Data quality audit & deduplication utility for finance.db.

Detects and cleans up legacy spacing-variant duplicates created when statements
were re-imported prior to hash normalization.
"""
from __future__ import annotations

import re
import sqlite3
import pandas as pd

from . import db, pipeline


def audit_duplicates() -> dict:
    """Audit the database for potential duplicate transactions.

    Returns summary of exact date/amount duplicates and formatting variant duplicates.
    """
    df = db.load_all()
    if df.empty:
        return {"total_rows": 0, "duplicate_candidates": 0, "details": []}

    df["clean_desc"] = df["description"].apply(
        lambda x: re.sub(r"[^a-zA-Z0-9]", "", str(x or "").lower())
    )

    groups = df.groupby(["account", "txn_date", "amount", "clean_desc"])
    duplicates = []

    for (acct, dt, amt, cdesc), group in groups:
        if len(group) > 1:
            sorted_g = group.sort_values("imported_at")
            keep = sorted_g.iloc[0]
            dups = sorted_g.iloc[1:]
            duplicates.append({
                "account": acct,
                "date": dt,
                "amount": abs(amt),
                "keep_id": keep["id"],
                "delete_ids": dups["id"].tolist(),
                "description": keep["description"],
                "count": len(group),
            })

    return {
        "total_rows": len(df),
        "duplicate_groups": len(duplicates),
        "duplicate_rows_to_remove": sum(len(d["delete_ids"]) for d in duplicates),
        "details": duplicates,
    }


def clean_duplicates() -> dict:
    """Remove spacing-variant duplicate rows from the database and re-reconcile."""
    audit = audit_duplicates()
    if audit["duplicate_rows_to_remove"] == 0:
        return {"removed": 0, "reconciled": pipeline.reconcile()}

    all_to_delete = []
    for d in audit["details"]:
        all_to_delete.extend(d["delete_ids"])

    conn = db.connect()
    try:
        with conn:
            cur = conn.executemany(
                "DELETE FROM transactions WHERE id = ?",
                [(id_val,) for id_val in all_to_delete],
            )
            deleted_count = cur.rowcount
    finally:
        conn.close()

    reconciled_count = pipeline.reconcile()
    return {"removed": deleted_count, "reconciled": reconciled_count}


if __name__ == "__main__":
    audit = audit_duplicates()
    print(f"Total rows: {audit['total_rows']}")
    print(f"Duplicate groups found: {audit['duplicate_groups']}")
    print(f"Duplicate rows to remove: {audit['duplicate_rows_to_remove']}")
