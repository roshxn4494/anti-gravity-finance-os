"""Precision money handling module for Finance OS.

Guarantees exact integer paise arithmetic to eliminate floating point binary drift.
Supports Decimal boundaries for external APIs and standardized Indian Rupee formatting.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Union


NumberLike = Union[int, float, str, Decimal]


def rupees_to_paise(amount: NumberLike) -> int:
    """Converts a Rupee value to exact integer paise using half-up rounding.
    
    Examples:
        rupees_to_paise(0.29) -> 29
        rupees_to_paise(19.99) -> 1999
        rupees_to_paise("-100.50") -> -10050
    """
    if isinstance(amount, int):
        return amount * 100
    if isinstance(amount, (float, str, Decimal)):
        d = Decimal(str(amount))
        return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))
    raise TypeError(f"Cannot convert type {type(amount)} to paise")


def paise_to_rupees(paise: int) -> float:
    """Converts integer paise to float rupees for display or charting.
    
    Examples:
        paise_to_rupees(12345) -> 123.45
        paise_to_rupees(29) -> 0.29
    """
    return float(Decimal(paise) / Decimal(100))


def format_inr_paise(paise: int, show_symbol: bool = True) -> str:
    """Formats integer paise into Indian numbering system (e.g. ₹1,20,000.50)."""
    sign = "-" if paise < 0 else ""
    abs_paise = abs(paise)
    rupees_part = abs_paise // 100
    paise_part = abs_paise % 100

    s = str(rupees_part)
    if len(s) > 3:
        last3 = s[-3:]
        other = s[:-3]
        groups = []
        while other:
            groups.append(other[-2:])
            other = other[:-2]
        groups.reverse()
        formatted_rupees = ",".join(groups) + "," + last3
    else:
        formatted_rupees = s

    if paise_part > 0:
        val = f"{sign}{formatted_rupees}.{paise_part:02d}"
    else:
        val = f"{sign}{formatted_rupees}"

    return f"₹{val}" if show_symbol else val


def format_paise_to_lakhs(paise: int) -> str:
    """Formats paise into Lakhs/Crores for executive summaries (e.g. ₹3.86L or ₹1.2Cr)."""
    rupees = paise_to_rupees(paise)
    abs_rupees = abs(rupees)
    sign = "-" if rupees < 0 else ""

    if abs_rupees >= 1_00_00_000:
        cr = abs_rupees / 1_00_00_000
        return f"{sign}₹{cr:.2f}Cr"
    elif abs_rupees >= 1_00_000:
        lakhs = abs_rupees / 1_00_000
        return f"{sign}₹{lakhs:.2f}L"
    else:
        return format_inr_paise(paise)


class Money:
    """Immutable exact money value stored in integer paise."""
    __slots__ = ("_paise",)

    def __init__(self, paise: int):
        self._paise = int(paise)

    @classmethod
    def from_rupees(cls, rupees: NumberLike) -> Money:
        return cls(rupees_to_paise(rupees))

    @classmethod
    def from_paise(cls, paise: int) -> Money:
        return cls(paise)

    @property
    def paise(self) -> int:
        return self._paise

    @property
    def rupees(self) -> float:
        return paise_to_rupees(self._paise)

    def to_decimal(self) -> Decimal:
        return Decimal(self._paise) / Decimal(100)

    def format_inr(self, show_symbol: bool = True) -> str:
        return format_inr_paise(self._paise, show_symbol=show_symbol)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._paise + other._paise)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self._paise - other._paise)

    def __mul__(self, factor: Union[int, float, Decimal]) -> Money:
        if isinstance(factor, (int, float, Decimal)):
            d = Decimal(str(factor))
            new_paise = int((Decimal(self._paise) * d).to_integral_value(rounding=ROUND_HALF_UP))
            return Money(new_paise)
        return NotImplemented

    def __neg__(self) -> Money:
        return Money(-self._paise)

    def __abs__(self) -> Money:
        return Money(abs(self._paise))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Money):
            return self._paise == other._paise
        return False

    def __lt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._paise < other._paise

    def __le__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._paise <= other._paise

    def __gt__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._paise > other._paise

    def __ge__(self, other: Money) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._paise >= other._paise

    def __repr__(self) -> str:
        return f"Money({self._paise}p, ₹{self.rupees:.2f})"

    def __str__(self) -> str:
        return self.format_inr()
