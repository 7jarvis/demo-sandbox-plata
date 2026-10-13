import re
from collections.abc import Callable

import allure
import pytest
from playwright.sync_api import Page, expect

from framework.customer import SignedInCustomer
from framework.pages import CardPage, CardsPage, NewCardPage
from framework.reporting import case

pytestmark = [allure.feature("Web UI"), allure.story("Cards")]


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A customer issues a card and sees it on 'My cards'")
@case("TC-UI-05")
def test_issue_card(signed_in_page: Page) -> None:
    cards, new_card, card_page = CardsPage(signed_in_page), NewCardPage(signed_in_page), CardPage(signed_in_page)
    cards.open()
    cards.issue_card_link.click()

    new_card.issue(label="Subscriptions", daily_limit="1500")

    expect(signed_in_page).to_have_url(re.compile(r"/cards/card_[0-9a-f]{24}$"))
    expect(card_page.flash.success).to_have_text("Card issued.")
    expect(card_page.heading).to_have_text("Subscriptions")
    expect(card_page.status).to_have_text("Active")
    expect(card_page.balance).to_have_text("0.00 MXN")
    expect(card_page.daily_limit).to_have_text("1500.00")
    expect(card_page.history.empty_state).to_have_text("No transactions yet.")

    cards.open()
    tile = cards.tile("Subscriptions")
    expect(tile.status).to_have_text("Active")
    expect(tile.balance).to_have_text("0.00 MXN")
    expect(tile.pan).to_have_text(re.compile(r"^\d{4} \*{4} \*{4} \d{4}$"))


@allure.title("An invalid daily limit is explained on the field")
@case("TC-UI-06")
def test_issue_card_with_invalid_daily_limit(signed_in_page: Page, customer: SignedInCustomer) -> None:
    new_card = NewCardPage(signed_in_page)
    new_card.open()

    new_card.issue(label="Too small", daily_limit="99.99")

    expect(new_card.daily_limit).to_have_accessible_description("must be between 100.00 and 100000.00")
    expect(new_card.label).to_have_value("Too small")
    assert customer.cards.list() == []


@allure.title("The fourth card is refused with an explanation")
@case("TC-UI-07")
def test_fourth_card_is_refused(signed_in_page: Page, customer: SignedInCustomer) -> None:
    for i in range(3):
        customer.cards.issue(label=f"Card {i + 1}")
    new_card = NewCardPage(signed_in_page)
    new_card.open()

    new_card.issue(label="Card 4")

    expect(new_card.flash.error).to_have_text("A customer can hold at most 3 cards that are not blocked.")
    CardsPage(signed_in_page).open()
    expect(CardsPage(signed_in_page).tiles).to_have_count(3)


@allure.title("A card of another customer cannot be opened")
@case("TC-UI-08")
def test_other_customers_card_is_not_shown(
    signed_in_page: Page, new_customer: Callable[[], SignedInCustomer]
) -> None:
    stranger_card = new_customer().cards.issue(label="Not yours")
    card_page = CardPage(signed_in_page, stranger_card.id)

    card_page.open()

    expect(card_page.heading).to_have_text("Page not found")
    expect(signed_in_page.get_by_text("Not yours")).to_have_count(0)
