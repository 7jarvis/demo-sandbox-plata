import re

import allure
import pytest
from playwright.sync_api import Page, expect

from framework import builders
from framework.config import Settings
from framework.customer import SignedInCustomer
from framework.pages import CardsPage, CodePage, LoginPage, RegisterPage
from framework.reporting import case
from framework.services import AuthService

pytestmark = [allure.feature("Web UI"), allure.story("Registration and sign-in")]


@pytest.mark.smoke
@allure.severity(allure.severity_level.BLOCKER)
@allure.title("A new customer registers and signs in through the web UI")
@case("TC-UI-01")
def test_register_and_sign_in(page: Page, settings: Settings) -> None:
    data = builders.registration()
    register, login, code, cards = RegisterPage(page), LoginPage(page), CodePage(page), CardsPage(page)

    register.open()
    register.register(data.full_name, data.phone, data.email)

    expect(page).to_have_url(re.compile(r"/login\?phone="))
    expect(login.flash.success).to_have_text("Registration complete. Sign in with your phone number.")
    expect(login.phone).to_have_value(data.phone)

    login.get_code_button.click()
    expect(code.phone_hint).to_have_text(data.phone)
    code.sign_in(settings.otp_code)

    expect(page).to_have_url(re.compile(r"/cards$"))
    expect(cards.heading).to_have_text("My cards")
    expect(cards.header.customer_name).to_have_text(data.full_name)
    expect(cards.empty_state).to_be_visible()


@allure.title("An empty registration form shows an error under every field")
@case("TC-UI-02")
def test_registration_form_shows_field_errors(page: Page) -> None:
    register = RegisterPage(page)
    register.open()

    register.submit_button.click()

    expect(register.full_name).to_have_accessible_description("must be 2 to 100 characters long")
    expect(register.phone).to_have_accessible_description("must be +52 followed by 10 digits")
    expect(register.email).to_have_accessible_description("must be a valid email address")
    for field in (register.full_name, register.phone, register.email):
        expect(field).to_have_attribute("aria-invalid", "true")


@allure.title("A taken phone number is reported on the phone field and the input is kept")
@case("TC-UI-02")
def test_registration_with_taken_phone(page: Page, auth: AuthService) -> None:
    existing = auth.register(builders.registration())
    data = builders.registration(phone=existing.phone)
    register = RegisterPage(page)
    register.open()

    register.register(data.full_name, data.phone, data.email)

    expect(register.phone).to_have_accessible_description("This phone number is already registered.")
    expect(register.full_name).to_have_value(data.full_name)
    expect(register.email).to_have_value(data.email)


@allure.title("A wrong code shows how many attempts are left")
@case("TC-UI-03")
def test_wrong_code_shows_attempts_left(page: Page, customer: SignedInCustomer) -> None:
    login, code = LoginPage(page), CodePage(page)
    login.open()
    login.request_code(customer.phone)

    code.sign_in("000000")

    expect(code.code).to_have_accessible_description("Incorrect code. 2 attempts left.")
    expect(page).to_have_url(re.compile(r"/login/code$"))


@allure.title("A phone in the wrong format is not accepted on the sign-in page")
@case("TC-UI-03")
def test_sign_in_with_malformed_phone(page: Page) -> None:
    login = LoginPage(page)
    login.open()

    login.request_code("5512345678")

    expect(login.phone).to_have_accessible_description("Enter the phone number as +52 followed by 10 digits.")


@allure.title("After signing out the cards page is no longer available")
@case("TC-UI-04")
def test_sign_out(signed_in_page: Page) -> None:
    cards = CardsPage(signed_in_page)
    cards.open()

    cards.header.sign_out()

    expect(signed_in_page).to_have_url(re.compile(r"/login$"))
    cards.open()
    expect(signed_in_page).to_have_url(re.compile(r"/login$"))
