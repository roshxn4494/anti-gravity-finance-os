"""Merchant/person extraction from narrations, and keyword → category matching."""
from __future__ import annotations

import re

from .. import config

# Tokens in a narration that carry no counterparty meaning.
_MARKERS = {
    "UPI", "DR", "CR", "NR", "P2P", "P2M", "P2A", "M2M", "COLLECT", "REQ",
    "NEFT", "IMPS", "RTGS", "FT", "ATM", "POS", "REF", "REFERENCE", "CHQ",
    "CHEQUE", "TRANSFER", "BETWEEN", "ACCOUNT", "TO", "BY", "VIA", "PAYMENT",
    "BEN", "SELF", "SWEEP",
    "WDL", "DEP", "TFR",   # SBI prefixes every narration: 'WDL TFR', 'DEP TFR'
}

_VPA_RE = re.compile(r"([A-Z0-9._\-]+@[A-Z0-9._\-]+)")


def extract_counterparty(description: str) -> str:
    """Pull a stable merchant/person token out of a narration.

    Prefers the local part of a UPI VPA (e.g. 'swiggy' from swiggy@okhdfc, a
    phone number from 98765@ybl). Falls back to the first meaningful token.
    """
    up = (description or "").upper().strip()
    if not up:
        return ""

    m = _VPA_RE.search(up)
    if m:
        return m.group(1).split("@")[0]

    tokens = [t for t in re.split(r"[^A-Z0-9]+", up) if t]
    for t in tokens:
        if t in _MARKERS:
            continue
        if len(t) < 3:
            continue
        if t.isdigit() and len(t) >= 6:
            continue  # looks like a reference number
        return t
    return tokens[0] if tokens else ""


def is_p2p(description: str, counterparty: str) -> bool:
    """Best-effort check that a payment went to a person, not a merchant."""
    up = (description or "").upper()
    if "P2P" in up:
        return True
    if counterparty and counterparty.isdigit():
        return True  # phone-number VPA
    return False


def categorize(description: str) -> str | None:
    """Return the category for a spend narration, or None if unmatched."""
    up = (description or "").upper()
    for category, keywords in config.CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in up:
                return category
    return None


def all_categories() -> list[str]:
    cats = list(config.CATEGORY_KEYWORDS.keys())
    if config.DEFAULT_CATEGORY not in cats:
        cats.append(config.DEFAULT_CATEGORY)
    return cats
