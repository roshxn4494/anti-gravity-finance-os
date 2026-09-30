"""Tab: Ashwin Pass-Through Ledger & Reconciliation."""
from __future__ import annotations

import textwrap
import pandas as pd
import streamlit as st

from ... import config, db, pipeline
from ..format import inr, mask_card


def _explain():
    st.subheader("Explain every rupee out")
    df = db.load_all()
    if df.empty:
        return
    by_class = df.groupby("classification")["amount"].apply(
        lambda s: -s[s < 0].sum()).rename("out")
    order = ["spend", "internal_transfer", "cc_payment", "investment", "fee"]
    labels = {
        "spend": "Spend", "internal_transfer": "Internal transfers",
        "cc_payment": "CC payments", "investment": "Investments",
        "fee": "Fees",
    }
    rows = [(labels.get(c, c), v) for c, v in by_class.items() if c in order]
    total = sum(v for _, v in rows)
    rows.append(("Total out", total))
    out_df = pd.DataFrame(rows, columns=["Where it went", "Amount"])
    st.dataframe(out_df, hide_index=True, width="stretch", height=240)


def tab_reconciliation():
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1:
        st.header("👥 Ashwin Pass-Through Ledger & Reconciliation", divider=True)
        st.caption("Real-time synchronization of Ashwin's pass-through debt, credit card EMIs, personal loans, and bank statement settlements.")
    with h_col2:
        st.write("")
        if st.button("⚡ Re-apply Auto-Categorization", help="Re-apply keyword classification rules to all transactions without manual overrides", key="recat_ashwin_btn", width="stretch"):
            n = pipeline.reclassify_all_unoverridden()
            st.toast(f"Updated {n} transactions based on rules.")
            st.rerun()

    all_txns = db.load_all()
    if all_txns.empty:
        st.info("No data yet — go to the **Upload** tab and import a statement.")
        return

    emis = db.load_cc_emis()
    stmts = db.load_cc_statements()
    loans = db.load_bank_loans()

    # Separate Ashwin loans
    if not loans.empty and "borrower" in loans.columns:
        ash_loans = loans[loans["borrower"] == "ashwin"]
    elif not loans.empty:
        ash_loans = loans[~loans["loan_name"].str.contains("KISETSU", case=False, na=False)]
    else:
        ash_loans = pd.DataFrame()

    # Top Exposure Metrics
    cc_lifetime = (emis["monthly_emi"] * emis["total_tenure"]).sum() if not emis.empty else 0.0
    loan_lifetime = (ash_loans["monthly_emi"] * ash_loans["total_tenure"]).sum() if not ash_loans.empty else 0.0
    tot_lifetime = cc_lifetime + loan_lifetime

    deposits = all_txns[all_txns["classification"] == config.CLASSIFICATION_FRIEND_DEPOSIT]
    payments = all_txns[all_txns["classification"] == config.CLASSIFICATION_CC_PAYMENT]

    tot_deposited = deposits["amount"].sum() if not deposits.empty else 0.0
    tot_paid = payments["amount"].abs().sum() if not payments.empty else 0.0
    net_cash_balance = tot_deposited - tot_paid

    cc_remaining = (emis["monthly_emi"] * emis["remaining_tenure"]).sum() if not emis.empty else 0.0
    loan_remaining = (ash_loans["monthly_emi"] * ash_loans["remaining_tenure"]).sum() if not ash_loans.empty else 0.0
    latest_stmts = stmts.sort_values("statement_date").groupby("card_name", as_index=False).last() if not stmts.empty else pd.DataFrame()
    cc_dues = latest_stmts["total_due"].sum() if not latest_stmts.empty else 0.0
    cc_emi_monthly = emis["monthly_emi"].sum() if not emis.empty else 0.0
    non_emi_dues = max(0.0, cc_dues - cc_emi_monthly)
    
    # Non-double-counted remaining exposure
    tot_owed_today = cc_remaining + loan_remaining + non_emi_dues
    loan_monthly_inflow = ash_loans["monthly_emi"].sum() if not ash_loans.empty else 0.0
    monthly_inflow = cc_dues + loan_monthly_inflow

    # 4 Top KPI Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Lifetime Borrowed", inr(tot_lifetime), help="Total contracted loan & EMI value across full tenures")
    k2.metric("Deposits Received to Date", inr(tot_deposited), help="Total money deposited by Ashwin across all bank statements")
    k3.metric("CC Bills & Loans Paid", inr(tot_paid), help="Total credit card and loan payments made from your bank accounts")
    k4.metric("Currently Owed Today", inr(tot_owed_today), delta=f"{inr(monthly_inflow)}/mo gross required", delta_color="off")

    # Settlement Status Box
    if net_cash_balance >= 0:
        st.success(f"**✅ Cash Settlement Status:** Ashwin has deposited **{inr(tot_deposited)}** vs. **{inr(tot_paid)}** paid from your accounts. Ashwin is currently **+{inr(net_cash_balance)}** ahead in cash reserves with you.")
    else:
        st.warning(f"**⏳ Cash Settlement Status:** You have paid **{inr(tot_paid)}** in CC bills vs. **{inr(tot_deposited)}** received. Ashwin currently owes **{inr(abs(net_cash_balance))}** in immediate cash reimbursements.")

    # Two Sub-Tabs: Monthly Ledger & Active Plans
    sec1, sec2 = st.tabs(["📅 Month-by-Month Bank Settlement Ledger", "📋 Active Pass-Through Plans (38 Plans)"])

    with sec1:
        st.subheader("Monthly Bank Statements Reconciliation")
        st.caption("Automatically updates every time you upload an Axis Bank, SBI, or Kotak statement.")

        if not deposits.empty or not payments.empty:
            dep_by_m = deposits.groupby(deposits["txn_date"].str[:7])["amount"].sum() if not deposits.empty else pd.Series(dtype=float)
            pay_by_m = payments.assign(_amt=payments["amount"].abs()).groupby(payments["txn_date"].str[:7])["_amt"].sum() if not payments.empty else pd.Series(dtype=float)
            all_m = sorted(set(dep_by_m.index) | set(pay_by_m.index), reverse=True)

            m_rows = []
            for m in all_m:
                d = dep_by_m.get(m, 0.0)
                p = pay_by_m.get(m, 0.0)
                diff = d - p
                status = f"✅ Surplus (+{inr(diff)})" if diff >= 0 else f"⏳ Deficit (-{inr(abs(diff))})"
                m_rows.append({
                    "Month": m,
                    "Ashwin Deposits (₹)": inr(d),
                    "CC Payments Made (₹)": inr(p),
                    "Net Difference (₹)": f"{'+' if diff >= 0 else ''}{inr(diff)}",
                    "Settlement Status": status
                })

            st.dataframe(pd.DataFrame(m_rows), width="stretch", hide_index=True)
        else:
            st.info("No Ashwin deposits or CC payments found yet.")

    with sec2:
        st.subheader("Ashwin's Active Credit Card EMIs & Personal Loans")
        st.caption(f"Total Monthly Commitment: **{inr(monthly_inflow)}/month** across {len(emis)} CC EMIs and {len(ash_loans)} Personal Loans.")

        # Show Personal Loans
        st.markdown("#### 🏦 Personal & NBFC Loans (3 Loans)")
        if not ash_loans.empty:
            loan_rows = []
            for _, l in ash_loans.iterrows():
                loan_rows.append({
                    "Loan Name": l["loan_name"],
                    "Lender": l["lender"],
                    "Monthly EMI": inr(l["monthly_emi"]),
                    "Tenure Progress": f"{l['paid_tenure']}/{l['total_tenure']} paid ({l['remaining_tenure']} left)",
                    "Remaining Balance": inr(l["remaining_principal"]),
                    "Debit Day": f"{l.get('debit_day', 3)}th",
                    "Notes": l.get("notes", "")
                })
            st.dataframe(pd.DataFrame(loan_rows), width="stretch", hide_index=True)

        # Show Credit Card EMIs
        st.markdown(f"#### 💳 Credit Card EMIs ({len(emis)} Plans)")
        if not emis.empty:
            emi_rows = []
            for _, e in emis.iterrows():
                tot_owed = e["monthly_emi"] * e["remaining_tenure"]
                emi_rows.append({
                    "Card": e["card_name"],
                    "Merchant / Description": e["merchant_name"],
                    "Monthly EMI": inr(e["monthly_emi"]),
                    "Progress": f"{e['paid_tenure']}/{e['total_tenure']} EMIs",
                    "Remaining EMIs": f"⏳ {e['remaining_tenure']} left",
                    "Remaining Total Owed": inr(tot_owed),
                })
            st.dataframe(pd.DataFrame(emi_rows), width="stretch", hide_index=True)

    # Standard Internal Transfer Section below
    st.markdown("---")
    st.subheader("🔄 Bank Internal Transfers & Pass-Through Matching")
    
    match_c1, match_c2 = st.columns([3, 1])
    with match_c1:
        st.caption("Transactions are paired within ±₹1.00 tolerance (including multi-part deposits summing to a single CC payment).")
    with match_c2:
        if st.button("Re-run auto-matching engine", type="secondary", use_container_width=True):
            n = pipeline.reconcile()
            st.success(f"Re-matched {n} rows.")
            st.rerun()

    u_transfer = db.load_unmatched(config.CLASSIFICATION_INTERNAL_TRANSFER)
    u_cc = db.load_unmatched(config.CLASSIFICATION_CC_PAYMENT)
    u_friend = db.load_unmatched(config.CLASSIFICATION_FRIEND_DEPOSIT)

    out = u_transfer[u_transfer["amount"] < 0]
    into = u_transfer[u_transfer["amount"] > 0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Unmatched transfer OUT", inr(out["amount"].abs().sum()))
    c2.metric("Unmatched transfer IN", inr(into["amount"].abs().sum()))
    c3.metric(
        "CC paid, no Ashwin deposit yet",
        inr(u_cc["amount"].abs().sum()),
        delta="Ashwin owes you" if u_cc["amount"].abs().sum() != 0 else None,
        delta_color="inverse",
    )
    c4.metric(
        "Ashwin deposited, no CC paid",
        inr(u_friend["amount"].abs().sum()),
        delta="You owe Ashwin" if u_friend["amount"].abs().sum() != 0 else None,
    )

    def _table(title, u):
        st.subheader(title)
        if u.empty:
            st.write("_Nothing unmatched here._")
            return
        show = u[["txn_date", "account", "description", "amount"]].copy()
        show["account"] = show["account"].map(lambda a: config.ACCOUNTS.get(a, {}).get("label", a))
        show.columns = ["Date", "Account", "Description", "Amount"]
        st.dataframe(show, width="stretch", height=200)

    left, right = st.columns(2)
    with left:
        _table("Unmatched internal transfers", u_transfer)
        _table("Unmatched credit-card payments", u_cc)
    with right:
        _table("Unmatched Ashwin deposits", u_friend)
        _explain()

    # Manual Pairing Workspace
    st.markdown("---")
    st.subheader("🔗 Manual Pairing Workspace")
    st.caption("Pair transactions that have date delays, split deposits, or slight variations beyond automated rules. User-verified pairings are permanently preserved.")

    pair_tab1, pair_tab2 = st.tabs(["Link Unmatched Transactions", "View & Manage Matched Pairs"])

    with pair_tab1:
        if u_cc.empty or u_friend.empty:
            st.info("Both unmatched Credit Card payments and unmatched Ashwin deposits are needed to manually pair.")
        else:
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.markdown("**1. Select CC Payment (Debit)**")
                cc_opts = u_cc.copy()
                cc_opts["display"] = cc_opts.apply(
                    lambda r: f"{r['txn_date']} | {config.ACCOUNTS.get(r['account'], {}).get('label', r['account'])} | {inr(abs(r['amount']))} | {r['description'][:35]}", axis=1
                )
                sel_cc_id = st.selectbox(
                    "Credit Card Payment",
                    options=cc_opts["id"].tolist(),
                    format_func=lambda tid: cc_opts.loc[cc_opts["id"] == tid, "display"].values[0],
                    key="manual_pair_cc"
                )
                sel_cc_amt = abs(cc_opts.loc[cc_opts["id"] == sel_cc_id, "amount"].values[0]) if sel_cc_id else 0.0

            with p_col2:
                st.markdown("**2. Select Ashwin Deposit(s) (Credits)**")
                dep_opts = u_friend.copy()
                dep_opts["display"] = dep_opts.apply(
                    lambda r: f"{r['txn_date']} | {config.ACCOUNTS.get(r['account'], {}).get('label', r['account'])} | {inr(r['amount'])} | {r['description'][:35]}", axis=1
                )
                sel_dep_ids = st.multiselect(
                    "Ashwin Deposit(s) (supports split deposits)",
                    options=dep_opts["id"].tolist(),
                    format_func=lambda tid: dep_opts.loc[dep_opts["id"] == tid, "display"].values[0],
                    key="manual_pair_deps"
                )
                sel_deps_amt = dep_opts.loc[dep_opts["id"].isin(sel_dep_ids), "amount"].sum() if sel_dep_ids else 0.0

            # Delta comparison & Link Action
            if sel_cc_id and sel_dep_ids:
                diff = abs(sel_deps_amt - sel_cc_amt)
                m_diff_col1, m_diff_col2, m_diff_col3 = st.columns(3)
                m_diff_col1.metric("CC Payment Amount", inr(sel_cc_amt))
                m_diff_col2.metric("Selected Deposits Total", inr(sel_deps_amt))
                m_diff_col3.metric("Difference", inr(diff), delta="Exact match" if diff == 0 else f"{inr(diff)} drift")

                if st.button("🔗 Link Selected Transactions", type="primary", use_container_width=True):
                    ok = db.manual_pair(sel_cc_id, sel_dep_ids)
                    if ok:
                        pipeline.reconcile()
                        st.success(f"Successfully paired CC payment with {len(sel_dep_ids)} deposit(s)!")
                        st.rerun()
                    else:
                        st.error("Failed to link selected transactions.")

    with pair_tab2:
        matched_df = db.load_matched_pairs()
        if matched_df.empty:
            st.info("No matched pairs found.")
        else:
            st.caption(f"{len(matched_df)} matched pairs. Manual matches will never be altered by auto-matching.")
            
            # Format preview dataframe
            preview = matched_df.copy()
            preview["debit_account"] = preview["debit_account"].map(lambda a: config.ACCOUNTS.get(a, {}).get("label", a))
            preview["credit_account"] = preview["credit_account"].map(lambda a: config.ACCOUNTS.get(a, {}).get("label", a) if pd.notna(a) else "-")
            preview["debit_amount"] = preview["debit_amount"].abs().map(inr)
            preview["credit_amount"] = preview["credit_amount"].map(lambda v: inr(v) if pd.notna(v) else "-")
            
            show_cols = ["debit_date", "debit_account", "debit_amount", "match_status", "credit_date", "credit_account", "credit_amount"]
            st.dataframe(preview[show_cols], use_container_width=True, height=260)

            # Unpair tool
            st.markdown("##### ✂️ Unlink a Paired Transaction")
            unpair_opts = matched_df.copy()
            unpair_opts["display"] = unpair_opts.apply(
                lambda r: f"{r['debit_date']} ({r['debit_amount']}) ↔ {r['credit_date'] or 'Split/Multi'} [{r['match_status']}]", axis=1
            )
            sel_unpair_id = st.selectbox(
                "Select Pair to Unlink",
                options=unpair_opts["debit_id"].tolist(),
                format_func=lambda tid: unpair_opts.loc[unpair_opts["debit_id"] == tid, "display"].values[0],
                key="manual_unpair_sel"
            )
            if st.button("✂️ Unlink Selected Pair", type="secondary"):
                if sel_unpair_id:
                    db.manual_unpair(sel_unpair_id)
                    pipeline.reconcile()
                    st.success("Transactions unlinked successfully.")
                    st.rerun()

    st.caption("Tip: an unmatched transfer OUT usually means that side is on a "
               "statement you haven't imported yet, or it was a payment to a "
               "person, not yourself — reclassify it in the Transactions tab.")


