"""Exact monetary arithmetic.

All persisted/derived monetary calculations should use integer minor units or
Decimal. This module intentionally avoids binary floating-point arithmetic.
""" 
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Union

Number = Union["Money", Decimal, int, str]

@dataclass(frozen=True, order=True)
class Money:
    """Immutable amount represented as minor units (paise for INR)."""

    minor: int
    currency: str = "INR"

    @classmethod
    def from_major(cls, value: Number, currency: str = "INR") -> "Money":
        if isinstance(value, Money):
            if value.currency != currency:
                raise ValueError("Currency mismatch")
            return value
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return cls(int(amount * 100), currency)

    @property
    def major(self) -> Decimal:
        return (Decimal(self.minor) / Decimal(100)).quantize(Decimal("0.01"))

    def __add__(self, other: Number) -> "Money":
        rhs = Money.from_major(other, self.currency)
        return Money(self.minor + rhs.minor, self.currency)

    def __sub__(self, other: Number) -> "Money":
        rhs = Money.from_major(other, self.currency)
        return Money(self.minor - rhs.minor, self.currency)

    def __mul__(self, factor: int) -> "Money":
        if not isinstance(factor, int):
            raise TypeError("Money multiplication requires an integer factor")
        return Money(self.minor * factor, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.minor, self.currency)

    def __str__(self) -> str:
        return f"{self.currency} {self.major:,.2f}"
