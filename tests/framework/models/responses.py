"""Response models: the contract from docs/openapi.yaml, checked on every call.

Parsing fails on an unknown field, a missing field, a wrong JSON type, a value
in the wrong format or a broken invariant, so a contract break surfaces as a
validation error at the point of the call, not as a confusing assert later.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Money = Annotated[str, StringConstraints(pattern=r"^(0|[1-9]\d{0,8})\.\d{2}$")]
Timestamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")]
Phone = Annotated[str, StringConstraints(pattern=r"^\+52\d{10}$")]
CustomerId = Annotated[str, StringConstraints(pattern=r"^cus_[0-9a-f]{24}$")]
CardId = Annotated[str, StringConstraints(pattern=r"^card_[0-9a-f]{24}$")]
TransactionId = Annotated[str, StringConstraints(pattern=r"^txn_[0-9a-f]{24}$")]
OtpId = Annotated[str, StringConstraints(pattern=r"^otp_[0-9a-f]{24}$")]

CardStatus = Literal["active", "frozen", "blocked"]
BlockReason = Literal["lost", "stolen", "fraud"]
TransactionType = Literal["top_up", "payment"]
TransactionStatus = Literal["completed", "declined"]
DeclineReason = Literal["CARD_BLOCKED", "CARD_FROZEN", "DAILY_LIMIT_EXCEEDED", "INSUFFICIENT_FUNDS"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Customer(Contract):
    id: CustomerId
    full_name: str
    phone: Phone
    email: str
    created_at: Timestamp


class OtpChallenge(Contract):
    otp_id: OtpId
    expires_in: int


class Token(Contract):
    access_token: Annotated[str, StringConstraints(min_length=20)]
    token_type: Literal["Bearer"]
    expires_in: int


class Card(Contract):
    id: CardId
    label: str | None
    pan_masked: Annotated[str, StringConstraints(pattern=r"^\d{4} \*{4} \*{4} \d{4}$")]
    expires: Annotated[str, StringConstraints(pattern=r"^(0[1-9]|1[0-2])/\d{2}$")]
    status: CardStatus
    block_reason: BlockReason | None
    currency: Literal["MXN"]
    balance: Money
    daily_limit: Money
    spent_today: Money
    created_at: Timestamp

    @model_validator(mode="after")
    def _block_reason_only_when_blocked(self) -> Self:
        if (self.status == "blocked") != (self.block_reason is not None):
            raise ValueError(f"block_reason={self.block_reason!r} contradicts status={self.status!r}")
        return self

    @property
    def last4(self) -> str:
        return self.pan_masked[-4:]


class CardList(Contract):
    items: list[Card]


class Transaction(Contract):
    id: TransactionId
    card_id: CardId
    type: TransactionType
    status: TransactionStatus
    amount: Money
    currency: Literal["MXN"]
    merchant: str | None
    decline_reason: DeclineReason | None
    balance_after: Money | None
    created_at: Timestamp

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.type == "top_up" and (self.status != "completed" or self.merchant is not None):
            raise ValueError("a top-up is always completed and has no merchant")
        if self.type == "payment" and not self.merchant:
            raise ValueError("a payment has a merchant")
        if self.status == "completed" and (self.decline_reason is not None or self.balance_after is None):
            raise ValueError("completed: balance_after is set and decline_reason is null")
        if self.status == "declined" and (self.decline_reason is None or self.balance_after is not None):
            raise ValueError("declined: decline_reason is set and balance_after is null")
        return self


class TransactionPage(Contract):
    items: list[Transaction]
    total: int
    limit: int
    offset: int

    @model_validator(mode="after")
    def _page_is_consistent(self) -> Self:
        if self.total < 0 or len(self.items) > self.limit:
            raise ValueError("page has more items than the limit or a negative total")
        return self


class FieldError(Contract):
    field: str
    message: str


class ErrorDetail(Contract):
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z_]+$")]
    message: Annotated[str, StringConstraints(min_length=1)]
    details: list[FieldError] | None


class ErrorResponse(Contract):
    error: ErrorDetail


class Health(Contract):
    status: Literal["ok"]
