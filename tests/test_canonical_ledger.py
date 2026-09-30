"""Unit tests for exact money arithmetic, canonical ledger events, and account models (Changes 2, 3, 4, 11, 12)."""
from __future__ import annotations

from decimal import Decimal
from finance.money import Money, rupees_to_paise, paise_to_rupees, format_inr_paise, format_paise_to_lakhs
from finance import db


def test_exact_money_class():
    m1 = Money.from_rupees("100.50")
    m2 = Money.from_rupees("200.25")
    m3 = m1 + m2
    assert m3.paise == 30075
    assert m3.rupees == 300.75

    # Multiplier
    m4 = m1 * 3
    assert m4.paise == 30150

    # Negative / subtraction
    m5 = m2 - m1
    assert m5.paise == 9975

    # Formatting
    assert "₹300.75" in m3.format_inr()
    assert format_paise_to_lakhs(38600000) == "₹3.86L"


def test_accounts_model():
    acc_id = "test_bank_kotak"
    db.upsert_account({
        "id": acc_id,
        "name": "Kotak 811 Savings",
        "account_type": "bank",
        "institution": "Kotak Mahindra Bank",
        "currency": "INR",
        "last_four": "5678",
        "status": "active",
        "ownership": "personal",
    })

    accs = db.load_accounts(account_type="bank")
    matched = accs[accs["id"] == acc_id]
    assert not matched.empty
    assert matched.iloc[0]["institution"] == "Kotak Mahindra Bank"


def test_canonical_ledger_sync():
    inserted, updated = db.sync_canonical_ledger()
    can_events = db.load_canonical_events()
    assert not can_events.empty
    # Every canonical event must have integer amount_paise and valid event_type
    for _, ev in can_events.head(20).iterrows():
        assert isinstance(int(ev["amount_paise"]), int)
        assert ev["event_type"] in [
            "income", "expense", "asset_acquisition", "asset_disposal",
            "liability_drawdown", "liability_payment", "transfer",
            "reimbursement", "refund", "fee", "tax", "cash_withdrawal",
            "cash_deposit", "adjustment"
        ]


def test_audit_and_provenance():
    # Audit event
    aid = db.record_audit_event(
        entity_type="transaction",
        entity_id="txn_test_123",
        action="classified",
        actor="rule_engine",
        before={"category": "Uncategorized"},
        after={"category": "Food & Dining"},
        reason="Matched Swiggy rule",
    )
    assert aid.startswith("aud_")
    audits = db.load_audit_events(limit=5)
    assert not audits.empty
    assert audits.iloc[0]["action"] == "classified"

    # Provenance
    pid = db.record_provenance(
        import_id="imp_test_axis_2026_06",
        file_hash="sha256_mock_hash_12345",
        source="csv",
        account_id="axis",
        statement_period="2026-06",
    )
    assert pid == "imp_test_axis_2026_06"
    provs = db.load_provenance(import_id="imp_test_axis_2026_06")
    assert not provs.empty
    assert provs.iloc[0]["file_hash"] == "sha256_mock_hash_12345"
