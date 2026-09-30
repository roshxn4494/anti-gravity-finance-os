"""Tab: Overview financial health, spending categories, and trend charts."""
from __future__ import annotations

import math
from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ... import config, db
from ..format import inr, month_key, prev_month, last_months, fmt_month
from ..theme import category_color, account_color, display_categories, layout_plot, SERIES


def _spend_df(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["classification"] == config.CLASSIFICATION_SPEND]


def _aligned_income(df: pd.DataFrame, mk: str) -> float:
    same_month = df[(df["txn_date"].str[:7] == mk) & (df["classification"] == config.CLASSIFICATION_INCOME)]
    same_early = same_month[same_month["txn_date"].str[8:].astype(int) < 25]["amount"].sum()

    prev_mk = prev_month(mk)
    prev_month_df = df[(df["txn_date"].str[:7] == prev_mk) & (df["classification"] == config.CLASSIFICATION_INCOME)]
    prev_late = prev_month_df[prev_month_df["txn_date"].str[8:].astype(int) >= 25]["amount"].sum()

    val = same_early + prev_late
    if val == 0:
        val = same_month["amount"].sum()
    return val


def _layout(fig: go.Figure, height: int = 340) -> go.Figure:
    return layout_plot(fig, height=height)


def _render_obligations_checklist(target_month: str) -> None:
    from ...services.recurring import get_monthly_obligations_summary
    data = get_monthly_obligations_summary(target_month)
    summ = data["summary"]
    rent = data["rent"]
    loans = data["loans"]
    ccs = data["credit_cards"]
    if not data or summ.get("total_count", 0) == 0:
        return

    st.markdown("---")

    # Header strip
    hdr_c1, hdr_c2 = st.columns([2.5, 1.5])
    with hdr_c1:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 2px;">
            <h3 style="margin: 0; font-size: 1.15rem; font-weight: 700; color: #09090b;">
                📋 Monthly Obligations & Bills Checklist
            </h3>
            <span style="background: #f4f4f5; border: 1px solid #e4e4e7; color: #09090b; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 9999px;">
                {fmt_month(target_month)}
            </span>
        </div>
        <p style="margin: 0; color: #71717a; font-size: 0.85rem;">
            Cycle-aware tracking of House Rent, Personal Loan EMIs, and Credit Card settlements.
        </p>
        """, unsafe_allow_html=True)
    with hdr_c2:
        badge_border = "#09090b" if summ["all_cleared"] else "#e4e4e7"
        badge_bg = "#ffffff" if summ["all_cleared"] else "#f4f4f5"
        st.markdown(f"""
        <div style="background: {badge_bg}; border: 1px solid {badge_border}; border-radius: 12px; padding: 10px 14px; text-align: right;">
            <div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #71717a; font-weight: 600;">Status</div>
            <div style="font-size: 1.05rem; font-weight: 700; color: #09090b;">
                {'✅ All Cleared' if summ['all_cleared'] else f"{summ['paid_count']} of {summ['total_count']} Cleared"}
            </div>
            <div style="font-size: 0.78rem; color: #71717a;">
                Paid {inr(summ['total_paid'])} <span style="color: #a1a1aa;">/</span> {inr(summ['total_expected'])}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    col1, col2, col3 = st.columns([1, 1.3, 1.5])

    # 1. House Rent
    with col1:
        rent_paid = (rent["status"] == "paid")
        status_pill = (
            '<span style="background: #09090b; color: #ffffff; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 700;">PAID</span>'
            if rent_paid else
            '<span style="background: #ffffff; border: 1px solid #71717a; color: #71717a; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 600;">PENDING</span>'
        )
        early_badge = (
            f'<div style="font-size: 0.75rem; color: #166534; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 4px 8px; border-radius: 6px; margin-top: 6px;">⚡ {rent["note"]}</div>'
            if rent.get("is_early") else ""
        )
        rent_date_str = f"Paid {rent['paid_date']}" if rent_paid else "Expected ~1st of month"
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 0px; height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-weight: 700; font-size: 0.92rem; color: #09090b;">🏠 House Rent</div>
                {status_pill}
            </div>
            <div style="font-size: 1.3rem; font-weight: 800; color: #09090b; letter-spacing: -0.02em;">
                {inr(rent['paid_amount'] if rent_paid else rent['expected_amount'])}
            </div>
            <div style="font-size: 0.8rem; color: #71717a; margin-top: 2px;">
                Payee: {rent['payee']} ({rent['account']})
            </div>
            <div style="font-size: 0.78rem; color: #71717a; margin-top: 2px;">
                {rent_date_str}
            </div>
            {early_badge}
        </div>
        """, unsafe_allow_html=True)

    # 2. Personal Loans
    with col2:
        loans_paid_cnt = sum(1 for l in loans if l["status"] == "paid")
        loans_tot_amt = sum(l["paid_amount"] if l["status"] == "paid" else l["expected_amount"] for l in loans)
        loans_pill = (
            f'<span style="background: #09090b; color: #ffffff; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 700;">{loans_paid_cnt}/{len(loans)} PAID</span>'
            if loans_paid_cnt == len(loans) else
            f'<span style="background: #f4f4f5; border: 1px solid #e4e4e7; color: #09090b; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 600;">{loans_paid_cnt}/{len(loans)} PAID</span>'
        )
        loan_rows_html = []
        for l in loans:
            is_p = (l["status"] == "paid")
            chk = "✅" if is_p else "⏳"
            d_str = l["paid_date"] if is_p else f"Due ~{l['debit_day']}th"
            amt_str = inr(l["paid_amount"] if is_p else l["expected_amount"])
            short_title = l['title'].replace("Personal Loan", "").replace("Smart Personal Loan", "").strip()
            if not short_title:
                short_title = l['title']
            loan_rows_html.append(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f4f4f5; font-size: 0.8rem;">
                <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 65%;">
                    <span>{chk}</span> <strong style="color: #09090b;">{short_title}</strong>
                    <div style="font-size: 0.72rem; color: #71717a; padding-left: 18px;">{d_str}</div>
                </div>
                <div style="font-weight: 700; color: #09090b; text-align: right;">{amt_str}</div>
            </div>
            """)

        loans_content = "".join(loan_rows_html)
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 0px; height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-weight: 700; font-size: 0.92rem; color: #09090b;">🏦 Personal Loans</div>
                {loans_pill}
            </div>
            <div style="font-size: 1.3rem; font-weight: 800; color: #09090b; letter-spacing: -0.02em; margin-bottom: 6px;">
                {inr(loans_tot_amt)}
            </div>
            <div style="display: flex; flex-direction: column;">
                {loans_content}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 3. Credit Card Bills
    with col3:
        cc_paid_cnt = sum(1 for c in ccs if c["status"] == "paid")
        cc_tot_amt = sum(c["paid_amount"] if c["status"] == "paid" else c["expected_amount"] for c in ccs)
        cc_pill = (
            f'<span style="background: #09090b; color: #ffffff; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 700;">{cc_paid_cnt}/{len(ccs)} SETTLED</span>'
            if cc_paid_cnt == len(ccs) else
            f'<span style="background: #f4f4f5; border: 1px solid #e4e4e7; color: #09090b; padding: 2px 7px; border-radius: 9999px; font-size: 10px; font-weight: 600;">{cc_paid_cnt}/{len(ccs)} SETTLED</span>'
        )
        cc_rows_html = []
        for c in ccs:
            is_p = (c["status"] == "paid")
            chk = "✅" if is_p else "⏳"
            d_str = c["paid_date"] if is_p else f"Due {c.get('due_date', '—')}"
            amt_str = inr(c["paid_amount"] if is_p else c["expected_amount"])
            short_name = c["title"].replace(" Credit Card", "").replace(" Federal", "")
            cc_rows_html.append(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f4f4f5; font-size: 0.8rem;">
                <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 65%;">
                    <span>{chk}</span> <strong style="color: #09090b;">{short_name}</strong>
                    <div style="font-size: 0.72rem; color: #71717a; padding-left: 18px;">{d_str}</div>
                </div>
                <div style="font-weight: 700; color: #09090b; text-align: right;">{amt_str}</div>
            </div>
            """)

        cc_content = "".join(cc_rows_html)
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 0px; height: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <div style="font-weight: 700; font-size: 0.92rem; color: #09090b;">💳 Credit Card Bills</div>
                {cc_pill}
            </div>
            <div style="font-size: 1.3rem; font-weight: 800; color: #09090b; letter-spacing: -0.02em; margin-bottom: 6px;">
                {inr(cc_tot_amt)}
            </div>
            <div style="display: flex; flex-direction: column;">
                {cc_content}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Detailed Audit & Proof Table Expander
    all_items = [rent] + loans + ccs
    with st.expander(f"🔍 Audit & Match Details — {fmt_month(target_month)} ({summ['paid_count']}/{len(all_items)} Cleared)", expanded=False):
        table_rows = []
        for it in all_items:
            cat_name = "House Rent" if it["id"] == "rent" else ("Personal Loan" if it in loans else "Credit Card Bill")
            is_p = (it["status"] == "paid")
            st_text = "✅ Paid" if is_p else "⏳ Pending"
            table_rows.append({
                "Status": st_text,
                "Obligation": it["title"],
                "Category": cat_name,
                "Expected (₹)": it["expected_amount"],
                "Paid (₹)": it["paid_amount"],
                "Paid Date": it["paid_date"] or "—",
                "Account": it.get("account", "—"),
                "Notes & Match Rule": it.get("note", "—"),
            })
        proof_df = pd.DataFrame(table_rows)
        st.dataframe(
            proof_df,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Obligation": st.column_config.TextColumn("Obligation", width="medium"),
                "Category": st.column_config.TextColumn("Category", width="small"),
                "Expected (₹)": st.column_config.NumberColumn("Expected", format="₹%d"),
                "Paid (₹)": st.column_config.NumberColumn("Paid", format="₹%d"),
                "Paid Date": st.column_config.TextColumn("Date", width="small"),
                "Account": st.column_config.TextColumn("Account", width="small"),
                "Notes & Match Rule": st.column_config.TextColumn("Notes / Match Proof", width="large"),
            },
            use_container_width=True,
        )


def tab_overview():
    df = db.load_all()
    st.header("Overview", divider=True)
    if df.empty:
        st.info("No data yet — go to the **Upload** tab and import a statement.")
        return

    spend = _spend_df(df)
    income = df[df["classification"] == config.CLASSIFICATION_INCOME]

    # --------------------------------------------------
    # Year & Month Filter Controls
    # --------------------------------------------------
    all_dates = sorted(df["txn_date"].unique())
    all_mks = sorted(list(set(d[:7] for d in all_dates)), reverse=True)
    all_years = sorted(list(set(mk[:4] for mk in all_mks)), reverse=True)

    today = date.today()
    default_year = today.strftime("%Y")
    if default_year not in all_years and all_years:
        default_year = all_years[0]

    MONTH_NAMES = {
        "All Months": "All Months (Full Year)",
        "01": "January (01)", "02": "February (02)", "03": "March (03)",
        "04": "April (04)", "05": "May (05)", "06": "June (06)",
        "07": "July (07)", "08": "August (08)", "09": "September (09)",
        "10": "October (10)", "11": "November (11)", "12": "December (12)"
    }

    col_filter1, col_filter2, _ = st.columns([1.5, 2, 4])
    with col_filter1:
        sel_year = st.selectbox("Year", all_years, index=0 if default_year in all_years else 0, key="overview_sel_year")

    # Get available months for selected year
    year_mks = [mk for mk in all_mks if mk.startswith(sel_year)]
    avail_m_nums = sorted([mk[5:7] for mk in year_mks], reverse=True)
    month_options = ["All Months"] + avail_m_nums

    default_m_idx = 1 if len(month_options) > 1 else 0

    with col_filter2:
        sel_m_code = st.selectbox(
            "Month",
            month_options,
            index=default_m_idx,
            format_func=lambda m: MONTH_NAMES.get(m, m),
            key="overview_sel_month"
        )

    # Calculate filtered period metrics & charts
    if sel_m_code != "All Months":
        this_mk = f"{sel_year}-{sel_m_code}"
        period_label = fmt_month(this_mk)

        sub_spend = spend[spend["txn_date"].str[:7] == this_mk]
        this_spend = sub_spend["amount"].abs().sum()

        # Use pay-period aligned salary income for the month
        this_income = _aligned_income(df, this_mk)
        net = this_income - this_spend
        rate = (net / this_income) if this_income > 0 else None

        prev_mk = prev_month(this_mk)
        prev_spend = spend[spend["txn_date"].str[:7] == prev_mk]["amount"].abs().sum()
        delta = None
        if prev_spend:
            delta = f"{((this_spend - prev_spend) / prev_spend) * 100:+.0f}%"

        end_dt = date(int(sel_year), int(sel_m_code), 1)
        months = []
        for i in range(5, -1, -1):
            y, m = end_dt.year, end_dt.month
            for _ in range(i):
                m -= 1
                if m == 0:
                    m, y = 12, y - 1
            months.append(f"{y:04d}-{m:02d}")

        spend_m = spend.assign(_m=spend["txn_date"].str[:7])
        trend = (spend_m[spend_m["_m"].isin(months)]
                 .assign(_amt=spend_m["amount"].abs())
                 .groupby("_m")["_amt"].sum().reindex(months).fillna(0))

        trend_title = f"Spend Trend — 6 months ending {fmt_month(this_mk)}"
        cat_df = sub_spend
        acct_df = sub_spend
    else:
        period_label = f"Full Year {sel_year}"

        sub_spend = spend[spend["txn_date"].str.startswith(sel_year)]
        sub_income = income[income["txn_date"].str.startswith(sel_year)]

        this_spend = sub_spend["amount"].abs().sum()
        this_income = sub_income["amount"].sum()
        net = this_income - this_spend
        rate = (net / this_income) if this_income > 0 else None
        delta = None

        months = [f"{sel_year}-{m:02d}" for m in range(1, 13)]
        spend_m = spend.assign(_m=spend["txn_date"].str[:7])
        trend = (spend_m[spend_m["_m"].isin(months)]
                 .assign(_amt=spend_m["amount"].abs())
                 .groupby("_m")["_amt"].sum().reindex(months).fillna(0))

        trend_title = f"Spend Trend — {sel_year} (All Months)"
        cat_df = sub_spend
        acct_df = sub_spend

    st.subheader(period_label)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card spend">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="metric-title">Real Spend</div>
                    <div class="metric-value">{inr(this_spend)}</div>
                </div>
                <div class="icon-badge">
                    <span class="material-symbols-rounded">credit_card</span>
                </div>
            </div>
            <div class="metric-sub">
                <span>{"vs prev: " + delta if delta else "Real consumption"}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="metric-card income">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="metric-title">Salary Income</div>
                    <div class="metric-value">{inr(this_income)}</div>
                </div>
                <div class="icon-badge">
                    <span class="material-symbols-rounded">payments</span>
                </div>
            </div>
            <div class="metric-sub">Credited salary</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        rate_str = f"{rate:.0%}" if rate is not None else "—"
        st.markdown(f"""
        <div class="metric-card savings">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="metric-title">Savings Rate</div>
                    <div class="metric-value">{rate_str}</div>
                </div>
                <div class="icon-badge">
                    <span class="material-symbols-rounded">savings</span>
                </div>
            </div>
            <div class="metric-sub">Saved {inr(net)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="metric-card invest">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="metric-title">Net Saved</div>
                    <div class="metric-value">{inr(net)}</div>
                </div>
                <div class="icon-badge">
                    <span class="material-symbols-rounded">account_balance</span>
                </div>
            </div>
            <div class="metric-sub">Retained savings</div>
        </div>
        """, unsafe_allow_html=True)

    # Monthly Obligations & Recurring Bills Checklist
    target_obl_month = this_mk if sel_m_code != "All Months" else all_mks[0]
    _render_obligations_checklist(target_obl_month)

    # Trend Chart
    fig_t = go.Figure(go.Scatter(
        x=[fmt_month(m) for m in months], y=trend.values,
        mode="lines+markers",
        line=dict(color=SERIES[0], width=3, shape="spline"),
        marker=dict(color=SERIES[0], size=8),
        hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>"))
    fig_t.update_yaxes(title="", gridcolor="#f4f4f5", zeroline=False, tickprefix="₹")
    fig_t.update_xaxes(gridcolor="#f4f4f5", showgrid=False)
    fig_t.update_layout(title=trend_title)
    _layout(fig_t)

    # Category Chart for selection
    cat_agg = (cat_df.assign(_amt=cat_df["amount"].abs())
               .groupby("category")["_amt"].sum().sort_values(ascending=False))
    top = cat_agg.head(7)
    if len(cat_agg) > 7:
        other = cat_agg.iloc[7:].sum()
        top = pd.concat([top, pd.Series({"Other": other})])
    top = top[top > 0]

    # Account Chart for selection
    acct_agg = (acct_df.assign(_amt=acct_df["amount"].abs())
                .groupby("account")["_amt"].sum().sort_values())

    c1, c2 = st.columns([2, 1])
    with c1:
        st.plotly_chart(fig_t, width="stretch")
        if not top.empty:
            fig_c = go.Figure(go.Bar(
                x=top.values, y=top.index, orientation="h",
                marker_color=[category_color(c) for c in top.index],
                text=[inr(v) for v in top.values],
                textposition="outside", textfont=dict(color="#09090b", size=11),
                hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            fig_c.update_xaxes(gridcolor="#f4f4f5", zeroline=False, tickprefix="₹")
            fig_c.update_yaxes(showgrid=False)
            fig_c.update_layout(title=f"Spend by Category ({period_label})", bargap=0.35)
            _layout(fig_c)
            st.plotly_chart(fig_c, width="stretch")
    with c2:
        if not acct_agg.empty:
            fig_a = go.Figure(go.Bar(
                x=acct_agg.values, y=[config.ACCOUNTS.get(a, {}).get("label", a) for a in acct_agg.index],
                orientation="h",
                marker_color=[account_color(a) for a in acct_agg.index],
                text=[inr(v) for v in acct_agg.values],
                textposition="outside", textfont=dict(color="#09090b", size=11),
                hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            fig_a.update_xaxes(gridcolor="#f4f4f5", zeroline=False, tickprefix="₹")
            fig_a.update_yaxes(showgrid=False)
            fig_a.update_layout(title=f"Spend by Account ({period_label})", bargap=0.4)
            _layout(fig_a)
            st.plotly_chart(fig_a, width="stretch")

    # Liquid Savings & Bank Balances Strip
    st.markdown("---")
    h_b1, h_b2 = st.columns([3, 1])
    with h_b1:
        st.subheader("🏦 Liquid Savings & Bank Balances")
        st.caption("Latest reconciled closing balances derived from your bank statements and savings ledgers.")
    with h_b2:
        st.write("")
        c_sync_btn, c_adj_btn = st.columns([1, 1])
        with c_sync_btn:
            if st.button("🔄 Sync", key="btn_sync_balances", width="stretch", help="Re-compute balances from latest statement transactions"):
                db.sync_account_balances_from_ledger()
                st.toast("Balances synchronized from latest statement transactions!")
                st.rerun()
        with c_adj_btn:
            with st.popover("⚙️ FD / Sweep", help="Update ActivMoney or Smart FD balance"):
                st.caption("Kotak ActivMoney Auto-Sweep FD compounds or shifts with sweep transactions. Enter your latest FD amount:")
                b_curr = db.load_account_balances()
                k_curr = b_curr[b_curr["account"] == "kotak"].iloc[0] if not b_curr.empty and not b_curr[b_curr["account"] == "kotak"].empty else None
                cur_fd_val = float(k_curr["smart_fd_balance"]) if k_curr is not None else 344390.39
                new_fd_val = st.number_input("Kotak ActivMoney FD (₹)", value=cur_fd_val, step=5000.0, key="inp_kotak_fd_adj")
                if st.button("Save FD Balance", type="primary", key="btn_save_fd_adj", width="stretch"):
                    if k_curr is not None:
                        new_total = float(k_curr["savings_balance"]) + float(new_fd_val)
                        db.upsert_account_balance({
                            "account": "kotak",
                            "label": k_curr["label"],
                            "total_balance": new_total,
                            "savings_balance": float(k_curr["savings_balance"]),
                            "smart_fd_balance": float(new_fd_val),
                            "as_of_date": k_curr["as_of_date"],
                            "notes": f"Manual update of ActivMoney Smart FD to ₹{new_fd_val:,.2f}"
                        })
                        st.toast("✅ ActivMoney FD balance updated!")
                        st.rerun()

    try:
        db.sync_account_balances_from_ledger()
        b_df = db.load_account_balances()
    except Exception:
        b_df = pd.DataFrame()

    if not b_df.empty:
        col_b1, col_b2, col_b3, col_b4 = st.columns(4)
        kotak_r = b_df[b_df["account"] == "kotak"].iloc[0] if not b_df[b_df["account"] == "kotak"].empty else None
        sbi_r = b_df[b_df["account"] == "sbi"].iloc[0] if not b_df[b_df["account"] == "sbi"].empty else None
        axis_r = b_df[b_df["account"] == "axis"].iloc[0] if not b_df[b_df["account"] == "axis"].empty else None
        tot_b = b_df["total_balance"].sum()

        with col_b1:
            st.metric("Total Liquid Savings", inr(tot_b), help="Consolidated liquid cash across all 3 bank accounts")
        with col_b2:
            if kotak_r is not None:
                st.metric("Kotak 811 (with Smart FD)", inr(kotak_r["total_balance"]), delta=f"Smart FD: {inr(kotak_r['smart_fd_balance'])} | As of {kotak_r['as_of_date']}", delta_color="off", help="Includes Active Money auto-sweep FD")
        with col_b3:
            if sbi_r is not None:
                st.metric("SBI Savings", inr(sbi_r["total_balance"]), delta=f"As of {sbi_r['as_of_date']}", delta_color="off", help="Secondary liquid savings")
        with col_b4:
            if axis_r is not None:
                st.metric("Axis Salary Account", inr(axis_r["total_balance"]), delta=f"As of {axis_r['as_of_date']}", delta_color="off", help="Primary operating/salary account")
