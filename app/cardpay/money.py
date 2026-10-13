"""Money is integer cents inside the service and a two-decimal string on the wire."""

from __future__ import annotations

import re

MONEY_RE = re.compile(r"^(0|[1-9]\d{0,8})\.\d{2}$")


def parse(value: str) -> int:
    """'12.30' -> 1230. The caller has already checked the format."""
    whole, frac = value.split(".")
    return int(whole) * 100 + int(frac)


def fmt(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"
