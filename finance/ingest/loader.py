"""Dispatch an uploaded statement file to the right parser."""
from __future__ import annotations

from . import cc_pdf_parser, csv_parsers, pdf_parsers


def parse_file(uploaded, account: str) -> tuple[list[dict], list[str]]:
    """Parse an uploaded bank statement file (Streamlit UploadedFile or .getvalue())."""
    name = getattr(uploaded, "name", "") or ""
    data = uploaded.getvalue()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext == "csv":
        return csv_parsers.parse_csv(data, name, account)
    if ext == "pdf":
        return pdf_parsers.parse_pdf(data, name, account)
    raise ValueError(
        f"Unsupported file type '.{ext}'. Please upload a CSV or PDF statement "
        f"downloaded from netbanking.")


def parse_cc_file(
    uploaded,
    card_name: str = "Credit Card",
    password: str | None = None
) -> tuple[dict, list[dict], list[dict], list[str]]:
    """Parse an uploaded credit card PDF statement.

    Returns (statement_summary, transactions, emis, warnings).
    """
    name = getattr(uploaded, "name", "") or ""
    data = uploaded.getvalue()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext == "pdf":
        return cc_pdf_parser.parse_cc_pdf(data, name, card_name=card_name, password=password)

    if ext == "csv":
        rows, warnings = csv_parsers.parse_csv(data, name, account="credit_card")
        stmt_info = {
            "card_name": card_name,
            "card_last4": "",
            "statement_date": rows[0]["txn_date"] if rows else "",
            "due_date": "",
            "total_due": sum(abs(r["amount"]) for r in rows if r["amount"] < 0),
            "min_due": 0.0,
            "credit_limit": 0.0,
            "available_limit": 0.0,
            "cash_limit": 0.0,
            "reward_points_earned": 0.0,
            "reward_points_balance": 0.0,
            "finance_charges": 0.0,
            "source_file": name,
        }
        cc_txns = []
        for r in rows:
            cc_txns.append({
                "card_name": card_name,
                "card_last4": "",
                "txn_date": r["txn_date"],
                "description": r["description"],
                "amount": abs(r["amount"]) if r["amount"] < 0 else -abs(r["amount"]),
                "category": r["category"],
                "counterparty": r["counterparty"],
                "source_file": name,
            })
        return stmt_info, cc_txns, [], warnings

    raise ValueError(f"Unsupported credit card statement file '.{ext}'. Please upload a PDF or CSV statement.")


def detect_account(uploaded) -> str | None:
    """Best-effort auto-detection of the bank/account for an uploaded file."""
    name = getattr(uploaded, "name", "") or ""
    data = uploaded.getvalue()
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "csv":
        return csv_parsers.detect_account(data, name)
    return None
