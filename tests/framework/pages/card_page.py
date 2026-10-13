"""Card page: figures, money forms, controls and history."""

from __future__ import annotations

from playwright.sync_api import Locator, Page

from framework.pages.base_page import BasePage
from framework.pages.components.card_forms import CardControls, PaymentForm, TopUpForm
from framework.pages.components.history_table import HistoryTable


class CardPage(BasePage):
    def __init__(self, page: Page, card_id: str = "") -> None:
        super().__init__(page)
        self.path = f"/cards/{card_id}"
        self.top_up_form = TopUpForm(page)
        self.payment_form = PaymentForm(page)
        self.controls = CardControls(page)
        self.history = HistoryTable(page)

    @property
    def balance(self) -> Locator:
        return self.page.get_by_test_id("card-balance")

    @property
    def status(self) -> Locator:
        return self.page.get_by_test_id("card-status")

    @property
    def spent_today(self) -> Locator:
        return self.page.get_by_test_id("card-spent-today")

    @property
    def daily_limit(self) -> Locator:
        return self.page.get_by_test_id("card-daily-limit")

    @property
    def pan(self) -> Locator:
        return self.page.get_by_test_id("card-pan")

    @property
    def blocked_notice(self) -> Locator:
        return self.page.get_by_test_id("blocked-notice")
