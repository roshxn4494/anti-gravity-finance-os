"""Rewards & Miles Optimizer Tab.

Allows users to manage credit card points balances, discover optimal redemption
avenues across Indian loyalty programs, and calculate award flight redemption options.
"""
from __future__ import annotations

import re
from datetime import datetime
import streamlit as st
import pandas as pd

from finance import db
from finance.rewards.catalog import CARD_PROGRAMS, FLIGHT_BENCHMARKS
from finance.rewards.optimizer import evaluate_card_portfolio, optimize_flight_booking, _inr_fmt


def tab_rewards():
    st.markdown("## 🎯 Rewards & Miles Optimizer")
    st.caption("Maximize the real-world Rupee value of your credit card points across airline miles, luxury hotels, vouchers, and travel portals.")

    # Load current cards from DB
    cards_df = db.load_card_rewards()

    # If empty, run seed to ensure statements are populated
    if cards_df.empty:
        db.seed_card_rewards_from_statements()
        cards_df = db.load_card_rewards()

    portfolio = evaluate_card_portfolio(cards_df)

    # Top KPI Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(
            label="Total Points Balance",
            value=f"{int(portfolio['total_points']):,}",
            help="Total reward points / miles accumulated across all tracked cards."
        )
    with m2:
        st.metric(
            label="Max Optimized Value",
            value=_inr_fmt(portfolio["total_optimal_val_inr"]),
            delta=f"+{_inr_fmt(portfolio['net_uplift_inr'])} vs Cash",
            help="Estimated Rupee value if redeemed via optimal airline/hotel transfer sweet spots."
        )
    with m3:
        st.metric(
            label="Baseline Cash Value",
            value=_inr_fmt(portfolio["total_baseline_val_inr"]),
            help="Value if redeemed for statement credit or generic cashback."
        )
    with m4:
        multiplier = (portfolio["total_optimal_val_inr"] / portfolio["total_baseline_val_inr"]) if portfolio["total_baseline_val_inr"] > 0 else 1.0
        st.metric(
            label="Value Multiplier",
            value=f"{multiplier:.2f}x",
            help="How many times more value you unlock by transferring to partner programs."
        )

    st.markdown("---")

    # Three functional sub-sections
    tab_port, tab_matrix, tab_flight = st.tabs([
        "💳 Points Portfolio & Card Manager",
        "🎁 Where Best to Use My Points",
        "✈️ Flight Booking Optimizer",
    ])

    # ---------------------------------------------------------
    # TAB 1: POINTS PORTFOLIO & CARD MANAGER
    # ---------------------------------------------------------
    with tab_port:
        st.markdown("### 💳 Credit Card Points Ledger")
        st.caption("Update your live points balances or adjust card variants. Balances auto-sync with imported statements.")

        variant_options = list(CARD_PROGRAMS.keys())

        if not cards_df.empty:
            for idx, r in cards_df.iterrows():
                cid = r["card_id"]
                cname = r["card_name"]
                cvar = r["card_variant"]
                last4 = r["card_last4"] or ""
                cur_pts = float(r["points_balance"] or 0.0)

                with st.container(border=True):
                    c_left, c_mid, c_pts, c_act = st.columns([3, 3, 2.5, 1.5])
                    
                    with c_left:
                        st.markdown(f"**{cname}**")
                        st.caption(f"Card Last 4: `{last4}` | ID: `{cid}`")
                    
                    with c_mid:
                        var_idx = variant_options.index(cvar) if cvar in variant_options else 0
                        chosen_variant = st.selectbox(
                            "Card Variant / Tier",
                            options=variant_options,
                            index=var_idx,
                            key=f"var_{cid}_{idx}",
                        )

                    with c_pts:
                        new_pts = st.number_input(
                            "Points / Miles Balance",
                            min_value=0.0,
                            max_value=10000000.0,
                            value=float(cur_pts),
                            step=500.0,
                            key=f"pts_{cid}_{idx}",
                        )

                    with c_act:
                        st.write("")
                        st.write("")
                        if st.button("💾 Save", key=f"save_{cid}_{idx}", use_container_width=True):
                            db.upsert_card_reward({
                                "card_id": cid,
                                "card_name": cname,
                                "card_variant": chosen_variant,
                                "card_last4": last4,
                                "points_balance": new_pts,
                                "source": "user_manual",
                                "notes": f"Manual update on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                            })
                            st.success(f"Saved {cname}!")
                            st.rerun()

        # Add New Card Form
        with st.expander("➕ Add Another Credit Card to Rewards Tracker"):
            with st.form("add_new_card_form"):
                fc1, fc2, fc3 = st.columns(3)
                with fc1:
                    new_card_name = st.text_input("Card Name", placeholder="e.g. HDFC Infinia")
                with fc2:
                    new_card_variant = st.selectbox("Card Variant", options=variant_options)
                with fc3:
                    new_last4 = st.text_input("Last 4 Digits", max_chars=4, placeholder="1234")

                new_initial_pts = st.number_input("Initial Points Balance", min_value=0.0, step=1000.0)
                submit_add = st.form_submit_button("Add Card to Portfolio")

                if submit_add:
                    if not new_card_name.strip():
                        st.error("Please provide a card name.")
                    else:
                        cid = re.sub(r"[^a-zA-Z0-9]+", "_", f"{new_card_name}_{new_last4}").strip("_").lower()
                        db.upsert_card_reward({
                            "card_id": cid,
                            "card_name": new_card_name.strip(),
                            "card_variant": new_card_variant,
                            "card_last4": new_last4.strip(),
                            "points_balance": new_initial_pts,
                            "source": "user_manual",
                        })
                        st.success(f"Added {new_card_name} to rewards tracker!")
                        st.rerun()

    # ---------------------------------------------------------
    # TAB 2: WHERE BEST TO USE MY POINTS (REDEMPTION MATRIX)
    # ---------------------------------------------------------
    with tab_matrix:
        st.markdown("### 🎁 Where Best to Use My Points")
        st.caption("Strategic valuation breakdown comparing hotel transfers, airline miles, travel portals, and statement cashback.")

        if not portfolio["cards"]:
            st.info("No card points available to analyze. Please add or update points above.")
        else:
            for c in portfolio["cards"]:
                pts = c["points_balance"]
                cname = c["card_name"]
                cvar = c["card_variant"]
                currency = c["currency_name"]
                opt_val = c["optimal_value_inr"]
                base_val = c["baseline_value_inr"]
                uplift = c["uplift_inr"]
                best_p = c["best_partner"]

                with st.expander(
                    f"**{cvar}** — {int(pts):,} {currency} (Max Value: {_inr_fmt(opt_val)})",
                    expanded=(pts > 0)
                ):
                    v_col1, v_col2, v_col3 = st.columns(3)
                    with v_col1:
                        st.markdown(f"**Current Balance**: `{int(pts):,} {currency}`")
                    with v_col2:
                        st.markdown(f"**Baseline Cash Value**: `{_inr_fmt(base_val)}` (₹{c['baseline_rate']:.2f}/pt)")
                    with v_col3:
                        if uplift > 0:
                            st.markdown(f"**Max Value**: :green[**{_inr_fmt(opt_val)}**] (+{_inr_fmt(uplift)})")
                        else:
                            st.markdown(f"**Max Value**: `{_inr_fmt(opt_val)}`")

                    if best_p and pts > 0:
                        st.success(
                            f"🏆 **Sweet Spot Recommendation**: Transfer to **{best_p['partner']}** "
                            f"(Ratio {best_p['ratio']}) to get **{best_p['transferred_points']:,} partner points**, "
                            f"worth approx **{_inr_fmt(best_p['estimated_val_inr'])}** (₹{best_p['effective_inr_per_card_pt']:.2f}/card pt)! "
                            f"*{best_p['notes']}*"
                        )

                    # Table of all transfer options
                    partners_data = []
                    for p in c["all_partners"]:
                        partners_data.append({
                            "Redemption Partner": p["partner"],
                            "Category": p["category"],
                            "Transfer Ratio": p["ratio"],
                            "Transferred Units": f"{p['transferred_points']:,}",
                            "Estimated Value (₹)": _inr_fmt(p["estimated_val_inr"]),
                            "Effective ₹ / Card Pt": f"₹{p['effective_inr_per_card_pt']:.2f}",
                            "Notes": p["notes"],
                        })

                    if partners_data:
                        st.dataframe(pd.DataFrame(partners_data), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # TAB 3: FLIGHT BOOKING OPTIMIZER
    # ---------------------------------------------------------
    with tab_flight:
        st.markdown("### ✈️ Flight Booking Redemption Optimizer")
        st.caption("Planning a trip? Enter your destination and cabin to see which card's points give you maximum value vs paying cash.")

        f_col1, f_col2, f_col3 = st.columns([3, 2, 2.5])
        
        with f_col1:
            route_names = list(FLIGHT_BENCHMARKS.keys())
            selected_route = st.selectbox(
                "Popular Route / Region",
                options=route_names,
                index=0,
            )

        with f_col2:
            cabin_class = st.selectbox("Cabin Class", options=["Economy", "Business"])

        # Default benchmark cash fare
        bench_fare = FLIGHT_BENCHMARKS[selected_route]["typical_cash_fare_inr"].get(cabin_class, 25000)

        with f_col3:
            cash_fare = st.number_input(
                "Estimated Cash Ticket Price (₹)",
                min_value=1000.0,
                max_value=2000000.0,
                value=float(bench_fare),
                step=1000.0,
            )

        dest_list = FLIGHT_BENCHMARKS[selected_route].get("destinations", [])
        st.caption(f"📍 Common destinations covered: {', '.join(dest_list)}")

        if st.button("⚡ Calculate Best Way to Book", type="primary", use_container_width=True):
            flight_res = optimize_flight_booking(
                route_name=selected_route,
                cabin=cabin_class,
                cash_fare_inr=cash_fare,
                cards_df=cards_df,
            )

            st.markdown("#### 💡 Strategic Recommendation")
            st.info(flight_res["verdict_summary"])

            # Detailed award options table
            st.markdown("#### 📊 Award Seat Transfer Analysis")
            if flight_res["all_award_options"]:
                award_rows = []
                for a in flight_res["all_award_options"]:
                    status = "✅ Ready to Book" if a["has_enough"] else f"⚠️ Shortfall: {a['shortfall']:,} pts"
                    award_rows.append({
                        "Airline Award Program": a["airline"],
                        "Source Card": f"{a['card_variant']} ({a['card_last4']})",
                        "Card Points Needed": f"{a['card_points_needed']:,}",
                        "Your Balance": f"{a['current_balance']:,}",
                        "Status": status,
                        "Taxes / Co-Pay": _inr_fmt(a["taxes_inr"]),
                        "Net Cash Saved": _inr_fmt(a["cash_saved_inr"]),
                        "Effective ₹ / Point": f"₹{a['effective_inr_per_pt']:.2f}",
                    })
                st.dataframe(pd.DataFrame(award_rows), use_container_width=True, hide_index=True)
            else:
                st.write("No direct award transfer programs mapped for this route.")

            # Cash booking alternative table
            st.markdown("#### 💳 Best Cards to Swipe for Cash Booking")
            st.caption("If award seats are unavailable, earn accelerated reward points by swiping the highest-yielding card:")
            if flight_res["all_cash_cards"]:
                cash_rows = []
                for cc in flight_res["all_cash_cards"]:
                    cash_rows.append({
                        "Card": f"{cc['card_variant']} ({cc['card_last4']})",
                        "Flight Earn Return": f"{cc['flight_earn_rate_pct']}%",
                        "Reward Value Back": _inr_fmt(cc["expected_reward_val_inr"]),
                    })
                st.dataframe(pd.DataFrame(cash_rows), use_container_width=True, hide_index=True)
