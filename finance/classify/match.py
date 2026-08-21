"""Pair related transactions so the dashboard shows true spend.

Two families get paired by amount + time window:
  * internal transfers — a sweep OUT of one account ↔ sweep IN to another (±3d)
  * cc pass-through     — a credit-card payment OUT ↔ Ashwin's deposit IN (±7d)

Matched pairs get match_status='matched' + matched_with; unpaired candidates
are left 'unmatched' so the reconciliation tab can surface them (e.g. a CC
payment with no Ashwin deposit yet = he still owes you).
"""
from __future__ import annotations

from datetime import date, timedelta

from .. import config


def match_all(rows: list[dict]) -> None:
    """Modifies rows in place: sets match_status / matched_with / flags."""
    for r in rows:
        r["match_status"] = None
        r["matched_with"] = None

    _pair(rows,
          debit_class=config.CLASSIFICATION_INTERNAL_TRANSFER,
          credit_class=config.CLASSIFICATION_INTERNAL_TRANSFER,
          window_days=config.MATCH_WINDOW_INTERNAL_DAYS,
          same_account_ok=False)
    _pair(rows,
          debit_class=config.CLASSIFICATION_CC_PAYMENT,
          credit_class=config.CLASSIFICATION_FRIEND_DEPOSIT,
          window_days=config.MATCH_WINDOW_CC_DAYS,
          same_account_ok=True)


def _pair(rows: list[dict], debit_class: str, credit_class: str,
          window_days: int, same_account_ok: bool) -> None:
    debits = [r for r in rows if r["classification"] == debit_class and r["amount"] < 0]
    credits = [r for r in rows if r["classification"] == credit_class and r["amount"] > 0]
    used: set[str] = set()

    for d in sorted(debits, key=lambda r: r["txn_date"]):
        d_amt = -d["amount"]
        d_date = _parse_date(d["txn_date"])
        best = None  # (credit_row, date_diff, amt_diff)
        for c in credits:
            if c["id"] in used:
                continue
            if not same_account_ok and c["account"] == d["account"]:
                continue
            amt_diff = abs(c["amount"] - d_amt)
            if amt_diff > config.MATCH_AMOUNT_TOLERANCE:
                continue
            c_date = _parse_date(c["txn_date"])
            if d_date is None or c_date is None:
                continue
            date_diff = abs((c_date - d_date).days)
            if date_diff > window_days:
                continue
            if (best is None
                    or date_diff < best[1]
                    or (date_diff == best[1] and amt_diff < best[2])):
                best = (c, date_diff, amt_diff)

        if best:
            c = best[0]
            used.add(c["id"])
            d["matched_with"] = c["id"]
            d["match_status"] = "matched"
            c["matched_with"] = d["id"]
            c["match_status"] = "matched"

    # Anything left unpaired in either family is 'unmatched' for reconciliation.
    for r in rows:
        if r["classification"] in (debit_class, credit_class) and not r["match_status"]:
            r["match_status"] = "unmatched"


def _parse_date(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
