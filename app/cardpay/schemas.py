"""Request bodies. Unknown fields and wrong JSON types are rejected, money must
be a string with exactly two decimals."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints, ValidationError

from . import domain, money

PHONE_RE = re.compile(r"^\+52\d{10}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")


def _money(lo: int, hi: int):  # type: ignore[no-untyped-def]
    def check(value: str) -> int:
        if not money.MONEY_RE.match(value):
            raise ValueError("must be a decimal string with exactly two decimals, e.g. '150.00'")
        cents = money.parse(value)
        if not lo <= cents <= hi:
            raise ValueError(f"must be between {money.fmt(lo)} and {money.fmt(hi)}")
        return cents

    return check


def _phone(value: str) -> str:
    if not PHONE_RE.match(value):
        raise ValueError("must be +52 followed by 10 digits")
    return value


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValueError("must be a valid email address")
    return value


def _full_name(value: str) -> str:
    value = " ".join(value.split())
    if not 2 <= len(value) <= 100:
        raise ValueError("must be 2 to 100 characters long")
    if not NAME_RE.match(value):
        raise ValueError("may contain only letters, spaces, hyphens and apostrophes")
    return value


def _label(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not 1 <= len(value) <= 30:
        raise ValueError("must be 1 to 30 characters long")
    return value


def _merchant(value: str) -> str:
    value = value.strip()
    if not 2 <= len(value) <= 60:
        raise ValueError("must be 2 to 60 characters long")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Phone = Annotated[str, AfterValidator(_phone)]


class RegisterIn(Strict):
    full_name: Annotated[str, AfterValidator(_full_name)]
    phone: Phone
    email: Annotated[str, AfterValidator(_email)]


class OtpIn(Strict):
    phone: Phone


class TokenIn(Strict):
    otp_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class IssueCardIn(Strict):
    label: Annotated[str | None, AfterValidator(_label)] = None
    daily_limit: Annotated[str, AfterValidator(_money(domain.DAILY_LIMIT_MIN, domain.DAILY_LIMIT_MAX))] | None = None


class TopUpIn(Strict):
    amount: Annotated[str, AfterValidator(_money(domain.TOP_UP_MIN, domain.TOP_UP_MAX))]


class PaymentIn(Strict):
    amount: Annotated[str, AfterValidator(_money(domain.PAYMENT_MIN, domain.PAYMENT_MAX))]
    merchant: Annotated[str, AfterValidator(_merchant)]


class BlockIn(Strict):
    reason: Literal["lost", "stolen", "fraud"]


def errors_to_details(exc: ValidationError) -> list[dict[str, str]]:
    details = []
    for err in exc.errors(include_url=False):
        field = ".".join(str(p) for p in err["loc"]) or "body"
        msg = err["msg"]
        if err["type"] == "extra_forbidden":
            msg = "unknown field"
        elif err["type"] == "missing":
            msg = "field required"
        elif msg.startswith("Value error, "):
            msg = msg.removeprefix("Value error, ")
        details.append({"field": field, "message": msg})
    return details
