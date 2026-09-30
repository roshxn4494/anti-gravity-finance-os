"""Tab: Bank & Personal Loans Tracker."""
from __future__ import annotations

from datetime import date, datetime
import re
import textwrap
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ... import config, db
from ..format import inr, ordinal
from ..theme import layout_plot


def _layout(fig: go.Figure, height: int = 340) -> go.Figure:
    return layout_plot(fig, height=height)
def tab_bank_loans():
    """Dedicated Bank & Personal Loans Tracker."""
    st.header("Bank & Personal Loans Tracker", divider=True)
    st.caption("Track recurring personal loans, NBFC EMIs, installment countdowns, payoff dates, and bank auto-debits.")

    loans_df = db.load_bank_loans()
    all_txns = db.load_all()

    if loans_df.empty:
        st.info("No bank loans tracked yet. Add your first loan below!")
    else:
        # Top KPI Metrics
        tot_orig = loans_df["total_loan_amount"].sum()
        tot_rem = loans_df["remaining_principal"].sum()
        tot_monthly = loans_df["monthly_emi"].sum()
        tot_paid_amt = max(0.0, tot_orig - tot_rem) if tot_orig > 0 else (loans_df["paid_tenure"] * loans_df["monthly_emi"]).sum()

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("Total Original Loans", inr(tot_orig) if tot_orig > 0 else "—")
        col_k2.metric("Total Outstanding Balance", inr(tot_rem))
        col_k3.metric("Monthly Loan Outflow", f"{inr(tot_monthly)}/mo")
        
        repay_pct = round((tot_paid_amt / (tot_paid_amt + tot_rem)) * 100, 1) if (tot_paid_amt + tot_rem) > 0 else 0
        col_k4.metric("Repayment Progress", f"{repay_pct}%", delta=f"{inr(tot_paid_amt)} paid")

        # Section 1: Active Loan Progress Cards
        st.subheader("📋 Active Personal Loans & Installment Countdowns")
        
        for _, loan in loans_df.iterrows():
            lid = loan["id"]
            lname = loan["loan_name"]
            lender = loan["lender"]
            emi_val = float(loan["monthly_emi"])
            tot_amt = float(loan["total_loan_amount"])
            tot_t = int(loan["total_tenure"])
            paid_t = int(loan["paid_tenure"])
            rem_t = int(loan["remaining_tenure"])
            rem_bal = float(loan["remaining_principal"])
            deb_day = int(loan.get("debit_day", 3))
            notes = loan.get("notes", "")

            pct = round((paid_t / tot_t) * 100, 1) if tot_t > 0 else 0
            bar_color = "#10b981" if pct >= 75 else ("#3b82f6" if pct >= 40 else "#f59e0b")

            matched_count = 0
            if not all_txns.empty and loan["match_keyword"]:
                kw = str(loan["match_keyword"]).upper()
                sub_txns = all_txns[all_txns["description"].str.upper().str.contains(kw, na=False) & (all_txns["amount"] < 0)]
                if float(loan.get("match_amount", 0.0)) > 0:
                    sub_txns = sub_txns[sub_txns["amount"].abs() == float(loan["match_amount"])]
                matched_count = len(sub_txns)

            day_str = ordinal(deb_day)
            card_html = textwrap.dedent(f"""
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 18px 22px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <div>
                        <div style="font-size: 11px; font-weight: 700; color: #09090b; background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 6px; padding: 2px 8px; display: inline-block; letter-spacing: 0.04em;">{lender}</div>
                        <div style="font-size: 17px; font-weight: 800; color: #09090b; margin-top: 6px;">{lname}</div>
                        <div style="font-size: 12px; color: #71717a; margin-top: 2px;">{notes}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 11px; font-weight: 700; color: #71717a;">Monthly EMI</div>
                        <div style="font-size: 20px; font-weight: 800; color: #09090b;">{inr(emi_val)}<span style="font-size: 12px; font-weight: 500; color: #71717a;">/mo</span></div>
                        <div style="font-size: 11px; font-weight: 600; color: #71717a; margin-top: 2px;">Debited: {day_str} of month</div>
                    </div>
                </div>
                <div style="margin: 14px 0 8px 0;">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; color: #71717a; margin-bottom: 6px;">
                        <span>Tenure Progress: <strong style="color: #09090b;">{paid_t} of {tot_t} EMIs Paid</strong></span>
                        <span style="color: #09090b;">⏳ {rem_t} EMIs Left ({pct}% Complete)</span>
                    </div>
                    <div style="width: 100%; height: 8px; background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 6px; overflow: hidden;">
                        <div style="width: {min(pct, 100)}%; height: 100%; background: #09090b; border-radius: 6px; transition: width 0.4s ease;"></div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 12px; color: #71717a; border-top: 1px solid #e4e4e7; padding-top: 10px; margin-top: 12px;">
                    <div>Original Loan: <strong style="color: #09090b;">{inr(tot_amt) if tot_amt > 0 else '—'}</strong></div>
                    <div>Remaining Balance: <strong style="color: #09090b;">{inr(rem_bal)}</strong></div>
                    <div>Bank Debits Logged: <strong style="color: #09090b;">{matched_count} debits</strong></div>
                </div>
            </div>
            """)
            st.markdown(card_html, unsafe_allow_html=True)

    # Section 2: 🗓️ Cashflow Relief & Payoff Timeline
    if not loans_df.empty:
        st.subheader("🗓️ Loan Debt-Free & Cashflow Relief Roadmap")
        st.caption("Here is how your monthly loan commitments will drop as each loan finishes:")
        
        timeline_items = []
        for _, l in loans_df.sort_values("remaining_tenure").iterrows():
            rem_m = int(l["remaining_tenure"])
            emi = float(l["monthly_emi"])
            lname = l["loan_name"]
            
            from dateutil.relativedelta import relativedelta
            from datetime import date
            payoff_dt = date.today() + relativedelta(months=rem_m)
            payoff_str = payoff_dt.strftime("%B %Y")
            
            timeline_items.append({
                "Loan": lname,
                "Monthly EMI": inr(emi),
                "EMIs Remaining": f"⏳ {rem_m} months",
                "Projected Payoff Date": payoff_str,
                "Monthly Cashflow Relief": f"🎉 Frees up {inr(emi)}/month"
            })
            
        st.dataframe(pd.DataFrame(timeline_items), width="stretch", hide_index=True)

    # Section 3: 🧾 Matched Bank Debits History
    st.subheader("🧾 Matched Loan Debits from Bank Statements")
    if not all_txns.empty:
        if not loans_df.empty:
            kws = [k for k in loans_df["match_keyword"].dropna().unique() if k]
            pat = "|".join([re.escape(k.upper()) for k in kws]) if kws else "LOAN|EMI|SPLN|KISETSU"
        else:
            pat = "KISETSU|IDFC FIRS|EMI-PL|SPLN"
        loan_txns = all_txns[all_txns["description"].str.upper().str.contains(pat, na=False) & (all_txns["amount"] < 0)].sort_values("txn_date", ascending=False)
        
        if not loan_txns.empty:
            disp = loan_txns[["txn_date", "account", "description", "amount"]].copy()
            disp["Amount"] = disp["amount"].apply(lambda x: inr(abs(x)))
            disp = disp.rename(columns={"txn_date": "Debit Date", "account": "Account", "description": "Bank Narration"})
            st.dataframe(disp[["Debit Date", "Account", "Bank Narration", "Amount"]], width="stretch", hide_index=True)
        else:
            st.info("No matching loan debits detected in bank transactions.")

    # Section 4: ✏️ In-App Add / Edit Loan Manager
    st.subheader("✏️ Add or Manage Bank Loans")
    with st.expander("➕ Add New Loan or Update Existing Loan Details", expanded=False):
        c_mode = st.radio("Action", ["Edit Existing Loan", "Add New Loan"], horizontal=True, key="loan_mode_radio")
        
        if c_mode == "Edit Existing Loan" and not loans_df.empty:
            sel_l_name = st.selectbox("Select Loan to Edit", loans_df["loan_name"].unique(), key="sel_loan_edit")
            curr_l = loans_df[loans_df["loan_name"] == sel_l_name].iloc[0]
            
            e_col1, e_col2, e_col3 = st.columns(3)
            with e_col1:
                e_tot_amt = st.number_input("Total Original Loan Amount (₹)", value=float(curr_l["total_loan_amount"]), step=1000.0, key="edit_tot_amt")
                e_emi = st.number_input("Monthly EMI (₹)", value=float(curr_l["monthly_emi"]), step=100.0, key="edit_emi")
            with e_col2:
                e_tot_t = st.number_input("Total Tenure (Months)", value=int(curr_l["total_tenure"]), min_value=1, step=1, key="edit_tot_t")
                e_paid_t = st.number_input("Paid Installments", value=int(curr_l["paid_tenure"]), min_value=0, step=1, key="edit_paid_t")
            with e_col3:
                e_rem_t = max(0, e_tot_t - e_paid_t)
                e_rem_bal = st.number_input("Remaining Balance (₹)", value=float(e_rem_t * e_emi), step=1000.0, key="edit_rem_bal")
                e_notes = st.text_input("Notes / Lender Info", value=str(curr_l.get("notes", "")), key="edit_notes")

            if st.button("Save Loan Changes", type="primary", key="save_loan_btn"):
                db.upsert_bank_loan({
                    "id": curr_l["id"],
                    "loan_name": curr_l["loan_name"],
                    "lender": curr_l["lender"],
                    "account": curr_l["account"],
                    "monthly_emi": e_emi,
                    "total_loan_amount": e_tot_amt,
                    "total_tenure": e_tot_t,
                    "paid_tenure": e_paid_t,
                    "remaining_tenure": e_rem_t,
                    "remaining_principal": e_rem_bal,
                    "match_keyword": curr_l["match_keyword"],
                    "match_amount": e_emi,
                    "debit_day": curr_l["debit_day"],
                    "notes": e_notes,
                })
                st.success(f"Updated {curr_l['loan_name']}!")
                st.rerun()

        elif c_mode == "Add New Loan":
            a_col1, a_col2 = st.columns(2)
            with a_col1:
                n_name = st.text_input("Loan Name", placeholder="e.g. HDFC Personal Loan", key="n_lname")
                n_lender = st.text_input("Lender Name", placeholder="e.g. HDFC Bank", key="n_lender")
                n_amt = st.number_input("Total Loan Amount (₹)", value=100000.0, step=5000.0, key="n_amt")
                n_emi = st.number_input("Monthly EMI (₹)", value=5000.0, step=500.0, key="n_emi")
            with a_col2:
                n_tot_t = st.number_input("Total Tenure (Months)", value=24, min_value=1, step=1, key="n_tot_t")
                n_paid_t = st.number_input("Paid EMIs to date", value=0, min_value=0, step=1, key="n_paid_t")
                n_kw = st.text_input("Bank Narration Match Keyword", placeholder="e.g. HDFC-PL", key="n_kw")
                n_day = st.number_input("Debit Day of Month", value=5, min_value=1, max_value=31, key="n_day")
                
            if st.button("Add Loan to Tracker", type="primary", key="add_loan_btn"):
                if n_name and n_emi > 0:
                    n_rem_t = max(0, n_tot_t - n_paid_t)
                    db.upsert_bank_loan({
                        "loan_name": n_name,
                        "lender": n_lender or n_name,
                        "account": "axis",
                        "monthly_emi": n_emi,
                        "total_loan_amount": n_amt,
                        "total_tenure": n_tot_t,
                        "paid_tenure": n_paid_t,
                        "remaining_tenure": n_rem_t,
                        "remaining_principal": n_rem_t * n_emi,
                        "match_keyword": n_kw,
                        "match_amount": n_emi,
                        "debit_day": n_day,
                        "notes": f"Created via loan manager.",
                    })
                    st.success(f"Added {n_name} to tracker!")
                    st.rerun()


