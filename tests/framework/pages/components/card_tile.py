from __future__ import annotations

from playwright.sync_api import Locator


class CardTile:
    """A card on the 'My cards' page."""

    def __init__(self, root: Locator) -> None:
        self.root = root

    @property
    def status(self) -> Locator:
        return self.root.get_by_test_id("card-status")

    @property
    def balance(self) -> Locator:
        return self.root.get_by_test_id("card-balance")

    @property
    def pan(self) -> Locator:
        return self.root.get_by_test_id("card-pan")
