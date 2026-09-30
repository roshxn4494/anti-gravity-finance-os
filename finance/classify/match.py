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
from ..ui.format import rupees_to_paise


def match_all(rows: list[dict]) -> None:
    """Modifies rows in place: sets match_status / matched_with / flags.
    
    Preserves rows marked as 'manual_matched' so user-verified pairings are permanent.
    """
    for r in rows:
        if r.get("match_status") != "manual_matched":
            r["match_status"] = None
            r["matched_with"] = None

    _pair(rows,
          debit_class=config.CLASSIFICATION_INTERNAL_TRANSFER,
          credit_class=config.CLASSIFICATION_INTERNAL_TRANSFER,
          window_days=config.MATCH_WINDOW_INTERNAL_DAYS,
          same_account_ok=False,
          allow_split=False)
    _pair(rows,
          debit_class=config.CLASSIFICATION_CC_PAYMENT,
          credit_class=config.CLASSIFICATION_FRIEND_DEPOSIT,
          window_days=config.MATCH_WINDOW_CC_DAYS,
          same_account_ok=True,
          allow_split=True)


def _pair(rows: list[dict], debit_class: str, credit_class: str,
          window_days: int, same_account_ok: bool,
          allow_split: bool = False) -> None:
    debits = [r for r in rows if r.get("classification") == debit_class and r.get("amount", 0) < 0]
    credits = [r for r in rows if r.get("classification") == credit_class and r.get("amount", 0) > 0]
    
    # Ensure amount_paise is populated on every candidate row for exact arithmetic
    for r in debits + credits:
        if "amount_paise" not in r or r["amount_paise"] is None:
            r["amount_paise"] = rupees_to_paise(r.get("amount"))

    tolerance_paise = rupees_to_paise(config.MATCH_AMOUNT_TOLERANCE)

    # Seed used with transactions that are already manually matched or already paired
    used: set[str] = set()
    for r in rows:
        if r.get("match_status") in ("manual_matched", "matched"):
            used.add(r["id"])
            if r.get("matched_with"):
                for mid in str(r["matched_with"]).split(","):
                    if mid.strip():
                        used.add(mid.strip())

    # Pass 1: 1-to-1 matching (closest date, smallest amount diff within tolerance)
    for d in sorted(debits, key=lambda r: r["txn_date"]):
        if d["id"] in used:
            continue
        d_amt_paise = -d["amount_paise"]
        d_date = _parse_date(d["txn_date"])
        best = None  # (credit_row, date_diff, amt_diff_paise)
        for c in credits:
            if c["id"] in used:
                continue
            if not same_account_ok and c.get("account") == d.get("account"):
                continue
            amt_diff_paise = abs(c["amount_paise"] - d_amt_paise)
            if amt_diff_paise > tolerance_paise:
                continue
            c_date = _parse_date(c["txn_date"])
            if d_date is None or c_date is None:
                continue
            date_diff = abs((c_date - d_date).days)
            if date_diff > window_days:
                continue
            if (best is None
                    or date_diff < best[1]
                    or (date_diff == best[1] and amt_diff_paise < best[2])):
                best = (c, date_diff, amt_diff_paise)

        if best:
            c = best[0]
            used.add(c["id"])
            used.add(d["id"])
            d["matched_with"] = c["id"]
            d["match_status"] = "matched"
            c["matched_with"] = d["id"]
            c["match_status"] = "matched"

    # Pass 2: 2-part split matching (e.g. 2 Ashwin deposits cleanly sum to 1 CC payment)
    if allow_split:
        for d in sorted(debits, key=lambda r: r["txn_date"]):
            if d["id"] in used:
                continue
            d_amt_paise = -d["amount_paise"]
            d_date = _parse_date(d["txn_date"])
            if d_date is None:
                continue

            available_credits = [
                c for c in credits
                if c["id"] not in used and (same_account_ok or c.get("account") != d.get("account"))
            ]
            best_split = None  # (c1, c2, max_date_diff, amt_diff_paise)

            for i in range(len(available_credits)):
                c1 = available_credits[i]
                c1_date = _parse_date(c1["txn_date"])
                if c1_date is None or abs((c1_date - d_date).days) > window_days:
                    continue
                for j in range(i + 1, len(available_credits)):
                    c2 = available_credits[j]
                    c2_date = _parse_date(c2["txn_date"])
                    if c2_date is None or abs((c2_date - d_date).days) > window_days:
                        continue
                    
                    combined_paise = c1["amount_paise"] + c2["amount_paise"]
                    amt_diff_paise = abs(combined_paise - d_amt_paise)
                    if amt_diff_paise <= tolerance_paise:
                        max_date_diff = max(abs((c1_date - d_date).days), abs((c2_date - d_date).days))
                        if (best_split is None
                                or max_date_diff < best_split[2]
                                or (max_date_diff == best_split[2] and amt_diff_paise < best_split[3])):
                            best_split = (c1, c2, max_date_diff, amt_diff_paise)

            if best_split:
                c1, c2, _, _ = best_split
                used.add(c1["id"])
                used.add(c2["id"])
                used.add(d["id"])
                d["matched_with"] = f"{c1['id']},{c2['id']}"
                d["match_status"] = "matched"
                c1["matched_with"] = d["id"]
                c1["match_status"] = "matched"
                c2["matched_with"] = d["id"]
                c2["match_status"] = "matched"

    # Anything left unpaired in either family is 'unmatched' for reconciliation.
    for r in rows:
        if r.get("classification") in (debit_class, credit_class) and not r.get("match_status"):
            r["match_status"] = "unmatched"


def _parse_date(iso: str) -> date | None:
    try:
        return date.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
