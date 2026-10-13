from collections.abc import Callable

import allure
import pytest

from framework import money
from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card
from framework.reporting import case
from framework.services import new_idempotency_key

pytestmark = [allure.feature("Money"), allure.story("Top-up")]


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A top-up credits the card and is recorded")
@case("TC-TOP-01")
def test_top_up_credits_balance(customer: SignedInCustomer, card: Card) -> None:
    result = customer.cards.top_up(card.id, "1500.00")

    txn = result.transaction
    assert not result.replayed
    assert (txn.card_id, txn.type, txn.status, txn.amount) == (card.id, "top_up", "completed", "1500.00")
    assert txn.balance_after == "1500.00"
    assert customer.cards.get(card.id).balance == "1500.00"


@allure.title("Several top-ups add up exactly")
@case("TC-TOP-01")
def test_top_ups_add_up(customer: SignedInCustomer, card: Card) -> None:
    amounts = ["1.10", "1.20", "1.01", "99.99"]

    for amount in amounts:
        customer.cards.top_up(card.id, amount)

    assert customer.cards.get(card.id).balance == money.add(*amounts)


@allure.title("Top-up amount on the boundary is accepted: {amount}")
@case("TC-TOP-02")
@pytest.mark.parametrize("amount", ["1.00", "50000.00"])
def test_top_up_amount_on_boundary(customer: SignedInCustomer, card: Card, amount: str) -> None:
    assert customer.cards.top_up(card.id, amount).transaction.balance_after == amount


@allure.title("Invalid top-up amount is rejected and nothing is credited: '{amount}'")
@case("TC-TOP-03")
@pytest.mark.parametrize(
    "amount", ["0.99", "50000.01", "0.00", "-10.00", "10", "10.5", "10.123", "1e3", "", " 10.00", "10,00"]
)
def test_top_up_with_invalid_amount_is_rejected(customer: SignedInCustomer, card: Card, amount: str) -> None:
    with rejected(422, "VALIDATION_ERROR", field="amount"):
        customer.cards.top_up(card.id, amount)

    assert customer.cards.get(card.id).balance == "0.00"
    assert customer.cards.history(card.id).total == 0


@allure.title("Repeating a top-up with the same key credits the card once")
@case("TC-TOP-04")
def test_repeated_top_up_with_same_key_is_credited_once(customer: SignedInCustomer, card: Card) -> None:
    key = new_idempotency_key()
    first = customer.cards.top_up(card.id, "250.00", idempotency_key=key)

    retry = customer.cards.top_up(card.id, "250.00", idempotency_key=key)

    assert retry.replayed
    assert retry.transaction == first.transaction
    assert customer.cards.get(card.id).balance == "250.00"
    assert customer.cards.history(card.id).total == 1


@allure.title("The same key with a different amount is rejected")
@case("TC-TOP-05")
def test_same_key_with_different_amount_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    key = new_idempotency_key()
    customer.cards.top_up(card.id, "250.00", idempotency_key=key)

    with rejected(422, "IDEMPOTENCY_KEY_REUSED"):
        customer.cards.top_up(card.id, "300.00", idempotency_key=key)

    assert customer.cards.get(card.id).balance == "250.00"


@allure.title("The same key for another card is rejected")
@case("TC-TOP-05")
def test_same_key_for_another_card_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    other = customer.cards.issue(label="Other")
    key = new_idempotency_key()
    customer.cards.top_up(card.id, "250.00", idempotency_key=key)

    with rejected(422, "IDEMPOTENCY_KEY_REUSED"):
        customer.cards.top_up(other.id, "250.00", idempotency_key=key)

    assert customer.cards.get(other.id).balance == "0.00"


@allure.title("Idempotency keys of different customers do not collide")
@case("TC-TOP-05")
def test_same_key_is_independent_between_customers(new_customer: Callable[[], SignedInCustomer]) -> None:
    alice, bob = new_customer(), new_customer()
    alice_card, bob_card = alice.cards.issue(), bob.cards.issue()
    key = new_idempotency_key()

    alice_txn = alice.cards.top_up(alice_card.id, "10.00", idempotency_key=key).transaction
    bob_result = bob.cards.top_up(bob_card.id, "10.00", idempotency_key=key)

    assert not bob_result.replayed
    assert bob_result.transaction.id != alice_txn.id


@allure.title("A top-up without an idempotency key is rejected")
@case("TC-TOP-06")
def test_top_up_without_idempotency_key_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    with rejected(400, "IDEMPOTENCY_KEY_REQUIRED"):
        customer.cards.top_up_raw(card.id, {"amount": "10.00"}, idempotency_key=None)

    assert customer.cards.get(card.id).balance == "0.00"


@allure.title("A frozen card can still be topped up")
@case("TC-TOP-07")
def test_frozen_card_can_be_topped_up(customer: SignedInCustomer, card: Card) -> None:
    customer.cards.freeze(card.id)

    customer.cards.top_up(card.id, "100.00")

    updated = customer.cards.get(card.id)
    assert (updated.status, updated.balance) == ("frozen", "100.00")


@allure.title("A blocked card cannot be topped up and nothing is recorded")
@case("TC-TOP-08")
def test_blocked_card_cannot_be_topped_up(customer: SignedInCustomer, card: Card) -> None:
    customer.cards.block(card.id, "stolen")

    with rejected(409, "CARD_BLOCKED"):
        customer.cards.top_up(card.id, "100.00")

    assert customer.cards.get(card.id).balance == "0.00"
    assert customer.cards.history(card.id).total == 0


@allure.title("The balance cannot exceed 500000.00")
@case("TC-TOP-09")
def test_balance_cannot_exceed_maximum(customer: SignedInCustomer, card: Card) -> None:
    for _ in range(10):
        customer.cards.top_up(card.id, "50000.00")
    assert customer.cards.get(card.id).balance == "500000.00"

    with rejected(409, "BALANCE_LIMIT_EXCEEDED"):
        customer.cards.top_up(card.id, "1.00")

    assert customer.cards.get(card.id).balance == "500000.00"
