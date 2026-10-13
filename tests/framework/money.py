"""Expected money values are computed here, independently of the service code."""

from __future__ import annotations

from decimal import Decimal


def _d(value: str) -> Decimal:
    return Decimal(value)


def fmt(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def add(*values: str) -> str:
    return fmt(sum((_d(v) for v in values), Decimal("0")))


def sub(a: str, *values: str) -> str:
    return fmt(_d(a) - sum((_d(v) for v in values), Decimal("0")))


def mul(a: str, n: int) -> str:
    return fmt(_d(a) * n)
