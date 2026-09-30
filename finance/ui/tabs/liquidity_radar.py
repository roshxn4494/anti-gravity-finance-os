"""Tab: 30-Day Proactive Liquidity Radar & Cashflow Simulator."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import textwrap
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ... import config, db
from ..format import inr
from ..theme import layout_plot
from ...forecast import liquidity


def _layout(fig: go.Figure, height: int = 340) -> go.Figure:
    return layout_plot(fig, height=height)
def tab_liquidity_radar():
    from finance.forecast import liquidity

    st.header("⚡ 30-Day Proactive Liquidity Radar", divider=True)
    st.caption("Day-by-day multi-bank cashflow forecasting, shortfall protection, and proactive internal transfer optimizer.")

    # 1. Interactive Simulator Controls
    with st.expander("🛠️ Simulator Scenario & Cashflow Controls", expanded=False):
        c_sc1, c_sc2, c_sc3, c_sc4 = st.columns(4)
        with c_sc1:
            horizon = st.slider("Simulation Horizon (Days)", min_value=15, max_value=60, value=30, step=5, key="sim_horizon")
            daily_burn_val = st.slider("Daily Lifestyle Burn (₹/day)", min_value=0, max_value=2000, value=600, step=50, key="sim_burn")
        with c_sc2:
            inc_savings = st.checkbox("Systematic Savings Routine", value=True, help="Quarantine savings into SBI, then sweep to Kotak Smart FD", key="sim_inc_savings")
            savings_target_val = st.number_input("Monthly Savings Target (₹)", value=48000.0, step=2000.0, key="sim_savings_target")
        with c_sc3:
            inc_salary = st.checkbox("Include Monthly Salary Credit", value=True, key="sim_inc_salary")
            salary_day_val = st.slider("Expected Salary Credit Day", min_value=25, max_value=31, value=29, key="sim_salary_day")
        with c_sc4:
            inc_ashwin = st.checkbox("Include Ashwin Monthly Deposit", value=True, key="sim_inc_ashwin")
            ashwin_day = st.slider("Expected Ashwin Deposit Day", min_value=1, max_value=25, value=10, key="sim_ashwin_day")

        st.markdown("---")
        st.markdown("##### ✈️ Simulate Planned One-Off Expense (What-If Scenario)")
        st.caption("Test how an upcoming large discretionary expense (e.g. flight tickets, gadget, festival shopping) impacts your multi-bank liquidity.")
        we1, we2, we3, we4 = st.columns([2, 1.5, 1.5, 1])
        with we1:
            sim_exp_title = st.text_input("Expense Description", value="", placeholder="e.g. Flight Tickets to Goa", key="sim_exp_title")
        with we2:
            sim_exp_amt = st.number_input("Amount (₹)", min_value=0.0, max_value=500000.0, value=0.0, step=1000.0, key="sim_exp_amt")
        with we3:
            sim_exp_date = st.date_input("Expected Debit Date", value=date.today() + timedelta(days=7), key="sim_exp_date")
        with we4:
            sim_exp_acct = st.selectbox("Account", options=["axis", "kotak", "sbi"], format_func=lambda a: config.ACCOUNTS.get(a, {}).get("label", a), key="sim_exp_acct")

    custom_expenses = []
    if sim_exp_amt > 0 and sim_exp_title:
        custom_expenses.append({
            "title": sim_exp_title,
            "amount": float(sim_exp_amt),
            "date": sim_exp_date.isoformat(),
            "account": sim_exp_acct,
            "category": "What-If Discretionary"
        })

    # Run Simulation
    sim = liquidity.simulate_cashflow(
        horizon_days=horizon,
        include_salary=inc_salary,
        salary_day=salary_day_val,
        include_ashwin=inc_ashwin,
        ashwin_deposit_day=ashwin_day,
        monthly_savings_target=float(savings_target_val) if inc_savings else 0.0,
        daily_burn=float(daily_burn_val),
        custom_expenses=custom_expenses
    )

    summ = sim["summary"]
    df_sim = sim["daily_df"]
    transfers = sim["recommended_transfers"]
    alerts = sim["alerts"]
    events = sim["events"]

    # 2. Top Metric Cards
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Starting Liquid Reserves", inr(summ["starting_liquid"]), help="Total cash across all 3 bank accounts today")
    k2.metric("Projected Ending Reserves", inr(summ["ending_liquid"]), delta=f"{'+' if summ['ending_liquid'] >= summ['starting_liquid'] else ''}{inr(summ['ending_liquid'] - summ['starting_liquid'])} net flow", delta_color="normal")
    k3.metric("Lowest Projected Point", inr(summ["min_total_liquid"]), delta="100% Solvent ✅", delta_color="off", help="Lowest total liquid reserves reached during simulation")
    k4.metric("Next Major Inflow", f"~{salary_day_val}th Aug/Sep", delta=f"{inr(summ['salary_amount'])} Salary", delta_color="off")

    # 3. Proactive Transfer Recommendations Callout
    if transfers:
        for t in transfers:
            st.info(f"💡 **Recommended Action ({t['date']})**: Transfer **{inr(t['amount'])}** from **{t['from_account'].upper()} ➔ {t['to_account'].upper()}** — *{t['reason']}*")

    # 4. Interactive Balance Trajectory Chart
    st.subheader("📈 Projected Multi-Bank Balance Trajectory")
    st.caption(f"Day-by-day cashflow simulation across 3 bank accounts ({summ['start_date']} to {summ['end_date']}).")
    
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatter(
        x=df_sim["day_name"], y=df_sim["axis_balance"],
        name="Axis Bank (Salary & Operating)",
        line=dict(color="#a855f7", width=2.5),
        mode="lines+markers",
        marker=dict(size=5)
    ))
    fig_radar.add_trace(go.Scatter(
        x=df_sim["day_name"], y=df_sim["kotak_total"],
        name="Kotak 811 (Checking + Smart FD)",
        line=dict(color="#06b6d4", width=2.5),
        mode="lines+markers",
        marker=dict(size=5)
    ))
    fig_radar.add_trace(go.Scatter(
        x=df_sim["day_name"], y=df_sim["sbi_balance"],
        name="State Bank of India",
        line=dict(color="#f59e0b", width=2),
        mode="lines"
    ))
    fig_radar.add_trace(go.Scatter(
        x=df_sim["day_name"], y=df_sim["total_liquid"],
        name="Total Consolidated Liquid Net Worth",
        line=dict(color="#10b981", width=3.5, dash="dot"),
        mode="lines"
    ))

    # Add Safe Zero Baseline
    fig_radar.add_hline(
        y=0, line_dash="dash", line_color="#ef4444",
        annotation_text="Zero Balance Baseline",
        annotation_position="bottom right",
        annotation_font=dict(color="#ef4444", size=10)
    )

    layout_plot(fig_radar, height=400)
    fig_radar.update_layout(
        margin=dict(l=20, r=20, t=50, b=50),
        hovermode="x unified",
        font=dict(family="'Plus Jakarta Sans', -apple-system, sans-serif", color="#52525b", size=12),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.06,
            x=0,
            font=dict(color="#09090b", size=11),
        )
    )
    fig_radar.update_xaxes(
        gridcolor="#f4f4f5",
        showgrid=True,
        tickangle=-30,
        nticks=10,
        tickfont=dict(size=11, color="#52525b")
    )
    fig_radar.update_yaxes(
        gridcolor="#f4f4f5",
        zeroline=False,
        tickprefix="₹",
        tickfont=dict(size=11, color="#52525b")
    )
    st.plotly_chart(fig_radar, width="stretch")

    # 5. Chronological Payment & Inflow Calendar Grid
    st.subheader("📅 Chronological Payment & Cashflow Schedule")
    st.caption("All upcoming salary credits, loan auto-debits, and credit card statement deadlines.")

    if events:
        ev_rows = []
        for ev in events:
            sign = "+" if ev["is_inflow"] else "-"
            ev_rows.append({
                "Date": ev["date"],
                "Account": ev["account"].upper(),
                "Event / Description": ev["title"],
                "Category": ev["category"],
                "Amount": f"{sign}{inr(abs(ev['amount']))}",
                "Type": "🟢 Inflow" if ev["is_inflow"] else "🔴 Debit"
            })
        st.dataframe(pd.DataFrame(ev_rows), width="stretch", hide_index=True)
    else:
        st.info("No scheduled events in this window.")


