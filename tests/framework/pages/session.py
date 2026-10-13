"""Signing a browser context in without clicking through the login pages.

Tests about something other than sign-in start already signed in: the login
forms are posted with the context's own request API, so the session cookie
lands in the same browser context. The login UI itself is covered by its own
tests.
"""

from __future__ import annotations

import allure
from playwright.sync_api import BrowserContext


@allure.step("Sign in as {phone} (through the login forms, without the UI)")
def sign_in(context: BrowserContext, phone: str, code: str) -> None:
    context.request.post("/login", form={"phone": phone})
    resp = context.request.post("/login/code", form={"code": code})
    if not resp.url.endswith("/cards"):
        raise AssertionError(f"sign-in for {phone} did not reach /cards, ended at {resp.url} ({resp.status})")
