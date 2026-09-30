"""Deterministic financial metrics engine (Changes 15, 16, 17, 18).

Separates:
1. Cash Flow (Income, Consumption Spend, Fees)
2. Asset Acquisitions (Investments, SIPs, Mutual Funds — NOT treated as spend)
3. Net Worth (Liquid Bank Assets + Investments - Outstanding Liabilities)
4. Liabilities & Debt (Loans principal, Credit Card dues & active EMIs, Pass-through debt)
All calculations use exact integer paise arithmetic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .. import config, db
from ..money import (
    Money,
    format_inr_paise,
    format_paise_to_lakhs,
    paise_to_rupees,
    rupees_to_paise,
)
from .timescope import TimeScope, get_timescope_service


@dataclass
class CashFlowMetrics:
    period: TimeScope
    income_paise: int
    other_income_paise: int
    spend_paise: int
    fees_paise: int
    investments_paise: int
    pass_through_in_paise: int
    pass_through_out_paise: int
    transfers_paise: int
    net_cash_flow_paise: int
    transaction_count: int
    category_breakdown_paise: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": {
                "start": self.period.start_date,
                "end": self.period.end_date,
                "label": self.period.label,
                "coverage": self.period.coverage,
            },
            "income": {
                "paise": self.income_paise,
                "rupees": paise_to_rupees(self.income_paise),
                "formatted": format_inr_paise(self.income_paise),
            },
            "consumption_spend": {
                "paise": self.spend_paise,
                "rupees": paise_to_rupees(self.spend_paise),
                "formatted": format_inr_paise(self.spend_paise),
            },
            "investments_asset_acquisition": {
                "paise": self.investments_paise,
                "rupees": paise_to_rupees(self.investments_paise),
                "formatted": format_inr_paise(self.investments_paise),
            },
            "fees": {
                "paise": self.fees_paise,
                "rupees": paise_to_rupees(self.fees_paise),
                "formatted": format_inr_paise(self.fees_paise),
            },
            "pass_through_reimbursements": {
                "received_paise": self.pass_through_in_paise,
                "paid_out_paise": self.pass_through_out_paise,
                "net_reimbursed_formatted": format_inr_paise(self.pass_through_in_paise),
            },
            "net_cash_flow": {
                "paise": self.net_cash_flow_paise,
                "rupees": paise_to_rupees(self.net_cash_flow_paise),
                "formatted": format_inr_paise(self.net_cash_flow_paise),
            },
            "transaction_count": self.transaction_count,
            "category_breakdown": {
                k: {"paise": v, "rupees": paise_to_rupees(v), "formatted": format_inr_paise(v)}
                for k, v in self.category_breakdown_paise.items()
            },
        }


class FinancialMetricsEngine:
    def __init__(self):
        self.ts_service = get_timescope_service()

    def compute_cash_flow(self, scope: TimeScope) -> CashFlowMetrics:
        """Calculates cash flow for the given time scope from canonical ledger / transactions."""
        conn = db.connect()
        query = """
            SELECT * FROM transactions
            WHERE txn_date >= ? AND txn_date <= ?
            ORDER BY txn_date ASC
        """
        df = pd.read_sql_query(query, conn, params=[scope.start_date, scope.end_date])
        conn.close()

        income_p = 0
        other_income_p = 0
        spend_p = 0
        fees_p = 0
        investments_p = 0
        pass_through_in_p = 0
        pass_through_out_p = 0
        transfers_p = 0
        cat_breakdown: dict[str, int] = {}

        for _, r in df.iterrows():
            cls = str(r.get("classification") or "")
            cat = str(r.get("category") or "Uncategorized")
            amt_p = r.get("amount_paise")
            if amt_p is None or pd.isna(amt_p):
                amt_p = rupees_to_paise(float(r.get("amount") or 0.0))
            else:
                amt_p = int(amt_p)

            abs_p = abs(amt_p)

            if cls == config.CLASSIFICATION_INCOME:
                income_p += abs_p
            elif cls == config.CLASSIFICATION_OTHER_INCOME:
                other_income_p += abs_p
            elif cls == config.CLASSIFICATION_FRIEND_DEPOSIT:
                pass_through_in_p += abs_p
            elif cls == config.CLASSIFICATION_CC_PAYMENT:
                pass_through_out_p += abs_p
            elif cls == config.CLASSIFICATION_INVESTMENT:
                investments_p += abs_p
            elif cls == config.CLASSIFICATION_FEE:
                fees_p += abs_p
            elif cls == config.CLASSIFICATION_INTERNAL_TRANSFER:
                transfers_p += abs_p
            elif cls == config.CLASSIFICATION_SPEND:
                spend_p += abs_p
                cat_breakdown[cat] = cat_breakdown.get(cat, 0) + abs_p

        # Total net cash flow = Inflows - Outflows
        total_inflow = income_p + other_income_p + pass_through_in_p
        total_outflow = spend_p + fees_p + pass_through_out_p + investments_p
        net_cash_flow = total_inflow - total_outflow

        return CashFlowMetrics(
            period=scope,
            income_paise=income_p,
            other_income_paise=other_income_p,
            spend_paise=spend_p,
            fees_paise=fees_p,
            investments_paise=investments_p,
            pass_through_in_paise=pass_through_in_p,
            pass_through_out_paise=pass_through_out_p,
            transfers_paise=transfers_p,
            net_cash_flow_paise=net_cash_flow,
            transaction_count=len(df),
            category_breakdown_paise=cat_breakdown,
        )

    def compute_liquid_balances(self) -> dict[str, Any]:
        """Calculates current liquid bank balances across all accounts."""
        b_df = db.load_account_balances()
        total_paise = 0
        savings_paise = 0
        fd_paise = 0
        accounts = {}

        if not b_df.empty:
            for _, r in b_df.iterrows():
                acc = str(r["account"])
                tot = rupees_to_paise(float(r.get("total_balance") or 0.0))
                sav = rupees_to_paise(float(r.get("savings_balance") or 0.0))
                sfd = rupees_to_paise(float(r.get("smart_fd_balance") or 0.0))
                total_paise += tot
                savings_paise += sav
                fd_paise += sfd
                accounts[acc] = {
                    "label": str(r.get("label", acc.title())),
                    "total_paise": tot,
                    "savings_paise": sav,
                    "fd_paise": sfd,
                    "total_formatted": format_inr_paise(tot),
                    "as_of_date": str(r.get("as_of_date", "")),
                }

        return {
            "total_liquid_paise": total_paise,
            "total_liquid_formatted": format_inr_paise(total_paise),
            "savings_paise": savings_paise,
            "savings_formatted": format_inr_paise(savings_paise),
            "fd_paise": fd_paise,
            "fd_formatted": format_inr_paise(fd_paise),
            "accounts": accounts,
        }

    def compute_liabilities(self) -> dict[str, Any]:
        """Computes loan principal and credit card dues, strictly separating personal vs pass-through debt."""
        # 1. Bank Loans
        loans_df = db.load_bank_loans()
        personal_principal_p = 0
        personal_monthly_emi_p = 0
        pass_through_principal_p = 0
        pass_through_monthly_emi_p = 0
        personal_loans = []
        pass_through_loans = []

        if not loans_df.empty:
            for _, r in loans_df.iterrows():
                borrower = str(r.get("borrower") or "user").lower()
                princ_p = rupees_to_paise(float(r.get("remaining_principal") or 0.0))
                emi_p = rupees_to_paise(float(r.get("monthly_emi") or 0.0))
                info = {
                    "id": str(r["id"]),
                    "name": str(r["loan_name"]),
                    "lender": str(r["lender"]),
                    "monthly_emi_paise": emi_p,
                    "monthly_emi_formatted": format_inr_paise(emi_p),
                    "remaining_principal_paise": princ_p,
                    "remaining_principal_formatted": format_inr_paise(princ_p),
                    "remaining_tenure": int(r.get("remaining_tenure") or 0),
                }
                if borrower == "user":
                    personal_principal_p += princ_p
                    personal_monthly_emi_p += emi_p
                    personal_loans.append(info)
                else:
                    pass_through_principal_p += princ_p
                    pass_through_monthly_emi_p += emi_p
                    pass_through_loans.append(info)

        # 2. Credit Cards
        stmts_df = db.load_cc_statements()
        cc_total_due_p = 0
        cc_min_due_p = 0
        cc_total_limit_p = 0
        cc_available_limit_p = 0
        cards = []

        if not stmts_df.empty:
            for _, r in stmts_df.iterrows():
                tdue_p = rupees_to_paise(float(r.get("total_due") or 0.0))
                mdue_p = rupees_to_paise(float(r.get("min_due") or 0.0))
                clim_p = rupees_to_paise(float(r.get("credit_limit") or 0.0))
                alim_p = rupees_to_paise(float(r.get("available_limit") or 0.0))
                cc_total_due_p += tdue_p
                cc_min_due_p += mdue_p
                cc_total_limit_p += clim_p
                cc_available_limit_p += alim_p
                cards.append({
                    "card_name": str(r["card_name"]),
                    "card_last4": str(r.get("card_last4") or ""),
                    "total_due_paise": tdue_p,
                    "total_due_formatted": format_inr_paise(tdue_p),
                    "due_date": str(r.get("due_date") or ""),
                })

        # Credit utilization
        util_pct = (cc_total_due_p / cc_total_limit_p * 100) if cc_total_limit_p > 0 else 0.0

        # Total Personal Liabilities = Personal Loans Principal + Credit Card Statement Dues
        total_personal_liabilities_p = personal_principal_p + cc_total_due_p

        return {
            "personal_loans": {
                "principal_paise": personal_principal_p,
                "principal_formatted": format_inr_paise(personal_principal_p),
                "monthly_emi_paise": personal_monthly_emi_p,
                "monthly_emi_formatted": format_inr_paise(personal_monthly_emi_p),
                "items": personal_loans,
            },
            "pass_through_loans": {
                "principal_paise": pass_through_principal_p,
                "principal_formatted": format_inr_paise(pass_through_principal_p),
                "monthly_emi_paise": pass_through_monthly_emi_p,
                "monthly_emi_formatted": format_inr_paise(pass_through_monthly_emi_p),
                "items": pass_through_loans,
            },
            "credit_cards": {
                "total_due_paise": cc_total_due_p,
                "total_due_formatted": format_inr_paise(cc_total_due_p),
                "min_due_paise": cc_min_due_p,
                "min_due_formatted": format_inr_paise(cc_min_due_p),
                "total_limit_paise": cc_total_limit_p,
                "total_limit_formatted": format_inr_paise(cc_total_limit_p),
                "utilization_pct": round(util_pct, 1),
                "cards": cards,
            },
            "total_personal_liabilities_paise": total_personal_liabilities_p,
            "total_personal_liabilities_formatted": format_inr_paise(total_personal_liabilities_p),
        }

    def compute_net_worth(self) -> dict[str, Any]:
        """Calculates Net Worth: (Liquid Cash + Cumulative Investments) - Personal Liabilities."""
        liquid = self.compute_liquid_balances()
        liab = self.compute_liabilities()

        # Cumulative investments from canonical events / transactions
        conn = db.connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT SUM(ABS(amount_paise)) FROM transactions WHERE classification = ?",
            (config.CLASSIFICATION_INVESTMENT,)
        )
        inv_row = cur.fetchone()
        conn.close()
        inv_paise = int(inv_row[0] or 0) if inv_row else 0

        total_assets_paise = liquid["total_liquid_paise"] + inv_paise
        total_personal_liab_paise = liab["total_personal_liabilities_paise"]
        net_worth_paise = total_assets_paise - total_personal_liab_paise

        return {
            "liquid_assets_paise": liquid["total_liquid_paise"],
            "liquid_assets_formatted": liquid["total_liquid_formatted"],
            "investment_assets_paise": inv_paise,
            "investment_assets_formatted": format_inr_paise(inv_paise),
            "total_assets_paise": total_assets_paise,
            "total_assets_formatted": format_inr_paise(total_assets_paise),
            "total_liabilities_paise": total_personal_liab_paise,
            "total_liabilities_formatted": liab["total_personal_liabilities_formatted"],
            "net_worth_paise": net_worth_paise,
            "net_worth_formatted": format_inr_paise(net_worth_paise),
            "net_worth_lakhs": format_paise_to_lakhs(net_worth_paise),
        }


_metrics_engine: FinancialMetricsEngine | None = None


def get_metrics_engine() -> FinancialMetricsEngine:
    global _metrics_engine
    if _metrics_engine is None:
        _metrics_engine = FinancialMetricsEngine()
    return _metrics_engine
