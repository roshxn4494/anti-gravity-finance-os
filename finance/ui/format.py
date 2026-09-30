"""Formatting helpers for Indian currency, dates, and card numbers."""
from __future__ import annotations

from datetime import date


def rupees_to_paise(amt: float | int | str | None) -> int:
    """Deterministically convert a rupee amount to integer paise (1 Rupee = 100 Paise)."""
    if amt is None:
        return 0
    try:
        return int(round(float(amt) * 100))
    except (ValueError, TypeError):
        return 0


def paise_to_rupees(paise: int | None) -> float:
    """Convert integer paise back to rupees as a float."""
    if paise is None:
        return 0.0
    try:
        return int(paise) / 100.0
    except (ValueError, TypeError):
        return 0.0


def inr(x: float | int | None) -> str:
    """Format float or int as ₹ with Indian digit grouping (e.g. ₹1,50,000)."""
    if x is None:
        return "₹0"
    try:
        x = int(round(float(x)))
    except (ValueError, TypeError):
        return "₹0"
    neg = x < 0
    x = abs(x)
    s = str(x)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + s


def inr_paise(paise: int | None) -> str:
    """Format integer paise directly as ₹ with Indian digit grouping."""
    return inr(paise_to_rupees(paise))


def ordinal(n: int) -> str:
    """Format integer as ordinal string (e.g. 1 -> 1st, 2 -> 2nd, 3 -> 3rd, 4 -> 4th)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def mask_card(last4: str) -> str:
    """Format masked credit card representation."""
    if not last4:
        return "•••• •••• •••• ••••"
    return f"•••• •••• •••• {last4}"


def month_key(iso: str) -> str:
    """Extract YYYY-MM from ISO date string."""
    return str(iso)[:7]


def prev_month(mk: str) -> str:
    """Return YYYY-MM string for previous month."""
    y, m = int(mk[:4]), int(mk[5:7])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}"


def last_months(n: int) -> list[str]:
    """Return list of last n month keys [YYYY-MM] ending at current month."""
    end = date.today()
    out = []
    for i in range(n - 1, -1, -1):
        y, m = end.year, end.month
        for _ in range(i):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def fmt_month(mk: str) -> str:
    """Format YYYY-MM as readable Month Year (e.g. Aug 2026)."""
    try:
        return date(int(mk[:4]), int(mk[5:7]), 1).strftime("%b %Y")
    except Exception:
        return str(mk)
