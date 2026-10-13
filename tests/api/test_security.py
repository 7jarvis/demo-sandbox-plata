from collections.abc import Callable

import allure
import pytest

from framework.adapters.cardpay_api import CardpayApi
from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card
from framework.reporting import case
from framework.services import AuthService, CardsService

pytestmark = [allure.feature("Security"), allure.story("Access control")]

CARD_ACTIONS: dict[str, Callable[[CardsService, str], object]] = {
    "get card": lambda s, card_id: s.get(card_id),
    "top up": lambda s, card_id: s.top_up(card_id, "10.00"),
    "pay": lambda s, card_id: s.pay(card_id, "10.00"),
    "freeze": lambda s, card_id: s.freeze(card_id),
    "unfreeze": lambda s, card_id: s.unfreeze(card_id),
    "block": lambda s, card_id: s.block(card_id, "lost"),
    "history": lambda s, card_id: s.history(card_id),
}

SMOKE_ACTIONS = ("get card", "pay")


def _actions(smoke: bool) -> list[object]:
    """Card actions as parameters; with ``smoke`` the key ones are also in the smoke suite."""
    return [
        pytest.param(name, marks=pytest.mark.smoke) if smoke and name in SMOKE_ACTIONS else name
        for name in CARD_ACTIONS
    ]


BAD_TOKENS = {
    "no token": None,
    "empty token": "",
    "unknown token": "x" * 43,
}


@allure.severity(allure.severity_level.BLOCKER)
@allure.title("Without a valid token every card operation is refused: {action}, {token_kind}")
@case("TC-SEC-01")
@pytest.mark.parametrize("token_kind", BAD_TOKENS)
@pytest.mark.parametrize("action", CARD_ACTIONS)
def test_card_operations_require_valid_token(
    api: CardpayApi, customer: SignedInCustomer, card: Card, action: str, token_kind: str
) -> None:
    anonymous = CardsService(api, BAD_TOKENS[token_kind])

    with rejected(401, "UNAUTHORIZED"):
        CARD_ACTIONS[action](anonymous, card.id)

    assert customer.cards.get(card.id) == card


@pytest.mark.smoke
@allure.title("Without a valid token the profile and the card list are refused")
@case("TC-SEC-01")
@pytest.mark.parametrize("token_kind", BAD_TOKENS)
def test_profile_and_list_require_valid_token(api: CardpayApi, auth: AuthService, token_kind: str) -> None:
    with rejected(401, "UNAUTHORIZED"):
        auth.me(BAD_TOKENS[token_kind])
    with rejected(401, "UNAUTHORIZED"):
        CardsService(api, BAD_TOKENS[token_kind]).list()


@allure.severity(allure.severity_level.BLOCKER)
@allure.title("Another customer's card looks like it does not exist: {action}")
@case("TC-SEC-02")
@pytest.mark.parametrize("action", _actions(smoke=True))
def test_other_customers_card_is_not_found(
    new_customer: Callable[[], SignedInCustomer],
    customer: SignedInCustomer,
    funded_card: Callable[..., Card],
    action: str,
) -> None:
    victim_card = funded_card(balance="100.00")
    intruder = new_customer()

    with rejected(404, "CARD_NOT_FOUND"):
        CARD_ACTIONS[action](intruder.cards, victim_card.id)

    assert customer.cards.get(victim_card.id) == victim_card
    assert customer.cards.history(victim_card.id).total == 1  # only the initial top-up


@allure.title("An unknown card id answers the same as another customer's card")
@case("TC-SEC-02")
def test_unknown_card_is_not_found(customer: SignedInCustomer) -> None:
    with rejected(404, "CARD_NOT_FOUND"):
        customer.cards.get("card_" + "0" * 24)
