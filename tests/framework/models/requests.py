"""Request models: valid payloads by construction. Negative tests that need an
invalid payload send a plain dict instead."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(Request):
    full_name: str
    phone: str
    email: str


class OtpRequest(Request):
    phone: str


class TokenRequest(Request):
    otp_id: str
    code: str


class IssueCardRequest(Request):
    label: str | None = None
    daily_limit: str | None = None


class TopUpRequest(Request):
    amount: str


class PaymentRequest(Request):
    amount: str
    merchant: str


class BlockRequest(Request):
    reason: Literal["lost", "stolen", "fraud"]
