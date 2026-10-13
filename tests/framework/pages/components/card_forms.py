"""Forms and dialogs on the card page. Each is scoped to its own region, which
is what makes the two 'Amount, MXN' fields on the page unambiguous."""

from __future__ import annotations

from typing import Literal

import allure
from playwright.sync_api import Locator, Page

BLOCK_REASONS = {"lost": "Lost", "stolen": "Stolen", "fraud": "Suspicious activity"}


class TopUpForm:
    def __init__(self, page: Page) -> None:
        self.root = page.get_by_role("region", name="Top up")

    @property
    def amount(self) -> Locator:
        return self.root.get_by_label("Amount, MXN")

    @property
    def submit_button(self) -> Locator:
        return self.root.get_by_role("button", name="Top up")

    @allure.step("Top up the card with {amount}")
    def top_up(self, amount: str) -> None:
        self.amount.fill(amount)
        self.submit_button.click()


class PaymentForm:
    def __init__(self, page: Page) -> None:
        self.root = page.get_by_role("region", name="Test purchase")

    @property
    def merchant(self) -> Locator:
        return self.root.get_by_label("Merchant")

    @property
    def amount(self) -> Locator:
        return self.root.get_by_label("Amount, MXN")

    @property
    def submit_button(self) -> Locator:
        return self.root.get_by_role("button", name="Pay")

    @allure.step("Pay {amount} at {merchant}")
    def pay(self, merchant: str, amount: str) -> None:
        self.merchant.fill(merchant)
        self.amount.fill(amount)
        self.submit_button.click()


class CardControls:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.root = page.get_by_role("region", name="Card controls")

    @property
    def freeze_button(self) -> Locator:
        # exact: by default the name matches as a substring, and "Unfreeze card" contains it
        return self.root.get_by_role("button", name="Freeze card", exact=True)

    @property
    def unfreeze_button(self) -> Locator:
        return self.root.get_by_role("button", name="Unfreeze card", exact=True)

    @property
    def block_button(self) -> Locator:
        return self.root.get_by_role("button", name="Block card")

    @allure.step("Freeze the card")
    def freeze(self) -> None:
        self.freeze_button.click()

    @allure.step("Unfreeze the card")
    def unfreeze(self) -> None:
        self.unfreeze_button.click()

    @allure.step("Open the block dialog")
    def open_block_dialog(self) -> BlockDialog:
        self.block_button.click()
        return BlockDialog(self.page)


class BlockDialog:
    def __init__(self, page: Page) -> None:
        self.root = page.get_by_role("dialog", name="Block this card?")

    def reason(self, reason: Literal["lost", "stolen", "fraud"]) -> Locator:
        return self.root.get_by_role("radio", name=BLOCK_REASONS[reason])

    @property
    def confirm_button(self) -> Locator:
        return self.root.get_by_role("button", name="Block permanently")

    @property
    def cancel_button(self) -> Locator:
        return self.root.get_by_role("button", name="Cancel")

    @allure.step("Block the card, reason {reason}")
    def block(self, reason: Literal["lost", "stolen", "fraud"]) -> None:
        self.reason(reason).check()
        self.confirm_button.click()

    @allure.step("Cancel blocking")
    def cancel(self) -> None:
        self.cancel_button.click()
