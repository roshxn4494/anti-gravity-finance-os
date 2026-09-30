"""AI Runtime, privacy gatekeeper, and fact verification engine (Changes 21, 23, 24, 25).

Centralizes:
1. Privacy mode enforcement (LOCAL, MINIMIZED, CLOUD_AI)
2. Provider configuration & failover (Groq, Nvidia NIM)
3. Anti-hallucination fact verification
4. Explainable financial answer structuring
"""
from __future__ import annotations

import os
import re
from typing import Any

from .. import profile, security
from ..money import format_inr_paise, format_paise_to_lakhs
from ..security import PrivacyMode, get_current_privacy_mode, is_cloud_ai_allowed, sanitize_html
from .metrics import get_metrics_engine
from .timescope import get_timescope_service


def verify_response_facts(response_text: str, facts: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Checks whether numerical values in AI response correspond to retrieved tool facts.
    
    Returns (is_valid, warnings).
    """
    warnings = []
    # Extract rupee numbers from text (e.g. ₹45,000, 45000, ₹1.2L)
    rupee_matches = re.findall(r"₹\s*([\d,]+(?:\.\d+)?)", response_text)
    if not rupee_matches:
        return True, []

    known_amounts = set()
    for f in facts:
        # Collect paise and rupees from fact payload
        for k, v in f.items():
            if isinstance(v, (int, float)):
                known_amounts.add(round(float(v), 2))
                known_amounts.add(round(float(v) / 100, 2))
            elif isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    if isinstance(sub_v, (int, float)):
                        known_amounts.add(round(float(sub_v), 2))
                        known_amounts.add(round(float(sub_v) / 100, 2))

    for m in rupee_matches:
        clean_num = float(m.replace(",", ""))
        # Allow zero or standard numbers
        if clean_num == 0 or clean_num in known_amounts:
            continue
        # Also check rounded integer
        if round(clean_num) in [round(k) for k in known_amounts]:
            continue
        # If number is very small (e.g. 1-10 percentage or day) ignore
        if clean_num <= 31:
            continue
        warnings.append(f"Unverified figure ₹{clean_num:,.2f} mentioned in response.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def build_local_deterministic_response(query: str) -> str:
    """Produces exact deterministic response when running in LOCAL privacy mode without cloud LLMs."""
    q_lower = query.lower()
    metrics = get_metrics_engine()
    ts = get_timescope_service()

    if "spend" in q_lower or "expense" in q_lower:
        scope = ts.resolve("current_month")
        if "last month" in q_lower or "previous" in q_lower:
            scope = ts.resolve("previous_month")
        cf = metrics.compute_cash_flow(scope)
        cats = [f"- **{k}**: {format_inr_paise(v)}" for k, v in sorted(cf.category_breakdown_paise.items(), key=lambda x: x[1], reverse=True)[:5]]
        return (
            f"### 💳 Spend Breakdown — {scope.label}\n"
            f"**Total Consumption Spend**: {format_inr_paise(cf.spend_paise)}\n"
            f"**Data Coverage**: {scope.coverage.title()} ({scope.coverage_notes})\n\n"
            f"**Top Categories**:\n"
            + "\n".join(cats)
            + f"\n\n*Asset Acquisitions / SIPs: {format_inr_paise(cf.investments_paise)} (excluded from spend)*"
        )

    elif "balance" in q_lower or "bank" in q_lower or "liquid" in q_lower or ("how much" in q_lower and "have" in q_lower):
        liq = metrics.compute_liquid_balances()
        items = [f"- **{acc['label']}**: {acc['total_formatted']} (as of {acc['as_of_date']})" for acc in liq["accounts"].values()]
        return (
            f"### 🏦 Liquid Bank Balances (Deterministic Local Mode)\n"
            f"**Total Available Liquid**: {liq['total_liquid_formatted']}\n\n"
            + "\n".join(items)
            + f"\n\n*Savings: {liq['savings_formatted']} | Smart FD: {liq['fd_formatted']}*\n"
            + f"*Mode: LOCAL (Privacy-First, 0 external AI calls)*"
        )

    elif "debt" in q_lower or "loan" in q_lower or "emi" in q_lower or "card" in q_lower:
        liab = metrics.compute_liabilities()
        p_loans = [f"- **{it['name']}**: EMI {it['monthly_emi_formatted']}, Principal {it['remaining_principal_formatted']}" for it in liab["personal_loans"]["items"]]
        return (
            f"### 📑 Liabilities & Debt Overview (Deterministic Local Mode)\n"
            f"**Total Personal Liabilities**: {liab['total_personal_liabilities_formatted']}\n\n"
            f"**Personal Bank Loans**: {liab['personal_loans']['principal_formatted']}\n"
            + "\n".join(p_loans)
            + f"\n\n**Credit Cards Total Due**: {liab['credit_cards']['total_due_formatted']} (Utilization: {liab['credit_cards']['utilization_pct']}%)\n"
            + f"*Pass-Through Loans Serviced by Counterparty: {liab['pass_through_loans']['principal_formatted']}*"
        )

    elif "net worth" in q_lower or "assets" in q_lower:
        nw = metrics.compute_net_worth()
        return (
            f"### 💎 Net Worth Statement (Deterministic Local Mode)\n"
            f"**Net Worth**: **{nw['net_worth_formatted']}** ({nw['net_worth_lakhs']})\n\n"
            f"- **Liquid Assets**: {nw['liquid_assets_formatted']}\n"
            f"- **Investment Assets**: {nw['investment_assets_formatted']}\n"
            f"- **Total Assets**: {nw['total_assets_formatted']}\n"
            f"- **Personal Liabilities**: {nw['total_liabilities_formatted']}\n\n"
            f"*Mode: LOCAL (Privacy-First, 0 external AI calls)*"
        )

    # General CFO Overview
    scope = ts.resolve("latest_available")
    cf = metrics.compute_cash_flow(scope)
    liq = metrics.compute_liquid_balances()
    nw = metrics.compute_net_worth()
    return (
        f"### 📊 CFO Financial Snapshot ({scope.label})\n"
        f"- **Net Worth**: {nw['net_worth_formatted']}\n"
        f"- **Liquid Cash**: {liq['total_liquid_formatted']}\n"
        f"- **Inflow / Salary**: {format_inr_paise(cf.income_paise)}\n"
        f"- **Consumption Spend**: {format_inr_paise(cf.spend_paise)}\n"
        f"- **Net Cashflow**: {format_inr_paise(cf.net_cash_flow_paise)}\n"
        f"- **Coverage**: {scope.coverage.title()} ({scope.coverage_notes})\n\n"
        f"*Mode: LOCAL (Privacy-First, exact deterministic arithmetic)*"
    )
