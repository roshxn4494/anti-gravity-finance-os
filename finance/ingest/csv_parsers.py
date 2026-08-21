"""CSV parsers for Axis / SBI / Kotak statements.

Real-world bank exports are messy: some have account-holder preamble before the
header, some use short DR/CR/BAL column names, and at least one Axis export puts
amounts in the *wrong* column (debits in CR, credits in DR). So this parser:

  * reads rows with the stdlib csv module (no column-count anchoring),
  * locates the real header row by content (a date column + an amount column),
  * maps columns by role,
  * and, when both a DR and a CR column exist, LEARNS the bank's convention
    from the running balance — which direction each column really means — so
    the signs come out right regardless of how the bank labels things.

Tune the role hints in `_classify_col` if a new bank uses unusual headers.
"""
from __future__ import annotations

import csv
import io
import re

from .normalize import make_transaction, parse_amount, parse_date


def _norm(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _classify_col(nc: str) -> str | None:
    """Map a normalized column name to a role: date/desc/debit/credit/balance/
    amount/type. Exact short names (DR, CR, BAL, amt) match alongside the long
    forms (Withdrawal Amt., Deposit Amt., Closing Balance)."""
    if nc == "dr" or "debit" in nc or "withdraw" in nc:
        return "debit"
    if nc == "cr" or "credit" in nc or "deposit" in nc:
        return "credit"
    if "balance" in nc or nc == "bal":
        return "balance"
    if "date" in nc or nc in ("trandate", "txndate"):
        return "date"
    if ("desc" in nc or "narr" in nc or "remark" in nc or "particular" in nc
            or "detail" in nc or "info" in nc):
        return "desc"
    if "amount" in nc or nc == "amt":
        return "amount"
    if nc in ("type", "drcr"):
        return "type"
    return None


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _read_rows(text: str) -> list[list[str]]:
    """Read into a list of rows (each a list of fields). Tries delimiters in
    order and keeps the one under which a real header row can be found."""
    for delim in (",", ";", "\t", "|"):
        try:
            rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
        except Exception:
            continue
        if _find_header_row(rows) is not None:
            return rows
    return [r for r in csv.reader(io.StringIO(text), delimiter=",")]


def _find_header_row(rows: list[list[str]]) -> int | None:
    """The header row has a date column plus an amount/debit/credit column."""
    for i, row in enumerate(rows[:60]):
        roles = {_classify_col(_norm(str(c))) for c in row if str(c).strip()}
        roles.discard(None)
        if "date" in roles and (roles & {"debit", "credit", "amount"}):
            return i
    return None


def _find_column_indices(header: list[str]) -> dict[str, int | None]:
    roles: dict[str, int | None] = {
        "date": None, "desc": None, "debit": None, "credit": None,
        "balance": None, "amount": None, "type": None}
    seen: set[str] = set()
    for i, c in enumerate(header):
        role = _classify_col(_norm(c))
        if role and role not in seen:
            roles[role] = i
            seen.add(role)
    return roles


def _cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def _clean_desc(desc: str) -> str:
    """Collapse whitespace into single spaces.

    SBI exports wrap every narration across two lines (mid-word), so a raw
    description arrives like 'Swiggy/ICIC/swiggystor\\n /NO REM …'. Normalising
    keeps it on one line so merchant keywords still match and the text is
    readable in the UI.
    """
    return re.sub(r"\s+", " ", desc).strip()


def _learn_dr_cr_convention(rows: list[dict]) -> str:
    """Return 'dr_is_credit' (DR column holds credits / CR holds debits — a
    swapped export) or 'dr_is_debit' (normal). Learns from the running balance:
    a value in the DR column that accompanies a balance *increase* is a credit."""
    dr_up = dr_dn = 0
    prev = None
    for r in rows:
        bal = r["bal"]
        if prev is not None and bal is not None:
            delta = bal - prev
            if abs(delta) > 0.01:
                for col, v in (("dr", r["dr"]), ("cr", r["cr"])):
                    if v is not None and abs(delta) >= abs(v) - 1:
                        if col == "dr":
                            dr_up += 1 if delta > 0 else 0
                            dr_dn += 1 if delta < 0 else 0
        prev = bal if bal is not None else prev
    if (dr_up + dr_dn) > 0:
        return "dr_is_credit" if dr_up > dr_dn else "dr_is_debit"
    return "dr_is_debit"  # no evidence → assume normal


def _signed_amount(r: dict, convention: str) -> float | None:
    """Signed amount for a row given the DR/CR convention (+ credit, − debit)."""
    dr, cr = r["dr"], r["cr"]
    if dr is None and cr is None:
        return None
    if dr is not None:
        return dr if convention == "dr_is_credit" else -dr
    return -cr if convention == "dr_is_credit" else cr


def parse_csv(data: bytes, source_file: str, account: str) -> tuple[list[dict], list[str]]:
    """Parse one CSV statement. Returns (transactions, warnings).

    Raises ValueError with a helpful message when the layout isn't recognised.
    """
    text = _decode(data)
    rows = _read_rows(text)
    warnings: list[str] = []

    header_idx = _find_header_row(rows)
    if header_idx is None:
        preview = [str(c) for c in rows[0]][:8] if rows else []
        raise ValueError(
            f"Could not find the statement column header in '{source_file}'. "
            f"First row reads: {preview}")

    header = [str(c).strip() for c in rows[header_idx]]
    idx = _find_column_indices(header)
    if idx["date"] is None:
        raise ValueError(f"No date column in '{source_file}'. Header: {header}")
    if idx["debit"] is None and idx["credit"] is None and idx["amount"] is None:
        raise ValueError(
            f"No Debit/Credit or Amount column in '{source_file}'. Header: {header}")

    has_dr_cr = idx["debit"] is not None and idx["credit"] is not None

    # Pass 1 — read raw cells.
    raw_rows: list[dict] = []
    for row in rows[header_idx + 1:]:
        txn_date = parse_date(_cell(row, idx["date"]))
        if txn_date is None:
            continue
        desc = _clean_desc(_cell(row, idx["desc"]))
        raw_rows.append({
            "date": txn_date, "desc": desc,
            "dr": parse_amount(_cell(row, idx["debit"])) if idx["debit"] is not None else None,
            "cr": parse_amount(_cell(row, idx["credit"])) if idx["credit"] is not None else None,
            "bal": parse_amount(_cell(row, idx["balance"])) if idx["balance"] is not None else None,
            "amt": parse_amount(_cell(row, idx["amount"])) if idx["amount"] is not None else None,
            "typ": _cell(row, idx["type"]),
            "raw": row,
        })

    convention = _learn_dr_cr_convention(raw_rows) if has_dr_cr else None
    if convention == "dr_is_credit":
        warnings.append(
            f"'{source_file}' uses a swapped DR/CR export — detected via the "
            "running balance and handled automatically.")

    txns: list[dict] = []
    for r in raw_rows:
        if has_dr_cr:
            amount = _signed_amount(r, convention)
            if amount is None or amount == 0:
                continue
        else:
            # Kotak style: single Amount column + a Dr/Cr type column.
            debit = credit = 0.0
            if r["amt"]:
                if r["typ"].lower().startswith(("c", "credit", "deposit")):
                    credit = abs(r["amt"])
                else:
                    debit = abs(r["amt"])
            amount = credit - debit
            if amount == 0 and not r["desc"]:
                continue

        txns.append(make_transaction(
            account=account, txn_date=r["date"], description=r["desc"],
            amount=amount, balance=r["bal"],
            raw=r["raw"], source_file=source_file))

    if not txns:
        warnings.append(
            f"No transaction rows parsed from '{source_file}' — check that it "
            "is a statement export and not a summary page.")

    return txns, warnings


# ---------------------------------------------------------------------------
# Bank auto-detection
# ---------------------------------------------------------------------------

def _detect_from_header(header: list[str], sample: list[list[str]]) -> str | None:
    """Return the account key for a parsed CSV, or None when unsure.

    Header text is decisive for the known bank layouts; content (how often each
    bank's own name appears in the narration rows) is the fallback for
    unrecognised headers — a statement is dominated by its own bank's name.
    """
    up = " | ".join(str(h).upper() for h in header)

    if "PARTICULARS" in up and ("SOL" in up or "CHQNO" in up):
        return "axis"   # real Axis export: Tran Date,CHQNO,PARTICULARS,DR,CR,BAL,SOL
    if "SL. NO." in up and "DR / CR" in up:
        return "kotak"  # real Kotak export: Sl. No.,…,Amount,Dr / Cr,Balance,Dr / Cr
    if "TRANSACTION TYPE" in up and "NARRATION" in up:
        return "kotak"  # simpler Kotak layout: Transaction Type,Narration,Debit,Credit,Balance
    if "CLOSING BALANCE" in up:
        return "sbi"    # SBI export: …,Withdrawal Amt,Deposit Amt,Closing Balance
    if "DETAILS" in up and "REF NO/CHEQUE NO" in up:
        return "sbi"    # real SBI export: Date,Details,Ref No/Cheque No,Debit,Credit,Balance
                        # (note: 'REF NO/CHEQUE NO' without periods distinguishes it from
                        # the Axis-sample 'Ref No./Cheque No.')
    if "REF NO./CHEQUE NO." in up and "WITHDRAWAL AMT." in up:
        return "axis"   # Axis sample layout: Ref No./Cheque No.,Withdrawal Amt.,…,Balance

    # Fallback: count own-bank markers across the first rows.
    markers = {
        "axis": ["AXIS", "AXBK", "UTIB"],
        "sbi": ["STATE BANK", "SBIN"],
        "kotak": ["KOTAK", "KKBK"],
    }
    scores = {k: 0 for k in markers}
    for row in sample:
        joined = " | ".join(str(c).upper() for c in row)
        for acct, kws in markers.items():
            if any(kw in joined for kw in kws):
                scores[acct] += 1
    top = max(scores.values())
    if top >= 3:
        winners = [a for a, s in scores.items() if s == top]
        if len(winners) == 1:
            return winners[0]
    return None


def detect_account(data: bytes, source_file: str = "") -> str | None:
    """Identify which bank a CSV statement belongs to ('axis'/'sbi'/'kotak'),
    or None when it can't be determined with confidence."""
    text = _decode(data)
    rows = _read_rows(text)
    header_idx = _find_header_row(rows)
    if header_idx is None:
        return None
    header = rows[header_idx]
    sample = rows[header_idx + 1: header_idx + 61]
    return _detect_from_header(header, sample)
