"""A registered, signed-in customer as tests use it."""

from __future__ import annotations

from dataclasses import dataclass

from framework.models import Customer
from framework.services import CardsService


@dataclass(frozen=True)
class SignedInCustomer:
    customer: Customer
    token: str
    cards: CardsService

    @property
    def phone(self) -> str:
        return self.customer.phone
