"""Tests for Credit Card Rewards & Miles Optimizer Engine and Agent Tool."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pandas as pd

from finance import db
from finance.rewards import evaluate_card_portfolio, optimize_flight_booking
from finance.rewards.catalog import CARD_PROGRAMS, FLIGHT_BENCHMARKS
from finance.agent.master_tools import recommend_points_redemption


def test_rewards_db_schema_and_seeding():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = str(Path(tmpdir) / "test_finance.db")
        db.set_db_path(test_db)
        db.init_db()

        # Insert a sample statement with reward points
        db.save_cc_statement({
            "card_name": "Axis Bank Credit Card",
            "card_last4": "9788",
            "statement_date": "2026-08-25",
            "due_date": "2026-09-14",
            "total_due": 25000.0,
            "min_due": 1250.0,
            "credit_limit": 300000.0,
            "available_limit": 275000.0,
            "cash_limit": 60000.0,
            "reward_points_balance": 18500.0,
            "reward_points_earned": 1200.0,
            "finance_charges": 0.0,
            "source_file": "axis_stmt.pdf",
        })

        db.seed_card_rewards_from_statements()
        df = db.load_card_rewards()

        assert not df.empty
        row = df.iloc[0]
        assert row["card_name"] == "Axis Bank Credit Card"
        assert row["card_last4"] == "9788"
        assert float(row["points_balance"]) == 18500.0
        assert row["card_variant"] == "Axis Atlas"


def test_rewards_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = str(Path(tmpdir) / "test_finance.db")
        db.set_db_path(test_db)
        db.init_db()

        # Upsert new card
        db.upsert_card_reward({
            "card_id": "amex_plat_travel_1001",
            "card_name": "American Express",
            "card_variant": "Amex Platinum Travel",
            "card_last4": "1001",
            "points_balance": 48000.0,
            "source": "user_manual",
        })

        df = db.load_card_rewards()
        assert len(df) == 1
        assert df.iloc[0]["points_balance"] == 48000.0

        # Update points balance
        db.upsert_card_reward({
            "card_id": "amex_plat_travel_1001",
            "card_name": "American Express",
            "card_variant": "Amex Platinum Travel",
            "card_last4": "1001",
            "points_balance": 52000.0,
            "source": "user_manual",
        })
        df_updated = db.load_card_rewards()
        assert df_updated.iloc[0]["points_balance"] == 52000.0

        # Delete card
        db.delete_card_reward("amex_plat_travel_1001")
        assert db.load_card_rewards().empty


def test_portfolio_evaluation_math():
    mock_cards = pd.DataFrame([
        {
            "card_id": "axis_atlas",
            "card_name": "Axis Bank",
            "card_variant": "Axis Atlas",
            "card_last4": "9788",
            "points_balance": 20000.0,
        },
        {
            "card_id": "idfc_wealth",
            "card_name": "IDFC FIRST",
            "card_variant": "IDFC FIRST Wealth",
            "card_last4": "5327",
            "points_balance": 10000.0,
        },
    ])

    eval_res = evaluate_card_portfolio(mock_cards)

    assert eval_res["total_points"] == 30000.0
    # Axis baseline: 20,000 * 1.00 = 20,000; IDFC baseline: 10,000 * 0.25 = 2,500 -> Total: 22,500
    assert eval_res["total_baseline_val_inr"] == 22500.0

    # Axis optimal (Accor: 1 EDGE Mile = 2 Accor @ 1.80 = 3.60/pt -> 20,000 * 3.60 = 72,000)
    # IDFC optimal (statement credit 2,500) -> Total: 74,500
    assert eval_res["total_optimal_val_inr"] == 74500.0
    assert eval_res["net_uplift_inr"] == 52000.0

    # Verify best partner on Axis Atlas
    axis_eval = next(c for c in eval_res["cards"] if c["card_variant"] == "Axis Atlas")
    assert axis_eval["best_partner"]["partner"] == "Accor Live Limitless (ALL)"
    assert axis_eval["best_partner"]["transferred_points"] == 40000


def test_flight_booking_optimizer_sufficient_points():
    mock_cards = pd.DataFrame([
        {
            "card_id": "axis_atlas",
            "card_name": "Axis Bank",
            "card_variant": "Axis Atlas",
            "card_last4": "9788",
            "points_balance": 25000.0,
        },
    ])

    res = optimize_flight_booking(
        route_name="India ⇄ Singapore / SE Asia",
        cabin="Economy",
        cash_fare_inr=28000.0,
        cards_df=mock_cards,
    )

    assert res["cabin"] == "Economy"
    assert res["cash_fare_inr"] == 28000.0
    assert res["top_award"] is not None
    assert res["top_award"]["has_enough"] is True
    assert res["top_award"]["card_variant"] == "Axis Atlas"
    assert "🏆 **Top Recommendation" in res["verdict_summary"]


def test_flight_booking_optimizer_insufficient_points():
    mock_cards = pd.DataFrame([
        {
            "card_id": "axis_atlas",
            "card_name": "Axis Bank",
            "card_variant": "Axis Atlas",
            "card_last4": "9788",
            "points_balance": 100.0,
        },
        {
            "card_id": "scapia",
            "card_name": "Scapia Federal",
            "card_variant": "Scapia Federal",
            "card_last4": "4302",
            "points_balance": 5000.0,
        },
    ])

    res = optimize_flight_booking(
        route_name="India ⇄ Dubai / Middle East",
        cabin="Economy",
        cash_fare_inr=24000.0,
        cards_df=mock_cards,
    )

    assert res["top_award"]["has_enough"] is False
    assert res["top_award"]["shortfall"] > 0
    # Should recommend best cash card (Axis Atlas 10%)
    assert res["best_cash_card"]["card_variant"] == "Axis Atlas"
    assert res["best_cash_card"]["flight_earn_rate_pct"] == 10.0


def test_agent_recommend_points_redemption_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = str(Path(tmpdir) / "test_finance.db")
        db.set_db_path(test_db)
        db.init_db()

        db.upsert_card_reward({
            "card_id": "idfc_5327",
            "card_name": "IDFC FIRST Credit Card",
            "card_variant": "IDFC FIRST Wealth",
            "card_last4": "5327",
            "points_balance": 12104.0,
            "source": "user_manual",
        })

        reply = recommend_points_redemption.invoke({
            "query": "Which points should I use for a flight to Singapore?",
            "destination": "Singapore",
            "cash_price": 26000.0,
        })

        assert "Rewards & Miles Optimization" in reply
        assert "IDFC FIRST Wealth" in reply
        assert "12,104" in reply
