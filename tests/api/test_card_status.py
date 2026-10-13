from collections.abc import Callable
from typing import Literal

import allure
import pytest

from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card
from framework.reporting import case

pytestmark = [allure.feature("Cards"), allure.story("Freeze and block")]


@pytest.mark.smoke
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("A card is frozen and unfrozen by its owner")
@case("TC-STAT-01")
def test_freeze_and_unfreeze(customer: SignedInCustomer, card: Card) -> None:
    frozen = customer.cards.freeze(card.id)
    assert frozen.status == "frozen"
    assert customer.cards.get(card.id).status == "frozen"

    active = customer.cards.unfreeze(card.id)

    assert active.status == "active"
    assert active.model_dump(exclude={"status"}) == frozen.model_dump(exclude={"status"})


@allure.title("Freezing a frozen card is rejected")
@case("TC-STAT-02")
def test_freeze_frozen_card_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    customer.cards.freeze(card.id)

    with rejected(409, "CARD_ALREADY_FROZEN"):
        customer.cards.freeze(card.id)


@allure.title("Unfreezing an active card is rejected")
@case("TC-STAT-02")
def test_unfreeze_active_card_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    with rejected(409, "CARD_NOT_FROZEN"):
        customer.cards.unfreeze(card.id)

    assert customer.cards.get(card.id).status == "active"


@allure.severity(allure.severity_level.CRITICAL)
@allure.title("A card is blocked with reason '{reason}' and keeps its balance")
@case("TC-STAT-03")
@pytest.mark.parametrize("reason", [pytest.param("lost", marks=pytest.mark.smoke), "stolen", "fraud"])
def test_block_card(
    customer: SignedInCustomer, funded_card: Callable[..., Card], reason: Literal["lost", "stolen", "fraud"]
) -> None:
    card = funded_card(balance="75.00")

    blocked = customer.cards.block(card.id, reason)

    assert (blocked.status, blocked.block_reason, blocked.balance) == ("blocked", reason, "75.00")
    assert customer.cards.get(card.id) == blocked


@allure.title("A blocked card cannot be unblocked, frozen or blocked again")
@case("TC-STAT-04")
@pytest.mark.parametrize("action", ["unfreeze", "freeze", "block"])
def test_blocked_card_is_final(customer: SignedInCustomer, card: Card, action: str) -> None:
    customer.cards.block(card.id, "lost")

    with rejected(409, "CARD_BLOCKED"):
        getattr(customer.cards, action)(card.id)

    assert customer.cards.get(card.id).status == "blocked"


@allure.title("A frozen card can be blocked")
@case("TC-STAT-05")
def test_frozen_card_can_be_blocked(customer: SignedInCustomer, card: Card) -> None:
    customer.cards.freeze(card.id)

    blocked = customer.cards.block(card.id, "stolen")

    assert (blocked.status, blocked.block_reason) == ("blocked", "stolen")


@allure.title("Blocking needs a known reason: {body}")
@case("TC-STAT-06")
@pytest.mark.parametrize("body", [{}, {"reason": "broken"}, {"reason": "LOST"}, {"reason": None}])
def test_block_with_invalid_reason_is_rejected(
    customer: SignedInCustomer, card: Card, body: dict[str, object]
) -> None:
    with rejected(422, "VALIDATION_ERROR", field="reason"):
        customer.cards.block_raw(card.id, body)

    assert customer.cards.get(card.id).status == "active"
