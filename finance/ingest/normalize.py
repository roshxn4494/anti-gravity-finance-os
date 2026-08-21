"""Normalize raw statement rows into one unified transaction shape."""
from __future__ import annotations

import re
from datetime import datetime

DATE_FORMATS = [
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%d%b%Y",
    "%Y-%m-%d",
    "%b %d, %Y",
    "%B %d, %Y",
]


def parse_date(value) -> str | None:
    """Parse a bank-statement date into ISO yyyy-mm-dd. Returns None if unusable."""
    if value is None:
        return None
    text = str(value).strip().strip('"')
    if not text or text.lower() in {"", "date", "nan", "none"}:
        return None
    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(text, fmt)
            if 1990 <= d.year <= 2100:
                return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_amount(value) -> float | None:
    """Parse an amount string (₹1,234.56 / 1.234,56 / -45 / (45)) to float."""
    if value is None:
        return None
    text = str(value).strip().replace("₹", "").replace("INR", "").strip()
    if text in {"", "-", "--", "nan", "None", "DR", "CR", "Dr", "Cr"}:
        return None
    # Handle parenthesised negatives: (1,234.56) -> -1234.56
    neg = text.startswith("(") and text.endswith(")")
    text = text.strip("() ")
    text = re.sub(r"[^0-9.,\-]", "", text)
    # Indian/European style: 1.234,56 -> thousands=dot, decimal=comma
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        val = float(text)
    except ValueError:
        return None
    return -val if neg else val


def make_transaction(
    account: str,
    txn_date: str,
    description: str,
    amount: float,
    balance: float | None = None,
    raw=None,
    source_file: str | None = None,
) -> dict:
    """Build a normalized transaction dict (id filled later by the pipeline)."""
    return {
        "id": None,
        "account": account,
        "txn_date": txn_date,
        "description": str(description).strip() if description else "",
        "amount": round(float(amount), 2),
        "balance": round(float(balance), 2) if balance is not None else None,
        "classification": None,
        "category": None,
        "counterparty": None,
        "matched_with": None,
        "match_status": None,
        "flags": None,
        "raw": raw,
        "source_file": source_file,
    }
