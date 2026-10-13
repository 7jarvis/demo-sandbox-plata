-- SQLite schema. Money columns are integer cents.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id          TEXT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

-- One-time codes. A code is issued for any phone (registered or not) so the
-- endpoint does not reveal which phones are customers.
CREATE TABLE IF NOT EXISTS otps (
    id           TEXT PRIMARY KEY,
    phone        TEXT NOT NULL,
    customer_id  TEXT REFERENCES customers(id),
    code         TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    used         INTEGER NOT NULL DEFAULT 0,
    expires_at   REAL NOT NULL
);

-- Only a hash of the access token is stored.
CREATE TABLE IF NOT EXISTS tokens (
    token_hash   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(id),
    expires_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    seq                INTEGER PRIMARY KEY AUTOINCREMENT,
    id                 TEXT NOT NULL UNIQUE,
    customer_id        TEXT NOT NULL REFERENCES customers(id),
    label              TEXT,
    last4              TEXT NOT NULL,
    expires            TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN ('active', 'frozen', 'blocked')),
    block_reason       TEXT CHECK (block_reason IN ('lost', 'stolen', 'fraud')),
    balance_cents      INTEGER NOT NULL DEFAULT 0 CHECK (balance_cents >= 0),
    daily_limit_cents  INTEGER NOT NULL,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_customer ON cards(customer_id);

CREATE TABLE IF NOT EXISTS transactions (
    seq                  INTEGER PRIMARY KEY AUTOINCREMENT,
    id                   TEXT NOT NULL UNIQUE,
    card_id              TEXT NOT NULL REFERENCES cards(id),
    type                 TEXT NOT NULL CHECK (type IN ('top_up', 'payment')),
    status               TEXT NOT NULL CHECK (status IN ('completed', 'declined')),
    amount_cents         INTEGER NOT NULL CHECK (amount_cents > 0),
    merchant             TEXT,
    decline_reason       TEXT,
    balance_after_cents  INTEGER,
    created_at           TEXT NOT NULL,
    created_day          TEXT NOT NULL  -- UTC date, for the daily spending limit
);
CREATE INDEX IF NOT EXISTS transactions_card ON transactions(card_id, seq);

-- Money-moving requests are idempotent per customer and key.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    customer_id     TEXT NOT NULL REFERENCES customers(id),
    key             TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    transaction_id  TEXT NOT NULL REFERENCES transactions(id),
    PRIMARY KEY (customer_id, key)
);
