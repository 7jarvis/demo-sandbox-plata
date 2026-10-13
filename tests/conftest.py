"""Fixtures and hooks shared by API and UI tests."""

from __future__ import annotations

import os
import platform
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from framework import builders
from framework.adapters.cardpay_api import CardpayApi
from framework.config import Settings
from framework.customer import SignedInCustomer
from framework.http_client import HttpClient
from framework.models import Card
from framework.services import AuthService, CardsService

SUITE_MARKERS = {"api", "ui"}
MAX_TOP_UP = Decimal("50000.00")


# ---------------------------------------------------------------- suites


@pytest.hookimpl(tryfirst=True)  # before -m deselects anything
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Regression is the full suite and smoke is its subset, so every test is in
    regression. The layer marker (api/ui) comes from the directory."""
    for item in items:
        parts = Path(str(item.path)).parts
        for layer in SUITE_MARKERS:
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
        item.add_marker(pytest.mark.regression)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Environment block of the Allure report."""
    results = session.config.getoption("--alluredir", default=None)
    if not results:
        return
    settings = Settings.from_env()
    Path(results).mkdir(parents=True, exist_ok=True)
    env = {
        "Base URL": settings.base_url,
        "Suite": os.getenv("TEST_SUITE", "local"),
        "Commit": os.getenv("GITHUB_SHA", "local")[:12],
        "Python": platform.python_version(),
    }
    lines = (f"{k.replace(' ', '.')}={v}" for k, v in env.items())
    (Path(results) / "environment.properties").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- framework


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture(scope="session")
def http(settings: Settings) -> Iterator[HttpClient]:
    client = HttpClient(settings.api_url, settings.http_timeout)
    yield client
    client.close()


@pytest.fixture(scope="session")
def api(http: HttpClient) -> CardpayApi:
    return CardpayApi(http)


@pytest.fixture(scope="session")
def auth(api: CardpayApi, settings: Settings) -> AuthService:
    return AuthService(api, settings.otp_code)


# ---------------------------------------------------------------- test data


@pytest.fixture
def new_customer(auth: AuthService, api: CardpayApi) -> Callable[[], SignedInCustomer]:
    """Factory: a freshly registered and signed-in customer. The service has no
    way to delete customers; isolation comes from every test owning unique
    customers, and CI discards the database after the run."""

    def make() -> SignedInCustomer:
        customer = auth.register(builders.registration())
        token = auth.login(customer.phone).access_token
        return SignedInCustomer(customer, token, CardsService(api, token))

    return make


@pytest.fixture
def customer(new_customer: Callable[[], SignedInCustomer]) -> SignedInCustomer:
    return new_customer()


@pytest.fixture
def card(customer: SignedInCustomer) -> Card:
    """An active card with zero balance."""
    return customer.cards.issue(label="Main")


@pytest.fixture
def funded_card(customer: SignedInCustomer) -> Callable[..., Card]:
    """Factory: an active card topped up with ``balance`` (in top-ups of at most
    50000.00, the largest single top-up)."""

    def make(balance: str = "1000.00", daily_limit: str | None = None, label: str | None = "Funded") -> Card:
        card = customer.cards.issue(label=label, daily_limit=daily_limit)
        left = Decimal(balance)
        while left > 0:
            chunk = min(left, MAX_TOP_UP)
            customer.cards.top_up(card.id, f"{chunk:.2f}")
            left -= chunk
        return customer.cards.get(card.id)

    return make
