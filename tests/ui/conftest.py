"""Browser fixtures. Preconditions (customer, cards, money) are created through
the API, which is faster and more reliable than clicking; the UI is used for
the behavior under test."""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any

import allure
import pytest
from playwright.sync_api import BrowserContext, Page, expect

from framework.config import Settings
from framework.customer import SignedInCustomer
from framework.pages.session import sign_in

expect.set_options(timeout=5_000)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return {**browser_context_args, "base_url": settings.base_url, "viewport": {"width": 1280, "height": 900}}


@pytest.fixture
def signed_in_page(
    context: BrowserContext, page: Page, customer: SignedInCustomer, settings: Settings
) -> Page:
    """A page whose browser context is signed in as ``customer``."""
    sign_in(context, customer.phone, settings.otp_code)
    return page


@pytest.fixture
def sign_in_as(context: BrowserContext, settings: Settings) -> Callable[[SignedInCustomer], None]:
    def do(who: SignedInCustomer) -> None:
        context.clear_cookies()
        sign_in(context, who.phone, settings.otp_code)

    return do


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any, None]:
    """Attach a screenshot of the page to the Allure report when a UI test fails."""
    outcome = yield
    report = outcome.get_result()
    page = item.funcargs.get("page") if hasattr(item, "funcargs") else None
    if report.when == "call" and report.failed and page is not None:
        try:
            allure.attach(page.screenshot(full_page=True), name="page on failure",
                          attachment_type=allure.attachment_type.PNG)  # fmt: skip
        except Exception:  # noqa: BLE001 - a broken page must not hide the real failure
            pass
