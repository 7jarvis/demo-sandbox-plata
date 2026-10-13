from __future__ import annotations

from typing import Literal

import allure
from playwright.sync_api import Locator, Page

FILTERS = {"all": "All", "top_up": "Top-ups", "payment": "Payments"}


class HistoryTable:
    def __init__(self, page: Page) -> None:
        self.root = page.get_by_role("region", name="Transactions")

    @property
    def rows(self) -> Locator:
        return self.root.get_by_test_id("transaction-row")

    def row(self, index: int) -> Locator:
        """0 is the newest operation."""
        return self.rows.nth(index)

    def amount(self, index: int) -> Locator:
        return self.row(index).get_by_test_id("transaction-amount")

    @property
    def empty_state(self) -> Locator:
        return self.root.get_by_test_id("history-empty")

    def filter_link(self, kind: Literal["all", "top_up", "payment"]) -> Locator:
        return self.root.get_by_role("navigation", name="Filter transactions").get_by_role(
            "link", name=FILTERS[kind]
        )

    @allure.step("Show {kind} operations")
    def show(self, kind: Literal["all", "top_up", "payment"]) -> None:
        self.filter_link(kind).click()
