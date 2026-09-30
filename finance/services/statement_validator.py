"""Statement validation and balance variance engine (Change 9).

Validates bank and credit card statement integrity:
- Bank Statements: Opening Balance + Total Credits - Total Debits ≈ Closing Balance
- Credit Card Statements: Previous Balance + Purchases/Fees - Payments/Credits ≈ Current Balance
Tracks variances in integer paise and logs signals to statement_validations and review_queue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .. import db
from ..money import Money, format_inr_paise


@dataclass
class ValidationReport:
    account_id: str
    period_start: str
    period_end: str
    opening_balance_paise: int
    closing_balance_paise: int
    credits_paise: int
    debits_paise: int
    calculated_closing_paise: int
    variance_paise: int
    status: str  # 'balanced' | 'variance_detected'
    evidence: str


def validate_statement(
    account_id: str,
    opening_balance_paise: int,
    closing_balance_paise: int,
    credits_paise: int,
    debits_paise: int,
    period_start: str = "",
    period_end: str = "",
    tolerance_paise: int = 100,  # ₹1.00 tolerance
) -> ValidationReport:
    """Validates mathematical balance integrity and stores record in SQLite."""
    calc_close = opening_balance_paise + credits_paise - debits_paise
    variance = abs(calc_close - closing_balance_paise)
    status = "balanced" if variance <= tolerance_paise else "variance_detected"

    if status == "balanced":
        ev = f"Statement balanced. Calculated ₹{calc_close/100:.2f} matches closing ₹{closing_balance_paise/100:.2f} (variance: ₹{variance/100:.2f})."
    else:
        ev = (
            f"Variance detected: Expected ₹{calc_close/100:.2f}, got actual ₹{closing_balance_paise/100:.2f}. "
            f"Discrepancy of ₹{variance/100:.2f}."
        )

    # Persist in DB
    report_dict = {
        "account_id": account_id,
        "statement_period_start": period_start,
        "statement_period_end": period_end,
        "opening_balance_paise": opening_balance_paise,
        "closing_balance_paise": closing_balance_paise,
        "credits_paise": credits_paise,
        "debits_paise": debits_paise,
        "calculated_closing_paise": calc_close,
        "variance_paise": variance,
        "status": status,
    }
    db.record_statement_validation(report_dict)

    if status == "variance_detected":
        db.upsert_review_item({
            "item_type": "statement_mismatch",
            "item_id": f"{account_id}_{period_end}",
            "reason": f"Balance mismatch of ₹{variance/100:.2f} detected on {account_id} statement ending {period_end}",
            "candidate_data": report_dict,
            "status": "pending",
        })

    return ValidationReport(
        account_id=account_id,
        period_start=period_start,
        period_end=period_end,
        opening_balance_paise=opening_balance_paise,
        closing_balance_paise=closing_balance_paise,
        credits_paise=credits_paise,
        debits_paise=debits_paise,
        calculated_closing_paise=calc_close,
        variance_paise=variance,
        status=status,
        evidence=ev,
    )


def audit_account_statements(account_id: str) -> list[ValidationReport]:
    """Scans historical transactions for the given account grouped by month to validate running balances."""
    conn = db.connect()
    txns = pd.read_sql_query(
        "SELECT * FROM transactions WHERE account = ? AND balance IS NOT NULL ORDER BY txn_date ASC",
        conn,
        params=[account_id],
    )
    conn.close()

    if txns.empty or len(txns) < 2:
        return []

    reports = []
    # Group by month
    txns["month"] = txns["txn_date"].str[:7]
    for month, group in txns.groupby("month"):
        sorted_g = group.sort_values(by=["txn_date", "id"])
        first_row = sorted_g.iloc[0]
        last_row = sorted_g.iloc[-1]

        # Invert debits to positive for equation
        creds = group[group["amount"] > 0]["amount"].sum()
        debs = abs(group[group["amount"] < 0]["amount"].sum())

        first_bal = float(first_row.get("balance") or 0.0)
        first_amt = float(first_row.get("amount") or 0.0)
        # Approximate opening balance prior to first transaction of month
        open_bal = first_bal - first_amt
        close_bal = float(last_row.get("balance") or 0.0)

        open_paise = int(round(open_bal * 100))
        close_paise = int(round(close_bal * 100))
        creds_paise = int(round(creds * 100))
        debs_paise = int(round(debs * 100))

        rep = validate_statement(
            account_id=account_id,
            opening_balance_paise=open_paise,
            closing_balance_paise=close_paise,
            credits_paise=creds_paise,
            debits_paise=debs_paise,
            period_start=f"{month}-01",
            period_end=str(last_row["txn_date"]),
        )
        reports.append(rep)

    return reports
