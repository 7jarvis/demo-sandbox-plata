"""Runtime settings, read once from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str
    session_secret: str
    sandbox_otp_code: str
    otp_ttl_seconds: int
    otp_max_attempts: int
    token_ttl_seconds: int
    max_cards_per_customer: int
    currency: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_path=os.getenv("DATABASE_PATH", "data/cardpay.db"),
            session_secret=os.getenv("SESSION_SECRET", "local-dev-session-secret"),
            # The sandbox has no SMS gateway: every one-time code equals this value.
            sandbox_otp_code=os.getenv("SANDBOX_OTP_CODE", "111111"),
            otp_ttl_seconds=int(os.getenv("OTP_TTL_SECONDS", "300")),
            otp_max_attempts=int(os.getenv("OTP_MAX_ATTEMPTS", "3")),
            token_ttl_seconds=int(os.getenv("TOKEN_TTL_SECONDS", "3600")),
            max_cards_per_customer=int(os.getenv("MAX_CARDS_PER_CUSTOMER", "3")),
            currency="MXN",
        )
