"""Business rules of the card sandbox.

Both the JSON API and the web UI call these functions, so a rule is written
exactly once. Functions take plain values, raise ``AppError`` on rejection and
return dicts shaped like the public contract.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from . import money
from .config import Settings
from .db import Database
from .errors import AppError, conflict, not_found, unauthorized

CARD_BIN = "537289"
BLOCK_REASONS = ("lost", "stolen", "fraud")

# Decline reasons, in the order they are checked.
CARD_BLOCKED = "CARD_BLOCKED"
CARD_FROZEN = "CARD_FROZEN"
DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"
INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"

TOP_UP_MIN = 100  # 1.00
TOP_UP_MAX = 50_000_00
PAYMENT_MIN = 1  # 0.01
PAYMENT_MAX = 100_000_00
BALANCE_MAX = 500_000_00
DAILY_LIMIT_MIN = 100_00
DAILY_LIMIT_MAX = 100_000_00
DAILY_LIMIT_DEFAULT = 20_000_00


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _luhn_check_digit(partial: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(partial)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


# ---------------------------------------------------------------- serialization


def customer_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "phone": row["phone"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def card_view(row: sqlite3.Row, spent_today_cents: int) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "pan_masked": f"{CARD_BIN[:4]} **** **** {row['last4']}",
        "expires": row["expires"],
        "status": row["status"],
        "block_reason": row["block_reason"],
        "currency": "MXN",
        "balance": money.fmt(row["balance_cents"]),
        "daily_limit": money.fmt(row["daily_limit_cents"]),
        "spent_today": money.fmt(spent_today_cents),
        "created_at": row["created_at"],
    }


def transaction_view(row: sqlite3.Row) -> dict[str, Any]:
    after = row["balance_after_cents"]
    return {
        "id": row["id"],
        "card_id": row["card_id"],
        "type": row["type"],
        "status": row["status"],
        "amount": money.fmt(row["amount_cents"]),
        "currency": "MXN",
        "merchant": row["merchant"],
        "decline_reason": row["decline_reason"],
        "balance_after": None if after is None else money.fmt(after),
        "created_at": row["created_at"],
    }


class CardService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # ---------------------------------------------------------------- customers

    def register(self, full_name: str, phone: str, email: str) -> dict[str, Any]:
        with self.db.tx() as conn:
            if conn.execute("SELECT 1 FROM customers WHERE phone = ?", (phone,)).fetchone():
                raise conflict("PHONE_ALREADY_REGISTERED", "This phone number is already registered.")
            if conn.execute("SELECT 1 FROM customers WHERE email = ?", (email,)).fetchone():
                raise conflict("EMAIL_ALREADY_REGISTERED", "This email is already registered.")
            cid = _new_id("cus")
            conn.execute(
                "INSERT INTO customers (id, full_name, phone, email, created_at) VALUES (?, ?, ?, ?, ?)",
                (cid, full_name, phone, email, _iso(_now())),
            )
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
        return customer_view(row)

    def get_customer(self, customer_id: str) -> dict[str, Any]:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if row is None:
            raise unauthorized()
        return customer_view(row)

    # ---------------------------------------------------------------- auth

    def request_otp(self, phone: str) -> dict[str, Any]:
        """Always issues a code: the answer must not reveal whether the phone is registered."""
        with self.db.tx() as conn:
            customer = conn.execute("SELECT id FROM customers WHERE phone = ?", (phone,)).fetchone()
            otp_id = _new_id("otp")
            conn.execute(
                "INSERT INTO otps (id, phone, customer_id, code, expires_at) VALUES (?, ?, ?, ?, ?)",
                (
                    otp_id,
                    phone,
                    customer["id"] if customer else None,
                    self.settings.sandbox_otp_code,
                    time.time() + self.settings.otp_ttl_seconds,
                ),
            )
        return {"otp_id": otp_id, "expires_in": self.settings.otp_ttl_seconds}

    def exchange_otp(self, otp_id: str, code: str) -> dict[str, Any]:
        """Returns a token, or raises. A failed attempt must be committed, so it is
        recorded first and the error is raised after the transaction ends."""
        error: AppError | None = None
        token: str | None = None
        with self.db.tx() as conn:
            otp = conn.execute("SELECT * FROM otps WHERE id = ?", (otp_id,)).fetchone()
            if otp is None or otp["used"]:
                error = AppError(401, "OTP_INVALID", "The code is incorrect.")
            elif otp["attempts"] >= self.settings.otp_max_attempts:
                error = AppError(429, "OTP_ATTEMPTS_EXCEEDED", "Too many attempts. Request a new code.")
            elif otp["expires_at"] < time.time():
                error = AppError(401, "OTP_EXPIRED", "The code has expired. Request a new code.")
            elif not secrets.compare_digest(otp["code"], code) or otp["customer_id"] is None:
                attempts = otp["attempts"] + 1
                conn.execute("UPDATE otps SET attempts = ? WHERE id = ?", (attempts, otp_id))
                left = self.settings.otp_max_attempts - attempts
                error = AppError(
                    401,
                    "OTP_INVALID",
                    "The code is incorrect.",
                    [{"field": "code", "message": f"{left} attempts left"}],
                )
            else:
                conn.execute("UPDATE otps SET used = 1 WHERE id = ?", (otp_id,))
                token = secrets.token_urlsafe(32)
                conn.execute(
                    "INSERT INTO tokens (token_hash, customer_id, expires_at) VALUES (?, ?, ?)",
                    (_hash(token), otp["customer_id"], time.time() + self.settings.token_ttl_seconds),
                )
        if error is not None:
            raise error
        assert token is not None
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": self.settings.token_ttl_seconds,
        }

    def customer_by_token(self, token: str) -> str:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT customer_id, expires_at FROM tokens WHERE token_hash = ?", (_hash(token),)
            ).fetchone()
        if row is None or row["expires_at"] < time.time():
            raise unauthorized("Access token is missing, invalid or expired.")
        return str(row["customer_id"])

    def revoke_token(self, token: str) -> None:
        with self.db.tx() as conn:
            conn.execute("DELETE FROM tokens WHERE token_hash = ?", (_hash(token),))

    # ---------------------------------------------------------------- cards

    @staticmethod
    def _spent_today(conn: sqlite3.Connection, card_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
            "WHERE card_id = ? AND type = 'payment' AND status = 'completed' AND created_day = ?",
            (card_id, _now().date().isoformat()),
        ).fetchone()
        return int(row[0])

    @staticmethod
    def _card_row(conn: sqlite3.Connection, customer_id: str, card_id: str) -> sqlite3.Row:
        # Another customer's card is reported exactly like a missing one.
        row = conn.execute(
            "SELECT * FROM cards WHERE id = ? AND customer_id = ?", (card_id, customer_id)
        ).fetchone()
        if row is None:
            raise not_found("CARD_NOT_FOUND", "Card not found.")
        return row

    def _view(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        return card_view(row, self._spent_today(conn, row["id"]))

    def issue_card(self, customer_id: str, label: str | None, daily_limit_cents: int | None) -> dict[str, Any]:
        limit = DAILY_LIMIT_DEFAULT if daily_limit_cents is None else daily_limit_cents
        with self.db.tx() as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM cards WHERE customer_id = ? AND status != 'blocked'", (customer_id,)
            ).fetchone()
            if count >= self.settings.max_cards_per_customer:
                raise conflict(
                    "CARD_LIMIT_REACHED",
                    f"A customer can hold at most {self.settings.max_cards_per_customer} cards "
                    "that are not blocked.",
                )
            body = CARD_BIN + "".join(secrets.choice("0123456789") for _ in range(9))
            pan = body + _luhn_check_digit(body)
            now = _now()
            expires = f"{now.month:02d}/{(now.year + 4) % 100:02d}"
            card_id = _new_id("card")
            conn.execute(
                "INSERT INTO cards (id, customer_id, label, last4, expires, status, daily_limit_cents, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (card_id, customer_id, label, pan[-4:], expires, limit, _iso(now)),
            )
            row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
            return self._view(conn, row)

    def list_cards(self, customer_id: str) -> list[dict[str, Any]]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM cards WHERE customer_id = ? ORDER BY seq", (customer_id,)
            ).fetchall()
            return [self._view(conn, r) for r in rows]

    def get_card(self, customer_id: str, card_id: str) -> dict[str, Any]:
        with self.db.read() as conn:
            return self._view(conn, self._card_row(conn, customer_id, card_id))

    def freeze(self, customer_id: str, card_id: str) -> dict[str, Any]:
        with self.db.tx() as conn:
            card = self._card_row(conn, customer_id, card_id)
            if card["status"] == "blocked":
                raise conflict(CARD_BLOCKED, "The card is blocked permanently.")
            if card["status"] == "frozen":
                raise conflict("CARD_ALREADY_FROZEN", "The card is already frozen.")
            conn.execute("UPDATE cards SET status = 'frozen' WHERE id = ?", (card_id,))
            return self._view(conn, self._card_row(conn, customer_id, card_id))

    def unfreeze(self, customer_id: str, card_id: str) -> dict[str, Any]:
        with self.db.tx() as conn:
            card = self._card_row(conn, customer_id, card_id)
            if card["status"] == "blocked":
                raise conflict(CARD_BLOCKED, "The card is blocked permanently.")
            if card["status"] != "frozen":
                raise conflict("CARD_NOT_FROZEN", "The card is not frozen.")
            conn.execute("UPDATE cards SET status = 'active' WHERE id = ?", (card_id,))
            return self._view(conn, self._card_row(conn, customer_id, card_id))

    def block(self, customer_id: str, card_id: str, reason: str) -> dict[str, Any]:
        with self.db.tx() as conn:
            card = self._card_row(conn, customer_id, card_id)
            if card["status"] == "blocked":
                raise conflict(CARD_BLOCKED, "The card is already blocked.")
            conn.execute(
                "UPDATE cards SET status = 'blocked', block_reason = ? WHERE id = ?", (reason, card_id)
            )
            return self._view(conn, self._card_row(conn, customer_id, card_id))

    # ---------------------------------------------------------------- money

    def _replay(
        self, conn: sqlite3.Connection, customer_id: str, key: str, request_hash: str
    ) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT request_hash, transaction_id FROM idempotency_keys WHERE customer_id = ? AND key = ?",
            (customer_id, key),
        ).fetchone()
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise AppError(
                422,
                "IDEMPOTENCY_KEY_REUSED",
                "This idempotency key was already used for a different request.",
            )
        txn = conn.execute("SELECT * FROM transactions WHERE id = ?", (row["transaction_id"],)).fetchone()
        return transaction_view(txn)

    @staticmethod
    def _request_hash(operation: str, card_id: str, payload: dict[str, Any]) -> str:
        return _hash(json.dumps({"op": operation, "card": card_id, **payload}, sort_keys=True))

    def _record(
        self,
        conn: sqlite3.Connection,
        customer_id: str,
        key: str,
        request_hash: str,
        card_id: str,
        kind: str,
        status: str,
        amount_cents: int,
        merchant: str | None,
        decline_reason: str | None,
        balance_after: int | None,
    ) -> dict[str, Any]:
        now = _now()
        txn_id = _new_id("txn")
        conn.execute(
            "INSERT INTO transactions (id, card_id, type, status, amount_cents, merchant, decline_reason, "
            "balance_after_cents, created_at, created_day) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                txn_id,
                card_id,
                kind,
                status,
                amount_cents,
                merchant,
                decline_reason,
                balance_after,
                _iso(now),
                now.date().isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO idempotency_keys (customer_id, key, request_hash, transaction_id) VALUES (?, ?, ?, ?)",
            (customer_id, key, request_hash, txn_id),
        )
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        return transaction_view(row)

    def top_up(
        self, customer_id: str, card_id: str, amount_cents: int, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        """Returns (transaction, replayed)."""
        request_hash = self._request_hash("top_up", card_id, {"amount": amount_cents})
        with self.db.tx() as conn:
            card = self._card_row(conn, customer_id, card_id)
            replayed = self._replay(conn, customer_id, idempotency_key, request_hash)
            if replayed is not None:
                return replayed, True
            if card["status"] == "blocked":
                raise conflict(CARD_BLOCKED, "A blocked card cannot be topped up.")
            new_balance = card["balance_cents"] + amount_cents
            if new_balance > BALANCE_MAX:
                raise conflict(
                    "BALANCE_LIMIT_EXCEEDED",
                    f"The card balance cannot exceed {money.fmt(BALANCE_MAX)} MXN.",
                )
            conn.execute("UPDATE cards SET balance_cents = ? WHERE id = ?", (new_balance, card_id))
            txn = self._record(
                conn, customer_id, idempotency_key, request_hash, card_id,
                "top_up", "completed", amount_cents, None, None, new_balance,
            )  # fmt: skip
            return txn, False

    def pay(
        self, customer_id: str, card_id: str, amount_cents: int, merchant: str, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        """A card purchase. A decline is a normal outcome: it is recorded in the
        history with a reason and does not change the balance."""
        request_hash = self._request_hash("payment", card_id, {"amount": amount_cents, "merchant": merchant})
        with self.db.tx() as conn:
            card = self._card_row(conn, customer_id, card_id)
            replayed = self._replay(conn, customer_id, idempotency_key, request_hash)
            if replayed is not None:
                return replayed, True

            decline: str | None = None
            if card["status"] == "blocked":
                decline = CARD_BLOCKED
            elif card["status"] == "frozen":
                decline = CARD_FROZEN
            elif self._spent_today(conn, card_id) + amount_cents > card["daily_limit_cents"]:
                decline = DAILY_LIMIT_EXCEEDED
            elif amount_cents > card["balance_cents"]:
                decline = INSUFFICIENT_FUNDS

            if decline is not None:
                txn = self._record(
                    conn, customer_id, idempotency_key, request_hash, card_id,
                    "payment", "declined", amount_cents, merchant, decline, None,
                )  # fmt: skip
                return txn, False

            new_balance = card["balance_cents"] - amount_cents
            conn.execute("UPDATE cards SET balance_cents = ? WHERE id = ?", (new_balance, card_id))
            txn = self._record(
                conn, customer_id, idempotency_key, request_hash, card_id,
                "payment", "completed", amount_cents, merchant, None, new_balance,
            )  # fmt: skip
            return txn, False

    def history(
        self,
        customer_id: str,
        card_id: str,
        kind: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        where = ["card_id = ?"]
        args: list[Any] = [card_id]
        if kind:
            where.append("type = ?")
            args.append(kind)
        if status:
            where.append("status = ?")
            args.append(status)
        clause = " AND ".join(where)
        with self.db.read() as conn:
            self._card_row(conn, customer_id, card_id)
            (total,) = conn.execute(f"SELECT COUNT(*) FROM transactions WHERE {clause}", args).fetchone()
            rows = conn.execute(
                f"SELECT * FROM transactions WHERE {clause} ORDER BY seq DESC LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return {
            "items": [transaction_view(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
