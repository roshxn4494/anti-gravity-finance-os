"""SQLite persistence layer.

A single `transactions` table holds every normalized row. The primary key is a
sha256 of (account|date|description|amount), which gives dedupe for free when a
statement is re-imported or overlaps a previously imported one.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime

import pandas as pd

from . import config
from .hardening import init_hardening

DB_PATH = None  # set from app.py / tests


def set_db_path(path: str) -> None:
    global DB_PATH
    DB_PATH = path


def connect() -> sqlite3.Connection:
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
    amount        REAL NOT NULL,          -- +credit / -debit
    balance       REAL,
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

    conn.executescript(SCHEMA)
    init_hardening(conn)

    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_loan_borrower ON bank_loans(borrower);")
    except Exception:
        pass

    conn.commit()
    conn.close()


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
                cur.execute(
                    """INSERT OR IGNORE INTO transactions
                       (id, account, txn_date, description, amount, balance,
                        classification, category, counterparty, matched_with,
                        match_status, flags, raw, source_file, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (r["id"], r["account"], r["txn_date"],
                     _safe_descr(r["description"]), r["amount"], r.get("balance"),
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
