"""Unit tests for AI Runtime, Fact Verification, and Anti-Hallucination Guardrails (Changes 21, 23, 24, 25, 30)."""
from __future__ import annotations

import os
from finance.services.ai_runtime import (
    verify_response_facts,
    build_local_deterministic_response,
)
from finance.agent.master_graph import ask_master


def test_local_privacy_mode_deterministic_response():
    # Force LOCAL mode
    os.environ["FINANCE_PRIVACY_MODE"] = "local"
    try:
        res = ask_master("What is my current bank balance?")
        assert "Liquid Bank Balances" in res
        assert "LOCAL" in res
        assert "₹" in res

        # Spend query
        res_spend = ask_master("How much did I spend?")
        assert "Spend Breakdown" in res_spend
        assert "Consumption Spend" in res_spend
    finally:
        os.environ.pop("FINANCE_PRIVACY_MODE", None)


def test_fact_verification():
    facts = [
        {"metric": "spend", "value_paise": 2298900, "value_rupees": 22989.0},
        {"metric": "income", "value_paise": 8500000, "value_rupees": 85000.0},
    ]

    # Valid response containing exact verified numbers
    valid_text = "You spent ₹22,989.00 this month and earned ₹85,000.00."
    is_valid, warnings = verify_response_facts(valid_text, facts)
    assert is_valid is True
    assert len(warnings) == 0

    # Hallucinated response introducing an unsupported figure (e.g. ₹99,999)
    hallucinated_text = "You spent ₹22,989.00 and have a bonus of ₹99,999.00."
    is_valid, warnings = verify_response_facts(hallucinated_text, facts)
    assert is_valid is False
    assert len(warnings) > 0
    assert "99,999" in warnings[0]
