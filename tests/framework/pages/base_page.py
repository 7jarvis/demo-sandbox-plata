"""Base for page objects.

Page objects expose locators and user actions; assertions stay in tests (with
Playwright's auto-waiting ``expect``). Locators were chosen on the live pages:
role + accessible name first, then label, then ``data-testid`` for values that
have no role (balances, statuses). No CSS classes, no XPath.
"""

from __future__ import annotations

import allure
from playwright.sync_api import Locator, Page

from framework.pages.components.flash import Flash
from framework.pages.components.header import Header


class BasePage:
    path = "/"

    def __init__(self, page: Page) -> None:
        self.page = page
        self.header = Header(page)
        self.flash = Flash(page)

    def open(self) -> None:
        with allure.step(f"Open {self.path}"):
            self.page.goto(self.path)

    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", level=1)
