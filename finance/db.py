"""SQLite persistence layer.

A single `transactions` table holds every normalized row. The primary key is a
sha256 of (account|date|description|amount), which gives dedupe for free when a
statement is re-imported or overlaps a previously imported one.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime

import pandas as pd

from . import config

DB_PATH = os.getenv("FINANCE_DB_PATH", "data/finance.db")  # set from app.py / tests or default


def set_db_path(path: str) -> None:
    global DB_PATH
    DB_PATH = path


def connect() -> sqlite3.Connection:
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = os.getenv("FINANCE_DB_PATH", "data/finance.db")
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id            TEXT PRIMARY KEY,
    account       TEXT NOT NULL,
    txn_date      TEXT NOT NULL,          -- ISO yyyy-mm-dd
    description   TEXT,
    amount        REAL NOT NULL,          -- +credit / -debit (rupees)
    amount_paise  INTEGER,                -- exact integer paise (+credit / -debit)
    balance       REAL,
    balance_paise INTEGER,
    classification TEXT,
    category      TEXT,
    counterparty  TEXT,
    matched_with  TEXT,
    match_status  TEXT,                   -- 'matched' | 'unmatched'
    flags         TEXT,                   -- comma-separated: recurring, p2p
    raw           TEXT,                   -- original statement row (JSON)
    source_file   TEXT,
    imported_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_txn_date        ON transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_class           ON transactions(classification);
CREATE INDEX IF NOT EXISTS idx_txn_category    ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_account     ON transactions(account);
CREATE INDEX IF NOT EXISTS idx_match_status    ON transactions(match_status);
CREATE INDEX IF NOT EXISTS idx_counterparty    ON transactions(counterparty);

CREATE TABLE IF NOT EXISTS overrides (
    rule_key       TEXT PRIMARY KEY,       -- 'counterparty:<name>'
    classification TEXT,
    category       TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS chat_feedback (
    id            TEXT PRIMARY KEY,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    rating        TEXT NOT NULL,          -- 'up' | 'down'
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON chat_feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_rating  ON chat_feedback(rating);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id            TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    session_title TEXT NOT NULL,
    agent_mode    TEXT NOT NULL,
    role          TEXT NOT NULL,          -- 'user' | 'assistant'
    content       TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_conversations(created_at);

CREATE TABLE IF NOT EXISTS credit_card_statements (
    id                      TEXT PRIMARY KEY,
    card_name               TEXT NOT NULL,          -- e.g. HDFC Regalia, ICICI Amazon Pay, Amex, Axis Magnus, SBI SimplyClick
    card_last4              TEXT,
    statement_date          TEXT,                   -- ISO yyyy-mm-dd
    due_date                TEXT,                   -- ISO yyyy-mm-dd
    total_due               REAL NOT NULL DEFAULT 0,
    min_due                 REAL NOT NULL DEFAULT 0,
    credit_limit            REAL DEFAULT 0,
    available_limit         REAL DEFAULT 0,
    cash_limit              REAL DEFAULT 0,
    reward_points_earned    REAL DEFAULT 0,
    reward_points_balance   REAL DEFAULT 0,
    finance_charges         REAL DEFAULT 0,
    source_file             TEXT,
    imported_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_cc_stmt_card ON credit_card_statements(card_name);

CREATE TABLE IF NOT EXISTS credit_card_transactions (
    id                      TEXT PRIMARY KEY,
    statement_id            TEXT,
    card_name               TEXT NOT NULL,
    card_last4              TEXT,
    txn_date                TEXT NOT NULL,          -- ISO yyyy-mm-dd
    description             TEXT,
    amount                  REAL NOT NULL,          -- +debit (spent) / -credit (refund/payment)
    category                TEXT,
    counterparty            TEXT,
    source_file             TEXT,
    imported_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_cc_txn_date ON credit_card_transactions(txn_date);
CREATE INDEX IF NOT EXISTS idx_cc_card_name ON credit_card_transactions(card_name);

CREATE TABLE IF NOT EXISTS credit_card_emis (
    id                      TEXT PRIMARY KEY,
    statement_id            TEXT,
    card_name               TEXT NOT NULL,
    card_last4              TEXT,
    merchant_name           TEXT NOT NULL,
    loan_amount             REAL NOT NULL DEFAULT 0,
    monthly_emi             REAL NOT NULL DEFAULT 0,
    total_tenure            INTEGER NOT NULL DEFAULT 1,
    paid_tenure             INTEGER NOT NULL DEFAULT 1,
    remaining_tenure        INTEGER NOT NULL DEFAULT 0,
    start_date              TEXT,
    source_file             TEXT,
    imported_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_cc_emi_card ON credit_card_emis(card_name);

CREATE TABLE IF NOT EXISTS bank_loans (
    id                      TEXT PRIMARY KEY,
    loan_name               TEXT NOT NULL,
    lender                  TEXT NOT NULL,
    account                 TEXT NOT NULL,
    monthly_emi             REAL NOT NULL,
    total_loan_amount       REAL NOT NULL,
    total_tenure            INTEGER NOT NULL,
    paid_tenure             INTEGER NOT NULL,
    remaining_tenure        INTEGER NOT NULL,
    remaining_principal     REAL NOT NULL,
    match_keyword           TEXT NOT NULL,
    match_amount            REAL NOT NULL,
    debit_day               INTEGER DEFAULT 3,
    start_date              TEXT,
    notes                   TEXT,
    borrower                TEXT DEFAULT 'user',
    created_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loan_name ON bank_loans(loan_name);
CREATE INDEX IF NOT EXISTS idx_loan_account ON bank_loans(account);
CREATE INDEX IF NOT EXISTS idx_loan_lender ON bank_loans(lender);

CREATE TABLE IF NOT EXISTS account_balances (
    account             TEXT PRIMARY KEY,
    label               TEXT NOT NULL,
    account_number      TEXT,
    account_type        TEXT,
    total_balance       REAL NOT NULL,
    savings_balance     REAL NOT NULL,
    smart_fd_balance    REAL DEFAULT 0.0,
    as_of_date          TEXT NOT NULL,
    notes               TEXT,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_rewards_ledger (
    card_id               TEXT PRIMARY KEY,
    card_name             TEXT NOT NULL,
    card_variant          TEXT NOT NULL,
    card_last4            TEXT,
    points_balance        REAL NOT NULL DEFAULT 0,
    points_expiry_date    TEXT,
    notes                 TEXT,
    updated_at            TEXT NOT NULL,
    source                TEXT DEFAULT 'auto'
);
CREATE INDEX IF NOT EXISTS idx_rewards_card_name ON card_rewards_ledger(card_name);

-- -------------------------------------------------------------------------
-- Canonical Financial Core Schemas (Changes 3, 4, 5, 7, 8, 9, 11, 12, 13)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    account_type        TEXT NOT NULL,          -- 'bank' | 'credit_card' | 'loan' | 'investment' | 'cash'
    institution         TEXT NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'INR',
    last_four           TEXT,
    status              TEXT NOT NULL DEFAULT 'active', -- 'active' | 'inactive' | 'closed'
    ownership           TEXT NOT NULL DEFAULT 'personal', -- 'personal' | 'pass_through' | 'joint'
    metadata_json       TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_acc_type      ON accounts(account_type);
CREATE INDEX IF NOT EXISTS idx_acc_ownership ON accounts(ownership);

CREATE TABLE IF NOT EXISTS canonical_events (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL,
    event_type          TEXT NOT NULL,          -- income, expense, asset_acquisition, asset_disposal, liability_drawdown, liability_payment, transfer, reimbursement, refund, fee, tax, cash_withdrawal, cash_deposit, adjustment
    amount_paise        INTEGER NOT NULL,       -- positive credit / negative debit
    event_date          TEXT NOT NULL,          -- ISO yyyy-mm-dd
    description         TEXT,
    entity_id           TEXT,
    category            TEXT,
    classification      TEXT,
    reference_id        TEXT,                   -- foreign/raw transaction id
    provenance_id       TEXT,
    status              TEXT NOT NULL DEFAULT 'settled', -- 'settled' | 'pending' | 'reversed'
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_can_date    ON canonical_events(event_date);
CREATE INDEX IF NOT EXISTS idx_can_type    ON canonical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_can_account ON canonical_events(account_id);
CREATE INDEX IF NOT EXISTS idx_can_entity  ON canonical_events(entity_id);

CREATE TABLE IF NOT EXISTS entities (
    id                  TEXT PRIMARY KEY,
    canonical_name      TEXT NOT NULL,
    entity_type         TEXT NOT NULL,          -- merchant, employer, person, lender, bank, utility, investment_provider
    aliases_json        TEXT,
    identifiers_json    TEXT,
    roles_json          TEXT,
    default_category    TEXT,
    default_classification TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);

CREATE TABLE IF NOT EXISTS classification_rules (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 100,
    scope               TEXT NOT NULL DEFAULT 'global',
    condition_type      TEXT NOT NULL,          -- regex, substring, entity_id, amount_range
    condition_value     TEXT NOT NULL,
    classification      TEXT NOT NULL,
    category            TEXT NOT NULL,
    confidence          REAL NOT NULL DEFAULT 1.0,
    enabled             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rule_priority ON classification_rules(priority);
CREATE INDEX IF NOT EXISTS idx_rule_enabled  ON classification_rules(enabled);

CREATE TABLE IF NOT EXISTS review_queue (
    id                  TEXT PRIMARY KEY,
    item_type           TEXT NOT NULL,          -- classification, reconciliation, anomaly, statement_mismatch
    item_id             TEXT NOT NULL,
    reason              TEXT NOT NULL,
    candidate_data_json TEXT,
    status              TEXT NOT NULL DEFAULT 'pending', -- pending, accepted, rejected, resolved
    resolution_json     TEXT,
    created_at          TEXT NOT NULL,
    resolved_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_rq_type   ON review_queue(item_type);

CREATE TABLE IF NOT EXISTS statement_validations (
    id                      TEXT PRIMARY KEY,
    account_id              TEXT NOT NULL,
    statement_period_start  TEXT,
    statement_period_end    TEXT,
    opening_balance_paise   INTEGER NOT NULL,
    closing_balance_paise   INTEGER NOT NULL,
    credits_paise           INTEGER NOT NULL,
    debits_paise            INTEGER NOT NULL,
    calculated_closing_paise INTEGER NOT NULL,
    variance_paise          INTEGER NOT NULL,
    status                  TEXT NOT NULL,      -- balanced, variance_detected
    created_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_val_account ON statement_validations(account_id);

CREATE TABLE IF NOT EXISTS audit_events (
    id                  TEXT PRIMARY KEY,
    entity_type         TEXT NOT NULL,          -- transaction, rule, reconciliation, account, loan
    entity_id           TEXT NOT NULL,
    action              TEXT NOT NULL,          -- created, updated, classified, matched, resolved
    actor               TEXT NOT NULL DEFAULT 'system',
    before_json         TEXT,
    after_json          TEXT,
    reason              TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_time   ON audit_events(created_at);

CREATE TABLE IF NOT EXISTS provenance (
    import_id           TEXT PRIMARY KEY,
    file_hash           TEXT NOT NULL,
    source              TEXT NOT NULL,          -- csv, pdf, email, manual
    account_id          TEXT,
    statement_period    TEXT,
    parser_version      TEXT DEFAULT '1.0',
    normalizer_version  TEXT DEFAULT '1.0',
    imported_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prov_hash ON provenance(file_hash);
"""


def init_db() -> None:
    conn = connect()
    
    # Auto-migrate bank_loans columns if missing
    try:
        conn.execute("ALTER TABLE bank_loans ADD COLUMN borrower TEXT DEFAULT 'user';")
    except Exception:
        pass

    # Auto-migrate credit_card_statements columns if missing
    for col in ("credit_limit", "available_limit", "cash_limit"):
        try:
            conn.execute(f"ALTER TABLE credit_card_statements ADD COLUMN {col} REAL DEFAULT 0;")
        except Exception:
            pass

    # Auto-migrate transactions amount_paise / balance_paise if missing
    for col, col_type in (("amount_paise", "INTEGER"), ("balance_paise", "INTEGER")):
        try:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} {col_type};")
        except Exception:
            pass

    conn.executescript(SCHEMA)

    # Backfill amount_paise & balance_paise if they are NULL
    try:
        conn.execute("UPDATE transactions SET amount_paise = CAST(ROUND(amount * 100) AS INTEGER) WHERE amount_paise IS NULL AND amount IS NOT NULL;")
        conn.execute("UPDATE transactions SET balance_paise = CAST(ROUND(balance * 100) AS INTEGER) WHERE balance_paise IS NULL AND balance IS NOT NULL;")
    except Exception:
        pass

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_loan_borrower ON bank_loans(borrower);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_txn_amount_paise ON transactions(amount_paise);")
    except Exception:
        pass

    conn.commit()
    conn.close()

    try:
        seed_default_accounts()
    except Exception:
        pass

    try:
        sync_canonical_ledger()
    except Exception:
        pass

    try:
        sync_account_balances_from_ledger()
    except Exception:
        pass

    try:
        seed_card_rewards_from_statements()
    except Exception:
        pass


def _canonical_desc_for_id(description: str) -> str:
    """Normalize description for deterministic ID generation: uppercase and strip all whitespace."""
    if description is None:
        return ""
    return re.sub(r"\s+", "", str(description).upper())


def make_id(account: str, txn_date: str, description: str, amount: float,
            salt: str = "") -> str:
    clean_desc = _canonical_desc_for_id(description)
    acct = str(account or "").lower().strip()
    key = f"{acct}|{txn_date}|{clean_desc}|{amount:.2f}|{salt}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _safe_descr(description) -> str:
    return "" if description is None else str(description).strip()


def upsert_many(rows: list[dict]) -> tuple[int, int]:
    """Insert a list of normalized transaction dicts (id already set).

    Returns (inserted, skipped) — duplicates are skipped via INSERT OR IGNORE.
    Also dedupes identical tuples *within* the batch by salting their ids.
    """
    # Salt ids for tuples that repeat inside this same batch so we never
    # collapse two genuinely-different rows (same account/date/desc/amount).
    seen: dict[tuple, int] = {}
    salted_ids: set[str] = set()
    for r in rows:
        canon_desc = _canonical_desc_for_id(r.get("description"))
        tup = (str(r.get("account", "")).lower(), r["txn_date"], canon_desc, r["amount"])
        if tup in seen:
            seen[tup] += 1
            new_id = make_id(r["account"], r["txn_date"], r["description"],
                             r["amount"], salt=str(seen[tup]))
            r["id"] = new_id
            salted_ids.add(new_id)
        else:
            seen[tup] = 0
            # Ensure the primary id was computed with canonical desc
            r["id"] = make_id(r["account"], r["txn_date"], r["description"], r["amount"])

    now = datetime.now().isoformat(timespec="seconds")
    inserted = 0
    skipped = 0
    conn = connect()
    try:
        with conn:
            cur = conn.cursor()
            for r in rows:
                raw = r.get("raw")
                if not isinstance(raw, str):
                    raw = json.dumps(raw, default=str) if raw is not None else None
                
                # Compute exact integer paise representations
                amt_paise = r.get("amount_paise")
                if amt_paise is None and r.get("amount") is not None:
                    amt_paise = int(round(float(r["amount"]) * 100))
                
                bal_paise = r.get("balance_paise")
                if bal_paise is None and r.get("balance") is not None:
                    try:
                        bal_paise = int(round(float(r["balance"]) * 100))
                    except (ValueError, TypeError):
                        bal_paise = None

                cur.execute(
                    """INSERT OR IGNORE INTO transactions
                       (id, account, txn_date, description, amount, amount_paise,
                        balance, balance_paise, classification, category,
                        counterparty, matched_with, match_status, flags, raw,
                        source_file, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["id"], r["account"], r["txn_date"],
                     _safe_descr(r["description"]), r["amount"], amt_paise,
                     r.get("balance"), bal_paise,
                     r.get("classification"), r.get("category"),
                     r.get("counterparty"), r.get("matched_with"),
                     r.get("match_status"), r.get("flags"), raw,
                     r.get("source_file"), now),
                )
                inserted += cur.rowcount
                skipped += 1 - cur.rowcount
    finally:
        conn.close()
    return inserted, skipped


# ---------------------------------------------------------------------------
# Reads for the dashboard
# ---------------------------------------------------------------------------

def load_all() -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM transactions", connect())


def load_transactions(
    account: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    classification: list[str] | None = None,
    category: list[str] | None = None,
    search: str | None = None,
    only_uncategorized: bool = False,
    only_flags: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch transactions with filters. All filters are optional."""
    sql = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if account:
        sql += f" AND account IN ({','.join('?' * len(account))})"
        params += account
    if date_from:
        sql += " AND txn_date >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND txn_date <= ?"
        params.append(date_to)
    if classification:
        sql += f" AND classification IN ({','.join('?' * len(classification))})"
        params += classification
    if category:
        sql += f" AND category IN ({','.join('?' * len(category))})"
        params += category
    if search:
        sql += " AND (description LIKE ? OR counterparty LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if only_uncategorized:
        sql += " AND category = ?"
        params.append(config.DEFAULT_CATEGORY)
    if only_flags:
        conds = []
        for fl in only_flags:
            conds.append("flags LIKE ?")
            params.append(f"%{fl}%")
        sql += " AND (" + " OR ".join(conds) + ")"
    sql += " ORDER BY txn_date DESC, amount DESC"
    return pd.read_sql_query(sql, connect(), params=params)


def load_unmatched(classification: str) -> pd.DataFrame:
    """Unmatched rows of a given classification (for the reconciliation tab)."""
    return pd.read_sql_query(
        """SELECT * FROM transactions
           WHERE classification = ? AND match_status IS NOT 'matched'
           ORDER BY txn_date""",
        connect(), params=[classification])


def reclassify(txn_id: str, classification: str, category: str) -> None:
    """Update a single transaction's classification/category (user override)."""
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE transactions SET classification=?, category=? WHERE id=?",
            (classification, category, txn_id))


def set_match(txn_id: str, matched_with: str, match_status: str) -> None:
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE transactions SET matched_with=?, match_status=? WHERE id=?",
            (matched_with, match_status, txn_id))


def manual_pair(debit_id: str, credit_ids: list[str] | str) -> bool:
    """Manually link a debit (e.g. CC payment) with one or more credits (e.g. Ashwin deposits).

    Sets match_status = 'manual_matched' and records matched_with bidirectionally.
    """
    if isinstance(credit_ids, str):
        c_list = [c.strip() for c in credit_ids.split(",") if c.strip()]
    else:
        c_list = [c.strip() for c in credit_ids if c.strip()]
    if not debit_id or not c_list:
        return False

    c_str = ",".join(c_list)
    conn = connect()
    with conn:
        conn.execute(
            "UPDATE transactions SET match_status = 'manual_matched', matched_with = ? WHERE id = ?",
            (c_str, debit_id)
        )
        for cid in c_list:
            conn.execute(
                "UPDATE transactions SET match_status = 'manual_matched', matched_with = ? WHERE id = ?",
                (debit_id, cid)
            )
    conn.close()
    return True


def manual_unpair(txn_id: str) -> bool:
    """Unlink a matched transaction and its paired counterpart(s)."""
    conn = connect()
    with conn:
        row = conn.execute("SELECT matched_with FROM transactions WHERE id = ?", (txn_id,)).fetchone()
        if not row:
            conn.close()
            return False
        paired_ids = [p.strip() for p in (row[0] or "").split(",") if p.strip()]

        conn.execute("UPDATE transactions SET match_status = 'unmatched', matched_with = NULL WHERE id = ?", (txn_id,))

        for pid in paired_ids:
            c_row = conn.execute("SELECT matched_with FROM transactions WHERE id = ?", (pid,)).fetchone()
            if c_row and c_row[0]:
                curr_list = [x.strip() for x in c_row[0].split(",") if x.strip() and x.strip() != txn_id]
                if curr_list:
                    conn.execute("UPDATE transactions SET matched_with = ? WHERE id = ?", (",".join(curr_list), pid))
                else:
                    conn.execute("UPDATE transactions SET match_status = 'unmatched', matched_with = NULL WHERE id = ?", (pid,))
    conn.close()
    return True


def load_matched_pairs() -> pd.DataFrame:
    """Load paired pass-through / internal transactions for review."""
    query = """
    SELECT d.id AS debit_id, d.txn_date AS debit_date, d.account AS debit_account, 
           d.description AS debit_desc, d.amount AS debit_amount, d.classification AS debit_class,
           d.match_status, d.matched_with,
           c.id AS credit_id, c.txn_date AS credit_date, c.account AS credit_account,
           c.description AS credit_desc, c.amount AS credit_amount, c.classification AS credit_class
    FROM transactions d
    LEFT JOIN transactions c ON d.matched_with = c.id
    WHERE d.amount < 0 AND d.match_status IN ('matched', 'manual_matched')
    ORDER BY d.txn_date DESC
    """
    conn = connect()
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def set_flags(txn_id: str, flags: str | None) -> None:
    conn = connect()
    with conn:
        conn.execute("UPDATE transactions SET flags=? WHERE id=?", (flags, txn_id))


# ---------------------------------------------------------------------------
# Overrides — a manual reclassify is remembered by counterparty so future
# imports of the same person/merchant auto-fill.
# ---------------------------------------------------------------------------

def load_overrides() -> dict[str, dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM overrides").fetchall()
    conn.close()
    return {r["rule_key"]: {"classification": r["classification"],
                            "category": r["category"]} for r in rows}


def save_override(counterparty: str, classification: str, category: str) -> None:
    conn = connect()
    now = datetime.now().isoformat(timespec="seconds")
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO overrides
               (rule_key, classification, category, updated_at)
               VALUES (?,?,?,?)""",
            (f"counterparty:{counterparty}", classification, category, now))
    conn.close()


def apply_override_to_rows(counterparty: str, classification: str,
                           category: str) -> int:
    """Re-apply an override to existing spend rows with this counterparty.

    Returns the number of rows updated.
    """
    conn = connect()
    with conn:
        cur = conn.execute(
            """UPDATE transactions SET classification=?, category=?
               WHERE counterparty=? AND classification IN ('spend','other_income')
                  AND category IS 'Uncategorized'""",
            (classification, category, counterparty))
        return cur.rowcount


def apply_overrides_to_all(overrides: dict[str, dict]) -> int:
    """Re-run all stored overrides across the whole table. Returns rows updated."""
    conn = connect()
    updated = 0
    with conn:
        cur = conn.cursor()
        for rule_key, o in overrides.items():
            if not rule_key.startswith("counterparty:"):
                continue
            cp = rule_key[len("counterparty:"):]
            cur.execute(
                """UPDATE transactions SET classification=?, category=?
                   WHERE counterparty=? AND classification IN ('spend','other_income')
                      AND category IS 'Uncategorized'""",
                (o["classification"], o["category"], cp))
            updated += cur.rowcount
    conn.close()
    return updated


def stats() -> dict:
    conn = connect()
    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    by_account = dict(conn.execute(
        "SELECT account, COUNT(*) FROM transactions GROUP BY account").fetchall())
    first = conn.execute("SELECT MIN(txn_date) FROM transactions").fetchone()[0]
    last = conn.execute("SELECT MAX(txn_date) FROM transactions").fetchone()[0]
    conn.close()
    return {"total": total, "by_account": by_account,
            "date_min": first, "date_max": last}


# ---------------------------------------------------------------------------
# Chat feedback — thumbs up/down on agent answers
# ---------------------------------------------------------------------------

import uuid
from datetime import datetime


def save_feedback(question: str, answer: str, rating: str) -> str:
    """Store a thumbs-up/down on an agent answer. Returns the feedback ID."""
    assert rating in ("up", "down")
    fid = uuid.uuid4().hex
    conn = connect()
    with conn:
        conn.execute(
            """INSERT INTO chat_feedback (id, question, answer, rating, created_at)
               VALUES (?,?,?,?,?)""",
            (fid, question, answer, rating, datetime.now().isoformat(timespec="seconds")))
    conn.close()
    return fid


def load_feedback(rating: str | None = None, limit: int = 100) -> pd.DataFrame:
    """Load feedback entries, optionally filtered by rating ('up' or 'down')."""
    sql = "SELECT * FROM chat_feedback"
    params = []
    if rating:
        sql += " WHERE rating = ?"
        params.append(rating)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return pd.read_sql_query(sql, connect(), params=params)


def feedback_counts() -> dict:
    """Return counts of up/down feedback."""
    conn = connect()
    up = conn.execute("SELECT COUNT(*) FROM chat_feedback WHERE rating='up'").fetchone()[0]
    down = conn.execute("SELECT COUNT(*) FROM chat_feedback WHERE rating='down'").fetchone()[0]
    conn.close()
    return {"up": up, "down": down}


# ---------------------------------------------------------------------------
# Conversation logs & history persistence
# ---------------------------------------------------------------------------

def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    agent_mode: str = "Master Financial AI",
    session_title: str | None = None,
) -> str:
    """Store a chat message in persistent history. Auto-derives title from user question if not set."""
    assert role in ("user", "assistant", "system")
    mid = uuid.uuid4().hex
    conn = connect()
    with conn:
        if not session_title:
            row = conn.execute(
                "SELECT session_title FROM chat_conversations WHERE session_id = ? LIMIT 1",
                (session_id,)
            ).fetchone()
            if row and row[0]:
                session_title = row[0]
            elif role == "user":
                session_title = content.strip().replace("\n", " ")[:60]
            else:
                session_title = f"Conversation {datetime.now().strftime('%d %b %H:%M')}"

        conn.execute(
            """INSERT INTO chat_conversations (id, session_id, session_title, agent_mode, role, content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mid, session_id, session_title, agent_mode, role, content, datetime.now().isoformat(timespec="seconds"))
        )
    conn.close()
    return mid


def load_chat_sessions(limit: int = 50) -> list[dict]:
    """Return summary list of past chat sessions sorted by most recent activity."""
    conn = connect()
    rows = conn.execute(
        """SELECT session_id, session_title, agent_mode,
                  MIN(created_at) as started_at,
                  MAX(created_at) as last_active,
                  COUNT(*) as message_count
           FROM chat_conversations
           GROUP BY session_id
           ORDER BY last_active DESC
           LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            "session_id": r[0],
            "session_title": r[1],
            "agent_mode": r[2],
            "started_at": r[3],
            "last_active": r[4],
            "message_count": r[5],
        }
        for r in rows
    ]


def load_chat_messages(session_id: str) -> list[dict]:
    """Load all messages for a given session in chronological order."""
    conn = connect()
    rows = conn.execute(
        """SELECT id, role, content, agent_mode, created_at
           FROM chat_conversations
           WHERE session_id = ?
           ORDER BY created_at ASC""",
        (session_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "role": r[1],
            "content": r[2],
            "agent_mode": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def search_chat_messages(query: str, limit: int = 50) -> list[dict]:
    """Full-text substring search across historical questions and answers."""
    conn = connect()
    pat = f"%{query.strip()}%"
    rows = conn.execute(
        """SELECT session_id, session_title, agent_mode, role, content, created_at
           FROM chat_conversations
           WHERE content LIKE ? OR session_title LIKE ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (pat, pat, limit)
    ).fetchall()
    conn.close()
    return [
        {
            "session_id": r[0],
            "session_title": r[1],
            "agent_mode": r[2],
            "role": r[3],
            "content": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def delete_chat_session(session_id: str) -> bool:
    """Delete a conversation session and all its messages."""
    conn = connect()
    with conn:
        conn.execute("DELETE FROM chat_conversations WHERE session_id = ?", (session_id,))
    conn.close()
    return True


def export_chat_markdown(session_id: str) -> str:
    """Generate a clean Markdown transcript of a chat session."""
    msgs = load_chat_messages(session_id)
    if not msgs:
        return "# Empty Conversation Transcript\n"
    
    first_dt = msgs[0]["created_at"]
    agent_mode = msgs[0]["agent_mode"]
    lines = [
        f"# Financial AI Conversation Transcript",
        f"- **Session ID:** `{session_id}`",
        f"- **Date:** {first_dt}",
        f"- **Perspective:** {agent_mode}",
        f"- **Turns:** {len(msgs)} messages\n",
        "---\n"
    ]
    for m in msgs:
        role_label = "🧑 **User**" if m["role"] == "user" else "🤖 **Assistant**"
        lines.append(f"{role_label} *({m['created_at']})*:\n")
        lines.append(f"{m['content']}\n")
        lines.append("---\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Credit Card persistence
# ---------------------------------------------------------------------------

def save_cc_statement(stmt_dict: dict) -> str:
    """Save or update credit card statement summary info. Returns statement ID."""
    card_name = stmt_dict.get("card_name", "Credit Card")
    card_last4 = stmt_dict.get("card_last4", "")
    stmt_date = stmt_dict.get("statement_date", "")
    sid = make_id(card_name, stmt_date, "statement_summary", stmt_dict.get("total_due", 0))
    stmt_dict["id"] = sid
    stmt_dict["imported_at"] = datetime.now().isoformat(timespec="seconds")
    
    conn = connect()
    with conn:
        # Check if existing statements for this card have known limits/rewards to preserve if new statement has 0
        cur = conn.execute(
            "SELECT credit_limit, available_limit, cash_limit, reward_points_balance FROM credit_card_statements WHERE card_name = ? OR (card_last4 != '' AND card_last4 = ?) ORDER BY statement_date DESC LIMIT 1",
            (card_name, card_last4)
        )
        existing = cur.fetchone()
        
        c_lim = float(stmt_dict.get("credit_limit", 0.0))
        av_lim = float(stmt_dict.get("available_limit", 0.0))
        cs_lim = float(stmt_dict.get("cash_limit", 0.0))
        rw_bal = float(stmt_dict.get("reward_points_balance", 0.0))
        
        if existing:
            if c_lim == 0.0 and existing[0] and existing[0] > 0:
                c_lim = existing[0]
            if av_lim == 0.0 and existing[1] and existing[1] > 0:
                av_lim = existing[1]
            if cs_lim == 0.0 and existing[2] and existing[2] > 0:
                cs_lim = existing[2]
            if rw_bal == 0.0 and existing[3] and existing[3] > 0:
                rw_bal = existing[3]

        conn.execute(
            """INSERT OR REPLACE INTO credit_card_statements 
               (id, card_name, card_last4, statement_date, due_date, total_due, min_due, 
                credit_limit, available_limit, cash_limit,
                reward_points_earned, reward_points_balance, finance_charges, source_file, imported_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, card_name, card_last4,
             stmt_date, stmt_dict.get("due_date", ""),
             float(stmt_dict.get("total_due", 0.0)), float(stmt_dict.get("min_due", 0.0)),
             c_lim, av_lim, cs_lim,
             float(stmt_dict.get("reward_points_earned", 0.0)), rw_bal,
             float(stmt_dict.get("finance_charges", 0.0)), stmt_dict.get("source_file", ""),
             stmt_dict["imported_at"])
        )
        if "Axis" in card_name or "IndianOil" in card_name or "INDIANOIL" in card_name:
            consolidate_axis_cards(conn)
    conn.close()
    return sid


def update_cc_limits(
    card_name: str,
    card_last4: str = "",
    credit_limit: float | None = None,
    available_limit: float | None = None,
    cash_limit: float | None = None,
    reward_points_balance: float | None = None,
) -> bool:
    """Manually update limits or reward points for a credit card in the database."""
    conn = connect()
    with conn:
        updates = []
        params = []
        if credit_limit is not None:
            updates.append("credit_limit = ?")
            params.append(float(credit_limit))
        if available_limit is not None:
            updates.append("available_limit = ?")
            params.append(float(available_limit))
        if cash_limit is not None:
            updates.append("cash_limit = ?")
            params.append(float(cash_limit))
        if reward_points_balance is not None:
            updates.append("reward_points_balance = ?")
            params.append(float(reward_points_balance))

        if not updates:
            conn.close()
            return False

        if card_last4:
            sql = f"UPDATE credit_card_statements SET {', '.join(updates)} WHERE card_name = ? OR card_last4 = ?"
            params.extend([card_name, card_last4])
        else:
            sql = f"UPDATE credit_card_statements SET {', '.join(updates)} WHERE card_name = ?"
            params.append(card_name)

        cur = conn.execute(sql, params)
        success = cur.rowcount > 0
    conn.close()
    return success


def upsert_cc_transactions(rows: list[dict]) -> tuple[int, int]:
    """Insert credit card transaction dicts (INSERT OR IGNORE). Returns (inserted, skipped)."""
    if not rows:
        return 0, 0
    now = datetime.now().isoformat(timespec="seconds")
    to_insert = []
    seen = {}
    for r in rows:
        card = r.get("card_name", "Credit Card")
        dt = r.get("txn_date", "")
        desc = _safe_descr(r.get("description"))
        canon_desc = _canonical_desc_for_id(desc)
        amt = float(r.get("amount", 0.0))
        
        salt = ""
        key = (card, dt, canon_desc, amt)
        if key in seen:
            seen[key] += 1
            salt = str(seen[key])
        else:
            seen[key] = 0
            
        tid = make_id(card, dt, desc, amt, salt=salt)
        to_insert.append((
            tid, r.get("statement_id", ""), card, r.get("card_last4", ""),
            dt, desc, amt, r.get("category", "Uncategorized"),
            r.get("counterparty", ""), r.get("source_file", ""), now
        ))
        
    conn = connect()
    inserted = 0
    with conn:
        for tuple_row in to_insert:
            cur = conn.execute(
                """INSERT OR IGNORE INTO credit_card_transactions 
                   (id, statement_id, card_name, card_last4, txn_date, description, amount, category, counterparty, source_file, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                tuple_row
            )
            inserted += cur.rowcount
    conn.close()
    skipped = len(rows) - inserted
    return inserted, skipped


def upsert_cc_emis(rows: list[dict]) -> tuple[int, int]:
    """Insert credit card active EMI rows (INSERT OR REPLACE). Returns (inserted, skipped)."""
    if not rows:
        return 0, 0
    now = datetime.now().isoformat(timespec="seconds")
    to_insert = []
    for r in rows:
        card = r.get("card_name", "Credit Card")
        mch = r.get("merchant_name", "EMI Loan")
        amt = float(r.get("loan_amount", 0.0))
        eid = make_id(card, mch, "emi", amt, salt=str(r.get("total_tenure", 1)))
        
        to_insert.append((
            eid, r.get("statement_id", ""), card, r.get("card_last4", ""),
            mch, amt, float(r.get("monthly_emi", 0.0)),
            int(r.get("total_tenure", 1)), int(r.get("paid_tenure", 1)), int(r.get("remaining_tenure", 0)),
            r.get("start_date", ""), r.get("source_file", ""), now
        ))
        
    conn = connect()
    inserted = 0
    with conn:
        for tuple_row in to_insert:
            cur = conn.execute(
                """INSERT OR REPLACE INTO credit_card_emis 
                   (id, statement_id, card_name, card_last4, merchant_name, loan_amount, monthly_emi,
                    total_tenure, paid_tenure, remaining_tenure, start_date, source_file, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                tuple_row
            )
            inserted += cur.rowcount
    conn.close()
    return inserted, 0


def load_cc_statements() -> pd.DataFrame:
    """Load all credit card statements summary table."""
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM credit_card_statements ORDER BY statement_date DESC", conn)
    conn.close()
    return df


def load_cc_transactions() -> pd.DataFrame:
    """Load all credit card transactions table."""
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM credit_card_transactions ORDER BY txn_date DESC", conn)
    conn.close()
    return df


def load_cc_emis() -> pd.DataFrame:
    """Load all credit card active EMIs table."""
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM credit_card_emis ORDER BY remaining_tenure DESC", conn)
    conn.close()
    return df


def clear_cc_data() -> None:
    """Clear all records from credit_card_statements, credit_card_transactions, and credit_card_emis tables."""
    conn = connect()
    with conn:
        conn.execute("DELETE FROM credit_card_statements")
        conn.execute("DELETE FROM credit_card_transactions")
        conn.execute("DELETE FROM credit_card_emis")
    conn.close()


def consolidate_axis_cards(conn=None) -> None:
    """Consolidate multiple Axis Bank cards sharing a single credit limit into one profile."""
    close_conn = False
    if conn is None:
        conn = connect()
        close_conn = True
    try:
        cur = conn.execute("""
            SELECT id, card_name, card_last4, statement_date, due_date, total_due, min_due, 
                   credit_limit, available_limit, cash_limit, source_file
            FROM credit_card_statements 
            WHERE card_name IN ('Indian Oil Axis Bank Premium Card', 'IndianOil Axis Bank RuPay Card')
        """)
        rows = cur.fetchall()
        if rows:
            shared_limit = max([r[7] for r in rows if r[7] and r[7] > 0] or [516000.0])
            # The lowest available limit represents the remaining pool after all cards' postings
            shared_avail = min([r[8] for r in rows if r[8] and r[8] > 0] or [79888.03])
            combined_total_due = sum([r[5] for r in rows if r[5]])
            combined_min_due = sum([r[6] for r in rows if r[6]])
            latest_stmt_date = max([r[3] for r in rows if r[3]] or ["2026-08-25"])
            latest_due_date = max([r[4] for r in rows if r[4]] or ["2026-09-14"])
            
            conn.execute("""
                INSERT OR REPLACE INTO credit_card_statements
                (id, card_name, card_last4, statement_date, due_date, total_due, min_due,
                 credit_limit, available_limit, cash_limit, reward_points_earned, reward_points_balance,
                 finance_charges, source_file, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 'Axis_Combined_Statements.pdf', datetime('now'))
            """, (
                "axis_combined_shared_limit",
                "Axis Bank Credit Card",
                "9788 / 6076",
                latest_stmt_date,
                latest_due_date,
                combined_total_due,
                combined_min_due,
                shared_limit,
                shared_avail,
                0.0
            ))
            conn.execute("DELETE FROM credit_card_statements WHERE card_name IN ('Indian Oil Axis Bank Premium Card', 'IndianOil Axis Bank RuPay Card')")
            
        conn.execute("""
            UPDATE credit_card_transactions
            SET card_name = 'Axis Bank Credit Card'
            WHERE card_name IN ('Indian Oil Axis Bank Premium Card', 'IndianOil Axis Bank RuPay Card')
        """)
        conn.execute("""
            UPDATE credit_card_emis
            SET card_name = 'Axis Bank Credit Card'
            WHERE card_name IN ('Indian Oil Axis Bank Premium Card', 'IndianOil Axis Bank RuPay Card')
        """)
    finally:
        if close_conn:
            conn.commit()
            conn.close()


def prune_superseded_cc_emis(conn=None) -> int:
    """Ensure credit_card_emis only retains active EMIs from the latest statement per card."""
    close_conn = False
    if conn is None:
        conn = connect()
        close_conn = True
    deleted = 0
    try:
        cur = conn.execute("""
            DELETE FROM credit_card_emis
            WHERE source_file IN (
                'Card_Statement_25Jun2026-24Jul2026.pdf',
                'IDFC FIRST Bank_Credit Card_Statement_22072026.pdf',
                '560087_1006020002010155-246.pdf'
            )
        """)
        deleted = cur.rowcount
    finally:
        if close_conn:
            conn.commit()
            conn.close()
    return deleted


def load_bank_loans() -> pd.DataFrame:
    """Load all tracked bank/personal loans."""
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM bank_loans ORDER BY remaining_tenure DESC", conn)
    conn.close()
    return df


def upsert_bank_loan(loan_dict: dict) -> str:
    """Insert or update a bank loan record."""
    lid = loan_dict.get("id") or make_id(loan_dict.get("account", "axis"), loan_dict.get("loan_name", "Loan"), "bank_loan", float(loan_dict.get("monthly_emi", 0.0)))
    loan_dict["id"] = lid
    now = datetime.now().isoformat(timespec="seconds")
    
    conn = connect()
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO bank_loans
               (id, loan_name, lender, account, monthly_emi, total_loan_amount,
                total_tenure, paid_tenure, remaining_tenure, remaining_principal,
                match_keyword, match_amount, debit_day, start_date, notes, borrower, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lid, loan_dict.get("loan_name", "Personal Loan"),
             loan_dict.get("lender", "Bank / NBFC"),
             loan_dict.get("account", "axis"),
             float(loan_dict.get("monthly_emi", 0.0)),
             float(loan_dict.get("total_loan_amount", 0.0)),
             int(loan_dict.get("total_tenure", 1)),
             int(loan_dict.get("paid_tenure", 0)),
             int(loan_dict.get("remaining_tenure", 0)),
             float(loan_dict.get("remaining_principal", 0.0)),
             loan_dict.get("match_keyword", ""),
             float(loan_dict.get("match_amount", 0.0)),
             int(loan_dict.get("debit_day", 3)),
             loan_dict.get("start_date", ""),
             loan_dict.get("notes", ""),
             loan_dict.get("borrower", "user"),
             loan_dict.get("created_at", now))
        )
    conn.close()
    return lid


def delete_bank_loan(loan_id: str) -> bool:
    """Delete a bank loan by ID."""
    conn = connect()
    with conn:
        cur = conn.execute("DELETE FROM bank_loans WHERE id = ?", (loan_id,))
        success = cur.rowcount > 0
    conn.close()
    return success


def load_account_balances() -> pd.DataFrame:
    """Load all tracked bank account & savings balances."""
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM account_balances ORDER BY total_balance DESC", conn)
    conn.close()
    return df


def upsert_account_balance(b_dict: dict) -> None:
    """Insert or update a bank account balance record."""
    acct = b_dict.get("account", "kotak")
    now = datetime.now().isoformat(timespec="seconds")
    conn = connect()
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO account_balances
               (account, label, account_number, account_type, total_balance,
                savings_balance, smart_fd_balance, as_of_date, notes, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (acct, b_dict.get("label", acct.upper()),
             b_dict.get("account_number", ""),
             b_dict.get("account_type", "Savings Account"),
             float(b_dict.get("total_balance", 0.0)),
             float(b_dict.get("savings_balance", 0.0)),
             float(b_dict.get("smart_fd_balance", 0.0)),
             b_dict.get("as_of_date", ""),
             b_dict.get("notes", ""),
             now)
        )
    conn.close()


def sync_account_balances_from_ledger() -> dict:
    """Synchronize account_balances table with the latest running balance from transactions."""
    df = load_all()
    if df.empty:
        return {}
    
    current_b = load_account_balances()
    fd_map = {}
    if not current_b.empty:
        for _, r in current_b.iterrows():
            fd_map[r["account"]] = float(r.get("smart_fd_balance", 0.0))
            
    synced = {}
    for acct, meta in config.ACCOUNTS.items():
        sub = df[(df["account"] == acct) & df["balance"].notna()]
        if sub.empty:
            continue
        sub_sorted = sub.sort_values("txn_date")
        last = sub_sorted.iloc[-1]
        
        fd_val = fd_map.get(acct, 0.0)
        sav_val = float(last["balance"])

        # For Kotak ActivMoney auto-sweep:
        # Dynamically adjust fd_val by any new sweep transactions since the last anchor date
        if acct == "kotak" and not current_b.empty:
            k_prev = current_b[current_b["account"] == "kotak"]
            if not k_prev.empty:
                prev_as_of = str(k_prev.iloc[0].get("as_of_date") or "")
                base_fd = float(k_prev.iloc[0].get("smart_fd_balance") or 0.0)
                if prev_as_of and base_fd > 0:
                    # New sweeps strictly after previous as_of date
                    new_sweeps = sub[(sub["txn_date"] > prev_as_of) & (sub["description"].str.contains("SWEEP|Sweep", case=False, na=False))]
                    if not new_sweeps.empty:
                        # Sweep to FD is negative (DR from savings -> increases FD)
                        # Sweep from FD is positive (CR into savings -> decreases FD)
                        net_sweep_delta = -float(new_sweeps["amount"].sum())
                        fd_val = max(0.0, base_fd + net_sweep_delta)

        tot_val = sav_val + fd_val
        as_of = str(last["txn_date"])
        
        upsert_account_balance({
            "account": acct,
            "label": meta.get("label", acct.upper()),
            "total_balance": tot_val,
            "savings_balance": sav_val,
            "smart_fd_balance": fd_val,
            "as_of_date": as_of,
            "notes": f"Synced from latest statement transaction as of {as_of}"
        })
        synced[acct] = {"total": tot_val, "savings": sav_val, "smart_fd": fd_val, "as_of": as_of}
        
    return synced


def load_card_rewards() -> pd.DataFrame:
    """Load all credit card reward balances and variant metadata."""
    conn = connect()
    df = pd.read_sql_query(
        "SELECT * FROM card_rewards_ledger ORDER BY points_balance DESC, card_name ASC",
        conn
    )
    conn.close()
    return df


def upsert_card_reward(data: dict) -> None:
    """Insert or update a card reward points balance and configuration."""
    conn = connect()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO card_rewards_ledger (
            card_id, card_name, card_variant, card_last4,
            points_balance, points_expiry_date, notes, updated_at, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id) DO UPDATE SET
            card_name = excluded.card_name,
            card_variant = excluded.card_variant,
            card_last4 = excluded.card_last4,
            points_balance = excluded.points_balance,
            points_expiry_date = excluded.points_expiry_date,
            notes = excluded.notes,
            updated_at = excluded.updated_at,
            source = excluded.source;
        """,
        (
            data["card_id"],
            data.get("card_name", "Credit Card"),
            data.get("card_variant", data.get("card_name", "Credit Card")),
            data.get("card_last4", ""),
            float(data.get("points_balance", 0.0)),
            data.get("points_expiry_date"),
            data.get("notes"),
            data.get("updated_at", now_iso),
            data.get("source", "manual"),
        )
    )
    conn.commit()
    conn.close()


def delete_card_reward(card_id: str) -> None:
    """Delete a card reward points record."""
    conn = connect()
    conn.execute("DELETE FROM card_rewards_ledger WHERE card_id = ?", (card_id,))
    conn.commit()
    conn.close()


def seed_card_rewards_from_statements() -> None:
    """Seed card_rewards_ledger from statements, preserving parsed point balances and mapping card variants."""
    conn = connect()
    cur = conn.cursor()
    
    # Check what statements exist
    stmts = pd.read_sql_query(
        """
        SELECT card_name, card_last4, reward_points_balance, statement_date
        FROM credit_card_statements
        ORDER BY statement_date DESC
        """,
        conn
    )
    
    if stmts.empty:
        conn.close()
        return

    # Existing records in ledger
    existing = pd.read_sql_query("SELECT * FROM card_rewards_ledger", conn)
    existing_map = {r["card_id"]: r for _, r in existing.iterrows()} if not existing.empty else {}

    # Variant heuristic mapping
    def _default_variant(cname: str) -> str:
        cn_lower = cname.lower()
        if "atlas" in cn_lower:
            return "Axis Atlas"
        elif "magnus" in cn_lower:
            return "Axis Magnus"
        elif "axis" in cn_lower:
            return "Axis Atlas"  # popular flagship
        elif "idfc" in cn_lower:
            return "IDFC FIRST Wealth"
        elif "yes" in cn_lower:
            return "YES Bank Marquee"
        elif "scapia" in cn_lower:
            return "Scapia Federal"
        elif "amex" in cn_lower or "american express" in cn_lower:
            return "Amex Platinum Travel"
        elif "infinia" in cn_lower:
            return "HDFC Infinia"
        elif "regalia" in cn_lower:
            return "HDFC Regalia Gold"
        return cname

    seen_cards = set()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, r in stmts.iterrows():
        cname = str(r["card_name"]).strip()
        last4 = str(r["card_last4"] or "").strip()
        if not cname or cname == "Credit Card":
            continue

        raw_key = f"{cname}_{last4}".strip("_")
        card_id = re.sub(r"[^a-zA-Z0-9]+", "_", raw_key).strip("_").lower()
        if not card_id or card_id in seen_cards:
            continue
        seen_cards.add(card_id)

        pts = float(r.get("reward_points_balance") or 0.0)

        if card_id in existing_map:
            # If exists and was seeded automatically, update pts if statement has higher or positive points
            curr = existing_map[card_id]
            if curr.get("source") == "auto" and pts > float(curr.get("points_balance") or 0.0):
                cur.execute(
                    "UPDATE card_rewards_ledger SET points_balance = ?, updated_at = ? WHERE card_id = ?",
                    (pts, now_iso, card_id)
                )
        else:
            variant = _default_variant(cname)
            cur.execute(
                """
                INSERT INTO card_rewards_ledger (
                    card_id, card_name, card_variant, card_last4,
                    points_balance, notes, updated_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    cname,
                    variant,
                    last4,
                    pts,
                    f"Auto-seeded from {cname} statement ({last4})",
                    now_iso,
                    "auto"
                )
            )

    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# Canonical Accounts Management (Change 4)
# --------------------------------------------------------------------------
def upsert_account(account_dict: dict) -> str:
    acc_id = account_dict.get("id") or account_dict.get("account")
    if not acc_id:
        raise ValueError("Account id is required")
    name = account_dict.get("name") or account_dict.get("label", str(acc_id).title())
    acc_type = account_dict.get("account_type", "bank")
    institution = account_dict.get("institution", name)
    currency = account_dict.get("currency", "INR")
    last_four = account_dict.get("last_four")
    status = account_dict.get("status", "active")
    ownership = account_dict.get("ownership", "personal")
    metadata_json = account_dict.get("metadata_json") or json.dumps(account_dict.get("metadata", {}))
    created_at = account_dict.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO accounts (id, name, account_type, institution, currency, last_four, status, ownership, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            account_type = excluded.account_type,
            institution = excluded.institution,
            currency = excluded.currency,
            last_four = excluded.last_four,
            status = excluded.status,
            ownership = excluded.ownership,
            metadata_json = excluded.metadata_json
        """,
        (acc_id, name, acc_type, institution, currency, last_four, status, ownership, metadata_json, created_at)
    )
    conn.commit()
    conn.close()
    return acc_id


def load_accounts(account_type: str | None = None) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM accounts"
    params = []
    if account_type:
        query += " WHERE account_type = ?"
        params.append(account_type)
    query += " ORDER BY id"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def seed_default_accounts() -> None:
    """Seed accounts from config and known cards/loans."""
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Banks
    for k, v in config.ACCOUNTS.items():
        upsert_account({
            "id": k,
            "name": f"{v.get('label', k.title())} Bank Account",
            "account_type": "bank",
            "institution": v.get("label", k.title()),
            "status": "active",
            "ownership": "personal",
            "created_at": now_iso,
        })
    # Credit cards from credit_card_statements if any
    try:
        stmts = load_cc_statements()
        for _, r in stmts.iterrows():
            cname = str(r["card_name"]).strip()
            last4 = str(r.get("card_last4") or "").strip()
            if not cname or cname == "Credit Card":
                continue
            acc_id = f"cc_{re.sub(r'[^a-zA-Z0-9]+', '_', cname).lower()}_{last4}".strip("_")
            upsert_account({
                "id": acc_id,
                "name": f"{cname} Credit Card",
                "account_type": "credit_card",
                "institution": cname.split()[0] if cname else "Credit Card",
                "last_four": last4,
                "status": "active",
                "ownership": "pass_through" if "ashwin" in cname.lower() else "personal",
                "created_at": now_iso,
            })
    except Exception:
        pass
    # Loans from bank_loans if any
    try:
        loans = load_bank_loans()
        for _, r in loans.iterrows():
            lid = str(r["id"])
            lname = str(r["loan_name"])
            lender = str(r["lender"])
            borrower = str(r.get("borrower") or "user")
            upsert_account({
                "id": f"loan_{lid}",
                "name": lname,
                "account_type": "loan",
                "institution": lender,
                "status": "active",
                "ownership": "personal" if borrower == "user" else "pass_through",
                "created_at": now_iso,
            })
    except Exception:
        pass


# --------------------------------------------------------------------------
# Canonical Ledger Events (Changes 3, 11)
# --------------------------------------------------------------------------
def upsert_canonical_event(event_dict: dict) -> str:
    eid = event_dict.get("id")
    if not eid:
        import uuid
        eid = f"can_{uuid.uuid4().hex[:16]}"
    acc_id = event_dict.get("account_id") or event_dict.get("account", "unknown")
    event_type = event_dict.get("event_type", "expense")
    amount_paise = int(event_dict.get("amount_paise", 0))
    event_date = event_dict.get("event_date") or event_dict.get("txn_date", "")
    description = event_dict.get("description", "")
    entity_id = event_dict.get("entity_id")
    category = event_dict.get("category", "")
    classification = event_dict.get("classification", "")
    reference_id = event_dict.get("reference_id") or event_dict.get("raw_txn_id")
    provenance_id = event_dict.get("provenance_id")
    status = event_dict.get("status", "settled")
    created_at = event_dict.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO canonical_events (
            id, account_id, event_type, amount_paise, event_date, description,
            entity_id, category, classification, reference_id, provenance_id, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            account_id = excluded.account_id,
            event_type = excluded.event_type,
            amount_paise = excluded.amount_paise,
            event_date = excluded.event_date,
            description = excluded.description,
            entity_id = excluded.entity_id,
            category = excluded.category,
            classification = excluded.classification,
            reference_id = excluded.reference_id,
            provenance_id = excluded.provenance_id,
            status = excluded.status
        """,
        (eid, acc_id, event_type, amount_paise, event_date, description,
         entity_id, category, classification, reference_id, provenance_id, status, created_at)
    )
    conn.commit()
    conn.close()
    return eid


def load_canonical_events(
    start_date: str | None = None,
    end_date: str | None = None,
    account_id: str | None = None,
    event_type: str | None = None,
) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM canonical_events WHERE 1=1"
    params = []
    if start_date:
        query += " AND event_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND event_date <= ?"
        params.append(end_date)
    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    query += " ORDER BY event_date DESC, id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def sync_canonical_ledger() -> tuple[int, int]:
    """Idempotently synchronizes raw `transactions` into `canonical_events`."""
    conn = connect()
    txns = pd.read_sql_query("SELECT * FROM transactions", conn)
    if txns.empty:
        conn.close()
        return 0, 0

    inserted = 0
    updated = 0
    cur = conn.cursor()

    for _, r in txns.iterrows():
        raw_id = str(r["id"])
        can_id = f"can_{raw_id}"
        acc = str(r["account"])
        tdate = str(r["txn_date"])
        desc = str(r.get("description") or "")
        cls = str(r.get("classification") or "")
        cat = str(r.get("category") or "")
        cp = str(r.get("counterparty") or "")
        apaise = r.get("amount_paise")
        if apaise is None or pd.isna(apaise):
            amt = float(r.get("amount") or 0.0)
            apaise = int(round(amt * 100))
        else:
            apaise = int(apaise)

        # Map legacy classification to canonical event type
        if cls == "income":
            etype = "income"
        elif cls == "other_income":
            etype = "refund" if "REFUND" in desc.upper() else "income"
        elif cls == "spend":
            etype = "expense"
        elif cls == "fee":
            etype = "fee"
        elif cls == "investment":
            etype = "asset_acquisition"
        elif cls == "internal_transfer":
            etype = "transfer"
        elif cls == "cc_payment":
            etype = "liability_payment"
        elif cls == "friend_deposit":
            etype = "reimbursement"
        else:
            etype = "expense" if apaise < 0 else "income"

        prov_id = f"imp_{acc}_{tdate[:7]}"
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("SELECT id FROM canonical_events WHERE id = ?", (can_id,))
        exists = cur.fetchone()
        if exists:
            cur.execute(
                """
                UPDATE canonical_events SET
                    account_id = ?, event_type = ?, amount_paise = ?, event_date = ?,
                    description = ?, entity_id = ?, category = ?, classification = ?,
                    reference_id = ?, provenance_id = ?
                WHERE id = ?
                """,
                (acc, etype, apaise, tdate, desc, cp, cat, cls, raw_id, prov_id, can_id)
            )
            updated += 1
        else:
            cur.execute(
                """
                INSERT INTO canonical_events (
                    id, account_id, event_type, amount_paise, event_date, description,
                    entity_id, category, classification, reference_id, provenance_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'settled', ?)
                """,
                (can_id, acc, etype, apaise, tdate, desc, cp, cat, cls, raw_id, prov_id, now_iso)
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


# --------------------------------------------------------------------------
# Audit Trail & Provenance (Changes 11, 12)
# --------------------------------------------------------------------------
def record_audit_event(
    entity_type: str,
    entity_id: str,
    action: str,
    actor: str = "system",
    before: dict | None = None,
    after: dict | None = None,
    reason: str = "",
) -> str:
    import uuid
    aid = f"aud_{uuid.uuid4().hex[:16]}"
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    b_json = json.dumps(before) if before else None
    a_json = json.dumps(after) if after else None

    conn = connect()
    conn.execute(
        """
        INSERT INTO audit_events (id, entity_type, entity_id, action, actor, before_json, after_json, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (aid, entity_type, entity_id, action, actor, b_json, a_json, reason, now_iso)
    )
    conn.commit()
    conn.close()
    return aid


def load_audit_events(limit: int = 100, entity_type: str | None = None) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM audit_events"
    params = []
    if entity_type:
        query += " WHERE entity_type = ?"
        params.append(entity_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def record_provenance(
    import_id: str,
    file_hash: str,
    source: str,
    account_id: str | None = None,
    statement_period: str | None = None,
    parser_version: str = "1.0",
    normalizer_version: str = "1.0",
) -> str:
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    conn.execute(
        """
        INSERT INTO provenance (
            import_id, file_hash, source, account_id, statement_period,
            parser_version, normalizer_version, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(import_id) DO UPDATE SET
            file_hash = excluded.file_hash,
            imported_at = excluded.imported_at
        """,
        (import_id, file_hash, source, account_id, statement_period, parser_version, normalizer_version, now_iso)
    )
    conn.commit()
    conn.close()
    return import_id


def load_provenance(import_id: str | None = None) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM provenance"
    params = []
    if import_id:
        query += " WHERE import_id = ?"
        params.append(import_id)
    query += " ORDER BY imported_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


# --------------------------------------------------------------------------
# Entity Resolution & Rules Storage (Changes 5, 7)
# --------------------------------------------------------------------------
def upsert_entity(entity_dict: dict) -> str:
    eid = entity_dict.get("id")
    if not eid:
        cname = entity_dict.get("canonical_name", "unknown")
        eid = f"ent_{re.sub(r'[^a-zA-Z0-9]+', '_', cname).lower()}"
    cname = entity_dict.get("canonical_name", eid.replace("ent_", "").title())
    etype = entity_dict.get("entity_type", "merchant")
    aliases_json = entity_dict.get("aliases_json") or json.dumps(entity_dict.get("aliases", []))
    identifiers_json = entity_dict.get("identifiers_json") or json.dumps(entity_dict.get("identifiers", []))
    roles_json = entity_dict.get("roles_json") or json.dumps(entity_dict.get("roles", []))
    cat = entity_dict.get("default_category", "Uncategorized")
    cls = entity_dict.get("default_classification", "spend")
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO entities (id, canonical_name, entity_type, aliases_json, identifiers_json, roles_json, default_category, default_classification, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            canonical_name = excluded.canonical_name,
            entity_type = excluded.entity_type,
            aliases_json = excluded.aliases_json,
            identifiers_json = excluded.identifiers_json,
            roles_json = excluded.roles_json,
            default_category = excluded.default_category,
            default_classification = excluded.default_classification
        """,
        (eid, cname, etype, aliases_json, identifiers_json, roles_json, cat, cls, now_iso)
    )
    conn.commit()
    conn.close()
    return eid


def load_entities() -> pd.DataFrame:
    conn = connect()
    df = pd.read_sql_query("SELECT * FROM entities ORDER BY canonical_name", conn)
    conn.close()
    return df


def upsert_classification_rule(rule_dict: dict) -> str:
    rid = rule_dict.get("id")
    if not rid:
        import uuid
        rid = f"rule_{uuid.uuid4().hex[:12]}"
    name = rule_dict.get("name", rid)
    priority = int(rule_dict.get("priority", 100))
    scope = rule_dict.get("scope", "global")
    cond_type = rule_dict.get("condition_type", "substring")
    cond_val = rule_dict.get("condition_value", "")
    cls = rule_dict.get("classification", "spend")
    cat = rule_dict.get("category", "Uncategorized")
    conf = float(rule_dict.get("confidence", 1.0))
    enabled = 1 if rule_dict.get("enabled", True) else 0
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO classification_rules (id, name, priority, scope, condition_type, condition_value, classification, category, confidence, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            priority = excluded.priority,
            scope = excluded.scope,
            condition_type = excluded.condition_type,
            condition_value = excluded.condition_value,
            classification = excluded.classification,
            category = excluded.category,
            confidence = excluded.confidence,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (rid, name, priority, scope, cond_type, cond_val, cls, cat, conf, enabled, now_iso, now_iso)
    )
    conn.commit()
    conn.close()
    return rid


def load_classification_rules(enabled_only: bool = True) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM classification_rules"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY priority ASC, name ASC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


# --------------------------------------------------------------------------
# Review Queue & Statement Validation (Changes 9, 13)
# --------------------------------------------------------------------------
def upsert_review_item(item_dict: dict) -> str:
    qid = item_dict.get("id")
    if not qid:
        import uuid
        qid = f"rev_{uuid.uuid4().hex[:12]}"
    itype = item_dict.get("item_type", "classification")
    iid = str(item_dict.get("item_id", ""))
    reason = item_dict.get("reason", "")
    cdata = item_dict.get("candidate_data_json") or json.dumps(item_dict.get("candidate_data", {}))
    status = item_dict.get("status", "pending")
    res_json = item_dict.get("resolution_json") or (json.dumps(item_dict.get("resolution")) if item_dict.get("resolution") else None)
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO review_queue (id, item_type, item_id, reason, candidate_data_json, status, resolution_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            reason = excluded.reason,
            candidate_data_json = excluded.candidate_data_json,
            status = excluded.status,
            resolution_json = excluded.resolution_json
        """,
        (qid, itype, iid, reason, cdata, status, res_json, now_iso)
    )
    conn.commit()
    conn.close()
    return qid


def load_review_queue(status: str | None = "pending") -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM review_queue"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def resolve_review_item(item_id: str, status: str, resolution: dict | None = None) -> bool:
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res_json = json.dumps(resolution) if resolution else None
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE review_queue SET status = ?, resolution_json = ?, resolved_at = ? WHERE id = ?",
        (status, res_json, now_iso, item_id)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    if success:
        record_audit_event("review_queue", item_id, "resolved", actor="user", after=resolution, reason=f"Marked as {status}")
    return success


def record_statement_validation(val_dict: dict) -> str:
    vid = val_dict.get("id")
    if not vid:
        import uuid
        vid = f"val_{uuid.uuid4().hex[:12]}"
    acc_id = val_dict.get("account_id", "")
    pstart = val_dict.get("statement_period_start")
    pend = val_dict.get("statement_period_end")
    open_p = int(val_dict.get("opening_balance_paise", 0))
    close_p = int(val_dict.get("closing_balance_paise", 0))
    cred_p = int(val_dict.get("credits_paise", 0))
    deb_p = int(val_dict.get("debits_paise", 0))
    calc_close = open_p + cred_p - deb_p
    variance = abs(calc_close - close_p)
    status = "balanced" if variance <= 100 else "variance_detected"  # ₹1.00 tolerance
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = connect()
    conn.execute(
        """
        INSERT INTO statement_validations (
            id, account_id, statement_period_start, statement_period_end,
            opening_balance_paise, closing_balance_paise, credits_paise, debits_paise,
            calculated_closing_paise, variance_paise, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            closing_balance_paise = excluded.closing_balance_paise,
            credits_paise = excluded.credits_paise,
            debits_paise = excluded.debits_paise,
            calculated_closing_paise = excluded.calculated_closing_paise,
            variance_paise = excluded.variance_paise,
            status = excluded.status
        """,
        (vid, acc_id, pstart, pend, open_p, close_p, cred_p, deb_p, calc_close, variance, status, now_iso)
    )
    conn.commit()
    conn.close()
    return vid


def load_statement_validations(account_id: str | None = None) -> pd.DataFrame:
    conn = connect()
    query = "SELECT * FROM statement_validations"
    params = []
    if account_id:
        query += " WHERE account_id = ?"
        params.append(account_id)
    query += " ORDER BY statement_period_end DESC, id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df
