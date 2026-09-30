"""Unit tests for Entity Resolution and Database-driven Rule Engine (Changes 5, 6, 7)."""
from __future__ import annotations

from finance.services.entity_resolver import get_entity_resolver
from finance.services.rule_engine import get_rule_engine
from finance import db


def test_entity_resolver():
    resolver = get_entity_resolver()
    
    # Swiggy
    r1 = resolver.resolve("UPI/SWIGGY/12345/DR/BANGALORE")
    assert r1 is not None
    assert r1.canonical_name == "Swiggy"
    assert r1.category == "Food & Dining"
    assert r1.confidence >= 0.85

    # Uber
    r2 = resolver.resolve("UBER INDIA SYSTEMS PVT LTD")
    assert r2 is not None
    assert r2.canonical_name == "Uber"
    assert r2.category == "Transport & Fuel"

    # BigBasket
    r3 = resolver.resolve("BB DAILY BANGALORE")
    assert r3 is not None
    assert r3.canonical_name == "BigBasket"
    assert r3.category == "Groceries"

    # Amazon Pay
    r4 = resolver.resolve("AMAZON PAY INDIA")
    assert r4 is not None
    assert r4.canonical_name == "Amazon"
    assert r4.category == "Shopping"


def test_rule_engine_evaluation():
    engine = get_rule_engine()

    # Salary Credit
    res1 = engine.classify("SALARY CREDIT FOR JUNE 2026", amount=85000.0, account="axis")
    assert res1.classification == "income"
    assert res1.category == "Salary"
    assert res1.confidence > 0.90

    # Rent Debit
    res2 = engine.classify("HOUSE RENT PAYMENT TO LANDLORD", amount=-25000.0, account="axis")
    assert res2.classification == "spend"
    assert res2.category == "Rent"

    # Override takes highest precedence
    overrides = {"counterparty:special_vendor": {"classification": "investment", "category": "Investments"}}
    res3 = engine.classify("PAYMENT", amount=-5000.0, account="axis", counterparty="special_vendor", overrides=overrides)
    assert res3.classifier == "override"
    assert res3.classification == "investment"
    assert res3.confidence == 1.0


def test_db_rule_persistence():
    rule_id = "test_custom_rule_gym"
    db.upsert_classification_rule({
        "id": rule_id,
        "name": "Cult Fit Gym Membership",
        "priority": 15,
        "scope": "global",
        "condition_type": "substring",
        "condition_value": "CULTFIT",
        "classification": "spend",
        "category": "Healthcare",
        "confidence": 0.98,
        "enabled": 1,
    })

    rules_df = db.load_classification_rules(enabled_only=True)
    matched = rules_df[rules_df["id"] == rule_id]
    assert not matched.empty
    assert matched.iloc[0]["priority"] == 15
