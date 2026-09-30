"""Recurring payments detection and tracking engine (Change 19).

Identifies repeating monthly obligations (rent, EMIs, salary credits, SIP investments, subscriptions),
verifies payment consistency, and flags upcoming or missing obligations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from .. import config, db
from ..money import format_inr_paise, rupees_to_paise


@dataclass
class RecurringObligation:
    counterparty: str
    category: str
    expected_amount_paise: int
    expected_day: int
    frequency: str  # 'monthly'
    occurrence_count: int
    last_payment_date: str
    status: str     # 'active' | 'missing' | 'drift_detected'
    evidence: str


def detect_recurring_payments() -> list[RecurringObligation]:
    """Scans historical transactions to detect recurring obligations."""
    conn = db.connect()
    df = pd.read_sql_query(
        "SELECT * FROM transactions WHERE counterparty IS NOT NULL AND counterparty != '' ORDER BY txn_date ASC",
        conn,
    )
    conn.close()

    if df.empty:
        return []

    df["day"] = df["txn_date"].str[8:10].astype(int)
    obligations = []

    for cp, group in df.groupby("counterparty"):
        if len(group) < config.P2P_MIN_OCCURRENCES:
            continue

        # Check amount consistency
        amounts = group["amount"].abs().tolist()
        avg_amt = sum(amounts) / len(amounts)
        if avg_amt == 0:
            continue

        max_drift = max(abs(a - avg_amt) / avg_amt for a in amounts)
        if max_drift > config.P2P_AMOUNT_TOLERANCE:
            continue

        # Check day-of-month consistency (circular distance across month boundary)
        days = group["day"].tolist()
        median_day = sorted(days)[len(days) // 2]
        max_day_drift = max(min(abs(d - median_day), 31 - abs(d - median_day)) for d in days)
        if max_day_drift > config.P2P_DAY_TOLERANCE:
            continue

        last_row = group.iloc[-1]
        cat = str(last_row.get("category") or "Uncategorized")
        exp_paise = rupees_to_paise(avg_amt)
        last_date = str(last_row["txn_date"])

        ev = (
            f"Detected {len(group)} recurring occurrences around day {median_day} "
            f"with average ₹{avg_amt:,.2f} (max drift {max_drift*100:.1f}%)."
        )

        obligations.append(
            RecurringObligation(
                counterparty=str(cp),
                category=cat,
                expected_amount_paise=exp_paise,
                expected_day=median_day,
                frequency="monthly",
                occurrence_count=len(group),
                last_payment_date=last_date,
                status="active",
                evidence=ev,
            )
        )

    return obligations


def get_monthly_obligations_summary(month_str: str = "") -> dict[str, Any]:
    """Cycle-aware monthly obligations tracking engine (Option C).

    Evaluates settlement status for House Rent, Personal Loan EMIs, and Credit Card bills
    for the specified month (e.g. '2026-09'), recognizing early month-end payments
    (e.g. rent paid on Aug 31 for the September cycle).
    """
    from dateutil.relativedelta import relativedelta
    from .. import profile

    txns = db.load_all()
    prof = profile.load_profile()

    all_dates = sorted(txns["txn_date"].unique()) if not txns.empty else []
    all_mks = sorted(list(set(d[:7] for d in all_dates)))
    target_month = month_str.strip() if month_str and month_str != "latest" else (all_mks[-1] if all_mks else datetime.now().strftime("%Y-%m"))

    dt = datetime.strptime(target_month + "-01", "%Y-%m-%d")
    prev_m = (dt - relativedelta(months=1)).strftime("%Y-%m")
    month_txns = txns[txns["txn_date"].str.startswith(target_month)] if not txns.empty else txns

    # -------------------------------------------------------------------------
    # 1. House Rent (Cycle-Aware)
    # -------------------------------------------------------------------------
    rent_kws = [k.upper() for k in prof.get("personal_categories", {}).get("Rent", ["SRINIVAS"])]
    rent_kws += ["SRINIVAS", "RENT", "9494012345"]
    
    is_rent = pd.Series(False, index=txns.index) if not txns.empty else pd.Series(dtype=bool)
    if not txns.empty:
        is_rent = (txns["category"] == "Rent") | (txns["counterparty"].fillna("").str.upper().isin(rent_kws))
        for kw in rent_kws:
            is_rent = is_rent | (txns["description"].fillna("").str.upper().str.contains(kw, na=False))
        rent_txns = txns[is_rent & (txns["amount"] <= -5000)].sort_values("txn_date")
    else:
        rent_txns = pd.DataFrame()

    rent_item = None
    last_known_rent = abs(float(rent_txns.iloc[-1]["amount"])) if not rent_txns.empty else 13000.0
    last_known_payee = str(rent_txns.iloc[-1].get("counterparty") or "").strip() or "Srinivas Reddy S L"
    last_known_account = str(rent_txns.iloc[-1].get("account") or "AXIS").upper()

    # Check within current month (1st through 25th)
    same_m = rent_txns[rent_txns["txn_date"].str.startswith(target_month) & (rent_txns["txn_date"].str[8:].astype(int) <= 25)] if not rent_txns.empty else pd.DataFrame()
    if not same_m.empty:
        r = same_m.iloc[-1]
        rent_item = {
            "id": "rent",
            "title": "House Rent",
            "payee": str(r.get("counterparty") or "").strip() or last_known_payee,
            "expected_amount": abs(float(r["amount"])),
            "status": "paid",
            "paid_date": r["txn_date"],
            "paid_amount": abs(float(r["amount"])),
            "account": r["account"].upper(),
            "is_early": False,
            "note": f"Paid on {r['txn_date']} via {r['account'].upper()} UPI",
            "raw_desc": r["description"],
        }
    else:
        # Check early month-end payment in previous month (between 26th and end of previous month)
        prev_tail = rent_txns[(rent_txns["txn_date"] >= f"{prev_m}-26") & (rent_txns["txn_date"] <= f"{prev_m}-31")] if not rent_txns.empty else pd.DataFrame()
        if not prev_tail.empty:
            r = prev_tail.iloc[-1]
            paid_dt = datetime.strptime(r["txn_date"], "%Y-%m-%d")
            days_early = (dt - paid_dt).days
            day_label = f"{days_early} day" if days_early == 1 else f"{days_early} days"
            rent_item = {
                "id": "rent",
                "title": "House Rent",
                "payee": str(r.get("counterparty") or "").strip() or last_known_payee,
                "expected_amount": abs(float(r["amount"])),
                "status": "paid",
                "paid_date": r["txn_date"],
                "paid_amount": abs(float(r["amount"])),
                "account": r["account"].upper(),
                "is_early": True,
                "note": f"Paid {day_label} early on {r['txn_date']} for {target_month} cycle",
                "raw_desc": r["description"],
            }
        else:
            rent_item = {
                "id": "rent",
                "title": "House Rent",
                "payee": last_known_payee,
                "expected_amount": last_known_rent,
                "status": "pending",
                "paid_date": None,
                "paid_amount": 0.0,
                "account": last_known_account,
                "is_early": False,
                "note": "Expected around 1st of month",
                "raw_desc": "",
            }

    # -------------------------------------------------------------------------
    # 2. Personal & Bank Loan EMIs
    # -------------------------------------------------------------------------
    loans_df = db.load_bank_loans()
    loan_items = []
    if not loans_df.empty and not month_txns.empty:
        for _, l in loans_df.iterrows():
            kw = str(l.get("match_keyword", "")).upper()
            amt = float(l.get("match_amount", 0.0) or l.get("monthly_emi", 0.0))
            m_debits = month_txns[month_txns["amount"] < 0]
            if kw:
                m_debits = m_debits[m_debits["description"].str.upper().str.contains(kw, na=False)]
            if amt > 0:
                amt_match = m_debits[m_debits["amount"].abs() == amt]
                if not amt_match.empty:
                    m_debits = amt_match
            if not m_debits.empty:
                d = m_debits.iloc[0]
                loan_items.append({
                    "id": l["id"],
                    "title": l["loan_name"],
                    "lender": l["lender"],
                    "expected_amount": float(l["monthly_emi"]),
                    "debit_day": int(l.get("debit_day", 3)),
                    "status": "paid",
                    "paid_date": d["txn_date"],
                    "paid_amount": abs(float(d["amount"])),
                    "account": d["account"].upper(),
                    "note": f"Debited on {d['txn_date']}",
                    "raw_desc": d["description"],
                })
            else:
                loan_items.append({
                    "id": l["id"],
                    "title": l["loan_name"],
                    "lender": l["lender"],
                    "expected_amount": float(l["monthly_emi"]),
                    "debit_day": int(l.get("debit_day", 3)),
                    "status": "pending",
                    "paid_date": None,
                    "paid_amount": 0.0,
                    "account": l.get("account", "AXIS").upper(),
                    "note": f"Expected on {l.get('debit_day', 3)}th of month",
                    "raw_desc": "",
                })

    # -------------------------------------------------------------------------
    # 3. Credit Card Statement Bills
    # -------------------------------------------------------------------------
    cc_stmts = db.load_cc_statements()
    cc_items = []
    if not cc_stmts.empty and not month_txns.empty:
        latest_cc = cc_stmts.sort_values("statement_date").groupby("card_name", as_index=False).last()
        for _, c in latest_cc.iterrows():
            tot_due = float(c.get("total_due", 0.0))
            if tot_due <= 0:
                continue
            c_name = c["card_name"]
            
            # Exact amount match
            exact_amt = month_txns[month_txns["amount"].abs() == tot_due]
            if not exact_amt.empty:
                p = exact_amt.iloc[0]
                cc_items.append({
                    "id": c_name,
                    "title": c_name,
                    "expected_amount": tot_due,
                    "due_date": c.get("due_date", ""),
                    "status": "paid",
                    "paid_date": p["txn_date"],
                    "paid_amount": abs(float(p["amount"])),
                    "account": p["account"].upper(),
                    "note": f"Paid on {p['txn_date']} via {p['account'].upper()} BBPS",
                    "raw_desc": p["description"],
                })
                continue
                
            # BBPS keyword match
            bbps = month_txns[month_txns["description"].str.contains("BBPS", case=False, na=False) & (month_txns["amount"] < 0)]
            bank_kw = c_name.split()[0].upper()
            bank_bbps = bbps[bbps["description"].str.upper().str.contains(bank_kw, na=False)]
            if not bank_bbps.empty:
                tot_p = bank_bbps["amount"].abs().sum()
                last_p = bank_bbps.iloc[-1]
                dates_str = last_p['txn_date'] if len(bank_bbps) == 1 else f"{bank_bbps.iloc[0]['txn_date']}, {last_p['txn_date']}"
                p_cnt_str = f" ({len(bank_bbps)} payments)" if len(bank_bbps) > 1 else ""
                cc_items.append({
                    "id": c_name,
                    "title": c_name,
                    "expected_amount": tot_due,
                    "due_date": c.get("due_date", ""),
                    "status": "paid",
                    "paid_date": last_p["txn_date"],
                    "paid_amount": float(tot_p),
                    "account": last_p["account"].upper(),
                    "note": f"Paid on {dates_str} via {last_p['account'].upper()} BBPS{p_cnt_str}",
                    "raw_desc": last_p["description"],
                })
            else:
                due_d = str(c.get("due_date", "")).strip()
                if due_d and due_d < f"{target_month}-01":
                    cc_items.append({
                        "id": c_name,
                        "title": c_name,
                        "expected_amount": 0.0,
                        "due_date": due_d,
                        "status": "pending",
                        "paid_date": None,
                        "paid_amount": 0.0,
                        "account": "—",
                        "note": f"Awaiting {target_month} statement (Aug bill settled on 25-Aug)",
                        "raw_desc": "",
                    })
                else:
                    cc_items.append({
                        "id": c_name,
                        "title": c_name,
                        "expected_amount": tot_due,
                        "due_date": c.get("due_date", ""),
                        "status": "pending",
                        "paid_date": None,
                        "paid_amount": 0.0,
                        "account": "—",
                        "note": f"Payment Due on {c.get('due_date', '—')}",
                        "raw_desc": "",
                    })

    all_items = [rent_item] + loan_items + cc_items
    paid_count = sum(1 for i in all_items if i["status"] == "paid")
    pending_count = sum(1 for i in all_items if i["status"] == "pending")
    tot_exp = sum(i["expected_amount"] for i in all_items)
    tot_paid = sum(i["paid_amount"] for i in all_items if i["status"] == "paid")

    return {
        "month": target_month,
        "rent": rent_item,
        "loans": loan_items,
        "credit_cards": cc_items,
        "summary": {
            "total_count": len(all_items),
            "paid_count": paid_count,
            "pending_count": pending_count,
            "total_expected": tot_exp,
            "total_paid": tot_paid,
            "all_cleared": (pending_count == 0),
        },
    }
