"""Schema hardening and audit/review primitives.

Legacy tables remain compatible. New tables use integer minor units for money,
explicit provenance, immutable audit events, and human review queues.
""" 
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def init_hardening(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS import_runs (
        id TEXT PRIMARY KEY,
        source_type TEXT NOT NULL,
        source_name TEXT,
        file_hash TEXT,
        account TEXT,
        statement_start TEXT,
        statement_end TEXT,
        parser_version TEXT,
        normalizer_version TEXT,
        classifier_version TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transaction_provenance (
        transaction_id TEXT PRIMARY KEY,
        import_run_id TEXT,
        source_row_hash TEXT,
        source_file TEXT,
        source_page INTEGER,
        source_line INTEGER,
        parser_version TEXT,
        normalizer_version TEXT,
        classifier_version TEXT,
        matching_version TEXT,
        schema_version INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(import_run_id) REFERENCES import_runs(id)
    );

    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        before_json TEXT,
        after_json TEXT,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_entity
        ON audit_events(entity_type, entity_id, created_at);

    CREATE TABLE IF NOT EXISTS review_queue (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        confidence REAL,
        evidence_json TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        reviewer TEXT,
        resolution_json TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_review_status
        ON review_queue(status, created_at);

    CREATE TABLE IF NOT EXISTS classification_rules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 100,
        scope TEXT NOT NULL DEFAULT 'transaction',
        condition_type TEXT NOT NULL,
        condition_value TEXT NOT NULL,
        classification TEXT,
        category TEXT,
        confidence REAL NOT NULL DEFAULT 0.90,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_rules_priority
        ON classification_rules(enabled, priority);

    CREATE TABLE IF NOT EXISTS metric_snapshots (
        id TEXT PRIMARY KEY,
        metric TEXT NOT NULL,
        period_start TEXT,
        period_end TEXT,
        value_minor INTEGER,
        currency TEXT NOT NULL DEFAULT 'INR',
        transaction_count INTEGER,
        coverage TEXT NOT NULL DEFAULT 'unknown',
        data_as_of TEXT,
        provenance_json TEXT,
        created_at TEXT NOT NULL
    );
    """)

def audit(conn: sqlite3.Connection, entity_type: str, entity_id: str,
          action: str, actor: str, before: Any = None,
          after: Any = None, reason: str | None = None) -> str:
    event_id = hashlib.sha256(
        f"{entity_type}|{entity_id}|{action}|{utc_now()}".encode()
    ).hexdigest()
    conn.execute(
        """INSERT INTO audit_events
           (id, entity_type, entity_id, action, actor, before_json, after_json, reason, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (event_id, entity_type, entity_id, action, actor,
         json.dumps(before, default=str, sort_keys=True) if before is not None else None,
         json.dumps(after, default=str, sort_keys=True) if after is not None else None,
         reason, utc_now()),
    )
    return event_id

def queue_review(conn: sqlite3.Connection, entity_type: str, entity_id: str,
                 reason_code: str, confidence: float | None,
                 evidence: dict[str, Any] | None = None) -> str:
    review_id = hashlib.sha256(
        f"{entity_type}|{entity_id}|{reason_code}|{utc_now()}".encode()
    ).hexdigest()
    conn.execute(
        """INSERT INTO review_queue
           (id, entity_type, entity_id, reason_code, confidence, evidence_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (review_id, entity_type, entity_id, reason_code, confidence,
         json.dumps(evidence or {}, default=str, sort_keys=True), utc_now()),
    )
    return review_id
