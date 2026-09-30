"""Tab: Credit Cards & Active EMI Intelligence."""
from __future__ import annotations

import textwrap
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ... import config, db
from ..format import inr
from ..theme import layout_plot


def _layout(fig: go.Figure, height: int = 340) -> go.Figure:
    return layout_plot(fig, height=height)
def tab_credit_cards():
    """Dedicated Credit Cards & EMI Intelligence Dashboard."""
    st.header("Credit Cards & EMI Intelligence", divider=True)
    st.caption("Track Active EMIs, Loan Schedules, Credit Limits, Available Free Limits, and Payment Due Dates.")

    cc_stmts = db.load_cc_statements()
    cc_txns = db.load_cc_transactions()
    cc_emis = db.load_cc_emis()

    if cc_stmts.empty and cc_txns.empty and cc_emis.empty:
        st.info("No credit card statements imported yet. Go to the Upload tab to import your Credit Card PDF statements!")
        return

    # Build list of distinct available cards for modular filter
    card_options = ["All Credit Cards"]
    card_map = {}

    all_card_names = set()
    if not cc_stmts.empty:
        all_card_names.update(cc_stmts["card_name"].unique())
    if not cc_txns.empty:
        all_card_names.update(cc_txns["card_name"].unique())
    if not cc_emis.empty:
        all_card_names.update(cc_emis["card_name"].unique())

    for c in sorted(all_card_names):
        last4 = ""
        if not cc_stmts.empty:
            sub = cc_stmts[cc_stmts["card_name"] == c]
            if not sub.empty and sub.iloc[0]["card_last4"]:
                last4 = sub.iloc[0]["card_last4"]
        if not last4 and not cc_txns.empty:
            sub = cc_txns[cc_txns["card_name"] == c]
            if not sub.empty and sub.iloc[0]["card_last4"]:
                last4 = sub.iloc[0]["card_last4"]

        opt_label = f"💳 {c} (..{last4})" if last4 else f"💳 {c}"
        card_options.append(opt_label)
        card_map[opt_label] = (c, last4)

    col_f1, col_f2 = st.columns([1, 2])

    with col_f1:
        selected_option = st.selectbox("Select Credit Card Filter", card_options, key="cc_card_filter")

    with col_f2:
        if selected_option != "All Credit Cards" and selected_option in card_map:
            sel_card_name, sel_last4 = card_map[selected_option]
            masked_card_no = f"•••• •••• •••• {sel_last4}" if sel_last4 else "•••• •••• •••• ••••"

            stmt_sub = cc_stmts[cc_stmts["card_name"] == sel_card_name] if not cc_stmts.empty else pd.DataFrame()
            tot_due_str = "—"
            due_d_str = "—"
            lim_str = "—"
            if not stmt_sub.empty:
                s_top = stmt_sub.sort_values("statement_date").iloc[-1]
                if s_top["total_due"]:
                    tot_due_str = inr(s_top["total_due"])
                if s_top["due_date"]:
                    due_d_str = s_top["due_date"]
                if s_top["credit_limit"]:
                    lim_str = inr(s_top["credit_limit"])

            st.markdown(textwrap.dedent(f"""
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #71717a; letter-spacing: 0.08em;">Active Card Profile</div>
                    <div style="font-size: 18px; font-weight: 800; color: #09090b; margin-top: 2px;">{sel_card_name}</div>
                    <div style="font-family: monospace; font-size: 13px; font-weight: 600; color: #52525b; margin-top: 4px; letter-spacing: 0.05em;">{masked_card_no}</div>
                </div>
                <div style="text-align: right; border-left: 1px solid #e4e4e7; padding-left: 20px;">
                    <div style="font-size: 11px; font-weight: 700; color: #71717a;">Total Due / Limit</div>
                    <div style="font-size: 16px; font-weight: 800; color: #09090b;">{tot_due_str} <span style="font-size: 12px; font-weight: 500; color: #71717a;">(Limit: {lim_str})</span></div>
                    <div style="font-size: 11.5px; font-weight: 700; color: #71717a; margin-top: 4px;">Payment Due Date: <span style="color: #09090b;">{due_d_str}</span></div>
                </div>
            </div>
            """), unsafe_allow_html=True)
        else:
            st.markdown(textwrap.dedent(f"""
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #71717a; letter-spacing: 0.08em;">Consolidated View</div>
                    <div style="font-size: 18px; font-weight: 800; color: #09090b; margin-top: 2px;">All Credit Cards</div>
                    <div style="font-size: 12.5px; color: #52525b; margin-top: 4px;">Showing combined metrics across all imported credit cards. Select a card on the left to inspect specific card EMIs & limits.</div>
                </div>
            </div>
            """), unsafe_allow_html=True)

    # Filter datasets dynamically by selected card
    if selected_option != "All Credit Cards" and selected_option in card_map:
        sel_card_name, _ = card_map[selected_option]
        if not cc_stmts.empty:
            cc_stmts = cc_stmts[cc_stmts["card_name"] == sel_card_name]
        if not cc_txns.empty:
            cc_txns = cc_txns[cc_txns["card_name"] == sel_card_name]
        if not cc_emis.empty:
            cc_emis = cc_emis[cc_emis["card_name"] == sel_card_name]

    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

    # Section 1: 💳 Credit Limits & Utilization Summary
    st.subheader("💳 Credit Limits & Available Free Limits")
    if not cc_stmts.empty and any(cc_stmts["credit_limit"] > 0):
        # Pick latest statement per unique card so older historical statements do not inflate total limits
        latest_lim_df = cc_stmts.sort_values("statement_date").groupby("card_name", as_index=False).last()
        lim_df = latest_lim_df[latest_lim_df["credit_limit"] > 0].copy()

        tot_lim = lim_df["credit_limit"].sum()
        tot_avail = lim_df["available_limit"].sum()
        tot_dues = lim_df["total_due"].sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Credit Limit", inr(tot_lim))
        c2.metric("Available Free Limit", inr(tot_avail), delta=f"{round((tot_avail/tot_lim)*100, 1)}% free" if tot_lim else None)
        c3.metric("Current Total Dues", inr(tot_dues))

        util_pct = round(((tot_lim - tot_avail) / tot_lim) * 100, 1) if tot_lim > 0 else 0
        c4.metric("Credit Utilization Rate", f"{util_pct}%")

        # Utilization Bar
        bar_color = "#09090b" if util_pct < 50 else "#71717a"
        st.markdown(textwrap.dedent(f"""
        <div style="margin: 10px 0 24px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #71717a; margin-bottom: 6px;">
                <span>Credit Utilization Progress</span>
                <span style="color: #09090b;">{util_pct}% Utilized ({inr(tot_lim - tot_avail)} used of {inr(tot_lim)})</span>
            </div>
            <div style="width: 100%; height: 8px; background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 6px; overflow: hidden;">
                <div style="width: {min(util_pct, 100)}%; height: 100%; background: {bar_color}; border-radius: 6px; transition: width 0.4s ease;"></div>
            </div>
        </div>
        """), unsafe_allow_html=True)

        with st.expander("✏️ Manually Adjust / Update Card Limits & Balances", expanded=False):
            st.caption("If a statement doesn't list the real-time available limit, or if your limit was increased, update it here:")
            all_raw_stmts = db.load_cc_statements()
            if not all_raw_stmts.empty:
                c_cards = sorted(all_raw_stmts["card_name"].unique())
                col_u1, col_u2, col_u3, col_u4 = st.columns([2, 2, 2, 1])
                with col_u1:
                    target_card = st.selectbox("Select Card", c_cards, key="adj_card_select")

                c_row = all_raw_stmts[all_raw_stmts["card_name"] == target_card].iloc[0]
                with col_u2:
                    new_clim = st.number_input("Credit Limit (₹)", value=float(c_row.get("credit_limit", 0.0)), step=1000.0, key=f"adj_clim_{target_card}")
                with col_u3:
                    new_avlim = st.number_input("Available Free Balance (₹)", value=float(c_row.get("available_limit", 0.0)), step=1000.0, key=f"adj_avlim_{target_card}")
                with col_u4:
                    st.write("")
                    st.write("")
                    if st.button("Save", key="adj_save_btn", type="primary"):
                        db.update_cc_limits(target_card, card_last4=c_row.get("card_last4", ""), credit_limit=new_clim, available_limit=new_avlim)
                        st.success(f"Updated {target_card} limits!")
                        st.rerun()
    else:
        st.caption("Credit limit metrics will populate when statements with limit data are loaded.")

    # Section 2: ⏳ Active EMIs & Loan Schedules Table
    st.subheader("⏳ Active EMIs & Remaining Installments Tracker")
    if not cc_emis.empty:
        tot_monthly = cc_emis["monthly_emi"].sum()
        max_rem = cc_emis["remaining_tenure"].max()

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Active EMIs Count", len(cc_emis))
        col_m2.metric("Total Monthly EMI Commitment", f"{inr(tot_monthly)}/month")
        col_m3.metric("Max Tenure Remaining", f"{max_rem} months left")

        emi_table = cc_emis.copy()
        emi_table["Card & Account"] = emi_table.apply(lambda r: f"{r['card_name']} (..{r['card_last4']})" if r.get('card_last4') else r['card_name'], axis=1)
        emi_table["Loan Amount"] = emi_table["loan_amount"].apply(lambda x: inr(x) if x else "—")
        emi_table["Monthly EMI"] = emi_table["monthly_emi"].apply(lambda x: inr(x) if x else "—")
        emi_table["Tenure (Paid/Total)"] = emi_table.apply(lambda r: f"{r['paid_tenure']}/{r['total_tenure']} months", axis=1)
        emi_table["Remaining EMIs Left"] = emi_table["remaining_tenure"].apply(lambda x: f"⏳ {x} EMIs left")

        disp_cols = ["Card & Account", "merchant_name", "Loan Amount", "Monthly EMI", "Tenure (Paid/Total)", "Remaining EMIs Left"]
        emi_display = emi_table[disp_cols].rename(columns={"merchant_name": "Merchant / Purpose"})
        st.dataframe(emi_display, width="stretch", hide_index=True)
    else:
        st.info("No active EMIs or loan schedules detected in imported credit card statements.")

    # Section 3: 🗓️ Payment Due Dates & Cards Summary
    st.subheader("🗓️ Payment Due Dates & Card Dues")
    if not cc_stmts.empty:
        due_cards = []
        for _, s in cc_stmts.sort_values("statement_date", ascending=False).iterrows():
            c_name = s["card_name"]
            last4 = f"..{s['card_last4']}" if s.get("card_last4") else ""
            tot_due = s["total_due"]
            min_due = s["min_due"]
            due_d = s["due_date"]
            stmt_d = s["statement_date"]

            due_cards.append({
                "Card": f"{c_name} {last4}".strip(),
                "Statement Date": stmt_d or "—",
                "Total Amount Due": inr(tot_due),
                "Minimum Due": inr(min_due),
                "Payment Due Date": due_d or "—",
            })
        st.dataframe(pd.DataFrame(due_cards), width="stretch", hide_index=True)

    # Section 4: 📊 Category Breakdown Chart
    if not cc_txns.empty:
        st.subheader("📊 Category Distribution (Credit Card Spend)")
        spend_txns = cc_txns[cc_txns["amount"] > 0]
        if not spend_txns.empty:
            cat_sum = spend_txns.groupby("category")["amount"].sum().reset_index()
            fig = px.pie(
                cat_sum,
                values="amount",
                names="category",
                hole=0.45,
                color_discrete_sequence=px.colors.sequential.Tealgrn,
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#cbd5e1",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, width="stretch")

