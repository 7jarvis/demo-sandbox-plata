"""Server-rendered web UI. It calls the same domain service as the API.

Money forms carry a one-time idempotency key rendered into the page, so a
double click or a browser resubmit cannot charge or credit twice.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool as run
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from .domain import CardService
from .errors import AppError
from .schemas import BlockIn, IssueCardIn, OtpIn, PaymentIn, RegisterIn, TokenIn, TopUpIn, errors_to_details

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

DECLINE_TEXT = {
    "INSUFFICIENT_FUNDS": "Insufficient funds",
    "CARD_FROZEN": "Card is frozen",
    "CARD_BLOCKED": "Card is blocked",
    "DAILY_LIMIT_EXCEEDED": "Daily spending limit exceeded",
}
templates.env.globals["decline_text"] = lambda code: DECLINE_TEXT.get(code, code)

AMOUNT_INPUT = re.compile(r"^\s*(\d{1,9})(?:[.,](\d{1,2}))?\s*$")


def _svc(request: Request) -> CardService:
    svc: CardService = request.app.state.cards
    return svc


def _normalize_amount(raw: str) -> str:
    """'500' -> '500.00', '12,5' -> '12.50'. Anything else is passed through and fails validation."""
    m = AMOUNT_INPUT.match(raw or "")
    if not m:
        return (raw or "").strip()
    return f"{int(m.group(1))}.{(m.group(2) or '0').ljust(2, '0')}"


def _flash(request: Request, kind: str, text: str) -> None:
    request.session["flash"] = {"kind": kind, "text": text}


def _render(request: Request, name: str, status: int = 200, **ctx: Any) -> Response:
    ctx.setdefault("flash", request.session.pop("flash", None))
    ctx.setdefault("errors", {})
    ctx.setdefault("form", {})
    return templates.TemplateResponse(request, name, ctx, status_code=status)


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _validate(model: type[BaseModel], data: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    try:
        return model.model_validate(data), {}
    except ValidationError as exc:
        return None, {d["field"]: d["message"] for d in errors_to_details(exc)}


async def _current(request: Request) -> tuple[str, dict[str, Any]] | None:
    token = request.session.get("token")
    if not token:
        return None
    try:
        customer_id = await run(_svc(request).customer_by_token, token)
        return customer_id, await run(_svc(request).get_customer, customer_id)
    except AppError:
        request.session.pop("token", None)
        return None


async def _form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


# ---------------------------------------------------------------- pages


async def home(request: Request) -> Response:
    return _redirect("/cards" if await _current(request) else "/login")


async def register(request: Request) -> Response:
    if request.method == "GET":
        return _render(request, "register.html")
    form = await _form(request)
    data = {k: form.get(k, "") for k in ("full_name", "phone", "email")}
    body, errors = _validate(RegisterIn, data)
    if not errors:
        try:
            await run(_svc(request).register, body.full_name, body.phone, body.email)
        except AppError as exc:
            field = "phone" if exc.code == "PHONE_ALREADY_REGISTERED" else "email"
            errors = {field: exc.message}
    if errors:
        return _render(request, "register.html", 422, errors=errors, form=data)
    _flash(request, "success", "Registration complete. Sign in with your phone number.")
    return _redirect(f"/login?phone={body.phone.replace('+', '%2B')}")


async def login(request: Request) -> Response:
    if request.method == "GET":
        return _render(request, "login.html", form={"phone": request.query_params.get("phone", "")})
    form = await _form(request)
    data = {"phone": form.get("phone", "").strip()}
    body, errors = _validate(OtpIn, data)
    if errors:
        errors = {"phone": "Enter the phone number as +52 followed by 10 digits."}
        return _render(request, "login.html", 422, errors=errors, form=data)
    otp = await run(_svc(request).request_otp, body.phone)
    request.session["otp"] = {"id": otp["otp_id"], "phone": body.phone}
    return _redirect("/login/code")


async def login_code(request: Request) -> Response:
    otp = request.session.get("otp")
    if not otp:
        return _redirect("/login")
    if request.method == "GET":
        return _render(request, "login_code.html", phone=otp["phone"])
    form = await _form(request)
    body, errors = _validate(TokenIn, {"otp_id": otp["id"], "code": form.get("code", "").strip()})
    if errors:
        return _render(request, "login_code.html", 422, phone=otp["phone"], errors={"code": "Enter the 6-digit code."})
    try:
        token = await run(_svc(request).exchange_otp, body.otp_id, body.code)
    except AppError as exc:
        if exc.code == "OTP_INVALID" and exc.details:
            message = f"Incorrect code. {exc.details[0]['message'].capitalize()}."
        else:
            message = exc.message
        return _render(request, "login_code.html", 401, phone=otp["phone"], errors={"code": message})
    request.session.pop("otp", None)
    request.session["token"] = token["access_token"]
    return _redirect("/cards")


async def logout(request: Request) -> Response:
    token = request.session.get("token")
    if token:
        await run(_svc(request).revoke_token, token)
    request.session.clear()
    return _redirect("/login")


async def cards(request: Request) -> Response:
    current = await _current(request)
    if current is None:
        return _redirect("/login")
    customer_id, customer = current
    items = await run(_svc(request).list_cards, customer_id)
    return _render(request, "cards.html", customer=customer, cards=items)


async def new_card(request: Request) -> Response:
    current = await _current(request)
    if current is None:
        return _redirect("/login")
    customer_id, customer = current
    if request.method == "GET":
        return _render(request, "card_new.html", customer=customer, form={"daily_limit": "20000.00"})
    form = await _form(request)
    data: dict[str, Any] = {
        "label": form.get("label", "").strip() or None,
        "daily_limit": _normalize_amount(form.get("daily_limit", "")) or None,
    }
    body, errors = _validate(IssueCardIn, data)
    if not errors:
        try:
            card = await run(_svc(request).issue_card, customer_id, body.label, body.daily_limit)
        except AppError as exc:
            errors = {"form": exc.message}
    if errors:
        shown = {k: v or "" for k, v in data.items()}
        return _render(request, "card_new.html", 422, customer=customer, errors=errors, form=shown)
    _flash(request, "success", "Card issued.")
    return _redirect(f"/cards/{card['id']}")


async def card_detail(request: Request) -> Response:
    current = await _current(request)
    if current is None:
        return _redirect("/login")
    customer_id, customer = current
    card_id = request.path_params["card_id"]
    kind = request.query_params.get("type")
    kind = kind if kind in ("top_up", "payment") else None
    try:
        card = await run(_svc(request).get_card, customer_id, card_id)
        history = await run(_svc(request).history, customer_id, card_id, kind, None, 50, 0)
    except AppError:
        return _render(request, "not_found.html", 404, customer=customer)
    errors = request.session.pop("errors", {})
    form = request.session.pop("form", {})
    return _render(
        request,
        "card.html",
        customer=customer,
        card=card,
        history=history,
        kind=kind,
        errors=errors,
        form=form,
        key=uuid.uuid4().hex,
    )


async def _card_action(request: Request, action: str) -> Response:
    current = await _current(request)
    if current is None:
        return _redirect("/login")
    customer_id, _ = current
    card_id = request.path_params["card_id"]
    back = f"/cards/{card_id}"
    form = await _form(request)
    svc = _svc(request)
    key = form.get("idempotency_key") or uuid.uuid4().hex

    try:
        if action == "top-up":
            data = {"amount": _normalize_amount(form.get("amount", ""))}
            body, errors = _validate(TopUpIn, data)
            if errors:
                request.session["errors"] = {f"topup_{k}": v for k, v in errors.items()}
                request.session["form"] = {"topup_amount": form.get("amount", "")}
                return _redirect(back)
            txn, replayed = await run(svc.top_up, customer_id, card_id, body.amount, key)
            if replayed:
                _flash(request, "info", "This top-up was already processed.")
            else:
                _flash(request, "success", f"Card topped up with {txn['amount']} MXN.")
        elif action == "pay":
            data = {"amount": _normalize_amount(form.get("amount", "")), "merchant": form.get("merchant", "")}
            body, errors = _validate(PaymentIn, data)
            if errors:
                request.session["errors"] = {f"pay_{k}": v for k, v in errors.items()}
                request.session["form"] = {"pay_amount": form.get("amount", ""), "pay_merchant": data["merchant"]}
                return _redirect(back)
            txn, replayed = await run(svc.pay, customer_id, card_id, body.amount, body.merchant, key)
            if replayed:
                _flash(request, "info", "This payment was already processed.")
            elif txn["status"] == "completed":
                _flash(request, "success", f"Paid {txn['amount']} MXN to {txn['merchant']}.")
            else:
                _flash(request, "error", f"Payment declined: {DECLINE_TEXT[txn['decline_reason']]}.")
        elif action == "freeze":
            await run(svc.freeze, customer_id, card_id)
            _flash(request, "success", "Card frozen. Payments are paused until you unfreeze it.")
        elif action == "unfreeze":
            await run(svc.unfreeze, customer_id, card_id)
            _flash(request, "success", "Card unfrozen.")
        elif action == "block":
            body, errors = _validate(BlockIn, {"reason": form.get("reason", "")})
            if errors:
                _flash(request, "error", "Choose why you are blocking the card.")
                return _redirect(back)
            await run(svc.block, customer_id, card_id, body.reason)
            _flash(request, "success", "Card blocked permanently.")
    except AppError as exc:
        if exc.status == 404:
            return _redirect("/cards")
        _flash(request, "error", exc.message)
    return _redirect(back)


async def top_up(request: Request) -> Response:
    return await _card_action(request, "top-up")


async def pay(request: Request) -> Response:
    return await _card_action(request, "pay")


async def freeze(request: Request) -> Response:
    return await _card_action(request, "freeze")


async def unfreeze(request: Request) -> Response:
    return await _card_action(request, "unfreeze")


async def block(request: Request) -> Response:
    return await _card_action(request, "block")


routes = [
    Route("/", home, methods=["GET"]),
    Route("/register", register, methods=["GET", "POST"]),
    Route("/login", login, methods=["GET", "POST"]),
    Route("/login/code", login_code, methods=["GET", "POST"]),
    Route("/logout", logout, methods=["POST"]),
    Route("/cards", cards, methods=["GET"]),
    Route("/cards/new", new_card, methods=["GET", "POST"]),
    Route("/cards/{card_id}", card_detail, methods=["GET"]),
    Route("/cards/{card_id}/top-up", top_up, methods=["POST"]),
    Route("/cards/{card_id}/pay", pay, methods=["POST"]),
    Route("/cards/{card_id}/freeze", freeze, methods=["POST"]),
    Route("/cards/{card_id}/unfreeze", unfreeze, methods=["POST"]),
    Route("/cards/{card_id}/block", block, methods=["POST"]),
]
