from __future__ import annotations

import allure
from playwright.sync_api import Locator, Page


class Header:
    def __init__(self, page: Page) -> None:
        self.root = page.get_by_role("banner")

    @property
    def customer_name(self) -> Locator:
        return self.root.get_by_test_id("customer-name")

    @property
    def sign_out_button(self) -> Locator:
        return self.root.get_by_role("button", name="Sign out")

    @allure.step("Sign out")
    def sign_out(self) -> None:
        self.sign_out_button.click()
