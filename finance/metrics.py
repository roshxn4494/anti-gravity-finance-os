"""Deterministic financial metrics.

The metrics layer is deliberately independent from the LLM. It converts legacy
REAL columns to Decimal at the database boundary and exposes explicit periods.
""" 
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .domain.money import Money

@dataclass(frozen=True)
class MetricResult:
    metric: str
    value: Money
    period_start: str | None
    period_end: str | None
    transaction_count: int
    coverage: str
    provenance: tuple[str, ...]

def _dec(value) -> Decimal:
    return Decimal(str(value or 0))

def sum_amounts(rows: Iterable, field: str = "amount") -> Money:
    total = Decimal("0")
    for row in rows:
        value = row[field] if isinstance(row, dict) else getattr(row, field)
        total += _dec(value)
    return Money.from_major(total)

def monthly_cashflow(transactions, month: str) -> dict[str, Money]:
    """Return deterministic income/spend/transfer totals for YYYY-MM."""
    if transactions is None or transactions.empty:
        return {"income": Money(0), "spend": Money(0), "transfers": Money(0)}
    subset = transactions[transactions["txn_date"].astype(str).str.startswith(month)]
    result = {"income": Decimal("0"), "spend": Decimal("0"), "transfers": Decimal("0")}
    for _, row in subset.iterrows():
        amount = _dec(row["amount"])
        cls = str(row.get("classification") or "")
        if cls == "income" and amount > 0:
            result["income"] += amount
        elif cls == "spend" and amount < 0:
            result["spend"] += abs(amount)
        elif cls == "internal_transfer":
            result["transfers"] += abs(amount)
    return {k: Money.from_major(v) for k, v in result.items()}
