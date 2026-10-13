"""Turning HTTP responses into results.

- the expected success status -> a validated response model;
- a documented business rejection (4xx with the error contract) -> ``ApiError``;
- anything else (5xx, an unexpected status, a body that breaks the contract)
  -> ``UnexpectedResponse``, which is an AssertionError.

So a test that expects a rejection catches ``ApiError`` and a server bug can
never pass for an expected rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from framework.http_client import HttpResponse
from framework.models import ErrorResponse

M = TypeVar("M", bound=BaseModel)

BUSINESS_REJECTIONS = frozenset({400, 401, 404, 409, 413, 422, 429})


class UnexpectedResponse(AssertionError):
    def __init__(self, resp: HttpResponse, reason: str) -> None:
        super().__init__(
            f"{reason}: {resp.method} {resp.url} -> {resp.status} "
            f"(X-Request-Id {resp.request_id})\n{resp.text[:2000]}"
        )
        self.response = resp


@dataclass
class ApiError(Exception):
    status: int
    code: str
    message: str
    fields: dict[str, str]
    response: HttpResponse

    def __str__(self) -> str:
        return f"{self.status} {self.code}: {self.message} {self.fields or ''}".strip()


def parse(resp: HttpResponse, model: type[M]) -> M:
    try:
        return model.model_validate_json(resp.body)
    except ValidationError as exc:
        raise UnexpectedResponse(resp, f"response breaks the {model.__name__} contract\n{exc}") from None


def expect(resp: HttpResponse, status: int | tuple[int, ...], model: type[M]) -> M:
    expected = (status,) if isinstance(status, int) else status
    if resp.status in expected:
        return parse(resp, model)
    if resp.status in BUSINESS_REJECTIONS:
        error = parse(resp, ErrorResponse).error
        raise ApiError(
            status=resp.status,
            code=error.code,
            message=error.message,
            fields={d.field: d.message for d in error.details or []},
            response=resp,
        )
    raise UnexpectedResponse(resp, f"expected {expected}")
