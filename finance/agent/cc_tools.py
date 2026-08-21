"""Credit Card Intelligence Agent Tools.

Operates strictly on the separate `credit_cards` dataset in `data/finance.db`.
"""
from __future__ import annotations

from pathlib import Path
import re
from datetime import date
import pandas as pd
from langchain_core.tools import tool

from .. import config, db

# Ensure DB_PATH is set (needed when running outside Streamlit, e.g., in tests or direct agent calls)
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


def _load_stmts() -> pd.DataFrame | None:
    try:
        df = db.load_cc_statements()
        return df if not df.empty else None
    except Exception:
        return None


def _load_txns() -> pd.DataFrame | None:
    try:
        df = db.load_cc_transactions()
        return df if not df.empty else None
    except Exception:
        return None


@tool
def cc_statement_summary(card_name: str = "", month: str = "") -> str:
    """Summary of credit card statement dues, payment due dates, minimum amount due,
    and billing cycles across cards (e.g. HDFC Regalia, ICICI Amazon, Amex).
    card_name = filter by card name/bank (optional)."""
    stmts = _load_stmts()
    if stmts is None or stmts.empty:
        return "No credit card statements imported yet. Go to the Upload tab to import a credit card PDF statement."

    if card_name:
        q = str(card_name).strip().upper()
        stmts = stmts[stmts["card_name"].str.upper().str.contains(q, na=False)]
        if stmts.empty:
            return f"No credit card statement summary found for card '{card_name}'."

    if month:
        m_str = str(month).strip()
        stmts = stmts[stmts["statement_date"].str.startswith(m_str)]

    out = ["Credit Card Statement Summaries:"]
    for _, r in stmts.head(10).iterrows():
        c_label = r["card_name"] + (f" (..{r['card_last4']})" if r["card_last4"] else "")
        due = _inr(r["total_due"])
        min_d = _inr(r["min_due"])
        d_date = r["due_date"] or "Not specified"
        s_date = r["statement_date"] or "—"
        out.append(f"  • {c_label} [Statement {s_date}]: Total Due {_inr(r['total_due'])} | Min Due {min_d} | Due Date: {d_date}")

    return "\n".join(out)


@tool
def cc_card_spend(card_name: str = "", month: str = "") -> str:
    """Total credit card purchases and spend breakdown by card and category.
    card_name = filter by card name (optional). month = filter by month 'YYYY-MM' (optional)."""
    txns = _load_txns()
    if txns is None or txns.empty:
        return "No credit card statement line items imported yet."

    if card_name:
        q = str(card_name).strip().upper()
        txns = txns[txns["card_name"].str.upper().str.contains(q, na=False)]
        if txns.empty:
            return f"No credit card transactions found for card '{card_name}'."

    if month:
        m_str = str(month).strip()
        txns = txns[txns["txn_date"].str.startswith(m_str)]
        if txns.empty:
            return f"No credit card transactions found for period '{month}'."

    debits = txns[txns["amount"] > 0]
    total_spent = debits["amount"].sum()

    out = [f"Credit Card Spend ({'Card: ' + card_name if card_name else 'All Cards'}): {_inr(total_spent)} across {len(debits)} purchases."]

    by_cat = debits.groupby("category")["amount"].sum().sort_values(ascending=False)
    out.append("Spend by category:")
    for cat, val in by_cat.head(6).items():
        out.append(f"  • {cat}: {_inr(val)}")

    return "\n".join(out)


@tool
def cc_reward_points(card_name: str = "") -> str:
    """Reward points earned, redeemed, and current reward points balance across cards."""
    stmts = _load_stmts()
    if stmts is None or stmts.empty:
        return "No credit card statements imported yet."

    if card_name:
        q = str(card_name).strip().upper()
        stmts = stmts[stmts["card_name"].str.upper().str.contains(q, na=False)]

    if stmts.empty:
        return f"No reward points info found for card '{card_name}'."

    out = ["Credit Card Reward Points Summary:"]
    latest_per_card = stmts.sort_values("statement_date").groupby("card_name").last()

    for c_name, r in latest_per_card.iterrows():
        pts_bal = int(r["reward_points_balance"])
        pts_earned = int(r["reward_points_earned"])
        out.append(f"  • {c_name}: {pts_bal:,} available points (earned {pts_earned:,} in latest cycle)")

    return "\n".join(out)


@tool
def cc_fee_tracker(card_name: str = "") -> str:
    """Track finance charges, annual membership fees, late payment charges, and GST on credit cards."""
    txns = _load_txns()
    stmts = _load_stmts()

    out = ["Credit Card Fees & Finance Charges Tracker:"]
    total_fees = 0.0

    if stmts is not None and not stmts.empty:
        fin_chg = stmts["finance_charges"].sum()
        if fin_chg > 0:
            out.append(f"  • Statement Finance Charges: {_inr(fin_chg)}")
            total_fees += fin_chg

    if txns is not None and not txns.empty:
        fee_kws = ["FEE", "CHARGE", "GST", "INTEREST", "FINANCE", "ANNUAL", "LATE"]
        pattern = "|".join(fee_kws)
        fee_txns = txns[txns["description"].str.upper().str.contains(pattern, na=False)]
        if not fee_txns.empty:
            out.append(f"  • Line Item Charges/Fees: {_inr(fee_txns['amount'].sum())} across {len(fee_txns)} items:")
            for _, r in fee_txns.head(5).iterrows():
                out.append(f"    - {r['txn_date']} {r['card_name']}: {_inr(r['amount'])} ({r['description'][:40]})")
            total_fees += fee_txns["amount"].sum()

    if total_fees == 0:
        out.append("  • No finance charges, annual fees, or late fees recorded! 🎉")

    return "\n".join(out)


@tool
def cc_line_items(merchant: str = "", card_name: str = "", month: str = "") -> str:
    """Search specific credit card line items/purchases by merchant or description (e.g. Swiggy, Amazon, Uber, Apple)."""
    txns = _load_txns()
    if txns is None or txns.empty:
        return "No credit card transaction line items imported yet."

    hit = txns
    if merchant:
        q = str(merchant).strip().upper()
        hit = hit[hit["description"].str.upper().str.contains(q, na=False)
                  | hit["counterparty"].str.upper().str.contains(q, na=False)]

    if card_name:
        c_q = str(card_name).strip().upper()
        hit = hit[hit["card_name"].str.upper().str.contains(c_q, na=False)]

    if month:
        m_q = str(month).strip()
        hit = hit[hit["txn_date"].str.startswith(m_q)]

    if hit.empty:
        return f"No credit card purchases found matching '{merchant}'."

    total = hit[hit["amount"] > 0]["amount"].sum()
    out = [f"Credit Card Line Items matching '{merchant}': {_inr(total)} across {len(hit)} purchases:", "Transactions:"]

    for _, r in hit.head(10).iterrows():
        out.append(f"  • {r['txn_date']} [{r['card_name']}] {_inr(r['amount'])} — {r['description'][:50]}")

    return "\n".join(out)


@tool
def cc_active_emis(card_name: str = "") -> str:
    """Lists active EMIs, loan amounts, monthly EMI payments, and remaining installments left across credit cards.
    card_name = filter by card name (optional)."""
    try:
        emis = db.load_cc_emis()
    except Exception:
        emis = pd.DataFrame()

    if emis.empty:
        return "No active EMIs or loan schedules found in imported credit card statements."

    if card_name:
        q = str(card_name).strip().upper()
        emis = emis[emis["card_name"].str.upper().str.contains(q, na=False)]
        if emis.empty:
            return f"No active EMIs found matching card '{card_name}'."

    lines = ["**Active EMIs & Loan Schedules:**"]
    tot_monthly = 0.0
    for _, r in emis.iterrows():
        c_name = r["card_name"]
        last4 = f" (..{r['card_last4']})" if r.get("card_last4") else ""
        mch = r["merchant_name"]
        loan_amt = _inr(r["loan_amount"]) if r["loan_amount"] else "—"
        emi_val = _inr(r["monthly_emi"]) if r["monthly_emi"] else "—"
        tot_m = r["total_tenure"]
        paid_m = r["paid_tenure"]
        rem_m = r["remaining_tenure"]
        tot_monthly += r["monthly_emi"]

        lines.append(f"• **{c_name}{last4}**: {mch} | Loan Amount: {loan_amt} | Monthly EMI: {emi_val} | Tenure: {paid_m}/{tot_m} months | **{rem_m} EMIs remaining**")

    lines.append(f"\n**Total Monthly EMI Commitment:** {_inr(tot_monthly)}/month")
    return "\n".join(lines)


@tool
def cc_monthly_bills_and_repayments(month: str = "") -> str:
    """Monthly sum of all Credit Card Bills (Total Due across all cards) and actual monthly CC bill repayments made from bank accounts.
    month = optional filter for a specific month (e.g. '2026-07', '2026-08', 'latest')."""
    stmts = _load_stmts()
    try:
        df_bank = db.load_all()
        if not df_bank.empty:
            df_bank_cc = df_bank[df_bank["classification"] == config.CLASSIFICATION_CC_PAYMENT]
        else:
            df_bank_cc = pd.DataFrame()
    except Exception:
        df_bank_cc = pd.DataFrame()

    out = ["**Credit Card Monthly Bills & Repayments Overview:**\n"]

    if stmts is not None and not stmts.empty:
        df_s = stmts.copy()
        df_s["month"] = df_s["statement_date"].str[:7]
        if month:
            m_str = str(month).strip()
            if m_str.lower() == "latest":
                avail = sorted(df_s["month"].dropna().unique())
                m_str = avail[-1] if avail else ""
            if m_str:
                df_s = df_s[df_s["month"] == m_str]

        out.append("**1. Monthly Credit Card Statement Bills (Total Due across cards):**")
        for m, grp in df_s.groupby("month", sort=False):
            m_tot = grp["total_due"].sum()
            out.append(f"• **Month {m}**: Total CC Bills = **{_inr(m_tot)}** across {len(grp)} cards:")
            for _, r in grp.iterrows():
                last4 = f" (..{r['card_last4']})" if r.get("card_last4") else ""
                out.append(f"  - {r['card_name']}{last4}: Total Due {_inr(r['total_due'])} | Min Due {_inr(r['min_due'])} (Due: {r['due_date'] or '—'})")

        if not month:
            out.append(f"\n**Total Active Credit Card Bills Across All Cards**: {_inr(stmts['total_due'].sum())}")
    else:
        out.append("No credit card statements imported yet.")

    if not df_bank_cc.empty:
        df_b = df_bank_cc.copy()
        df_b["month"] = df_b["txn_date"].str[:7]
        if month:
            m_str = str(month).strip()
            if m_str.lower() == "latest":
                avail = sorted(df_b["month"].dropna().unique())
                m_str = avail[-1] if avail else ""
            if m_str:
                df_b = df_b[df_b["month"] == m_str]

        out.append("\n**2. Monthly Bank Account CC Bill Repayments (Debits to CCs / Cred / BBPS / NEFT):**")
        months_seen = sorted(df_b["month"].unique(), reverse=True)
        for m in months_seen[:8]:
            grp = df_b[df_b["month"] == m]
            tot_paid = grp["amount"].abs().sum()
            out.append(f"• **Month {m}**: Repaid **{_inr(tot_paid)}** ({len(grp)} CC payments from bank accounts)")

    return "\n".join(out)


ALL_CC_TOOLS = [
    cc_statement_summary,
    cc_monthly_bills_and_repayments,
    cc_card_spend,
    cc_reward_points,
    cc_fee_tracker,
    cc_line_items,
    cc_active_emis,
]
