"""Valid, unique test data. Every test registers its own customer, so tests
never share state and can run in any order or in parallel."""

from __future__ import annotations

import random
import uuid

from framework.models import RegisterRequest

FIRST_NAMES = ("Ana", "Lucía", "Mateo", "Diego", "Valeria", "Sofía", "Iker", "Renata")
LAST_NAMES = ("García", "Hernández", "López", "Martínez", "Ramírez", "Torres", "Núñez")


def unique_phone() -> str:
    # +52 and ten digits; the first digit is never 0 so it looks like a real
    # Mexican mobile number. 9*10^9 values make a collision in one run negligible.
    return f"+52{random.randint(1_000_000_000, 9_999_999_999)}"


def unique_email() -> str:
    return f"qa.{uuid.uuid4().hex[:12]}@example.test"


def full_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def registration(**overrides: str) -> RegisterRequest:
    data = {"full_name": full_name(), "phone": unique_phone(), "email": unique_email()}
    data.update(overrides)
    return RegisterRequest(**data)


def registration_dict(**overrides: object) -> dict[str, object]:
    """For negative tests: a valid body as a dict that can be broken field by field."""
    data: dict[str, object] = registration().model_dump()
    data.update(overrides)
    return data
