"""Rewards & Miles Valuation and Flight Redemption Optimizer.

Provides analytical engines to:
1. Maximize portfolio value across Indian hotel/airline transfer partners vs cashback.
2. Calculate flight award seat requirements, partner transfer conversions, net ₹/pt value,
   and recommend optimal booking paths (points vs cash).
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional
import pandas as pd
from .catalog import CARD_PROGRAMS, FLIGHT_BENCHMARKS


def _inr_fmt(val: float) -> str:
    """Format float into standard Indian Rupee notation."""
    val_int = int(round(val))
    neg = val_int < 0
    s = str(abs(val_int))
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


def get_card_program(variant: str) -> Dict[str, Any]:
    """Retrieve catalog profile for a card variant or provide fallback."""
    if variant in CARD_PROGRAMS:
        return CARD_PROGRAMS[variant]
    
    # Fuzzy match by keyword
    v_lower = variant.lower()
    for name, prog in CARD_PROGRAMS.items():
        if name.lower() in v_lower or v_lower in name.lower():
            return prog
        
    # Generic fallback
    return {
        "issuer": "Bank",
        "currency_name": "Reward Points",
        "baseline_value_inr": 0.25,
        "statement_credit_inr": 0.20,
        "flight_spend_earn_pct": 2.0,
        "general_spend_earn_pct": 1.0,
        "transfer_partners": [
            {
                "partner": "Statement Credit",
                "category": "Cashback",
                "card_pts": 1,
                "partner_pts": 1,
                "partner_pt_val_inr": 0.25,
                "effective_inr_per_card_pt": 0.25,
                "sweet_spot": True,
                "notes": "Direct statement credit / shopping offset.",
            }
        ],
    }


def evaluate_card_portfolio(cards_df: pd.DataFrame) -> Dict[str, Any]:
    """Evaluate full portfolio points balance, baseline vs optimal valuations,
    and find the best redemption channel per card.
    """
    if cards_df is None or cards_df.empty:
        return {
            "total_points": 0,
            "total_baseline_val_inr": 0.0,
            "total_optimal_val_inr": 0.0,
            "net_uplift_inr": 0.0,
            "cards": [],
        }

    card_evals = []
    tot_points = 0.0
    tot_base_val = 0.0
    tot_opt_val = 0.0

    for _, r in cards_df.iterrows():
        pts = float(r.get("points_balance") or 0.0)
        cname = str(r.get("card_name", "Card"))
        variant = str(r.get("card_variant") or cname)
        last4 = str(r.get("card_last4") or "")
        cid = str(r.get("card_id", ""))

        prog = get_card_program(variant)
        base_rate = prog.get("baseline_value_inr", 0.25)
        base_val = pts * base_rate

        partners_analysis = []
        best_partner = None
        best_val = base_val
        best_eff_rate = base_rate

        for p in prog.get("transfer_partners", []):
            card_unit = p.get("card_pts", 1)
            partner_unit = p.get("partner_pts", 1)
            pt_val = p.get("partner_pt_val_inr", 1.0)
            
            # Transfer output
            transferred_pts = (pts / card_unit) * partner_unit if card_unit > 0 else 0.0
            tot_p_val = transferred_pts * pt_val
            eff_rate = tot_p_val / pts if pts > 0 else (partner_unit / card_unit) * pt_val

            p_entry = {
                "partner": p["partner"],
                "category": p.get("category", "Partner"),
                "ratio": f"{card_unit}:{partner_unit}",
                "transferred_points": round(transferred_pts),
                "estimated_val_inr": tot_p_val,
                "effective_inr_per_card_pt": eff_rate,
                "sweet_spot": p.get("sweet_spot", False),
                "notes": p.get("notes", ""),
            }
            partners_analysis.append(p_entry)

            if tot_p_val > best_val:
                best_val = tot_p_val
                best_eff_rate = eff_rate
                best_partner = p_entry

        uplift = best_val - base_val

        tot_points += pts
        tot_base_val += base_val
        tot_opt_val += best_val

        card_evals.append({
            "card_id": cid,
            "card_name": cname,
            "card_variant": variant,
            "card_last4": last4,
            "currency_name": prog.get("currency_name", "Points"),
            "points_balance": pts,
            "baseline_value_inr": base_val,
            "baseline_rate": base_rate,
            "optimal_value_inr": best_val,
            "optimal_rate": best_eff_rate,
            "uplift_inr": uplift,
            "best_partner": best_partner,
            "all_partners": partners_analysis,
            "flight_spend_earn_pct": prog.get("flight_spend_earn_pct", 2.0),
        })

    return {
        "total_points": tot_points,
        "total_baseline_val_inr": tot_base_val,
        "total_optimal_val_inr": tot_opt_val,
        "net_uplift_inr": tot_opt_val - tot_base_val,
        "cards": card_evals,
    }


def optimize_flight_booking(
    route_name: str,
    cabin: str,
    cash_fare_inr: float,
    cards_df: pd.DataFrame,
) -> Dict[str, Any]:
    """Calculate award flight redemption opportunities vs cash flight ticket.

    Compares:
    1. Direct airline award transfers (KrisFlyer, Qatar Avios, Virgin Atlantic, Air India).
    2. Travel portal points redemptions (Scapia coins, YES Cart, SmartBuy).
    3. Optimal card to swipe if paying cash (maximizing points accrual).
    """
    benchmark = FLIGHT_BENCHMARKS.get(route_name)
    if not benchmark:
        # Fallback to Singapore/SE Asia as a benchmark representative
        route_name = "India ⇄ Singapore / SE Asia"
        benchmark = FLIGHT_BENCHMARKS[route_name]

    cabin_clean = cabin.capitalize()
    if cabin_clean not in ("Economy", "Business"):
        cabin_clean = "Economy"

    typical_fares = benchmark.get("typical_cash_fare_inr", {})
    if cash_fare_inr <= 0:
        cash_fare_inr = float(typical_fares.get(cabin_clean, 25000))

    portfolio = evaluate_card_portfolio(cards_df)
    user_cards = portfolio["cards"]

    # Analyze airline award redemption possibilities
    award_options = []

    for prog in benchmark.get("programs", []):
        airline = prog["airline"]
        needed_miles = prog["business_miles"] if cabin_clean == "Business" else prog["economy_miles"]
        taxes = prog.get("taxes_inr", 3000)
        net_cash_saved = max(0.0, cash_fare_inr - taxes)

        # Check which cards can transfer to this airline
        for c in user_cards:
            variant_prog = get_card_program(c["card_variant"])
            for tp in variant_prog.get("transfer_partners", []):
                # Match partner by name or airline keyword
                pname = tp["partner"].lower()
                air_lower = airline.lower()
                matches = (
                    pname in air_lower
                    or air_lower in pname
                    or ("krisflyer" in pname and "krisflyer" in air_lower)
                    or ("qatar" in pname and "qatar" in air_lower)
                    or ("avios" in pname and "avios" in air_lower)
                    or ("virgin" in pname and "virgin" in air_lower)
                    or ("air india" in pname and "air india" in air_lower)
                )

                if matches:
                    card_u = tp.get("card_pts", 1)
                    part_u = tp.get("partner_pts", 1)
                    card_pts_needed = needed_miles * (card_u / part_u)
                    user_bal = c["points_balance"]
                    has_enough = user_bal >= card_pts_needed
                    shortfall = max(0.0, card_pts_needed - user_bal)
                    val_per_card_pt = (net_cash_saved / card_pts_needed) if card_pts_needed > 0 else 0.0

                    award_options.append({
                        "type": "Airline Award Transfer",
                        "airline": airline,
                        "card_name": c["card_name"],
                        "card_variant": c["card_variant"],
                        "card_last4": c["card_last4"],
                        "currency": c["currency_name"],
                        "transfer_ratio": f"{card_u}:{part_u}",
                        "needed_miles": needed_miles,
                        "card_points_needed": int(round(card_pts_needed)),
                        "current_balance": int(round(user_bal)),
                        "has_enough": has_enough,
                        "shortfall": int(round(shortfall)),
                        "taxes_inr": taxes,
                        "cash_saved_inr": net_cash_saved,
                        "effective_inr_per_pt": val_per_card_pt,
                        "score": (val_per_card_pt * 100) + (50 if has_enough else -30),
                    })

    # Direct Portal redemptions (e.g. Scapia coins or YES Cart)
    portal_options = []
    for c in user_cards:
        v_lower = c["card_variant"].lower()
        if "scapia" in v_lower and c["points_balance"] > 0:
            # 5 coins = 1 INR
            coin_val = c["points_balance"] * 0.20
            applied_val = min(cash_fare_inr, coin_val)
            portal_options.append({
                "type": "Travel Portal Pay-with-Points",
                "portal": "Scapia App Flights",
                "card_variant": c["card_variant"],
                "points_used": int(round(applied_val / 0.20)),
                "cash_discount_inr": applied_val,
                "copay_inr": max(0.0, cash_fare_inr - applied_val),
                "effective_inr_per_pt": 0.20,
            })
        elif "yes" in v_lower and c["points_balance"] > 0:
            # 1 YES pt = 0.25 INR on YES Cart
            yes_val = c["points_balance"] * 0.25
            applied_val = min(cash_fare_inr, yes_val)
            portal_options.append({
                "type": "Travel Portal Pay-with-Points",
                "portal": "YES Cart Flights",
                "card_variant": c["card_variant"],
                "points_used": int(round(applied_val / 0.25)),
                "cash_discount_inr": applied_val,
                "copay_inr": max(0.0, cash_fare_inr - applied_val),
                "effective_inr_per_pt": 0.25,
            })

    # Find best card to pay cash if purchasing directly
    cash_spend_recommendations = []
    for c in user_cards:
        rate = c.get("flight_spend_earn_pct", 2.0)
        expected_reward_val = cash_fare_inr * (rate / 100.0)
        cash_spend_recommendations.append({
            "card_name": c["card_name"],
            "card_variant": c["card_variant"],
            "card_last4": c["card_last4"],
            "flight_earn_rate_pct": rate,
            "expected_reward_val_inr": expected_reward_val,
        })
    cash_spend_recommendations.sort(key=lambda x: x["flight_earn_rate_pct"], reverse=True)
    best_cash_card = cash_spend_recommendations[0] if cash_spend_recommendations else None

    # Rank award options by score (has_enough first, then highest value per point)
    award_options.sort(key=lambda x: (x["has_enough"], x["effective_inr_per_pt"]), reverse=True)
    top_award = award_options[0] if award_options else None

    # Formulate executive summary verdict
    verdict_lines = []
    if top_award and top_award["has_enough"]:
        verdict_lines.append(
            f"🏆 **Top Recommendation: Book via {top_award['airline']} Award Seat**\n"
            f"• Transfer **{top_award['card_points_needed']:,} {top_award['currency']}** from your **{top_award['card_variant']}** "
            f"(Ratio {top_award['transfer_ratio']}) to get {top_award['needed_miles']:,} miles.\n"
            f"• Net cash saved: **{_inr_fmt(top_award['cash_saved_inr'])}** (after paying {_inr_fmt(top_award['taxes_inr'])} taxes).\n"
            f"• Effective value unlocked: **₹{top_award['effective_inr_per_pt']:.2f} per card point** (vs standard ₹0.25 baseline)."
        )
    elif top_award:
        verdict_lines.append(
            f"💡 **Best Award Path: {top_award['airline']} (Points Shortfall)**\n"
            f"• Requires **{top_award['card_points_needed']:,} points** on **{top_award['card_variant']}**, but your current balance is **{top_award['current_balance']:,}** "
            f"(shortfall of {top_award['shortfall']:,} pts).\n"
            f"• Value unlocked if topped up: **₹{top_award['effective_inr_per_pt']:.2f} per point**."
        )
    else:
        verdict_lines.append("No direct airline transfer partner detected for this specific route.")

    if portal_options:
        p0 = portal_options[0]
        verdict_lines.append(
            f"• *Alternative Portal Option*: Redeem {p0['points_used']:,} points on **{p0['portal']}** to instantly slash "
            f"**{_inr_fmt(p0['cash_discount_inr'])}** off the ticket (Pay remaining {_inr_fmt(p0['copay_inr'])})."
        )

    if best_cash_card:
        verdict_lines.append(
            f"💳 **Best Card to Pay Cash**: If booking with cash, use your **{best_cash_card['card_variant']}** "
            f"to earn an accelerated **{best_cash_card['flight_earn_rate_pct']}% return** "
            f"(~{_inr_fmt(best_cash_card['expected_reward_val_inr'])} reward value back)."
        )

    return {
        "route_name": route_name,
        "cabin": cabin_clean,
        "cash_fare_inr": cash_fare_inr,
        "top_award": top_award,
        "all_award_options": award_options,
        "portal_options": portal_options,
        "best_cash_card": best_cash_card,
        "all_cash_cards": cash_spend_recommendations,
        "verdict_summary": "\n\n".join(verdict_lines),
    }
