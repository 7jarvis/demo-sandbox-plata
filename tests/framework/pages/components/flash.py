from __future__ import annotations

from playwright.sync_api import Locator, Page


class Flash:
    """One-shot message after an action: role=status for success/info, role=alert for errors."""

    def __init__(self, page: Page) -> None:
        self.page = page

    @property
    def success(self) -> Locator:
        return self.page.get_by_role("status")

    @property
    def error(self) -> Locator:
        return self.page.get_by_role("alert")
