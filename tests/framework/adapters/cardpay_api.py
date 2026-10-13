"""Adapter: knows the API surface (method, path, headers, serialization) and
nothing about what a response means. Returns raw ``HttpResponse``.

Payloads are either request models (the normal case) or plain dicts, which
negative tests use to send what a model would never allow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from framework.http_client import HttpClient, HttpResponse

Payload = BaseModel | dict[str, Any]


def _serialize(payload: Payload | None) -> Any:
    if payload is None:
        return None
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json", exclude_none=True)
    return payload


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


class CardpayApi:
    def __init__(self, http: HttpClient) -> None:
        self.http = http

    # auth and customers

    def register(self, payload: Payload) -> HttpResponse:
        return self.http.request("POST", "/customers", json_body=_serialize(payload))

    def request_otp(self, payload: Payload) -> HttpResponse:
        return self.http.request("POST", "/auth/otp", json_body=_serialize(payload))

    def exchange_otp(self, payload: Payload) -> HttpResponse:
        return self.http.request("POST", "/auth/token", json_body=_serialize(payload))

    def me(self, token: str | None) -> HttpResponse:
        return self.http.request("GET", "/me", headers=_auth(token))

    # cards

    def list_cards(self, token: str | None) -> HttpResponse:
        return self.http.request("GET", "/cards", headers=_auth(token))

    def issue_card(self, token: str | None, payload: Payload | None) -> HttpResponse:
        return self.http.request("POST", "/cards", json_body=_serialize(payload) or {}, headers=_auth(token))

    def get_card(self, token: str | None, card_id: str) -> HttpResponse:
        return self.http.request("GET", f"/cards/{card_id}", headers=_auth(token))

    def freeze(self, token: str | None, card_id: str) -> HttpResponse:
        return self.http.request("POST", f"/cards/{card_id}/freeze", headers=_auth(token))

    def unfreeze(self, token: str | None, card_id: str) -> HttpResponse:
        return self.http.request("POST", f"/cards/{card_id}/unfreeze", headers=_auth(token))

    def block(self, token: str | None, card_id: str, payload: Payload) -> HttpResponse:
        return self.http.request("POST", f"/cards/{card_id}/block", json_body=_serialize(payload), headers=_auth(token))

    # money

    def top_up(self, token: str | None, card_id: str, payload: Payload, idempotency_key: str | None) -> HttpResponse:
        headers = _auth(token)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return self.http.request("POST", f"/cards/{card_id}/top-ups", json_body=_serialize(payload), headers=headers)

    def pay(self, token: str | None, card_id: str, payload: Payload, idempotency_key: str | None) -> HttpResponse:
        headers = _auth(token)
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return self.http.request("POST", f"/cards/{card_id}/payments", json_body=_serialize(payload), headers=headers)

    def transactions(self, token: str | None, card_id: str, params: dict[str, Any] | None = None) -> HttpResponse:
        return self.http.request("GET", f"/cards/{card_id}/transactions", headers=_auth(token), params=params)

    # escape hatch for contract tests: an arbitrary body to an arbitrary endpoint

    def send_raw(
        self, method: str, path: str, token: str | None, body: bytes | str, extra_headers: dict[str, str] | None = None
    ) -> HttpResponse:
        headers = {**_auth(token), "Content-Type": "application/json", **(extra_headers or {})}
        return self.http.request(method, path, raw_body=body, headers=headers)
