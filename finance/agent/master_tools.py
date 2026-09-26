"""Deterministic financial intelligence tools.

These tools calculate from current database state. They contain no user-specific
balances, names, employers, loan amounts, or hard-coded recommendations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta
from langchain_core.tools import tool

from .. import config, db
from ..metrics import monthly_cashflow
from . import tools as bank_tools
from . import cc_tools

if db.DB_PATH is None:
    default_db = Path(__file__).resolve().parents[2] / "data" / "finance.db"
    if default_db.exists():
        db.set_db_path(str(default_db))

def _inr(value) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("1"))
    sign = "-" if amount < 0 else ""
    return f"{sign}₹{abs(int(amount)):,}"

def _borrower_groups(loans: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if loans.empty:
        return loans, loans
    borrower = loans.get("borrower", pd.Series("user", index=loans.index)).fillna("user").astype(str)
    user = loans[borrower.str.lower() == "user"]
    passthrough = loans[borrower.str.lower() != "user"]
    return user, passthrough

@tool
def master_financial_summary(month: str = "") -> str:
    """Deterministic monthly cashflow summary.

    month must be YYYY-MM. Blank means the current calendar month; "latest"
    explicitly means the latest month present in imported transaction data.
    """
    txns = db.load_all()
    if txns.empty:
        return "No bank transaction data imported yet."

    requested = month.strip().lower()
    if requested == "latest":
        target = sorted(txns["txn_date"].astype(str).str[:7].unique())[-1]
    elif requested:
        target = requested
        if len(target) != 7 or target[4] != "-":
            return "Invalid month. Use YYYY-MM or 'latest'."
    else:
        target = date.today().strftime("%Y-%m")

    m = monthly_cashflow(txns, target)
    loans = db.load_bank_loans()
    user_loans, passthrough_loans = _borrower_groups(loans)

    user_emi = user_loans["monthly_emi"].map(Decimal).sum() if not user_loans.empty else Decimal("0")
    passthrough_emi = passthrough_loans["monthly_emi"].map(Decimal).sum() if not passthrough_loans.empty else Decimal("0")

    balances = db.load_account_balances()
    liquid = Decimal("0")
    if not balances.empty:
        liquid = sum((Decimal(str(x)) for x in balances["total_balance"]), Decimal("0"))

    return "\n".join([
        f"**Financial Summary — {target}**",
        f"- Income: {_inr(m['income'].major)}",
        f"- Spending: {_inr(m['spend'].major)}",
        f"- Internal transfers: {_inr(m['transfers'].major)}",
        f"- Net cashflow from classified income/spend: {_inr((m['income'] - m['spend']).major)}",
        f"- Tracked liquid balances: {_inr(liquid)}",
        f"- User loan EMI total: {_inr(user_emi)}/month",
        f"- Non-user/pass-through loan EMI total: {_inr(passthrough_emi)}/month",
        "",
        "**Coverage:** figures are derived from imported records for the requested calendar month; "
        "missing statements or unclassified rows can make the result partial.",
    ])

@tool
def master_debt_and_dti_overview() -> str:
    """Inventory tracked liabilities without relying on hard-coded loan names."""
    loans = db.load_bank_loans()
    txns = db.load_all()
    cc_stmts = db.load_cc_statements()
    cc_emis = db.load_cc_emis()

    user, passthrough = _borrower_groups(loans)
    user_emi = Decimal(str(user["monthly_emi"].sum())) if not user.empty else Decimal("0")
    user_principal = Decimal(str(user["remaining_principal"].sum())) if not user.empty else Decimal("0")
    other_emi = Decimal(str(passthrough["monthly_emi"].sum())) if not passthrough.empty else Decimal("0")
    other_principal = Decimal(str(passthrough["remaining_principal"].sum())) if not passthrough.empty else Decimal("0")
    cc_due = Decimal(str(cc_stmts["total_due"].sum())) if not cc_stmts.empty else Decimal("0")
    cc_emi = Decimal(str(cc_emis["monthly_emi"].sum())) if not cc_emis.empty else Decimal("0")

    income = txns[txns["classification"] == config.CLASSIFICATION_INCOME] if not txns.empty else pd.DataFrame()
    monthly_income = Decimal("0")
    if not income.empty:
        grouped = income.groupby(income["txn_date"].astype(str).str[:7])["amount"].sum()
        if not grouped.empty:
            monthly_income = Decimal(str(grouped.iloc[-1]))

    dti = (user_emi / monthly_income * 100) if monthly_income else Decimal("0")
    out = [
        "**Debt & Fixed-Commitment Inventory**",
        f"- User loan EMI: {_inr(user_emi)}/month",
        f"- User remaining principal: {_inr(user_principal)}",
        f"- User DTI using latest classified income: {dti.quantize(Decimal('0.1'))}%",
        f"- Pass-through loan EMI: {_inr(other_emi)}/month",
        f"- Pass-through loan principal: {_inr(other_principal)}",
        f"- Credit-card statement dues currently stored: {_inr(cc_due)}",
        f"- Credit-card EMI schedule currently stored: {_inr(cc_emi)}/month",
        "",
        "Credit-card statement dues and component EMIs are shown separately as source "
        "facts and must not be summed unless the statement model explicitly says they are separate obligations.",
    ]
    return "\n".join(out)

@tool
def master_debt_free_roadmap() -> str:
    """Project tracked loan/EMI end months from explicit remaining tenures."""
    loans = db.load_bank_loans()
    emis = db.load_cc_emis()
    events = []
    today = date.today().replace(day=1)

    for _, row in loans.iterrows():
        remaining = int(row.get("remaining_tenure", 0) or 0)
        if remaining > 0:
            end = today + relativedelta(months=remaining)
            events.append((end, str(row.get("loan_name") or "Loan"), Decimal(str(row.get("monthly_emi") or 0))))
    for _, row in emis.iterrows():
        remaining = int(row.get("remaining_tenure", 0) or 0)
        if remaining > 0:
            end = today + relativedelta(months=remaining)
            name = f"{row.get('card_name', 'Card')} — {row.get('merchant_name', 'EMI')}"
            events.append((end, name, Decimal(str(row.get("monthly_emi") or 0))))

    if not events:
        return "No active loan or card-EMI schedules with remaining tenure were found."

    events.sort(key=lambda x: x[0])
    out = ["**Debt Schedule Projection**"]
    current = sum((amount for _, _, amount in events), Decimal("0"))
    for end, name, amount in events:
        current = max(Decimal("0"), current - amount)
        out.append(f"- **{end.strftime('%B %Y')}**: {name} — {_inr(amount)}/month ends; projected remaining scheduled EMI {_inr(current)}")
    out.append("")
    out.append("This is a schedule projection, not a principal/interest calculation. Exact payoff dates depend on lender terms and actual payments.")
    return "\n".join(out)

@tool
def master_liquidity_and_upcoming_outflows() -> str:
    """List currently stored due dates and recurring loan debit amounts."""
    loans = db.load_bank_loans()
    stmts = db.load_cc_statements()
    items = []

    for _, row in loans.iterrows():
        day = int(row.get("debit_day", 0) or 0)
        items.append((day, str(row.get("loan_name") or "Loan"), Decimal(str(row.get("monthly_emi") or 0)), "loan"))

    for _, row in stmts.iterrows():
        due = str(row.get("due_date") or "")
        day = int(due[8:10]) if len(due) >= 10 and due[8:10].isdigit() else 0
        items.append((day, str(row.get("card_name") or "Credit card"), Decimal(str(row.get("total_due") or 0)), "statement"))

    if not items:
        return "No upcoming debt or card due records are stored."

    items.sort(key=lambda x: x[0] if x[0] else 99)
    out = ["**Stored Upcoming Outflows**"]
    for day, name, amount, kind in items:
        when = f"day {day}" if day else "date not stored"
        out.append(f"- {when}: {name} ({kind}) — {_inr(amount)}")
    return "\n".join(out)

@tool
def master_prepayment_advisor(extra_cash: float | None = None) -> str:
    """Show debt candidates and missing data needed for a defensible prepayment calculation.

    No hard-coded APR, GST, lender, or merchant assumptions are used. A true
    interest-saving optimizer requires APR/rate, fees, foreclosure terms and
    current principal for each obligation.
    """
    loans = db.load_bank_loans()
    emis = db.load_cc_emis()
    if loans.empty and emis.empty:
        return "No debt schedules are stored."

    out = ["**Prepayment Analysis — Evidence Based**"]
    if extra_cash is not None:
        out.append(f"- Available extra cash supplied: {_inr(extra_cash)}")
    out.append("- The database does not expose enough rate/fee/foreclosure data to claim an exact interest-saving ranking.")

    candidates = []
    for _, row in loans.iterrows():
        candidates.append(("Loan", str(row.get("loan_name") or "Loan"), Decimal(str(row.get("remaining_principal") or 0)), Decimal(str(row.get("monthly_emi") or 0))))
    for _, row in emis.iterrows():
        candidates.append(("Card EMI", f"{row.get('card_name', 'Card')} — {row.get('merchant_name', 'EMI')}", Decimal(str(row.get("loan_amount") or 0)), Decimal(str(row.get("monthly_emi") or 0))))

    for kind, name, principal, emi in sorted(candidates, key=lambda x: x[2], reverse=True):
        out.append(f"- {kind}: {name} | tracked balance/amount {_inr(principal)} | monthly EMI {_inr(emi)}")
    out.append("- Required before optimizing: annual rate, current principal, foreclosure/prepayment fee, tax treatment, and lender-specific terms.")
    return "\n".join(out)

@tool
def ashwin_monthly_dues_and_settlement(month: str = "") -> str:
    """Backward-compatible settlement tool.

    It now uses the borrower field in the database instead of a hard-coded
    person's name. The tool name is retained so existing chat routing continues
    to work.
    """
    target = month.strip() if month.strip() else date.today().strftime("%Y-%m")
    txns = db.load_all()
    loans = db.load_bank_loans()
    stmts = db.load_cc_statements()
    _, passthrough = _borrower_groups(loans)

    monthly_loan = Decimal(str(passthrough["monthly_emi"].sum())) if not passthrough.empty else Decimal("0")
    statement_due = Decimal(str(stmts["total_due"].sum())) if not stmts.empty else Decimal("0")

    deposits = txns[
        txns["txn_date"].astype(str).str.startswith(target)
        & txns["classification"].eq(config.CLASSIFICATION_FRIEND_DEPOSIT)
    ] if not txns.empty else pd.DataFrame()
    already_sent = Decimal(str(deposits["amount"].sum())) if not deposits.empty else Decimal("0")
    gross = statement_due + monthly_loan
    remaining = max(Decimal("0"), gross - already_sent)

    out = [
        f"**Pass-through Settlement — {target}**",
        f"- Stored statement dues: {_inr(statement_due)}",
        f"- Stored pass-through loan EMIs: {_inr(monthly_loan)}",
        f"- Gross tracked obligation: {_inr(gross)}",
        f"- Recorded deposits in {target}: {_inr(already_sent)}",
        f"- Remaining tracked amount: {_inr(remaining)}",
        "",
        "Coverage is limited to records classified as pass-through deposits and the currently stored statement/loan schedules.",
    ]
    return "\n".join(out)

MASTER_TOOLS = [
    master_financial_summary,
    master_debt_and_dti_overview,
    ashwin_monthly_dues_and_settlement,
    master_debt_free_roadmap,
    master_liquidity_and_upcoming_outflows,
    master_prepayment_advisor,
] + bank_tools.TOOLS + cc_tools.ALL_CC_TOOLS
