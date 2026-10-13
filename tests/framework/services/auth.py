"""Customer registration and sign-in, in business terms."""

from __future__ import annotations

from typing import Any

import allure

from framework.adapters.cardpay_api import CardpayApi
from framework.models import (
    Customer,
    OtpChallenge,
    OtpRequest,
    RegisterRequest,
    Token,
    TokenRequest,
)
from framework.services.base import expect


class AuthService:
    def __init__(self, api: CardpayApi, otp_code: str) -> None:
        self.api = api
        self.otp_code = otp_code

    @allure.step("Register a customer")
    def register(self, request: RegisterRequest | dict[str, Any]) -> Customer:
        return expect(self.api.register(request), 201, Customer)

    @allure.step("Request a one-time code for {phone}")
    def request_otp(self, phone: str) -> OtpChallenge:
        return expect(self.api.request_otp(OtpRequest(phone=phone)), 201, OtpChallenge)

    @allure.step("Exchange code for a token")
    def exchange(self, otp_id: str, code: str) -> Token:
        return expect(self.api.exchange_otp(TokenRequest(otp_id=otp_id, code=code)), 200, Token)

    @allure.step("Request a code with body {body}")
    def request_otp_raw(self, body: dict[str, Any]) -> OtpChallenge:
        return expect(self.api.request_otp(body), 201, OtpChallenge)

    @allure.step("Exchange a code with body {body}")
    def exchange_raw(self, body: dict[str, Any]) -> Token:
        return expect(self.api.exchange_otp(body), 200, Token)

    @allure.step("Sign in as {phone}")
    def login(self, phone: str) -> Token:
        challenge = self.request_otp(phone)
        return self.exchange(challenge.otp_id, self.otp_code)

    @allure.step("Get the signed-in customer")
    def me(self, token: str | None) -> Customer:
        return expect(self.api.me(token), 200, Customer)
