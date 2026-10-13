"""Registration and sign-in pages."""

from __future__ import annotations

import allure
from playwright.sync_api import Locator

from framework.pages.base_page import BasePage


class RegisterPage(BasePage):
    path = "/register"

    @property
    def full_name(self) -> Locator:
        return self.page.get_by_label("Full name")

    @property
    def phone(self) -> Locator:
        return self.page.get_by_label("Mobile phone")

    @property
    def email(self) -> Locator:
        return self.page.get_by_label("Email")

    @property
    def submit_button(self) -> Locator:
        return self.page.get_by_role("button", name="Create account")

    @allure.step("Fill in the registration form and submit")
    def register(self, full_name: str, phone: str, email: str) -> None:
        self.full_name.fill(full_name)
        self.phone.fill(phone)
        self.email.fill(email)
        self.submit_button.click()


class LoginPage(BasePage):
    path = "/login"

    @property
    def phone(self) -> Locator:
        return self.page.get_by_label("Mobile phone")

    @property
    def get_code_button(self) -> Locator:
        return self.page.get_by_role("button", name="Get code")

    @allure.step("Request a code for {phone}")
    def request_code(self, phone: str) -> None:
        self.phone.fill(phone)
        self.get_code_button.click()


class CodePage(BasePage):
    path = "/login/code"

    @property
    def code(self) -> Locator:
        return self.page.get_by_label("One-time code")

    @property
    def phone_hint(self) -> Locator:
        return self.page.get_by_test_id("otp-phone")

    @property
    def sign_in_button(self) -> Locator:
        return self.page.get_by_role("button", name="Sign in")

    @allure.step("Enter the code and sign in")
    def sign_in(self, code: str) -> None:
        self.code.fill(code)
        self.sign_in_button.click()
