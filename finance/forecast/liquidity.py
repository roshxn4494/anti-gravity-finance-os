"""30-Day to 60-Day Proactive Liquidity & Cashflow Simulator Engine.

Projects daily bank account balances (Axis, Kotak 811 Checking, Kotak Smart FD, SBI)
across scheduled salary credits, loan auto-debits, credit card statement due dates,
and discretionary burn rates, generating proactive transfer alerts.
"""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd

from finance import db, config


def _fmt_date(d: date) -> str:
    return d.isoformat()


def simulate_cashflow(
    start_date: Optional[date | str] = None,
    horizon_days: int = 45,
    include_salary: bool = True,
    salary_amount: float = 112729.0,
    salary_day: int = 29,
    include_ashwin: bool = True,
    ashwin_amount: Optional[float] = None,
    ashwin_deposit_day: int = 10,
    monthly_savings_target: float = 48000.0,
    daily_burn: float = 600.0,
    burn_account: str = "axis",
    min_safe_buffer: float = 2000.0
) -> Dict[str, Any]:
    """Run a day-by-day cashflow simulation over horizon_days."""
    if start_date is None:
        cur_date = date.today()
    elif isinstance(start_date, str):
        cur_date = date.fromisoformat(start_date)
    else:
        cur_date = start_date

    # 1. Load starting balances from database
    b_df = db.load_account_balances()
    
    # Defaults if not populated
    bal_axis = 1208.21
    bal_kotak_sav = 43555.72
    bal_kotak_fd = 295417.42
    bal_sbi = 49857.96

    if not b_df.empty:
        for _, r in b_df.iterrows():
            acct = r["account"]
            if acct == "axis":
                bal_axis = float(r["total_balance"])
            elif acct == "kotak":
                bal_kotak_sav = float(r.get("savings_balance", 43555.72))
                bal_kotak_fd = float(r.get("smart_fd_balance", 295417.42))
            elif acct == "sbi":
                bal_sbi = float(r["total_balance"])

    # 2. Load scheduled loans
    loans_df = db.load_bank_loans()
    # 3. Load credit card statements
    cc_stmts = db.load_cc_statements()
    cc_emis = db.load_cc_emis()

    # Calculate standard Ashwin monthly obligation if not overridden
    tot_cc_dues = cc_stmts["total_due"].sum() if not cc_stmts.empty else 93027.22
    ash_loans_monthly = 8682.0
    if not loans_df.empty and "borrower" in loans_df.columns:
        ash_loans = loans_df[loans_df["borrower"] == "ashwin"]
        if not ash_loans.empty:
            ash_loans_monthly = float(ash_loans["monthly_emi"].sum())

    computed_ashwin_monthly = tot_cc_dues + ash_loans_monthly
    final_ashwin_amt = ashwin_amount if ashwin_amount is not None else computed_ashwin_monthly

    # 4. Map scheduled recurring calendar events for the simulation period
    # Generate schedule map: date -> list of events
    events_by_date: Dict[date, List[Dict[str, Any]]] = {}

    end_date = cur_date + timedelta(days=horizon_days)
    d = cur_date

    while d <= end_date:
        events_by_date[d] = []
        d += timedelta(days=1)

    # A. Salary Credits & Systematic Savings Flow (Axis ➔ SBI ➔ Kotak Smart FD)
    if include_salary:
        d = cur_date
        while d <= end_date:
            # Check if this day is salary day
            is_sal_day = False
            if d.day == salary_day:
                is_sal_day = True
            elif d.day >= 28:
                next_day = d + timedelta(days=1)
                if next_day.month != d.month and salary_day > d.day:
                    is_sal_day = True

            if is_sal_day and d >= cur_date:
                # 1. Salary credit into Axis
                events_by_date[d].append({
                    "type": "salary",
                    "title": "Monthly Net Salary Credit",
                    "description": "Salary credited from Tiger Analytics",
                    "account": "axis",
                    "amount": salary_amount,
                    "is_inflow": True,
                    "category": "Salary"
                })

                # 2. Systematic Monthly Savings Quarantine: Transfer ₹48,000 from Axis -> SBI
                if monthly_savings_target > 0:
                    events_by_date[d].append({
                        "type": "savings_quarantine",
                        "title": "Systematic Savings: Axis ➔ SBI",
                        "description": f"Quarantine ₹{monthly_savings_target:,.0f} savings immediately into SBI vault",
                        "account": "axis",
                        "amount": -monthly_savings_target,
                        "is_inflow": False,
                        "category": "Investments & Savings"
                    })
                    events_by_date[d].append({
                        "type": "savings_staged",
                        "title": "Savings Received into SBI Vault",
                        "description": f"Staging ₹{monthly_savings_target:,.0f} monthly savings in SBI",
                        "account": "sbi",
                        "amount": monthly_savings_target,
                        "is_inflow": True,
                        "category": "Investments & Savings"
                    })

                    # 3. Scheduled Move: SBI ➔ Kotak (Sweeps into Active Money Smart FD on 1st of month)
                    move_to_kotak_day = d + timedelta(days=2) # 1st of next month
                    if move_to_kotak_day <= end_date:
                        if move_to_kotak_day not in events_by_date:
                            events_by_date[move_to_kotak_day] = []
                        events_by_date[move_to_kotak_day].append({
                            "type": "savings_sweep",
                            "title": "SBI ➔ Kotak Smart FD Sweep",
                            "description": f"Move ₹{monthly_savings_target:,.0f} to Kotak 811 Active Money Smart FD (~7.5% interest)",
                            "account": "sbi",
                            "amount": -monthly_savings_target,
                            "is_inflow": False,
                            "category": "Investments & Savings"
                        })
                        events_by_date[move_to_kotak_day].append({
                            "type": "savings_compounded",
                            "title": "Smart FD Active Money Deposit",
                            "description": f"₹{monthly_savings_target:,.0f} earning ~7.5% in Kotak Smart FD",
                            "account": "kotak",
                            "amount": monthly_savings_target,
                            "is_inflow": True,
                            "category": "Investments & Savings"
                        })

            d += timedelta(days=1)

    # B. Mutual Fund SIPs & Insurance Premiums (from Axis Bank)
    d = cur_date
    while d <= end_date:
        if d.day == 3 and d >= cur_date:
            events_by_date[d].append({
                "type": "sip",
                "title": "Mutual Fund SIP 1 (INDIANESIGN)",
                "description": "ACH e-mandate mutual fund SIP",
                "account": "axis",
                "amount": -1000.0,
                "is_inflow": False,
                "category": "Investments & Savings"
            })
        if d.day == 4 and d >= cur_date:
            events_by_date[d].append({
                "type": "sip",
                "title": "Mutual Fund SIP 2 (INDIANESIGN)",
                "description": "ACH e-mandate mutual fund SIP",
                "account": "axis",
                "amount": -1000.0,
                "is_inflow": False,
                "category": "Investments & Savings"
            })
        if d.day == 7 and d >= cur_date:
            events_by_date[d].append({
                "type": "insurance",
                "title": "Health & Term Insurance Premium",
                "description": "ICICI Bank / INDmoney protection plan",
                "account": "axis",
                "amount": -1389.0,
                "is_inflow": False,
                "category": "Insurance & Protection"
            })
        d += timedelta(days=1)

    # C. Ashwin Expected Settlement Deposits (Into Axis Bank)
    if include_ashwin and final_ashwin_amt > 0:
        d = cur_date
        while d <= end_date:
            if d.day == ashwin_deposit_day and d >= cur_date:
                events_by_date[d].append({
                    "type": "friend_deposit",
                    "title": "Ashwin Pass-Through Monthly Deposit",
                    "description": f"Reimbursement for CC bills (₹{tot_cc_dues:,.0f}) & loans (₹{ash_loans_monthly:,.0f})",
                    "account": "axis",
                    "amount": final_ashwin_amt,
                    "is_inflow": True,
                    "category": "Ashwin"
                })
            d += timedelta(days=1)

    # D. Bank Loan Auto-Debits
    if not loans_df.empty:
        for _, l in loans_df.iterrows():
            deb_day = int(l.get("debit_day", 3))
            emi = float(l["monthly_emi"])
            acct = l.get("account", "axis")
            loan_name = l["loan_name"]
            borrower = l.get("borrower", "user")

            d = cur_date
            while d <= end_date:
                if d.day == deb_day and d >= cur_date:
                    events_by_date[d].append({
                        "type": "loan_emi",
                        "title": f"Loan EMI: {loan_name}",
                        "description": f"{l['lender']} ({'Personal' if borrower == 'user' else 'Ashwin'})",
                        "account": acct,
                        "amount": -emi,
                        "is_inflow": False,
                        "category": "Loans & EMIs"
                    })
                d += timedelta(days=1)

    # D. Credit Card Due Dates (Paid from Kotak 811 via BBPS BillPay)
    # Default typical due dates based on historical statements:
    # YES: 5th | IDFC: 6th | Scapia Federal: 12th | Axis: 14th | Amex: 26th
    card_due_defaults = {
        "YES Bank": {"day": 5, "due": 17783.98, "account": "kotak"},
        "IDFC FIRST": {"day": 6, "due": 11069.62, "account": "kotak"},
        "Scapia": {"day": 12, "due": 20390.64, "account": "kotak"},
        "Axis": {"day": 14, "due": 22702.23, "account": "kotak"},
        "American Express": {"day": 26, "due": 21080.75, "account": "axis"}
    }

    # If statements are in DB, use exact card totals
    if not cc_stmts.empty:
        for _, c in cc_stmts.iterrows():
            c_name = c["card_name"]
            c_due = float(c["total_due"])
            c_due_date = str(c.get("due_date", ""))
            
            # Determine debit day
            deb_day = 15
            if c_due_date and len(c_due_date) >= 10:
                try:
                    deb_day = int(c_due_date[8:10])
                except Exception:
                    deb_day = 15
            else:
                for k, v in card_due_defaults.items():
                    if k.lower() in c_name.lower():
                        deb_day = v["day"]
                        break

            target_acct = "kotak" if "american" not in c_name.lower() else "axis"

            d = cur_date
            while d <= end_date:
                if d.day == deb_day and d >= cur_date:
                    events_by_date[d].append({
                        "type": "cc_payment",
                        "title": f"CC Bill Due: {c_name}",
                        "description": f"Statement bill ({'Kotak BBPS' if target_acct == 'kotak' else 'Axis Direct'})",
                        "account": target_acct,
                        "amount": -c_due,
                        "is_inflow": False,
                        "category": "Credit Card"
                    })
                d += timedelta(days=1)

    # 5. Execute Day-by-Day Simulation
    daily_records = []
    all_events_flat = []
    alerts = []
    recommended_transfers = []

    c_axis = bal_axis
    c_kotak_sav = bal_kotak_sav
    c_kotak_fd = bal_kotak_fd
    c_sbi = bal_sbi

    d = cur_date
    while d <= end_date:
        day_events = events_by_date.get(d, [])
        net_axis_day = 0.0
        net_kotak_day = 0.0
        net_sbi_day = 0.0

        # Apply daily lifestyle burn (from Axis)
        if daily_burn > 0:
            if burn_account == "axis":
                net_axis_day -= daily_burn
            elif burn_account == "kotak":
                net_kotak_day -= daily_burn
            elif burn_account == "sbi":
                net_sbi_day -= daily_burn

        event_titles = []
        for ev in day_events:
            amt = ev["amount"]
            acct = ev["account"]
            if acct == "axis":
                net_axis_day += amt
            elif acct == "kotak":
                net_kotak_day += amt
            elif acct == "sbi":
                net_sbi_day += amt

            ev_copy = dict(ev)
            ev_copy["date"] = _fmt_date(d)
            all_events_flat.append(ev_copy)
            
            sign = "+" if amt > 0 else "-"
            event_titles.append(f"{ev['title']} ({sign}₹{abs(amt):,.0f})")

        c_axis += net_axis_day
        c_kotak_sav += net_kotak_day
        c_sbi += net_sbi_day

        # If Kotak savings goes negative, simulate Smart FD auto-sweep
        if c_kotak_sav < 0:
            deficit = abs(c_kotak_sav)
            if c_kotak_fd >= deficit:
                c_kotak_fd -= deficit
                c_kotak_sav = 0.0
            else:
                c_kotak_sav += c_kotak_fd
                c_kotak_fd = 0.0

        kotak_tot = c_kotak_sav + c_kotak_fd
        tot_liquid = c_axis + kotak_tot + c_sbi

        # Check for Shortfall / Buffer Alerts
        if c_axis < min_safe_buffer and d > cur_date:
            # Check if this alert was already raised recently
            alerts.append({
                "date": _fmt_date(d),
                "account": "axis",
                "severity": "high" if c_axis < 0 else "medium",
                "balance": c_axis,
                "message": f"Axis Bank balance dips to ₹{c_axis:,.0f} on {d.strftime('%d %b')}.",
                "action": "Ensure salary or Ashwin deposit is received on time."
            })

        # Suggest Axis -> Kotak transfer if CC bills due on Kotak exceed Kotak checking
        # Check if tomorrow has a major debit on Kotak that exceeds current checking buffer
        fut_kotak_debit_tomorrow = 0.0
        fut_d = d + timedelta(days=1)
        if fut_d in events_by_date:
            for fe in events_by_date[fut_d]:
                if fe["account"] == "kotak" and fe["amount"] < 0:
                    fut_kotak_debit_tomorrow += abs(fe["amount"])

        if fut_kotak_debit_tomorrow > c_kotak_sav:
            needed = fut_kotak_debit_tomorrow - c_kotak_sav + 2000.0 # include safety buffer
            # Avoid repeating recommendations within 3 days
            last_transfer_date = recommended_transfers[-1]["date"] if recommended_transfers else ""
            if not last_transfer_date or (d - date.fromisoformat(last_transfer_date)).days >= 3:
                recommended_transfers.append({
                    "date": _fmt_date(d),
                    "from_account": "axis",
                    "to_account": "kotak",
                    "amount": round(needed, -2), # round to nearest 100
                    "reason": f"Transfer before {fut_d.strftime('%d %b')} to clear {config.ACCOUNTS['kotak']['label']} bill of ₹{fut_kotak_debit_tomorrow:,.0f} without auto-sweep FD breakage."
                })

        daily_records.append({
            "date": _fmt_date(d),
            "day_name": d.strftime("%a, %d %b"),
            "axis_balance": round(c_axis, 2),
            "kotak_savings": round(c_kotak_sav, 2),
            "kotak_smart_fd": round(c_kotak_fd, 2),
            "kotak_total": round(kotak_tot, 2),
            "sbi_balance": round(c_sbi, 2),
            "total_liquid": round(tot_liquid, 2),
            "events_count": len(day_events),
            "events_summary": " | ".join(event_titles) if event_titles else "Regular daily spend"
        })

        d += timedelta(days=1)

    df_res = pd.DataFrame(daily_records)

    # Deduplicate alerts by date and account
    unique_alerts = []
    seen_alert_keys = set()
    for al in alerts:
        key = (al["date"], al["account"])
        if key not in seen_alert_keys:
            seen_alert_keys.add(key)
            unique_alerts.append(al)

    return {
        "daily_df": df_res,
        "events": all_events_flat,
        "alerts": unique_alerts,
        "recommended_transfers": recommended_transfers,
        "summary": {
            "start_date": _fmt_date(cur_date),
            "end_date": _fmt_date(end_date),
            "horizon_days": horizon_days,
            "starting_liquid": bal_axis + bal_kotak_sav + bal_kotak_fd + bal_sbi,
            "ending_liquid": daily_records[-1]["total_liquid"] if daily_records else 0.0,
            "min_axis": df_res["axis_balance"].min(),
            "min_kotak_total": df_res["kotak_total"].min(),
            "min_total_liquid": df_res["total_liquid"].min(),
            "salary_amount": salary_amount,
            "ashwin_amount": final_ashwin_amt,
            "ashwin_deposit_day": ashwin_deposit_day,
        }
    }
