"""Money under concurrent requests.

Each worker thread gets its own HTTP session (``requests.Session`` is not
thread-safe), all for the same customer. Requests are released together by a
barrier so they really overlap on the server.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import allure
import pytest

from framework.adapters.cardpay_api import CardpayApi
from framework.config import Settings
from framework.customer import SignedInCustomer
from framework.http_client import HttpClient
from framework.models import Card
from framework.reporting import case
from framework.services import CardsService, MoneyResult, new_idempotency_key

pytestmark = [allure.feature("Money"), allure.story("Concurrency"), pytest.mark.slow]

WORKERS = 10


def run_in_parallel(
    settings: Settings, token: str, action: Callable[[CardsService], MoneyResult], workers: int = WORKERS
) -> list[MoneyResult]:
    barrier = Barrier(workers)

    def worker(_: int) -> MoneyResult:
        http = HttpClient(settings.api_url, settings.http_timeout)
        try:
            service = CardsService(CardpayApi(http), token)
            barrier.wait()
            return action(service)
        finally:
            http.close()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(worker, range(workers)))


@allure.title("Ten simultaneous payments cannot spend more than the balance")
@case("TC-PAY-11")
def test_parallel_payments_cannot_overdraw(
    settings: Settings, customer: SignedInCustomer, funded_card: Callable[..., Card]
) -> None:
    card = funded_card(balance="100.00")

    results = run_in_parallel(settings, customer.token, lambda s: s.pay(card.id, "30.00"))

    statuses = sorted(r.transaction.status for r in results)
    assert statuses == ["completed"] * 3 + ["declined"] * 7
    assert {r.transaction.decline_reason for r in results if r.transaction.status == "declined"} == {
        "INSUFFICIENT_FUNDS"
    }
    assert customer.cards.get(card.id).balance == "10.00"
    balances = sorted(r.transaction.balance_after for r in results if r.transaction.balance_after)
    assert balances == ["10.00", "40.00", "70.00"]


@allure.title("Simultaneous retries of one top-up credit the card once")
@case("TC-TOP-10")
def test_parallel_retries_with_same_key_credit_once(settings: Settings, customer: SignedInCustomer, card: Card) -> None:
    key = new_idempotency_key()

    results = run_in_parallel(settings, customer.token, lambda s: s.top_up(card.id, "500.00", idempotency_key=key))

    assert len({r.transaction.id for r in results}) == 1
    assert sorted(r.replayed for r in results) == [False] + [True] * (WORKERS - 1)
    assert customer.cards.get(card.id).balance == "500.00"
    assert customer.cards.history(card.id).total == 1
