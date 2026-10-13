"""Contract robustness: what the API does with bodies a model would never send.

These tests work one layer lower than the rest, through the adapter's raw
request, because a malformed body cannot be expressed as a request model.
"""

import allure
import pytest

from framework.adapters.cardpay_api import CardpayApi
from framework.assertions import rejected
from framework.customer import SignedInCustomer
from framework.models import Card, ErrorResponse, Transaction
from framework.reporting import case
from framework.services import new_idempotency_key
from framework.services.base import expect, parse

pytestmark = [allure.feature("Security"), allure.story("Contract robustness")]


@allure.title("A body that is not a JSON object is rejected: {body}")
@case("TC-SEC-03")
@pytest.mark.parametrize("body", ["{", '{"amount": "10.00"', "[]", '"10.00"', "null", "\x00\x01"])
def test_malformed_body_is_rejected_and_nothing_is_credited(
    api: CardpayApi, customer: SignedInCustomer, card: Card, body: str
) -> None:
    key = {"Idempotency-Key": new_idempotency_key()}

    with rejected(400, "MALFORMED_JSON"):
        expect(api.send_raw("POST", f"/cards/{card.id}/top-ups", customer.token, body, key), 201, Transaction)

    assert customer.cards.get(card.id).balance == "0.00"


@allure.title("Unknown fields are rejected, not ignored")
@case("TC-SEC-04")
def test_unknown_field_is_rejected(customer: SignedInCustomer, card: Card) -> None:
    with rejected(422, "VALIDATION_ERROR", field="currency") as rejection:
        customer.cards.top_up_raw(card.id, {"amount": "10.00", "currency": "USD"})

    assert rejection.error is not None
    assert rejection.error.fields["currency"] == "unknown field"
    assert customer.cards.get(card.id).balance == "0.00"


@allure.title("Money sent as a JSON number is rejected: {amount}")
@case("TC-SEC-05")
@pytest.mark.parametrize("amount", [10, 10.5, True])
def test_money_as_number_is_rejected(customer: SignedInCustomer, card: Card, amount: object) -> None:
    with rejected(422, "VALIDATION_ERROR", field="amount"):
        customer.cards.top_up_raw(card.id, {"amount": amount})
    with rejected(422, "VALIDATION_ERROR", field="amount"):
        customer.cards.pay_raw(card.id, {"amount": amount, "merchant": "Oxxo"})

    assert customer.cards.history(card.id).total == 0


@allure.title("Every error has the same shape and the request id is echoed")
@case("TC-SEC-06")
def test_error_shape_and_request_id(api: CardpayApi, customer: SignedInCustomer) -> None:
    resp = api.get_card(customer.token, "card_does_not_exist")

    error = parse(resp, ErrorResponse).error
    assert (resp.status, error.code, error.details) == (404, "CARD_NOT_FOUND", None)
    assert resp.header("X-Request-Id") == resp.request_id
    assert resp.header("Content-Type") == "application/json"


@allure.title("An unknown API path answers with the error contract")
@case("TC-SEC-06")
def test_unknown_path_uses_error_contract(api: CardpayApi) -> None:
    resp = api.send_raw("POST", "/no-such-endpoint", None, "{}")

    assert resp.status == 404
    assert parse(resp, ErrorResponse).error.code == "NOT_FOUND"


@allure.title("A body above 16 KB is refused")
@case("TC-SEC-03")
def test_oversized_body_is_rejected(api: CardpayApi, customer: SignedInCustomer, card: Card) -> None:
    body = '{"amount": "10.00", "pad": "' + "x" * 20_000 + '"}'
    key = {"Idempotency-Key": new_idempotency_key()}

    with rejected(413, "PAYLOAD_TOO_LARGE"):
        expect(api.send_raw("POST", f"/cards/{card.id}/top-ups", customer.token, body, key), 201, Transaction)
