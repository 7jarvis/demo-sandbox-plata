"""Allure metadata shared by API and UI tests.

``case("TC-PAY-01")`` links an automated test to its manual test case in
docs/test-cases, so the report shows which documented case a test covers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import allure

F = TypeVar("F", bound=Callable[..., object])

DOCS_URL = "https://github.com/7jarvis/demo-sandbox-plata/blob/main/docs/test-cases"

CASE_FILES = {
    "REG": "registration-and-login.md",
    "AUTH": "registration-and-login.md",
    "CARD": "cards.md",
    "TOP": "top-ups.md",
    "PAY": "payments.md",
    "STAT": "card-status.md",
    "HIST": "history.md",
    "SEC": "security-and-contract.md",
}


def case(case_id: str) -> Callable[[F], F]:
    prefix = case_id.split("-")[1]
    url = f"{DOCS_URL}/{CASE_FILES[prefix]}#{case_id.lower()}"

    def decorate(fn: F) -> F:
        return allure.link(url, name=case_id)(allure.label("case_id", case_id)(fn))  # type: ignore[no-any-return]

    return decorate
