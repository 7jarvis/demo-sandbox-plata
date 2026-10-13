from collections.abc import Callable

import allure
import pytest

from framework import money
from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card
from framework.reporting import case
from framework.services import new_idempotency_key

pytestmark = [allure.feature("Money"), allure.story("Card payment")]

FundedCard = Callable[..., Card]


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A payment within balance and limit is completed and debits the card")
@case("TC-PAY-01")
def test_payment_debits_balance(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="1000.00")

    result = customer.cards.pay(card.id, "320.50", merchant="Soriana")

    txn = result.transaction
    assert (txn.type, txn.status, txn.amount, txn.merchant) == ("payment", "completed", "320.50", "Soriana")
    assert txn.decline_reason is None
    assert txn.balance_after == "679.50"
    updated = customer.cards.get(card.id)
    assert (updated.balance, updated.spent_today) == ("679.50", "320.50")


@allure.title("Paying the whole balance leaves exactly zero")
@case("TC-PAY-02")
def test_payment_of_entire_balance(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="250.75")

    result = customer.cards.pay(card.id, "250.75")

    assert result.transaction.status == "completed"
    assert customer.cards.get(card.id).balance == "0.00"


@allure.title("A payment one cent above the balance is declined and recorded")
@case("TC-PAY-03")
def test_payment_above_balance_is_declined(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="100.00")

    txn = customer.cards.pay(card.id, money.add("100.00", "0.01")).transaction

    assert (txn.status, txn.decline_reason, txn.balance_after) == ("declined", "INSUFFICIENT_FUNDS", None)
    updated = customer.cards.get(card.id)
    assert (updated.balance, updated.spent_today) == ("100.00", "0.00")
    assert customer.cards.history(card.id, type="payment").items == [txn]


@allure.title("Payments up to the daily limit pass, one cent more is declined")
@case("TC-PAY-04")
def test_daily_limit_boundary(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="1000.00", daily_limit="100.00")

    first = customer.cards.pay(card.id, "60.00").transaction
    second = customer.cards.pay(card.id, "40.00").transaction
    third = customer.cards.pay(card.id, "0.01").transaction

    assert [first.status, second.status] == ["completed", "completed"]
    assert (third.status, third.decline_reason) == ("declined", "DAILY_LIMIT_EXCEEDED")
    updated = customer.cards.get(card.id)
    assert (updated.balance, updated.spent_today) == ("900.00", "100.00")


@allure.title("A single payment above the daily limit is declined even with enough money")
@case("TC-PAY-04")
def test_single_payment_above_daily_limit(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="1000.00", daily_limit="100.00")

    txn = customer.cards.pay(card.id, "100.01").transaction

    assert txn.decline_reason == "DAILY_LIMIT_EXCEEDED"
    assert customer.cards.get(card.id).balance == "1000.00"


@allure.title("Declined payments do not use up the daily limit")
@case("TC-PAY-05")
def test_declined_payment_does_not_count_towards_daily_limit(
    customer: SignedInCustomer, funded_card: FundedCard
) -> None:
    card = funded_card(balance="50.00", daily_limit="100.00")
    declined = customer.cards.pay(card.id, "80.00").transaction
    assert declined.decline_reason == "INSUFFICIENT_FUNDS"

    customer.cards.top_up(card.id, "50.00")
    txn = customer.cards.pay(card.id, "100.00").transaction

    assert txn.status == "completed"
    assert customer.cards.get(card.id).spent_today == "100.00"


@allure.title("A frozen card declines payments until it is unfrozen")
@case("TC-PAY-06")
def test_frozen_card_declines_payment(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="100.00")
    customer.cards.freeze(card.id)

    declined = customer.cards.pay(card.id, "10.00").transaction
    customer.cards.unfreeze(card.id)
    completed = customer.cards.pay(card.id, "10.00").transaction

    assert (declined.status, declined.decline_reason) == ("declined", "CARD_FROZEN")
    assert completed.status == "completed"
    assert customer.cards.get(card.id).balance == "90.00"


@allure.title("A blocked card declines payments")
@case("TC-PAY-07")
def test_blocked_card_declines_payment(customer: SignedInCustomer, funded_card: FundedCard) -> None:
    card = funded_card(balance="100.00")
    customer.cards.block(card.id, "fraud")

    txn = customer.cards.pay(card.id, "10.00").transaction

    assert (txn.status, txn.decline_reason) == ("declined", "CARD_BLOCKED")
    assert customer.cards.get(card.id).balance == "100.00"


@allure.title("Card status is checked before money: a frozen empty card declines as frozen")
@case("TC-PAY-08")
def test_decline_reason_precedence(customer: SignedInCustomer, card: Card) -> None:
    customer.cards.freeze(card.id)

    txn = customer.cards.pay(card.id, "10.00").transaction

    assert txn.decline_reason == "CARD_FROZEN"


@allure.title("Invalid payment is rejected and not recorded: {field}='{value}'")
@case("TC-PAY-09")
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", "0.00"),
        ("amount", "100000.01"),
        ("amount", "5"),
        ("amount", "-5.00"),
        ("merchant", ""),
        ("merchant", "A"),
        ("merchant", "   "),
        ("merchant", "M" * 61),
    ],
)
def test_invalid_payment_is_rejected(
    customer: SignedInCustomer, funded_card: FundedCard, field: str, value: str
) -> None:
    card = funded_card(balance="100.00")
    body = {"amount": "10.00", "merchant": "Oxxo", field: value}

    with rejected(422, "VALIDATION_ERROR", field=field):
        customer.cards.pay_raw(card.id, body)

    assert customer.cards.history(card.id, type="payment").total == 0
    assert customer.cards.get(card.id).balance == "100.00"


@allure.title("Payment amount on the boundary: {amount}")
@case("TC-PAY-09")
@pytest.mark.parametrize("amount", ["0.01", "100000.00"])
def test_payment_amount_on_boundary(customer: SignedInCustomer, funded_card: FundedCard, amount: str) -> None:
    card = funded_card(balance="100000.00", daily_limit="100000.00")

    txn = customer.cards.pay(card.id, amount).transaction

    assert txn.status == "completed"
    assert txn.balance_after == money.sub("100000.00", amount)


@allure.title("A repeated payment is not charged twice and a declined one is not re-evaluated")
@case("TC-PAY-10")
def test_repeated_payment_returns_original_outcome(customer: SignedInCustomer, card: Card) -> None:
    key = new_idempotency_key()
    declined = customer.cards.pay(card.id, "100.00", idempotency_key=key).transaction
    customer.cards.top_up(card.id, "200.00")

    retry = customer.cards.pay(card.id, "100.00", idempotency_key=key)

    assert retry.replayed
    assert retry.transaction == declined
    assert customer.cards.get(card.id).balance == "200.00"
