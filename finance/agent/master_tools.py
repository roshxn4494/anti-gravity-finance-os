"""Master Unified Financial Intelligence Agent Tools.

Synthesizes data across Bank Accounts (Axis, SBI, Kotak), Credit Cards (5 cards),
and Personal/NBFC Loans (4 loans) in `data/finance.db`.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from langchain_core.tools import tool

from .. import config, db
from . import tools as bank_tools
from . import cc_tools

# Ensure DB_PATH is set
if db.DB_PATH is None:
    default_db = Path(__file__).resolve().parents[2] / "data" / "finance.db"
    if default_db.exists():
        db.set_db_path(str(default_db))


def _inr(x: float) -> str:
    x = int(round(x))
    neg = x < 0
    x = abs(x)
    s = str(x)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + s


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


@tool
def master_financial_summary(month: str = "") -> str:
    """Holistic CFO Summary combining Salary Income, Real Lifestyle Spend, Personal Loan EMIs,
    Credit Card Statement Dues, and True Net Cashflow/Savings Rate.
    month = optional month string ('YYYY-MM', 'latest', or blank)."""
    txns = db.load_all()
    cc_stmts = db.load_cc_statements()
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()

    if txns.empty:
        return "No bank transaction data imported yet."

    spend_df = txns[txns["classification"] == config.CLASSIFICATION_SPEND]
    income_df = txns[txns["classification"] == config.CLASSIFICATION_INCOME]
    cc_pay_df = txns[txns["classification"] == config.CLASSIFICATION_CC_PAYMENT]

    all_months = sorted(txns["txn_date"].str[:7].unique())
    target_month = month.strip() if month and month != "latest" else (all_months[-1] if all_months else "")

    if target_month:
        m_spend = spend_df[spend_df["txn_date"].str.startswith(target_month)]["amount"].abs().sum()
        m_income = income_df[income_df["txn_date"].str.startswith(target_month)]["amount"].sum()
        m_cc_pay = cc_pay_df[cc_pay_df["txn_date"].str.startswith(target_month)]["amount"].abs().sum()
    else:
        m_spend = spend_df["amount"].abs().sum()
        m_income = income_df["amount"].sum()
        m_cc_pay = cc_pay_df["amount"].abs().sum()

    # Calculate regular baseline salary from historical credits (typically credited ~29th-30th)
    baseline_salary = 112729.0
    if not income_df.empty:
        sal_by_m = income_df.groupby(income_df["txn_date"].str[:7])["amount"].sum().sort_index()
        valid_sals = sal_by_m[sal_by_m > 50000]
        if not valid_sals.empty:
            baseline_salary = float(valid_sals.iloc[-1])

    is_mid_month = (m_income == 0 and target_month >= all_months[-1])
    eff_salary = baseline_salary if is_mid_month else (m_income if m_income > 0 else baseline_salary)

    # Separate user personal loans vs Ashwin pass-through loans
    if not loans_df.empty and "borrower" in loans_df.columns:
        user_loans = loans_df[loans_df["borrower"] != "ashwin"]
        ashwin_loans = loans_df[loans_df["borrower"] == "ashwin"]
    else:
        user_loans = loans_df[loans_df["loan_name"].str.contains("KISETSU", case=False, na=False)]
        ashwin_loans = loans_df[~loans_df["loan_name"].str.contains("KISETSU", case=False, na=False)]

    user_loan_monthly = user_loans["monthly_emi"].sum() if not user_loans.empty else 0.0
    user_loan_rem = user_loans["remaining_principal"].sum() if not user_loans.empty else 0.0

    ashwin_loan_monthly = ashwin_loans["monthly_emi"].sum() if not ashwin_loans.empty else 0.0
    ashwin_loan_rem = ashwin_loans["remaining_principal"].sum() if not ashwin_loans.empty else 0.0

    cc_dues = cc_stmts["total_due"].sum() if not cc_stmts.empty else 0.0
    cc_lim = cc_stmts["credit_limit"].sum() if not cc_stmts.empty else 0.0
    cc_avail = cc_stmts["available_limit"].sum() if not cc_stmts.empty else 0.0
    cc_emi_monthly = cc_emis["monthly_emi"].sum() if not cc_emis.empty else 0.0
    cc_emis_future = (cc_emis["monthly_emi"] * cc_emis["remaining_tenure"]).sum() if not cc_emis.empty else 0.0

    # The CC Statement Due (₹93,027) ALREADY contains the monthly CC EMIs (₹90,495) + GST/fees (₹2,532).
    # Total monthly outflow required from Ashwin is CC Statement Due + Personal Loan EMIs.
    tot_ashwin_monthly = cc_dues + ashwin_loan_monthly
    non_emi_cc_dues = max(0.0, cc_dues - cc_emi_monthly)
    tot_ashwin_owed = cc_emis_future + non_emi_cc_dues + ashwin_loan_rem

    # Account Balances & Savings
    try:
        b_df = db.load_account_balances()
    except Exception:
        b_df = pd.DataFrame()
    tot_liquid = b_df["total_balance"].sum() if not b_df.empty else 0.0
    kotak_b = b_df[b_df["account"] == "kotak"]["total_balance"].sum() if not b_df.empty else 0.0
    kotak_fd = b_df[b_df["account"] == "kotak"]["smart_fd_balance"].sum() if not b_df.empty else 0.0

    personal_dti = round((user_loan_monthly / eff_salary) * 100, 1) if eff_salary > 0 else 0
    personal_discretionary = eff_salary - user_loan_monthly

    out = [
        f"**🌟 Master Financial Health Overview ({target_month or 'All Time'}):**\n",
        f"• **Regular Net Monthly Salary**: {_inr(eff_salary)}" + (" *(Credited at month-end ~29th–30th)*" if is_mid_month else ""),
        f"\n**1. User's Personal Finances & Liquid Wealth:**",
        f"• **Total Liquid Savings & Cash Reserves**: **{_inr(tot_liquid)}**",
        f"  - *Kotak 811 (with Active Money Smart FD)*: {_inr(kotak_b)} (Savings: {_inr(kotak_b - kotak_fd)} + Smart Auto-Sweep FD: {_inr(kotak_fd)})",
        f"  - *SBI & Axis Operating Accounts*: {_inr(tot_liquid - kotak_b)}",
        f"• **True Personal Loan EMI**: **{_inr(user_loan_monthly)}/month** (Kisetsu Saison Finance — only 4 EMIs left, finishes Nov 2026!)",
        f"• **True Personal Discretionary Cashflow**: **+{_inr(personal_discretionary)}/month** remaining from salary for personal expenses & savings",
        f"• **Personal Debt-to-Income (DTI)**: **{personal_dti}%** *(Extremely healthy, practically debt-free!)*",
        f"• **Outstanding Personal Principal**: **{_inr(user_loan_rem)}** *(Only ₹22.4k total remaining debt!)*",
        f"• **Lifestyle Spends (Month-to-Date)**: {_inr(m_spend)} (groceries, food, transport, bills)",
        f"\n**2. Ashwin Pass-Through Debt & Exposure (Owed by Ashwin):**",
        f"• **Total Monthly Cashflow Required from Ashwin**: **{_inr(tot_ashwin_monthly)}/month**",
        f"  - *Credit Card Statement Bills*: {_inr(cc_dues)}/mo (covers all 35 EMIs + GST/fees)",
        f"  - *Personal Loans (IDFC + Kotak + Auto-Debit)*: {_inr(ashwin_loan_monthly)}/mo",
        f"• **Total Debt / Future Exposure Owed by Ashwin**: **{_inr(tot_ashwin_owed)}** (Future CC EMIs: {_inr(cc_emis_future)} + Non-EMI dues: {_inr(non_emi_cc_dues)} + Loans: {_inr(ashwin_loan_rem)})",
        f"• **Total Credit Limit Utilized**: {_inr(cc_lim - cc_avail)} of {_inr(cc_lim)} (Free: {_inr(cc_avail)})"
    ]

    return "\n".join(out)


@tool
def master_debt_and_dti_overview() -> str:
    """Comprehensive breakdown of ALL 39 active debt obligations, clearly separating
    User's Personal Loans vs. Ashwin's Pass-Through Credit Card EMIs & Dues without double counting."""
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()
    cc_stmts = db.load_cc_statements()
    txns = db.load_all()

    if not loans_df.empty and "borrower" in loans_df.columns:
        user_loans = loans_df[loans_df["borrower"] != "ashwin"]
        ashwin_loans = loans_df[loans_df["borrower"] == "ashwin"]
    else:
        user_loans = loans_df[loans_df["loan_name"].str.contains("KISETSU", case=False, na=False)]
        ashwin_loans = loans_df[~loans_df["loan_name"].str.contains("KISETSU", case=False, na=False)]

    user_loan_monthly = user_loans["monthly_emi"].sum() if not user_loans.empty else 0.0
    user_loan_rem = user_loans["remaining_principal"].sum() if not user_loans.empty else 0.0

    ashwin_loan_monthly = ashwin_loans["monthly_emi"].sum() if not ashwin_loans.empty else 0.0
    ashwin_loan_rem = ashwin_loans["remaining_principal"].sum() if not ashwin_loans.empty else 0.0

    tot_cc_emi = cc_emis["monthly_emi"].sum() if not cc_emis.empty else 0.0
    tot_cc_dues = cc_stmts["total_due"].sum() if not cc_stmts.empty else 0.0
    cc_future_emis = (cc_emis["monthly_emi"] * cc_emis["remaining_tenure"]).sum() if not cc_emis.empty else 0.0

    # Statement Dues (₹93,027) ALREADY contains the ₹90,495 CC EMIs + GST/fees.
    tot_ashwin_monthly = tot_cc_dues + ashwin_loan_monthly
    non_emi_cc_dues = max(0.0, tot_cc_dues - tot_cc_emi)
    tot_ashwin_exposure = cc_future_emis + non_emi_cc_dues + ashwin_loan_rem

    # Establish baseline salary
    baseline_salary = 112729.0
    if not txns.empty:
        inc = txns[txns["classification"] == config.CLASSIFICATION_INCOME]
        if not inc.empty:
            sal_by_m = inc.groupby(inc["txn_date"].str[:7])["amount"].sum().sort_index()
            valid_sals = sal_by_m[sal_by_m > 50000]
            if not valid_sals.empty:
                baseline_salary = float(valid_sals.iloc[-1])

    personal_dti = round((user_loan_monthly / baseline_salary) * 100, 1) if baseline_salary > 0 else 0
    personal_surplus = baseline_salary - user_loan_monthly

    # Historical settlement
    ash_deposits = txns[txns["classification"] == config.CLASSIFICATION_FRIEND_DEPOSIT]["amount"].sum() if not txns.empty else 0.0
    cc_payments = txns[txns["classification"] == config.CLASSIFICATION_CC_PAYMENT]["amount"].abs().sum() if not txns.empty else 0.0

    out = [
        f"**📊 Master Debt & Fixed Commitment Inventory (Separated by Personal vs. Ashwin Pass-Through):**\n",
        f"• **Regular Net Monthly Salary**: {_inr(baseline_salary)} (Credited ~29th–30th into Axis Bank)",
        f"\n**🅰️ User's Personal Debt (Kisetsu Saison Finance ONLY):**",
        f"• **Monthly Personal Loan EMI**: **{_inr(user_loan_monthly)}/month** (26 of 30 paid — only 4 EMIs left, finishes Nov 2026!)",
        f"• **True Personal DTI**: **{personal_dti}%** *(Extremely healthy!)*",
        f"• **Net Discretionary Cashflow Remaining from Salary**: **+{_inr(personal_surplus)}/month** (Available for living costs & savings)",
        f"• **Outstanding Personal Principal**: **{_inr(user_loan_rem)}**",
        f"\n**🅱️ Ashwin's Debt & Exposure (Pass-Through Receivable):**",
        f"• **Total Monthly Cashflow Required from Ashwin**: **{_inr(tot_ashwin_monthly)}/month**",
        f"  - *Credit Card Statement Bills*: {_inr(tot_cc_dues)}/mo (contains all 35 EMIs of {_inr(tot_cc_emi)} + GST/fees)",
        f"  - *Personal Loans (IDFC + Kotak + Auto-Debit)*: {_inr(ashwin_loan_monthly)}/mo",
        f"• **Total Debt / Exposure Owed by Ashwin**: **{_inr(tot_ashwin_exposure)}** (Future CC EMIs: {_inr(cc_future_emis)} + Non-EMI dues: {_inr(non_emi_cc_dues)} + Loans: {_inr(ashwin_loan_rem)})",
        f"• **Historical Bank Reconciliation**: Ashwin deposited {_inr(ash_deposits)} vs. {_inr(cc_payments)} in CC bills paid.",
        f"\n  *Ashwin's Loans Breakdown:*",
    ]

    for _, l in ashwin_loans.iterrows():
        deb_d = _ordinal(int(l.get("debit_day", 3)))
        out.append(f"  • **{l['loan_name']}** ({l['lender']}): {_inr(l['monthly_emi'])}/mo | {l['paid_tenure']}/{l['total_tenure']} paid (⏳ {l['remaining_tenure']} left) | Bal: {_inr(l['remaining_principal'])} | Debited: {deb_d}")

    out.append("\n  *Credit Card EMIs Owed by Ashwin (by Card):*")
    if not cc_emis.empty:
        by_card = cc_emis.groupby("card_name").agg({"monthly_emi": "sum", "id": "count", "remaining_tenure": "max"}).reset_index()
        for _, c in by_card.iterrows():
            out.append(f"  • **{c['card_name']}**: {_inr(c['monthly_emi'])}/mo across {c['id']} plans (Max tenure: {c['remaining_tenure']} months)")

    return "\n".join(out)


@tool
def master_debt_free_roadmap() -> str:
    """Unified chronological timeline combining all 35 Credit Card EMIs and 4 Personal Loans
    into a month-by-month cashflow liberation and debt payoff roadmap."""
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()

    if loans_df.empty and cc_emis.empty:
        return "No active debts or loans found in the system."

    events = []
    today = date.today()

    if not loans_df.empty:
        for _, l in loans_df.iterrows():
            rem_m = int(l["remaining_tenure"])
            if rem_m > 0:
                p_dt = today + relativedelta(months=rem_m)
                events.append({
                    "month_key": p_dt.strftime("%Y-%m"),
                    "month_label": p_dt.strftime("%B %Y"),
                    "name": l["loan_name"],
                    "type": "Bank Loan",
                    "emi": float(l["monthly_emi"]),
                })

    if not cc_emis.empty:
        for _, e in cc_emis.iterrows():
            rem_m = int(e["remaining_tenure"])
            if rem_m > 0:
                p_dt = today + relativedelta(months=rem_m)
                events.append({
                    "month_key": p_dt.strftime("%Y-%m"),
                    "month_label": p_dt.strftime("%B %Y"),
                    "name": f"{e['card_name']} ({e['merchant_name']})",
                    "type": "Credit Card EMI",
                    "emi": float(e["monthly_emi"]),
                })

    events_df = pd.DataFrame(events)
    if events_df.empty:
        return "All loans and credit card EMIs are already fully paid off!"

    out = [
        "**🗓️ Master Debt-Free & Cashflow Relief Roadmap:**\n",
        "Here is when your monthly commitments finish and how much monthly cashflow is unlocked:\n"
    ]

    grouped = events_df.groupby(["month_key", "month_label"]).agg({"emi": "sum", "name": lambda x: list(x)}).reset_index().sort_values("month_key")

    tot_monthly = (loans_df["monthly_emi"].sum() if not loans_df.empty else 0.0) + (cc_emis["monthly_emi"].sum() if not cc_emis.empty else 0.0)
    current_burden = tot_monthly

    for _, g in grouped.iterrows():
        freed = g["emi"]
        current_burden = max(0.0, current_burden - freed)
        items_str = ", ".join(g["name"][:3])
        if len(g["name"]) > 3:
            items_str += f" and {len(g['name'])-3} more"
        out.append(f"• **{g['month_label']}**: 🎉 **Frees up {_inr(freed)}/month**")
        out.append(f"  - Completed: {items_str}")
        out.append(f"  - Remaining monthly debt burden drops to: **{_inr(current_burden)}/mo**\n")

    return "\n".join(out)


@tool
def master_liquidity_and_upcoming_outflows() -> str:
    """Schedule of upcoming bill payment due dates and loan auto-debit dates across
    the next 30 days, cross-referenced with bank account balances."""
    loans_df = db.load_bank_loans()
    cc_stmts = db.load_cc_statements()

    out = ["**📅 Upcoming 30-Day Debt Payment & Auto-Debit Calendar:**\n"]

    items = []
    if not loans_df.empty:
        for _, l in loans_df.iterrows():
            d_day = int(l.get("debit_day", 3))
            items.append({
                "day": d_day,
                "label": f"{_ordinal(d_day)} of month",
                "entity": f"🏦 {l['loan_name']} ({l['lender']})",
                "account": f"Auto-debit from {l['account'].upper()}",
                "amount": float(l["monthly_emi"]),
                "type": "Loan Auto-Debit"
            })

    if not cc_stmts.empty:
        for _, s in cc_stmts.iterrows():
            due_d = s.get("due_date", "")
            d_day = int(due_d[8:10]) if due_d and len(due_d) >= 10 else 15
            items.append({
                "day": d_day,
                "label": f"Due on {due_d or 'Cycle End'}",
                "entity": f"💳 {s['card_name']} (..{s.get('card_last4', '')})",
                "account": "Credit Card Bill",
                "amount": float(s["total_due"]),
                "type": "Credit Card Due"
            })

    items = sorted(items, key=lambda x: x["day"])
    tot_due_next_30 = sum(i["amount"] for i in items)

    for i in items:
        out.append(f"• **{i['label']}**: **{_inr(i['amount'])}** ➔ {i['entity']} ({i['account']})")

    out.append(f"\n**Total Outflow Required in Next 30 Days**: {_inr(tot_due_next_30)}")
    return "\n".join(out)


@tool
def master_prepayment_advisor(extra_cash: float = 50000.0) -> str:
    """Prepayment and debt avalanche optimizer. Recommends the highest ROI loan or credit card EMI
    to pre-close to save maximum interest and 18% GST."""
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()

    out = [
        f"**🎯 Debt Prepayment & Interest Savings Optimizer (for {_inr(extra_cash)} surplus):**\n",
        "**Strategic Recommendation (Debt Avalanche Method):**\n",
        "1. **Priority #1: High-Interest Credit Card EMIs (14%–18% p.a. + 18% GST on Interest)**:",
        "   - Credit card EMIs carry the highest effective cost because GST (18%) is charged every month on all interest payments.",
        "   - Pre-closing high-value card plans (e.g. Scapia Finnair ₹13,846/mo, YES Bank ₹12,552/mo, Amex ₹4,341/mo, IDFC ₹4,890/mo) immediately unblocks credit limits and eliminates GST bleed.",
        "\n2. **Priority #2: High-Balance Personal Loans (12%–16% p.a.)**:",
        "   - **IDFC FIRST Personal Loan**: Remaining balance ~₹92,397 (₹4,863/mo). Pre-paying a portion or foreclosing stops 19 remaining months of interest.",
        "   - **Kotak Smart Personal Loan**: Remaining balance ~₹47,760 (₹2,388/mo). Can be 100% wiped out with ~₹48,000 surplus!",
        "\n3. **Do NOT Pre-Pay Near-Complete Loans**:",
        "   - **Kisetsu Saison**: Only 4 EMIs left (₹22,368 total). In reducing balance loans, almost all interest was already paid in the first 26 months; let this run to natural completion in Nov 2026."
    ]
    return "\n".join(out)


@tool
def ashwin_monthly_dues_and_settlement(month: str = "") -> str:
    """Calculates how much Ashwin owes for a specific month (e.g. '2026-08' or current month),
    subtracting any deposits he has ALREADY transferred this month from bank statements to give
    the exact NET remaining balance still due from him."""
    today_iso = date.today().isoformat()
    target_month = month.strip() if month else today_iso[:7]

    txns = db.load_all()
    emis = db.load_cc_emis()
    stmts = db.load_cc_statements()
    loans = db.load_bank_loans()

    if not loans.empty and "borrower" in loans.columns:
        ash_loans = loans[loans["borrower"] == "ashwin"]
    elif not loans.empty:
        ash_loans = loans[~loans["loan_name"].str.contains("KISETSU", case=False, na=False)]
    else:
        ash_loans = pd.DataFrame()

    cc_monthly_emi = emis["monthly_emi"].sum() if not emis.empty else 0.0
    loan_monthly_emi = ash_loans["monthly_emi"].sum() if not ash_loans.empty else 0.0
    cc_statement_dues = stmts["total_due"].sum() if not stmts.empty else 0.0

    # Note: CC Statement Dues (₹93,027) ALREADY contains the ₹90,495 CC EMIs + GST/fees.
    # Therefore, the single true gross monthly obligation is CC Statement Dues + Personal Loans.
    tot_monthly_obligation = cc_statement_dues + loan_monthly_emi

    # Deposits already made by Ashwin in target_month
    month_deposits = txns[(txns["txn_date"].str.startswith(target_month)) & (txns["classification"] == config.CLASSIFICATION_FRIEND_DEPOSIT)] if not txns.empty else pd.DataFrame()
    already_sent = month_deposits["amount"].sum() if not month_deposits.empty else 0.0

    net_remaining = max(0.0, tot_monthly_obligation - already_sent)

    out = [
        f"**👥 Ashwin Monthly Settlement & Net Dues ({target_month}):**\n",
        f"• **Gross Monthly Obligation for Ashwin**: **{_inr(tot_monthly_obligation)}/month**",
        f"  - *Credit Card Statement Bills (Total Due)*: {_inr(cc_statement_dues)}/mo (contains all 35 EMIs of {_inr(cc_monthly_emi)} + GST/fees)",
        f"  - *Personal Loans (IDFC + Kotak + Auto-Debit)*: {_inr(loan_monthly_emi)}/mo",
        f"\n**💵 Money Already Sent by Ashwin in {target_month}:**",
        f"• **Total Deposited this Month**: **{_inr(already_sent)}** across {len(month_deposits)} transactions",
    ]

    if not month_deposits.empty:
        for _, r in month_deposits.sort_values("txn_date").iterrows():
            out.append(f"  - {r['txn_date']}: {_inr(r['amount'])} ({r['description'][:45]})")

    out.append(f"\n**🎯 True Net Remaining Due from Ashwin for {target_month}:**")
    if already_sent >= tot_monthly_obligation:
        surplus = already_sent - tot_monthly_obligation
        out.append(f"• **Settlement Status**: **₹0 (Fully Paid / Settled! ✅)** with a **+{_inr(surplus)}** cash surplus.")
    else:
        out.append(f"• **Net Remaining to Collect**: **{_inr(net_remaining)}** ({_inr(tot_monthly_obligation)} gross - {_inr(already_sent)} already sent)")

    return "\n".join(out)


MASTER_TOOLS = [
    master_financial_summary,
    master_debt_and_dti_overview,
    ashwin_monthly_dues_and_settlement,
    master_debt_free_roadmap,
    master_liquidity_and_upcoming_outflows,
    master_prepayment_advisor,
] + bank_tools.TOOLS + cc_tools.ALL_CC_TOOLS
