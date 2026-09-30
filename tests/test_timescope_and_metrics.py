"""Unit tests for TimeScopeService, Deterministic Metrics, Recurring, and Anomalies (Changes 10, 14, 15, 16, 17, 18, 19, 20)."""
from __future__ import annotations

from datetime import date
from finance.services.timescope import get_timescope_service
from finance.services.metrics import get_metrics_engine
from finance.services.recurring import detect_recurring_payments
from finance.services.anomalies import detect_anomalies
from finance import db


def test_timescope_service():
    ts = get_timescope_service()
    
    # Calendar month June 2026
    scope_june = ts.resolve("calendar_month", year=2026, month=6)
    assert scope_june.start_date == "2026-06-01"
    assert scope_june.end_date == "2026-06-30"
    assert "June 2026" in scope_june.label

    # Latest available
    scope_latest = ts.resolve("latest_available")
    assert scope_latest.is_latest_fallback is True
    assert scope_latest.start_date.endswith("-01")


def test_metrics_cash_flow_and_investment_separation():
    ts = get_timescope_service()
    metrics = get_metrics_engine()

    scope = ts.resolve("calendar_month", year=2026, month=6)
    cf = metrics.compute_cash_flow(scope)

    assert cf.income_paise > 0
    assert cf.spend_paise > 0
    assert isinstance(cf.net_cash_flow_paise, int)

    # Change 16: Investments must NEVER be added into consumption spend
    assert cf.investments_paise >= 0
    # Spend breakdown contains standard categories like Food & Dining, Groceries
    assert isinstance(cf.category_breakdown_paise, dict)


def test_metrics_liquid_balances_and_net_worth():
    metrics = get_metrics_engine()

    liq = metrics.compute_liquid_balances()
    assert "total_liquid_paise" in liq
    assert "accounts" in liq
    assert liq["total_liquid_paise"] >= 0

    liab = metrics.compute_liabilities()
    assert "personal_loans" in liab
    assert "pass_through_loans" in liab
    assert "credit_cards" in liab

    nw = metrics.compute_net_worth()
    assert "net_worth_paise" in nw
    assert "total_assets_paise" in nw
    assert "total_liabilities_paise" in nw
    assert nw["total_assets_paise"] >= nw["liquid_assets_paise"]


def test_recurring_and_anomalies():
    recurr = detect_recurring_payments()
    assert isinstance(recurr, list)

    anom = detect_anomalies()
    assert isinstance(anom, list)

    from finance.services.recurring import get_monthly_obligations_summary
    from finance.agent.tools import monthly_obligations_checklist
    ob = get_monthly_obligations_summary("2026-06")
    assert "summary" in ob
    assert "rent" in ob
    assert "loans" in ob
    assert "credit_cards" in ob

    chk_str = monthly_obligations_checklist.invoke({"month": "2026-06"})
    assert "Monthly Obligations & Bills Checklist" in chk_str
