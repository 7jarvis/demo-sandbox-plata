"""Test settings. Everything environment-specific comes from env vars, nothing
is hardcoded in tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

PRODUCTION_HOSTS = ("cardpay.example.com",)


@dataclass(frozen=True)
class Settings:
    base_url: str
    otp_code: str
    http_timeout: float
    headless: bool

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            base_url=os.getenv("BASE_URL", "http://localhost:8000").rstrip("/"),
            # The sandbox issues the same code for every login; it is configured,
            # not a secret, and comes from the same variable as the service's.
            otp_code=os.getenv("SANDBOX_OTP_CODE", "111111"),
            http_timeout=float(os.getenv("HTTP_TIMEOUT", "10")),
            headless=os.getenv("HEADED", "0") != "1",
        )
        host = urlparse(settings.base_url).hostname or ""
        if host in PRODUCTION_HOSTS:
            raise RuntimeError(f"Refusing to run tests against production host {host}")
        return settings

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v1"
