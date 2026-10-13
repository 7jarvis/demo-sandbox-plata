from collections.abc import Callable
from datetime import UTC, datetime

import allure
import pytest

from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.reporting import case

pytestmark = [allure.feature("Cards"), allure.story("Issuing a card")]


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("An issued card is active, empty and has the default daily limit")
@case("TC-CARD-01")
def test_issue_card_with_defaults(customer: SignedInCustomer) -> None:
    card = customer.cards.issue(label="  Online shopping ")

    assert card.status == "active"
    assert card.block_reason is None
    assert card.label == "Online shopping"
    assert (card.balance, card.spent_today, card.daily_limit) == ("0.00", "0.00", "20000.00")
    now = datetime.now(UTC)
    assert card.expires == f"{now.month:02d}/{(now.year + 4) % 100:02d}"
    assert customer.cards.list() == [card]


@allure.title("A card without a name can be issued")
@case("TC-CARD-01")
def test_issue_card_without_label(customer: SignedInCustomer) -> None:
    card = customer.cards.issue_raw({})

    assert card.label is None
    assert card.daily_limit == "20000.00"


@allure.title("Daily limit on the boundary is accepted: {limit}")
@case("TC-CARD-02")
@pytest.mark.parametrize("limit", ["100.00", "100000.00"])
def test_issue_card_with_daily_limit_on_boundary(customer: SignedInCustomer, limit: str) -> None:
    card = customer.cards.issue(daily_limit=limit)

    assert card.daily_limit == limit


@allure.title("Invalid daily limit is rejected: '{limit}'")
@case("TC-CARD-03")
@pytest.mark.parametrize("limit", ["99.99", "100000.01", "0.00", "500", "500.0", "500.001", "-100.00", "1e3"])
def test_issue_card_with_invalid_daily_limit_is_rejected(customer: SignedInCustomer, limit: str) -> None:
    with rejected(422, "VALIDATION_ERROR", field="daily_limit"):
        customer.cards.issue(daily_limit=limit)

    assert customer.cards.list() == []


@allure.title("Card name length: {length} characters -> accepted={accepted}")
@case("TC-CARD-04")
@pytest.mark.parametrize(("length", "accepted"), [(1, True), (30, True), (31, False)])
def test_card_label_length(customer: SignedInCustomer, length: int, accepted: bool) -> None:
    label = "x" * length
    if accepted:
        assert customer.cards.issue(label=label).label == label
    else:
        with rejected(422, "VALIDATION_ERROR", field="label"):
            customer.cards.issue(label=label)


@allure.title("A blank card name is rejected")
@case("TC-CARD-04")
def test_blank_card_label_is_rejected(customer: SignedInCustomer) -> None:
    with rejected(422, "VALIDATION_ERROR", field="label"):
        customer.cards.issue(label="   ")


@allure.title("A customer cannot hold more than three cards that are not blocked")
@case("TC-CARD-05")
def test_fourth_card_is_rejected(customer: SignedInCustomer) -> None:
    for i in range(3):
        customer.cards.issue(label=f"Card {i + 1}")

    with rejected(409, "CARD_LIMIT_REACHED"):
        customer.cards.issue(label="Card 4")

    assert len(customer.cards.list()) == 3


@allure.title("A blocked card frees a slot for a new one")
@case("TC-CARD-06")
def test_blocked_card_does_not_count_towards_limit(customer: SignedInCustomer) -> None:
    cards = [customer.cards.issue(label=f"Card {i + 1}") for i in range(3)]
    customer.cards.block(cards[0].id, "lost")

    replacement = customer.cards.issue(label="Replacement")

    statuses = {c.id: c.status for c in customer.cards.list()}
    assert statuses == {cards[0].id: "blocked", cards[1].id: "active", cards[2].id: "active", replacement.id: "active"}


@allure.title("A new customer has an empty card list")
@case("TC-CARD-07")
def test_new_customer_has_no_cards(customer: SignedInCustomer) -> None:
    assert customer.cards.list() == []


@allure.title("Each customer sees only their own cards")
@case("TC-CARD-07")
def test_card_list_contains_only_own_cards(new_customer: Callable[[], SignedInCustomer]) -> None:
    alice, bob = new_customer(), new_customer()
    alice_card = alice.cards.issue(label="Alice")
    bob.cards.issue(label="Bob")

    assert [c.id for c in alice.cards.list()] == [alice_card.id]
