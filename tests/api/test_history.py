from collections.abc import Callable

import allure
import pytest

from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card
from framework.reporting import case

pytestmark = [allure.feature("History"), allure.story("Card transactions")]


@pytest.fixture
def card_with_history(customer: SignedInCustomer, funded_card: Callable[..., Card]) -> Card:
    """top-up 500.00, payments 120.00 (ok), 900.00 (declined), 30.50 (ok)."""
    card = funded_card(balance="500.00")
    customer.cards.pay(card.id, "120.00", merchant="Cinépolis")
    customer.cards.pay(card.id, "900.00", merchant="Liverpool")
    customer.cards.pay(card.id, "30.50", merchant="Oxxo")
    return card


@pytest.mark.smoke
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("History shows every operation, newest first, with running balance")
@case("TC-HIST-01")
def test_history_lists_operations_newest_first(customer: SignedInCustomer, card_with_history: Card) -> None:
    page = customer.cards.history(card_with_history.id)

    rows = [(t.type, t.status, t.amount, t.merchant, t.balance_after) for t in page.items]
    assert rows == [
        ("payment", "completed", "30.50", "Oxxo", "349.50"),
        ("payment", "declined", "900.00", "Liverpool", None),
        ("payment", "completed", "120.00", "Cinépolis", "380.00"),
        ("top_up", "completed", "500.00", None, "500.00"),
    ]
    assert page.total == 4
    assert customer.cards.get(card_with_history.id).balance == page.items[0].balance_after


@allure.title("History filter type={type} status={status} -> {expected} operations")
@case("TC-HIST-02")
@pytest.mark.parametrize(
    ("type", "status", "expected"),
    [
        ("top_up", None, 1),
        ("payment", None, 3),
        (None, "declined", 1),
        (None, "completed", 3),
        ("payment", "completed", 2),
        ("top_up", "declined", 0),
    ],
)
def test_history_filters(
    customer: SignedInCustomer,
    card_with_history: Card,
    type: str | None,  # noqa: A002 - API filter name
    status: str | None,
    expected: int,
) -> None:
    page = customer.cards.history(card_with_history.id, type=type, status=status)  # type: ignore[arg-type]

    assert page.total == expected
    assert len(page.items) == expected
    if type:
        assert {t.type for t in page.items} <= {type}
    if status:
        assert {t.status for t in page.items} <= {status}


@allure.title("Pages of the history do not overlap and together cover it all")
@case("TC-HIST-03")
def test_history_pagination(customer: SignedInCustomer, card_with_history: Card) -> None:
    full = customer.cards.history(card_with_history.id).items

    pages = [customer.cards.history(card_with_history.id, limit=3, offset=offset) for offset in (0, 3, 6)]

    assert [len(p.items) for p in pages] == [3, 1, 0]
    assert all(p.total == 4 for p in pages)
    assert [t.id for p in pages for t in p.items] == [t.id for t in full]


@allure.title("Invalid history parameter is rejected: {params}")
@case("TC-HIST-04")
@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": "abc"},
        {"offset": -1},
        {"type": "refund"},
        {"status": "pending"},
    ],
)
def test_history_with_invalid_parameter_is_rejected(
    customer: SignedInCustomer, card: Card, params: dict[str, object]
) -> None:
    with rejected(422, "VALIDATION_ERROR", field=next(iter(params))):
        customer.cards.history_raw(card.id, params)


@allure.title("A card without operations has an empty history")
@case("TC-HIST-05")
def test_empty_history(customer: SignedInCustomer, card: Card) -> None:
    page = customer.cards.history(card.id)

    assert (page.items, page.total, page.limit, page.offset) == ([], 0, 20, 0)
