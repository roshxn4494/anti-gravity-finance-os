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
import os
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


def detect_pdf_account(data: bytes, password: str | None = None) -> str | None:
    """Scan first page of PDF statement to auto-detect bank ('axis', 'sbi', 'kotak')."""
    passwords = [password] if password else [None]
    env_pwds = os.getenv("PDF_PASSWORDS", "")
    if env_pwds:
        for p in env_pwds.split(","):
            p_clean = p.strip()
            if p_clean and p_clean not in passwords:
                passwords.append(p_clean)

    for pwd in passwords:
        try:
            open_kwargs = {"password": pwd} if pwd else {}
            with pdfplumber.open(io.BytesIO(data), **open_kwargs) as pdf:
                if not pdf.pages:
                    return None
                text = (pdf.pages[0].extract_text() or "").upper()
                if "AXIS BANK" in text or "UTIB" in text or "AXISBANK" in text:
                    return "axis"
                if "STATE BANK OF INDIA" in text or "SBIN" in text or "SBI" in text:
                    return "sbi"
                if "KOTAK MAHINDRA" in text or "KKBK" in text or "811" in text or "KOTAK" in text:
                    return "kotak"
                return None
        except Exception:
            continue
    return None


def parse_pdf(data: bytes, source_file: str, account: str, password: str | None = None) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    rows: list[dict] = []

    # Candidate passwords to try
    candidate_passwords: list[str | None] = [password] if password else [None]
    env_pwds = os.getenv("PDF_PASSWORDS", "")
    if env_pwds:
        for p in env_pwds.split(","):
            p_clean = p.strip()
            if p_clean and p_clean not in candidate_passwords:
                candidate_passwords.append(p_clean)

    opened_pdf = None
    last_exc = None
    for pwd in candidate_passwords:
        try:
            open_kwargs = {"password": pwd} if pwd else {}
            pdf = pdfplumber.open(io.BytesIO(data), **open_kwargs)
            # Test access to first page to verify decrypt succeeded
            if pdf.pages:
                _ = pdf.pages[0].extract_text()
            opened_pdf = pdf
            break
        except Exception as exc:
            last_exc = exc
            continue

    if opened_pdf is None:
        err_msg = str(last_exc).lower() if last_exc else ""
        if "password" in err_msg or "encrypted" in err_msg or "pdfpasswordincorrect" in err_msg:
            raise ValueError(
                f"PDF '{source_file}' is password protected. Please enter the statement password."
            )
        raise ValueError(
            f"Could not read PDF '{source_file}': {last_exc}. If it is a bank "
            "statement, try downloading the CSV export instead."
        )

    try:
        with opened_pdf as pdf:
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
    except Exception as exc:
        raise ValueError(f"Error parsing tables in PDF '{source_file}': {exc}") from exc

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
