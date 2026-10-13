"""'My cards' and 'Issue a card' pages."""

from __future__ import annotations

import allure
from playwright.sync_api import Locator

from framework.pages.base_page import BasePage
from framework.pages.components.card_tile import CardTile


class CardsPage(BasePage):
    path = "/cards"

    @property
    def issue_card_link(self) -> Locator:
        return self.page.get_by_role("link", name="Issue a card")

    @property
    def tiles(self) -> Locator:
        return self.page.get_by_test_id("card-tile")

    def tile(self, label: str) -> CardTile:
        """The tile of the card with this name; names are unique in tests."""
        return CardTile(self.tiles.filter(has_text=label))

    @property
    def empty_state(self) -> Locator:
        return self.page.get_by_test_id("cards-empty")

    @allure.step("Open the card '{label}'")
    def open_card(self, label: str) -> None:
        self.tile(label).root.click()


class NewCardPage(BasePage):
    path = "/cards/new"

    @property
    def label(self) -> Locator:
        return self.page.get_by_label("Card name (optional)")

    @property
    def daily_limit(self) -> Locator:
        return self.page.get_by_label("Daily spending limit, MXN")

    @property
    def submit_button(self) -> Locator:
        return self.page.get_by_role("button", name="Issue card")

    @allure.step("Issue a card (name={label}, daily limit={daily_limit})")
    def issue(self, label: str = "", daily_limit: str | None = None) -> None:
        self.label.fill(label)
        if daily_limit is not None:
            self.daily_limit.fill(daily_limit)
        self.submit_button.click()
