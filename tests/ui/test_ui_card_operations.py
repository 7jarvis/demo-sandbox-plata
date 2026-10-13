from collections.abc import Callable

import allure
import pytest
from playwright.sync_api import Page, expect

from framework.customer import SignedInCustomer
from framework.models import Card
from framework.pages import CardPage
from framework.reporting import case

pytestmark = [allure.feature("Web UI"), allure.story("Card operations")]


def open_card(page: Page, card: Card) -> CardPage:
    card_page = CardPage(page, card.id)
    card_page.open()
    return card_page


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A top-up updates the balance and appears in the history")
@case("TC-UI-09")
def test_top_up(signed_in_page: Page, card: Card, customer: SignedInCustomer) -> None:
    card_page = open_card(signed_in_page, card)

    card_page.top_up_form.top_up("1500")

    expect(card_page.flash.success).to_have_text("Card topped up with 1500.00 MXN.")
    expect(card_page.balance).to_have_text("1500.00 MXN")
    expect(card_page.history.rows).to_have_count(1)
    expect(card_page.history.row(0)).to_contain_text("Top-up")
    expect(card_page.history.amount(0)).to_have_text("+1500.00")
    assert customer.cards.get(card.id).balance == "1500.00"


@allure.title("An invalid top-up amount is explained and nothing is credited")
@case("TC-UI-10")
def test_top_up_with_invalid_amount(signed_in_page: Page, card: Card, customer: SignedInCustomer) -> None:
    card_page = open_card(signed_in_page, card)

    card_page.top_up_form.top_up("0.50")

    expect(card_page.top_up_form.amount).to_have_accessible_description("must be between 1.00 and 50000.00")
    expect(card_page.top_up_form.amount).to_have_value("0.50")
    expect(card_page.balance).to_have_text("0.00 MXN")
    assert customer.cards.history(card.id).total == 0


@pytest.mark.smoke
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("A payment is completed and the balance and today's spending change")
@case("TC-UI-11")
def test_completed_payment(signed_in_page: Page, funded_card: Callable[..., Card]) -> None:
    card = funded_card(balance="500.00")
    card_page = open_card(signed_in_page, card)

    card_page.payment_form.pay("Cinépolis", "120.50")

    expect(card_page.flash.success).to_have_text("Paid 120.50 MXN to Cinépolis.")
    expect(card_page.balance).to_have_text("379.50 MXN")
    expect(card_page.spent_today).to_have_text("120.50")
    expect(card_page.history.row(0)).to_contain_text("Cinépolis")
    expect(card_page.history.row(0)).to_contain_text("Completed")


@allure.title("A declined payment shows the reason and leaves the balance as it was")
@case("TC-UI-12")
def test_declined_payment(signed_in_page: Page, funded_card: Callable[..., Card]) -> None:
    card = funded_card(balance="100.00")
    card_page = open_card(signed_in_page, card)

    card_page.payment_form.pay("Liverpool", "100.01")

    expect(card_page.flash.error).to_have_text("Payment declined: Insufficient funds.")
    expect(card_page.balance).to_have_text("100.00 MXN")
    expect(card_page.history.row(0)).to_contain_text("Declined")
    expect(card_page.history.row(0)).to_contain_text("Insufficient funds")


@allure.title("A frozen card declines payments; unfreezing restores it")
@case("TC-UI-13")
def test_freeze_and_unfreeze(signed_in_page: Page, funded_card: Callable[..., Card]) -> None:
    card = funded_card(balance="100.00")
    card_page = open_card(signed_in_page, card)

    card_page.controls.freeze()

    expect(card_page.flash.success).to_have_text("Card frozen. Payments are paused until you unfreeze it.")
    expect(card_page.status).to_have_text("Frozen")
    expect(card_page.controls.freeze_button).to_have_count(0)

    card_page.payment_form.pay("Oxxo", "10")
    expect(card_page.flash.error).to_have_text("Payment declined: Card is frozen.")

    card_page.controls.unfreeze()
    expect(card_page.status).to_have_text("Active")
    expect(card_page.controls.freeze_button).to_be_visible()


@pytest.mark.smoke
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Blocking through the dialog is permanent and hides money operations")
@case("TC-UI-14")
def test_block_card(signed_in_page: Page, funded_card: Callable[..., Card], customer: SignedInCustomer) -> None:
    card = funded_card(balance="250.00")
    card_page = open_card(signed_in_page, card)

    dialog = card_page.controls.open_block_dialog()
    expect(dialog.root).to_be_visible()
    dialog.block("stolen")

    expect(card_page.flash.success).to_have_text("Card blocked permanently.")
    expect(card_page.status).to_have_text("Blocked")
    expect(card_page.blocked_notice).to_contain_text("reason: stolen")
    expect(card_page.top_up_form.root).to_have_count(0)
    expect(card_page.payment_form.root).to_have_count(0)
    expect(card_page.balance).to_have_text("250.00 MXN")
    blocked = customer.cards.get(card.id)
    assert (blocked.status, blocked.block_reason) == ("blocked", "stolen")


@allure.title("Cancelling the block dialog leaves the card active")
@case("TC-UI-14")
def test_cancel_block(signed_in_page: Page, card: Card, customer: SignedInCustomer) -> None:
    card_page = open_card(signed_in_page, card)

    dialog = card_page.controls.open_block_dialog()
    dialog.cancel()

    expect(dialog.root).to_be_hidden()
    expect(card_page.status).to_have_text("Active")
    assert customer.cards.get(card.id).status == "active"


@allure.title("The block dialog cannot be confirmed without a reason")
@case("TC-UI-14")
def test_block_requires_reason(signed_in_page: Page, card: Card, customer: SignedInCustomer) -> None:
    card_page = open_card(signed_in_page, card)
    dialog = card_page.controls.open_block_dialog()

    dialog.confirm_button.click()

    expect(dialog.root).to_be_visible()
    assert customer.cards.get(card.id).status == "active"


@allure.title("History can be filtered to payments only")
@case("TC-UI-15")
def test_history_filter(signed_in_page: Page, funded_card: Callable[..., Card], customer: SignedInCustomer) -> None:
    card = funded_card(balance="300.00")
    customer.cards.pay(card.id, "50.00", merchant="Oxxo")
    customer.cards.pay(card.id, "500.00", merchant="Liverpool")
    card_page = open_card(signed_in_page, card)
    expect(card_page.history.rows).to_have_count(3)

    card_page.history.show("payment")

    expect(card_page.history.filter_link("payment")).to_have_attribute("aria-current", "page")
    expect(card_page.history.rows).to_have_count(2)
    expect(card_page.history.row(0)).to_contain_text("Liverpool")
    expect(card_page.history.row(1)).to_contain_text("Oxxo")

    card_page.history.show("top_up")
    expect(card_page.history.rows).to_have_count(1)
    expect(card_page.history.amount(0)).to_have_text("+300.00")
