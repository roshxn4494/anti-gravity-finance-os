"""Unit tests for multi-factor reconciliation, review queue, and statement balance validation (Changes 8, 9, 13)."""
from __future__ import annotations

from finance.services.reconciliation_engine import get_reconciliation_engine
from finance.services.statement_validator import validate_statement
from finance import db


def test_reconciliation_scoring():
    engine = get_reconciliation_engine()

    source = {
        "id": "deb_axis_1",
        "amount": -20000.0,
        "amount_paise": -2000000,
        "txn_date": "2026-06-15",
        "description": "NEFT TRANSFER TO SBI A/C",
        "account": "axis",
    }
    target = {
        "id": "cred_sbi_1",
        "amount": 20000.0,
        "amount_paise": 2000000,
        "txn_date": "2026-06-15",
        "description": "NEFT CREDIT FROM AXIS BANK",
        "account": "sbi",
    }

    cand = engine.score_pair(source, target)
    assert cand is not None
    assert cand.amount_score == 40.0
    assert cand.date_score == 25.0
    assert cand.direction_score == 20.0
    assert cand.context_score > 0
    assert cand.total_score >= 85.0
    assert cand.confidence >= 0.85


def test_review_queue_lifecycle():
    item_id = "test_review_ambiguous_txn_999"
    db.upsert_review_item({
        "id": "rev_test_1",
        "item_type": "classification",
        "item_id": item_id,
        "reason": "Low confidence match: 0.52",
        "candidate_data": {"candidates": ["Food & Dining", "Shopping"]},
        "status": "pending",
    })

    pending = db.load_review_queue(status="pending")
    assert not pending[pending["id"] == "rev_test_1"].empty

    # Resolve
    success = db.resolve_review_item("rev_test_1", "resolved", resolution={"chosen_category": "Food & Dining"})
    assert success is True

    pending_after = db.load_review_queue(status="pending")
    assert pending_after[pending_after["id"] == "rev_test_1"].empty


def test_statement_validation_math():
    # 1. Balanced statement
    rep_balanced = validate_statement(
        account_id="axis",
        opening_balance_paise=10000000,   # ₹1,00,000
        credits_paise=5000000,           # +₹50,000
        debits_paise=3000000,            # -₹30,000
        closing_balance_paise=12000000,  # ₹1,20,000
        period_start="2026-06-01",
        period_end="2026-06-30",
    )
    assert rep_balanced.status == "balanced"
    assert rep_balanced.variance_paise == 0

    # 2. Statement with variance discrepancy
    rep_variance = validate_statement(
        account_id="axis",
        opening_balance_paise=10000000,   # ₹1,00,000
        credits_paise=5000000,           # +₹50,000
        debits_paise=3000000,            # -₹30,000
        closing_balance_paise=11950000,  # ₹1,19,500 (₹500 missing)
        period_start="2026-06-01",
        period_end="2026-06-30",
    )
    assert rep_variance.status == "variance_detected"
    assert rep_variance.variance_paise == 50000  # ₹500
