"""Card operations of one signed-in customer, in business terms.

Tests call these methods and get typed models back; they never see HTTP.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

import allure

from framework.adapters.cardpay_api import CardpayApi
from framework.http_client import HttpResponse
from framework.models import (
    BlockRequest,
    Card,
    CardList,
    IssueCardRequest,
    PaymentRequest,
    TopUpRequest,
    Transaction,
    TransactionPage,
)
from framework.services.base import UnexpectedResponse, expect


@dataclass(frozen=True)
class MoneyResult:
    """Outcome of a top-up or payment. ``replayed`` is True when the service
    returned an earlier transaction for a repeated idempotency key."""

    transaction: Transaction
    replayed: bool


def new_idempotency_key() -> str:
    return f"test-{uuid.uuid4()}"


class CardsService:
    def __init__(self, api: CardpayApi, token: str | None) -> None:
        self.api = api
        self.token = token

    @allure.step("Issue a card (label={label}, daily limit={daily_limit})")
    def issue(self, label: str | None = None, daily_limit: str | None = None) -> Card:
        resp = self.api.issue_card(self.token, IssueCardRequest(label=label, daily_limit=daily_limit))
        return expect(resp, 201, Card)

    @allure.step("Issue a card with body {body}")
    def issue_raw(self, body: dict[str, Any]) -> Card:
        """Negative tests: sends exactly ``body``."""
        return expect(self.api.issue_card(self.token, body), 201, Card)

    @allure.step("List cards")
    def list(self) -> list[Card]:
        return expect(self.api.list_cards(self.token), 200, CardList).items

    @allure.step("Get card {card_id}")
    def get(self, card_id: str) -> Card:
        return expect(self.api.get_card(self.token, card_id), 200, Card)

    @allure.step("Freeze card {card_id}")
    def freeze(self, card_id: str) -> Card:
        return expect(self.api.freeze(self.token, card_id), 200, Card)

    @allure.step("Unfreeze card {card_id}")
    def unfreeze(self, card_id: str) -> Card:
        return expect(self.api.unfreeze(self.token, card_id), 200, Card)

    @allure.step("Block card {card_id}, reason {reason}")
    def block(self, card_id: str, reason: Literal["lost", "stolen", "fraud"] = "lost") -> Card:
        return expect(self.api.block(self.token, card_id, BlockRequest(reason=reason)), 200, Card)

    @allure.step("Block card {card_id} with body {body}")
    def block_raw(self, card_id: str, body: dict[str, Any]) -> Card:
        return expect(self.api.block(self.token, card_id, body), 200, Card)

    @allure.step("Top up card {card_id} with {amount}")
    def top_up(self, card_id: str, amount: str, idempotency_key: str | None = None) -> MoneyResult:
        key = idempotency_key or new_idempotency_key()
        resp = self.api.top_up(self.token, card_id, TopUpRequest(amount=amount), key)
        return self._money_result(expect(resp, (200, 201), Transaction), resp)

    @allure.step("Top up card {card_id} with body {body}")
    def top_up_raw(self, card_id: str, body: dict[str, Any], idempotency_key: str | None = "auto") -> MoneyResult:
        """Negative tests: exact body; ``idempotency_key=None`` omits the header."""
        key = new_idempotency_key() if idempotency_key == "auto" else idempotency_key
        resp = self.api.top_up(self.token, card_id, body, key)
        return self._money_result(expect(resp, (200, 201), Transaction), resp)

    @allure.step("Pay {amount} at {merchant} with card {card_id}")
    def pay(
        self, card_id: str, amount: str, merchant: str = "Test Store", idempotency_key: str | None = None
    ) -> MoneyResult:
        key = idempotency_key or new_idempotency_key()
        resp = self.api.pay(self.token, card_id, PaymentRequest(amount=amount, merchant=merchant), key)
        return self._money_result(expect(resp, (200, 201), Transaction), resp)

    @allure.step("Pay with card {card_id}, body {body}")
    def pay_raw(self, card_id: str, body: dict[str, Any], idempotency_key: str | None = "auto") -> MoneyResult:
        key = new_idempotency_key() if idempotency_key == "auto" else idempotency_key
        resp = self.api.pay(self.token, card_id, body, key)
        return self._money_result(expect(resp, (200, 201), Transaction), resp)

    @allure.step("Read history of card {card_id}")
    def history(
        self,
        card_id: str,
        type: Literal["top_up", "payment"] | None = None,  # noqa: A002 - mirrors the API filter name
        status: Literal["completed", "declined"] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> TransactionPage:
        params = {"type": type, "status": status, "limit": limit, "offset": offset}
        return self.history_raw(card_id, {k: v for k, v in params.items() if v is not None})

    def history_raw(self, card_id: str, params: dict[str, Any]) -> TransactionPage:
        return expect(self.api.transactions(self.token, card_id, params), 200, TransactionPage)

    @staticmethod
    def _money_result(txn: Transaction, resp: HttpResponse) -> MoneyResult:
        replayed_header = resp.header("Idempotent-Replayed")
        if resp.status == 201 and replayed_header is None:
            return MoneyResult(txn, replayed=False)
        if resp.status == 200 and replayed_header == "true":
            return MoneyResult(txn, replayed=True)
        raise UnexpectedResponse(resp, f"status {resp.status} with Idempotent-Replayed={replayed_header!r}")
