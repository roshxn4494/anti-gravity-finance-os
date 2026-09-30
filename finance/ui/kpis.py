"""Shared portfolio KPI and exposure computations."""
from __future__ import annotations

import pandas as pd
from .. import db


def get_portfolio_summary() -> dict:
    """Calculate unified cross-domain metrics (Loans, Credit Cards, Available Limits)."""
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()
    cc_stmts = db.load_cc_statements()

    tot_loan_emi = float(loans_df["monthly_emi"].sum()) if not loans_df.empty else 0.0
    tot_cc_emi = float(cc_emis["monthly_emi"].sum()) if not cc_emis.empty else 0.0
    tot_debt_emi = tot_loan_emi + tot_cc_emi

    latest_cc_stmts = (
        cc_stmts.sort_values("statement_date").groupby("card_name", as_index=False).last()
        if not cc_stmts.empty else pd.DataFrame()
    )
    tot_cc_lim = float(latest_cc_stmts["credit_limit"].sum()) if not latest_cc_stmts.empty else 0.0
    tot_cc_avail = float(latest_cc_stmts["available_limit"].sum()) if not latest_cc_stmts.empty else 0.0
    tot_cc_dues = float(latest_cc_stmts["total_due"].sum()) if not latest_cc_stmts.empty else 0.0

    return {
        "loans_df": loans_df,
        "cc_emis": cc_emis,
        "cc_stmts": cc_stmts,
        "latest_cc_stmts": latest_cc_stmts,
        "tot_loan_emi": tot_loan_emi,
        "tot_cc_emi": tot_cc_emi,
        "tot_debt_emi": tot_debt_emi,
        "tot_cc_lim": tot_cc_lim,
        "tot_cc_avail": tot_cc_avail,
        "tot_cc_dues": tot_cc_dues,
        "active_plans_count": len(loans_df) + len(cc_emis),
    }
