"""PDF statement parser (pdfplumber).

Bank PDF statements are ruled tables; we locate the transaction table on each
page by finding a header row that mentions a date and amount columns, map
columns by position, then read every row below it until the page ends.

PDF layouts differ a lot between banks (and between export options), so this is
the part most likely to need a tune against your real files — the header-hint
lists below are the levers.
"""
from __future__ import annotations

import io
import re

import pdfplumber

from .normalize import make_transaction, parse_amount, parse_date

DATE_HINTS = ["date", "txn"]
DEBIT_HINTS = ["debit", "withdrawal", "withdraw", "paid"]
CREDIT_HINTS = ["credit", "deposit", "received"]
BAL_HINTS = ["balance", "closing"]
NARR_HINTS = ["narration", "description", "particular", "details", "remark"]


def _cell_text(cell) -> str:
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    return str(cell).strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _find_header(table) -> int | None:
    for i, row in enumerate(table[:10]):
        cells = [_norm(_cell_text(c)) for c in row]
        joined = " ".join(cells)
        has_date = any("date" in c for c in cells)
        has_amount = any(k in joined for k in ("debit", "credit", "withdrawal",
                                               "deposit", "balance"))
        if has_date and has_amount:
            return i
    return None


def _map_columns(header: list) -> dict:
    date_col = debit_col = credit_col = bal_col = None
    narr_cols: list[int] = []
    for i, c in enumerate(header):
        nc = _norm(_cell_text(c))
        if date_col is None and any(h in nc for h in DATE_HINTS):
            date_col = i
        elif debit_col is None and any(h in nc for h in DEBIT_HINTS):
            debit_col = i
        elif credit_col is None and any(h in nc for h in CREDIT_HINTS):
            credit_col = i
        elif bal_col is None and any(h in nc for h in BAL_HINTS):
            bal_col = i
    # Narration = the columns between date and the first amount column.
    amt_start = min([i for i in (debit_col, credit_col, bal_col) if i is not None],
                    default=None)
    if date_col is not None and amt_start is not None:
        narr_cols = list(range(date_col + 1, amt_start))
    return {"date": date_col, "debit": debit_col, "credit": credit_col,
            "balance": bal_col, "narr": narr_cols}


def parse_pdf(data: bytes, source_file: str, account: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    rows: list[dict] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    header_idx = _find_header(table)
                    if header_idx is None:
                        continue
                    cols = _map_columns(table[header_idx])
                    if cols["date"] is None:
                        continue
                    for row in table[header_idx + 1:]:
                        txn = _row_to_txn(row, cols, account, source_file)
                        if txn:
                            rows.append(txn)
    except Exception as exc:  # pdfplumber raises a lot of layout-specific errors
        raise ValueError(
            f"Could not read PDF '{source_file}': {exc}. If it is a bank "
            "statement, try downloading the CSV export instead.") from exc

    if not rows:
        warnings.append(
            f"No transaction rows found in '{source_file}'. PDF layouts vary by "
            "bank — try the CSV export, or send me a sample to tune the parser.")

    return rows, warnings


def _row_to_txn(row: list, cols: dict, account: str, source_file: str) -> dict | None:
    if not row:
        return None
    txn_date = parse_date(_cell_text(row[cols["date"]]))
    if txn_date is None:
        return None

    debit = credit = None
    if cols["debit"] is not None:
        debit = parse_amount(_cell_text(row[cols["debit"]]))
    if cols["credit"] is not None:
        credit = parse_amount(_cell_text(row[cols["credit"]]))
    debit = debit if debit is not None else 0.0
    credit = credit if credit is not None else 0.0
    amount = credit - debit
    if amount == 0:
        # Some statements put the value in one column with a Dr/Cr suffix.
        amount = parse_amount(_cell_text(row[cols["debit"]])) or 0.0
        if amount == 0:
            return None

    narr = " ".join(_cell_text(row[i]) for i in cols["narr"] if i < len(row))
    narr = re.sub(r"\s+", " ", narr).strip()

    balance = None
    if cols["balance"] is not None and cols["balance"] < len(row):
        balance = parse_amount(_cell_text(row[cols["balance"]]))

    return make_transaction(account=account, txn_date=txn_date, description=narr,
                            amount=amount, balance=balance, raw=row,
                            source_file=source_file)
