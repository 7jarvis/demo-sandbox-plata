"""JSON API, mounted under /api/v1. Contract: docs/openapi.yaml."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .domain import CardService
from .errors import AppError, unauthorized
from .schemas import BlockIn, IssueCardIn, OtpIn, PaymentIn, RegisterIn, TokenIn, TopUpIn, errors_to_details

M = TypeVar("M", bound=BaseModel)

MAX_BODY_BYTES = 16 * 1024
TYPES = ("top_up", "payment")
STATUSES = ("completed", "declined")


def _service(request: Request) -> CardService:
    svc: CardService = request.app.state.cards
    return svc


async def _body(request: Request, model: type[M]) -> M:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise AppError(413, "PAYLOAD_TOO_LARGE", "Request body is too large.")
    if not raw.strip():
        data: Any = {}
    else:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AppError(400, "MALFORMED_JSON", "Request body is not valid JSON.") from None
    if not isinstance(data, dict):
        raise AppError(400, "MALFORMED_JSON", "Request body must be a JSON object.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise AppError(422, "VALIDATION_ERROR", "Request validation failed.", errors_to_details(exc)) from None


def _token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthorized("Access token is missing, invalid or expired.")
    return token.strip()


async def _customer(request: Request) -> str:
    return await run_in_threadpool(_service(request).customer_by_token, _token(request))


def _idempotency_key(request: Request) -> str:
    key = request.headers.get("idempotency-key", "").strip()
    if not key:
        raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required.")
    if len(key) > 64:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            [{"field": "Idempotency-Key", "message": "must be at most 64 characters"}],
        )
    return key


def _int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not raw.isdigit() or not lo <= int(raw) <= hi:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            [{"field": name, "message": f"must be an integer between {lo} and {hi}"}],
        )
    return int(raw)


def _enum_param(request: Request, name: str, allowed: tuple[str, ...]) -> str | None:
    raw = request.query_params.get(name)
    if raw is None:
        return None
    if raw not in allowed:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            [{"field": name, "message": f"must be one of: {', '.join(allowed)}"}],
        )
    return raw


def _money_response(txn: dict[str, Any], replayed: bool) -> JSONResponse:
    if replayed:
        return JSONResponse(txn, status_code=200, headers={"Idempotent-Replayed": "true"})
    return JSONResponse(txn, status_code=201)


# ---------------------------------------------------------------- handlers
# The service is synchronous (sqlite3), so calls run in the thread pool and
# concurrent requests really do race for the database write lock.

run = run_in_threadpool


async def register(request: Request) -> Response:
    body = await _body(request, RegisterIn)
    customer = await run(_service(request).register, body.full_name, body.phone, body.email)
    return JSONResponse(customer, status_code=201)


async def request_otp(request: Request) -> Response:
    body = await _body(request, OtpIn)
    return JSONResponse(await run(_service(request).request_otp, body.phone), status_code=201)


async def exchange_otp(request: Request) -> Response:
    body = await _body(request, TokenIn)
    return JSONResponse(await run(_service(request).exchange_otp, body.otp_id, body.code))


async def me(request: Request) -> Response:
    customer = await _customer(request)
    return JSONResponse(await run(_service(request).get_customer, customer))


async def cards(request: Request) -> Response:
    customer = await _customer(request)
    svc = _service(request)
    if request.method == "GET":
        return JSONResponse({"items": await run(svc.list_cards, customer)})
    body = await _body(request, IssueCardIn)
    daily_limit: int | None = body.daily_limit  # type: ignore[assignment]  # validated to cents
    return JSONResponse(await run(svc.issue_card, customer, body.label, daily_limit), status_code=201)


async def card(request: Request) -> Response:
    customer = await _customer(request)
    return JSONResponse(await run(_service(request).get_card, customer, request.path_params["card_id"]))


async def freeze(request: Request) -> Response:
    customer = await _customer(request)
    return JSONResponse(await run(_service(request).freeze, customer, request.path_params["card_id"]))


async def unfreeze(request: Request) -> Response:
    customer = await _customer(request)
    return JSONResponse(await run(_service(request).unfreeze, customer, request.path_params["card_id"]))


async def block(request: Request) -> Response:
    customer = await _customer(request)
    body = await _body(request, BlockIn)
    card_id = request.path_params["card_id"]
    return JSONResponse(await run(_service(request).block, customer, card_id, body.reason))


async def top_up(request: Request) -> Response:
    customer = await _customer(request)
    key = _idempotency_key(request)
    body = await _body(request, TopUpIn)
    amount: int = body.amount  # type: ignore[assignment]  # validated to cents
    card_id = request.path_params["card_id"]
    txn, replayed = await run(_service(request).top_up, customer, card_id, amount, key)
    return _money_response(txn, replayed)


async def pay(request: Request) -> Response:
    customer = await _customer(request)
    key = _idempotency_key(request)
    body = await _body(request, PaymentIn)
    amount: int = body.amount  # type: ignore[assignment]  # validated to cents
    card_id = request.path_params["card_id"]
    txn, replayed = await run(_service(request).pay, customer, card_id, amount, body.merchant, key)
    return _money_response(txn, replayed)


async def transactions(request: Request) -> Response:
    customer = await _customer(request)
    page = await run(
        _service(request).history,
        customer,
        request.path_params["card_id"],
        kind=_enum_param(request, "type", TYPES),
        status=_enum_param(request, "status", STATUSES),
        limit=_int_param(request, "limit", 20, 1, 100),
        offset=_int_param(request, "offset", 0, 0, 1_000_000),
    )
    return JSONResponse(page)


routes = [
    Route("/customers", register, methods=["POST"]),
    Route("/auth/otp", request_otp, methods=["POST"]),
    Route("/auth/token", exchange_otp, methods=["POST"]),
    Route("/me", me, methods=["GET"]),
    Route("/cards", cards, methods=["GET", "POST"]),
    Route("/cards/{card_id}", card, methods=["GET"]),
    Route("/cards/{card_id}/freeze", freeze, methods=["POST"]),
    Route("/cards/{card_id}/unfreeze", unfreeze, methods=["POST"]),
    Route("/cards/{card_id}/block", block, methods=["POST"]),
    Route("/cards/{card_id}/top-ups", top_up, methods=["POST"]),
    Route("/cards/{card_id}/payments", pay, methods=["POST"]),
    Route("/cards/{card_id}/transactions", transactions, methods=["GET"]),
]
