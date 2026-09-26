from __future__ import annotations

import sqlite3

from finance.domain.money import Money
from finance.hardening import init_hardening, queue_review, audit
from finance.security import escape_html, redact_account_number

def test_money_uses_minor_units():
    assert (Money.from_major("0.10") + Money.from_major("0.20")).minor == 30

def test_security_helpers():
    assert escape_html('<script>alert("x")</script>') == "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"
    assert redact_account_number("1234567890") == "••••7890"

def test_hardening_tables_and_audit():
    conn = sqlite3.connect(":memory:")
    init_hardening(conn)
    audit_id = audit(conn, "transaction", "tx1", "classify", "test", after={"category":"Food"})
    review_id = queue_review(conn, "transaction", "tx1", "low_confidence", 0.42, {"rule":"test"})
    conn.commit()
    assert conn.execute("select count(*) from audit_events").fetchone()[0] == 1
    assert conn.execute("select count(*) from review_queue").fetchone()[0] == 1
    assert audit_id and review_id
