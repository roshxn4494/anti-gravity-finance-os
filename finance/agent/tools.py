"""Query tools the finance chat agent calls.

Every tool reads the same ``db.load_all()`` frame the dashboard uses, so the
agent's numbers always match the Overview / Transactions tabs. Tools return
compact, already-Indian-formatted strings; the LLM's job is just to interpret
them and answer in English.

Month convention for tool args:
  * ""                   → all imported data
  * "latest"             → the most recent month that has data
  * "last_month"         → the month prior to latest/current
  * "last_3_months"      → last 3 months aggregated
  * "this_year" / "ytd"  → current year
  * "YYYY-MM"            → one month  (e.g. "2026-06")
  * "YYYY"               → a whole year
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
import pandas as pd
from langchain_core.tools import tool

from .. import config, db

# Ensure DB_PATH is set (needed when running outside Streamlit, e.g., in tests or direct agent calls)
if db.DB_PATH is None:
    default_db = Path(__file__).resolve().parents[2] / "data" / "finance.db"
    if default_db.exists():
        db.set_db_path(str(default_db))


def _load() -> pd.DataFrame | None:
    df = db.load_all()
    return df if not df.empty else None


def _spend(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["classification"] == config.CLASSIFICATION_SPEND]


def _inr(x: float) -> str:
    """₹ with Indian digit grouping."""
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


def _months(df: pd.DataFrame) -> list[str]:
    return sorted(set(df["txn_date"].str[:7]))


def _int(value, default: int) -> int:
    """Coerce a tool arg to int."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scope(df: pd.DataFrame, month: str | None) -> tuple[list[str] | None, str | None]:
    """Resolve a month arg → (month keys, error).

    Returns (None, None) for all-time, (list, None) for a matched scope,
    or (None, error) when the month doesn't exist in the data.
    Supports relative terms like 'latest', 'last_month', 'last_3_months', 'this_year', 'last_year'.
    """
    if not month:
        return None, None
    m = str(month).strip()
    lower = m.lower().replace(" ", "_")
    all_ms = _months(df)
    if not all_ms:
        return None, "No statement data imported yet."

    today = date.today()
    cur_m = today.strftime("%Y-%m")

    # Relative shortcuts
    if lower in ("latest", "this_month", "current_month"):
        target = cur_m if cur_m in all_ms else all_ms[-1]
        return [target], None
    if lower in ("last_month", "previous_month", "prev_month"):
        anchor = cur_m if cur_m in all_ms else all_ms[-1]
        y, m_idx = int(anchor[:4]), int(anchor[5:7])
        m_idx -= 1
        if m_idx == 0:
            m_idx, y = 12, y - 1
        prev_m = f"{y:04d}-{m_idx:02d}"
        if prev_m in all_ms:
            return [prev_m], None
        if len(all_ms) >= 2:
            return [all_ms[-2]], None
        return None, f"No data for previous month ('{prev_m}'). Available months: {', '.join(all_ms)}."
    if lower in ("last_3_months", "last_3m", "3_months"):
        return all_ms[-3:], None
    if lower in ("last_6_months", "last_6m", "6_months"):
        return all_ms[-6:], None
    if lower in ("this_year", "current_year", "ytd"):
        yr = str(today.year)
        matched = [x for x in all_ms if x.startswith(yr)]
        if not matched:
            yr = all_ms[-1][:4]
            matched = [x for x in all_ms if x.startswith(yr)]
        return matched, None
    if lower in ("last_year", "previous_year"):
        yr = str(today.year - 1)
        matched = [x for x in all_ms if x.startswith(yr)]
        return (matched, None) if matched else (None, f"No data for last year ({yr}).")

    parts = m.split("-")
    if len(parts) == 2 and len(parts[1]) == 1:
        m = f"{parts[0]}-0{parts[1]}"
    if len(parts) == 1 and len(parts[0]) == 4:  # bare year
        matched = [x for x in all_ms if x.startswith(parts[0])]
        return (matched, None) if matched else (None, f"No data for year '{parts[0]}'.")
    if m in all_ms:
        return [m], None
    avail = ", ".join(all_ms)
    return None, (f"No data for month '{month}'. Available months: {avail}."
                  if avail else "No statement data imported yet.")


def _sub(df: pd.DataFrame, month: str | None):
    """Return (subset, error, label)."""
    months, err = _scope(df, month)
    if err:
        return None, err, ""
    if months is None:
        return df, None, "all time"
    if not months:
        return None, f"No data for {month}.", ""
    sub = df[df["txn_date"].str[:7].isin(months)]
    if len(months) == 1:
        lbl = months[0]
    elif len(months) <= 3:
        lbl = ", ".join(months)
    else:
        lbl = f"{len(months)} months ({months[0]} to {months[-1]})"
    return sub, None, lbl


def _fmt_rows(series: pd.Series, fmt, limit: int = 0) -> str:
    lines = []
    for name, val in series.items():
        lines.append(f"{name}: {fmt(val)}")
        if limit and len(lines) >= limit:
            break
    return "\n".join(lines) or "—"


# Category synonyms map to actual category names in DB
CATEGORY_SYNONYMS = {
    "salary": "Salary",
    "payroll": "Salary",
    "paycheck": "Salary",
    "food": "Food & Dining",
    "dining": "Food & Dining",
    "eating": "Food & Dining",
    "restaurants": "Food & Dining",
    "swiggy": "Food & Dining",
    "zomato": "Food & Dining",
    "groceries": "Groceries",
    "grocery": "Groceries",
    "supermarket": "Groceries",
    "bigbasket": "Groceries",
    "blinkit": "Groceries",
    "zepto": "Groceries",
    "travel": "Transport & Fuel",
    "fuel": "Transport & Fuel",
    "transport": "Transport & Fuel",
    "cabs": "Transport & Fuel",
    "uber": "Transport & Fuel",
    "ola": "Transport & Fuel",
    "petrol": "Transport & Fuel",
    "shopping": "Shopping",
    "clothes": "Shopping",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "myntra": "Shopping",
    "utilities": "Utilities & Bills",
    "bills": "Utilities & Bills",
    "recharge": "Utilities & Bills",
    "electricity": "Utilities & Bills",
    "broadband": "Utilities & Bills",
    "wifi": "Utilities & Bills",
    "medical": "Healthcare",
    "healthcare": "Healthcare",
    "health": "Healthcare",
    "doctor": "Healthcare",
    "pharmacy": "Healthcare",
    "medicine": "Healthcare",
    "pharmeasy": "Healthcare",
    "family": "Family & Support",
    "support": "Family & Support",
    "parents": "Family & Support",
    "rent": "Rent",
    "partner": "Partner",
    "cash": "Cash & ATM",
    "atm": "Cash & ATM",
    "entertainment": "Entertainment & Leisure",
    "movies": "Entertainment & Leisure",
    "uncategorized": "Uncategorized",
    "unknown": "Uncategorized",
}


def _resolve_category(df: pd.DataFrame, category_query: str) -> tuple[str | None, list[str]]:
    """Resolve a category string to an exact category name in the DB using synonyms & fuzzy matching."""
    all_cats = sorted(df["category"].dropna().unique())
    if not category_query:
        return None, all_cats
    q = str(category_query).strip().lower()

    # 1. Direct case-insensitive match
    for c in all_cats:
        if c.lower() == q:
            return c, all_cats

    # 2. Synonym match
    if q in CATEGORY_SYNONYMS and CATEGORY_SYNONYMS[q] in all_cats:
        return CATEGORY_SYNONYMS[q], all_cats

    # 3. Partial substring match in category names
    for c in all_cats:
        if q in c.lower() or c.lower() in q:
            return c, all_cats

    # 4. Partial synonym token match
    for syn_key, target_cat in CATEGORY_SYNONYMS.items():
        if syn_key in q and target_cat in all_cats:
            return target_cat, all_cats

    return None, all_cats


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def spend_total(month: str = "") -> str:
    """Total real spend, optionally for one month ('YYYY-MM'), 'latest', 'last_month',
    'last_3_months', 'this_year', or blank for all time. Real spend excludes internal
    transfers, credit-card payments, friend deposits, investments and fees."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    s = _spend(sub)
    return (f"Real spend ({lbl}): {_inr(s['amount'].abs().sum())} across "
            f"{len(s)} transactions.")


@tool
def spend_by_category(month: str = "") -> str:
    """Real spend grouped by category (Food & Dining, Groceries, Rent, …),
    largest first. Optionally for one month ('YYYY-MM'), 'latest', 'last_month'."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    agg = (_spend(sub).assign(_amt=sub["amount"].abs())
           .groupby("category")["_amt"].sum().sort_values(ascending=False))
    return f"Spend by category ({lbl}):\n" + _fmt_rows(agg, _inr)


@tool
def spend_by_account(month: str = "") -> str:
    """Real spend per bank account (Axis / SBI / Kotak). Optionally for one month."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    agg = (_spend(sub).assign(_amt=sub["amount"].abs())
           .groupby("account")["_amt"].sum().sort_values(ascending=False))
    labelled = {a: config.ACCOUNTS[a]["label"] for a in agg.index}
    out = f"Spend by account ({lbl}):\n"
    out += "\n".join(f"{labelled.get(a, a)}: {_inr(v)}" for a, v in agg.items())
    return out


@tool
def spend_by_month(n: int = 6) -> str:
    """Monthly real-spend trend for the last n months (default 6)."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    num = _int(n, 6)
    ms = _months(df)[-max(1, min(num, 36)):]
    sub = df[df["txn_date"].str[:7].isin(ms)]
    agg = (_spend(sub).assign(_amt=sub["amount"].abs())
           .groupby(sub["txn_date"].str[:7])["_amt"].sum().reindex(ms).fillna(0))
    return "Spend by month:\n" + "\n".join(
        f"{m}: {_inr(v)}" for m, v in agg.items())


@tool
def income_summary(month: str = "") -> str:
    """Salary income, other income (refunds, interest, transfers from people)
    and their total. Optionally for one month ('YYYY-MM'), 'latest', 'last_month'."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    sal = sub[sub["classification"] == config.CLASSIFICATION_INCOME]["amount"].sum()
    other = sub[sub["classification"] == config.CLASSIFICATION_OTHER_INCOME]["amount"].sum()
    return (f"Income ({lbl}):\n"
            f"Salary: {_inr(sal)}\n"
            f"Other income: {_inr(other)}\n"
            f"Total: {_inr(sal + other)}")


@tool
def savings_rate(month: str = "") -> str:
    """Savings rate = (income − spend) / income for a month. Optionally one month."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    income = sub[sub["classification"] == config.CLASSIFICATION_INCOME]["amount"].sum()
    spend = _spend(sub)["amount"].abs().sum()
    if income <= 0:
        return (f"Savings rate ({lbl}): no salary income in this period "
                f"(spend was {_inr(spend)}).")
    rate = (income - spend) / income
    return (f"Savings rate ({lbl}): {rate:.0%} — income {_inr(income)}, "
            f"spend {_inr(spend)}, saved {_inr(income - spend)}.")


@tool
def top_counterparties(month: str = "", k: int = 10) -> str:
    """Who you spent the most money on (merchants & people), largest first.
    k = how many to list (default 10)."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    num_k = _int(k, 10)
    agg = (_spend(sub).assign(_amt=sub["amount"].abs())
           .groupby(sub["counterparty"])["_amt"].sum()
           .sort_values(ascending=False).head(max(1, min(num_k, 50))))
    return f"Top counterparties ({lbl}):\n" + _fmt_rows(agg, _inr)


@tool
def category_spend(category: str, month: str = "") -> str:
    """Spend or income in one category (e.g. 'Food & Dining', 'Salary', 'Rent', 'Groceries',
    'Travel', 'Medical', 'Bills', 'Shopping'). Automatically maps synonyms.
    Optionally for one month ('YYYY-MM'), 'latest', 'last_month'."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err

    resolved_cat, available_cats = _resolve_category(df, category)
    if not resolved_cat:
        cats_str = ", ".join(available_cats)
        return f"Could not find category matching '{category}' ({lbl}). Available categories: {cats_str}."

    if resolved_cat in ("Salary", "Income"):
        agg = sub[sub["classification"] == config.CLASSIFICATION_INCOME]
        title_word = "Income"
    else:
        spend = _spend(sub)
        agg = spend[spend["category"] == resolved_cat]
        title_word = "Spend"

    if agg.empty:
        return f"No {title_word.lower()} in '{resolved_cat}' ({lbl})."

    total = agg["amount"].abs().sum()
    out = [f"{title_word} in {resolved_cat} ({lbl}): {_inr(total)} across {len(agg)} transactions."]

    if len(agg) <= 6:
        out.append("Transactions:")
        for _, r in agg.sort_values("txn_date", ascending=False).iterrows():
            out.append(f"  • {r['txn_date']} {r['counterparty']}: {_inr(abs(r['amount']))}")
    else:
        top_cps = (agg.assign(_amt=agg["amount"].abs())
                   .groupby("counterparty")["_amt"].sum()
                   .sort_values(ascending=False).head(3))
        out.append("Top merchants/counterparties:")
        out.append("  " + _fmt_rows(top_cps, _inr, 3).replace("\n", "\n  "))
    return "\n".join(out)


@tool
def category_by_month(category: str, year: str = "") -> str:
    """Amount in ONE category broken down month by month (e.g. 'Food & Dining', 'Salary', 'Rent').
    Automatically resolves synonyms like 'travel', 'food', 'salary', 'bills'. year is optional ('2026') to restrict."""
    df = _load()
    if df is None:
        return "No statement data imported yet."

    resolved_cat, available_cats = _resolve_category(df, category)
    if not resolved_cat:
        cats_str = ", ".join(available_cats)
        return f"Could not find category matching '{category}'. Available categories: {cats_str}."

    if resolved_cat in ("Salary", "Income"):
        agg = df[df["classification"] == config.CLASSIFICATION_INCOME]
        title_word = "Income"
    else:
        agg = _spend(df)
        agg = agg[agg["category"] == resolved_cat]
        title_word = "Spend"

    if year:
        agg = agg[agg["txn_date"].str.startswith(str(year))]
        if agg.empty:
            return f"No {title_word.lower()} in '{resolved_cat}' in {year}."
    by_month = (agg.assign(_amt=agg["amount"].abs())
                .groupby(agg["txn_date"].str[:7])["_amt"].sum())
    out = [f"{resolved_cat} {title_word.lower()} by month:"]
    for m, v in by_month.items():
        out.append(f"  {m}: {_inr(v)}")
    return "\n".join(out)


@tool
def merchant_summary(merchant: str, month: str = "") -> str:
    """Detailed spend and summary for a specific merchant or person (e.g., 'Uber',
    'Swiggy', 'Amazon', 'Zomato', 'Airtel', 'Kiran'). Shows total spend, order count,
    average transaction size, and recent orders."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err

    q = str(merchant).strip().upper()
    hit = sub[sub["description"].str.upper().str.contains(q, na=False)
              | sub["counterparty"].str.upper().str.contains(q, na=False)]
    if hit.empty:
        return f"No transactions found matching merchant/person '{merchant}' ({lbl})."

    debits = hit[hit["amount"] < 0]
    credits = hit[hit["amount"] > 0]
    total_spent = debits["amount"].abs().sum()
    total_credited = credits["amount"].sum()
    avg_txn = (total_spent / len(debits)) if not debits.empty else 0

    out = [f"Merchant Summary for '{merchant}' ({lbl}):",
           f"Total Spent: {_inr(total_spent)} across {len(debits)} debits" + (f" (avg {_inr(avg_txn)}/order)" if len(debits) > 1 else ""),
          ]
    if not credits.empty:
        out.append(f"Total Received/Refunded: {_inr(total_credited)} across {len(credits)} credits")

    out.append("Recent transactions:")
    for _, r in hit.sort_values("txn_date", ascending=False).head(5).iterrows():
        out.append(f"  {r['txn_date']} [{r['category']}] {_inr(abs(r['amount']))} — {r['description'][:50]}")
    return "\n".join(out)


@tool
def investment_summary(month: str = "") -> str:
    """Summary of all investments (Mutual Funds, SIPs, Fixed Deposits, NPS, real
    estate / land purchases, LIC policies). Excluded from real spend, but tracked
    here. Optionally for one month ('YYYY-MM'), 'latest', 'last_month'."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err

    inv = sub[sub["classification"] == config.CLASSIFICATION_INVESTMENT]
    if inv.empty:
        return f"No investment transactions recorded in {lbl}."

    total = inv["amount"].abs().sum()
    by_cp = (inv.assign(_amt=inv["amount"].abs())
             .groupby("counterparty")["_amt"].sum()
             .sort_values(ascending=False))

    out = [f"Investments ({lbl}): {_inr(total)} total across {len(inv)} transactions.",
           "Breakdown by investment type / merchant:",
           "  " + _fmt_rows(by_cp, _inr, 10).replace("\n", "\n  ")]
    return "\n".join(out)


@tool
def cashflow_breakdown(month: str = "") -> str:
    """Complete breakdown of all outgoing money (where every rupee went): Real Spend,
    Investments, Credit Card Bill Payments, Internal Transfers, and Fees. Optionally for one month."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err

    debits = sub[sub["amount"] < 0].copy()
    if debits.empty:
        return f"No outgoing transactions in {lbl}."

    debits["_amt"] = debits["amount"].abs()
    by_class = debits.groupby("classification")["_amt"].sum().sort_values(ascending=False)

    labels = {
        config.CLASSIFICATION_SPEND: "Real Spend (consumption)",
        config.CLASSIFICATION_INVESTMENT: "Investments (SIPs, FDs, NPS, Assets)",
        config.CLASSIFICATION_CC_PAYMENT: "Credit Card Bill Payments (Pass-through)",
        config.CLASSIFICATION_INTERNAL_TRANSFER: "Internal Self-Transfers",
        config.CLASSIFICATION_FEE: "Bank Fees & Charges",
    }

    total_out = debits["_amt"].sum()
    out = [f"Total Outflow ({lbl}): {_inr(total_out)}",
           "Where your money went:"]
    for c, amt in by_class.items():
        pct = (amt / total_out) * 100
        lbl_str = labels.get(c, c)
        out.append(f"  • {lbl_str}: {_inr(amt)} ({pct:.1f}%)")
    return "\n".join(out)


@tool
def compare_months(month1: str, month2: str) -> str:
    """Side-by-side comparison of two months (e.g. month1='2026-06', month2='2026-07').
    Compares total spend, income, savings rate, and category changes."""
    df = _load()
    if df is None:
        return "No statement data imported yet."

    sub1, err1, lbl1 = _sub(df, month1)
    if err1:
        return f"Error for month 1: {err1}"
    sub2, err2, lbl2 = _sub(df, month2)
    if err2:
        return f"Error for month 2: {err2}"

    s1 = _spend(sub1)
    s2 = _spend(sub2)
    tot1 = s1["amount"].abs().sum()
    tot2 = s2["amount"].abs().sum()
    diff = tot2 - tot1
    pct_change = ((tot2 - tot1) / tot1 * 100) if tot1 > 0 else 0

    inc1 = sub1[sub1["classification"] == config.CLASSIFICATION_INCOME]["amount"].sum()
    inc2 = sub2[sub2["classification"] == config.CLASSIFICATION_INCOME]["amount"].sum()

    out = [f"Comparison: {lbl1} vs {lbl2}:",
           f"• Spend: {lbl1} = {_inr(tot1)} | {lbl2} = {_inr(tot2)} "
           f"({'+' if diff >= 0 else ''}{_inr(diff)}, {pct_change:+.1f}%)",
           f"• Income: {lbl1} = {_inr(inc1)} | {lbl2} = {_inr(inc2)}",
          ]

    cat1 = s1.assign(_amt=s1["amount"].abs()).groupby("category")["_amt"].sum()
    cat2 = s2.assign(_amt=s2["amount"].abs()).groupby("category")["_amt"].sum()
    all_cats = sorted(set(cat1.index) | set(cat2.index))

    changes = []
    for c in all_cats:
        v1 = cat1.get(c, 0.0)
        v2 = cat2.get(c, 0.0)
        changes.append((c, v1, v2, v2 - v1))

    changes.sort(key=lambda x: abs(x[3]), reverse=True)
    out.append("Major Category Changes:")
    for c, v1, v2, d in changes[:5]:
        out.append(f"  • {c}: {_inr(v1)} → {_inr(v2)} ({'+' if d >= 0 else ''}{_inr(d)})")
    return "\n".join(out)


@tool
def uncategorized_detail(month: str = "", limit: int = 20) -> str:
    """Break down the 'Uncategorized' spend — what it's made of, grouped by
    merchant/person (counterparty), biggest first."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    un = _spend(sub)
    un = un[un["category"] == config.DEFAULT_CATEGORY]
    if un.empty:
        return f"No uncategorized spend ({lbl})."
    lim = _int(limit, 20)
    total = un["amount"].abs().sum()
    by_cp = (un.assign(_amt=un["amount"].abs())
             .groupby(un["counterparty"])["_amt"].sum()
             .sort_values(ascending=False).head(max(1, min(lim, 40))))
    return (f"Uncategorized spend ({lbl}): {_inr(total)} total across "
            f"{len(un)} transactions.\n"
            + _fmt_rows(by_cp, _inr))


@tool
def find_transactions(query: str, limit: int = 10) -> str:
    """Search transactions by text — matches merchant/person name or any part
    of the narration. limit = how many to return (default 10)."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    q = str(query).strip().upper()
    hit = df[df["description"].str.upper().str.contains(q, na=False)
             | df["counterparty"].str.upper().str.contains(q, na=False)
             | df["category"].str.upper().str.contains(q, na=False)
             | df["classification"].str.upper().str.contains(q, na=False)]
    lim = _int(limit, 10)
    hit = hit.sort_values("txn_date", ascending=False).head(max(1, min(lim, 25)))
    if hit.empty:
        return f"No transactions matching '{query}'."
    rows = []
    for _, r in hit.iterrows():
        acct = config.ACCOUNTS.get(r["account"], {}).get("label", r["account"])
        rows.append(f"{r['txn_date']} {acct} {_inr(r['amount'])} "
                    f"[{r['classification']}/{r['category']}] {r['description'][:55]}")
    return "Matching transactions (newest first):\n" + "\n".join(rows)


@tool
def reconciliation_status() -> str:
    """Money that doesn't balance: unmatched internal transfers, unmatched
    credit-card payments (Ashwin still owes), and unmatched Ashwin deposits
    (you owe Ashwin)."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    out = ["Reconciliation:"]
    for cls, title in [
        (config.CLASSIFICATION_CC_PAYMENT, "CC bills paid, no matching Ashwin deposit (he owes you)"),
        (config.CLASSIFICATION_FRIEND_DEPOSIT, "Ashwin deposits with no matching bill (you owe him)"),
        (config.CLASSIFICATION_INTERNAL_TRANSFER, "Unmatched internal transfers"),
    ]:
        u = db.load_unmatched(cls)
        if u.empty:
            out.append(f"• {title}: none 🎉")
        else:
            out.append(f"• {title}: {_inr(u['amount'].abs().sum())} "
                       f"across {len(u)} rows")
    return "\n".join(out)


@tool
def account_balances() -> str:
    """Latest statement balances and liquid savings across bank accounts (Axis, SBI, Kotak 811),
    including Kotak Active Money (Smart Auto-Sweep FD) and total liquid reserves."""
    try:
        b_df = db.load_account_balances()
    except Exception:
        b_df = pd.DataFrame()

    if not b_df.empty:
        rows = ["**🏦 Liquid Savings & Bank Account Balances:**"]
        tot_liquid = b_df["total_balance"].sum()
        
        for _, r in b_df.iterrows():
            acct_lbl = r["label"]
            tot = _inr(r["total_balance"])
            as_of = r["as_of_date"]
            if r.get("smart_fd_balance", 0) > 0:
                sav = _inr(r["savings_balance"])
                fd = _inr(r["smart_fd_balance"])
                rows.append(f"• **{acct_lbl}**: **{tot}** *(Savings: {sav} + Smart FD / Active Money: {fd})* (as of {as_of})")
            else:
                rows.append(f"• **{acct_lbl}**: **{tot}** (as of {as_of})")

        rows.append(f"\n**💰 Total Consolidated Liquid Savings**: **{_inr(tot_liquid)}**")
        return "\n".join(rows)

    # Fallback to last ledger row
    df = _load()
    if df is None:
        return "No statement data imported yet."
    rows = []
    for acct in config.ACCOUNT_ORDER:
        a = df[(df["account"] == acct) & df["balance"].notna()]
        if a.empty:
            continue
        last = a.sort_values("txn_date").iloc[-1]
        rows.append(f"{config.ACCOUNTS[acct]['label']}: {_inr(last['balance'])} "
                    f"(as of {last['txn_date']})")
    return "\n".join(rows) if rows else "No balance data."


@tool
def monthly_overview(month: str = "") -> str:
    """One-call summary of a month: spend, income, savings rate, biggest
    categories and biggest counterparties. Best tool for open questions like
    'how am I doing?' or 'what happened in June?'."""
    df = _load()
    if df is None:
        return "No statement data imported yet."
    sub, err, lbl = _sub(df, month)
    if err:
        return err
    spend = _spend(sub)
    total = spend["amount"].abs().sum()
    income = sub[sub["classification"] == config.CLASSIFICATION_INCOME]["amount"].sum()
    other = sub[sub["classification"] == config.CLASSIFICATION_OTHER_INCOME]["amount"].sum()
    rate = (income - total) / income if income > 0 else None
    cats = (spend.assign(_amt=spend["amount"].abs())
            .groupby("category")["_amt"].sum().sort_values(ascending=False))
    cps = (spend.assign(_amt=spend["amount"].abs())
           .groupby(spend["counterparty"])["_amt"].sum()
           .sort_values(ascending=False))
    out = [f"Overview ({lbl}):",
           f"Spend: {_inr(total)}  ({len(spend)} txns)",
           f"Salary income: {_inr(income)}",
           f"Other income: {_inr(other)}",
           (f"Savings rate: {rate:.0%} (saved {_inr(income - total)})"
            if rate is not None else "Savings rate: n/a (no salary income)"),
           "Top categories:",
           "  " + _fmt_rows(cats, _inr, 5).replace("\n", "\n  "),
           "Top counterparties:",
           "  " + _fmt_rows(cps, _inr, 5).replace("\n", "\n  ")]
    return "\n".join(out)


@tool
def daily_spend(date_query: str = "today") -> str:
    """Real spend for a specific date (e.g. 'today', 'yesterday', or 'YYYY-MM-DD' like '2026-08-01').
    Returns total spend and itemized transactions for that exact day."""
    df = _load()
    if df is None:
        return "No statement data imported yet."

    q = str(date_query).strip().lower()
    today_iso = date.today().isoformat()
    all_dates = sorted(df["txn_date"].unique())
    if not all_dates:
        return "No statement data imported yet."

    if q in ("today", "current_day"):
        target_date = today_iso if today_iso in all_dates else all_dates[-1]
    elif q in ("yesterday", "prev_day", "previous_day"):
        yest_iso = (date.today() - timedelta(days=1)).isoformat()
        target_date = yest_iso if yest_iso in all_dates else (all_dates[-2] if len(all_dates) >= 2 else all_dates[-1])
    else:
        matched = [d for d in all_dates if q in d]
        if matched:
            target_date = matched[0]
        else:
            return f"No transaction data for date '{date_query}'. Latest available date is {all_dates[-1]}."

    day_txns = df[df["txn_date"] == target_date]
    spend_txns = _spend(day_txns)

    if spend_txns.empty:
        return f"Real spend on {target_date}: ₹0 across 0 transactions."

    total_spent = spend_txns["amount"].abs().sum()
    out = [f"Real spend on {target_date}: {_inr(total_spent)} across {len(spend_txns)} transactions.", "Transactions:"]

    for _, r in spend_txns.sort_values("amount").iterrows():
        out.append(f"  • {r['counterparty']} [{r['category']}]: {_inr(abs(r['amount']))} ({r['description'][:45]})")

    return "\n".join(out)


@tool
def cc_payments_overview(month: str = "") -> str:
    """Overview of credit card bill repayments and payments made from bank accounts (Axis, SBI, Kotak) to credit cards.
    month = optional month string ('YYYY-MM', 'latest', or blank for all)."""
    df = _load()
    if df is None:
        return "No transaction data imported yet."

    cc_df = df[df["classification"] == config.CLASSIFICATION_CC_PAYMENT]
    if cc_df.empty:
        return "No credit card payments found in bank account statements."

    sub, err, lbl = _sub(cc_df, month)
    if err:
        return err

    total_paid = sub["amount"].abs().sum()
    out = [f"Credit Card Bill Payments ({lbl}): {_inr(total_paid)} across {len(sub)} payments."]

    months_list = sub["txn_date"].str[:7].unique()
    if len(months_list) > 1:
        out.append("\nBy month:")
        for m in sorted(months_list, reverse=True)[:8]:
            grp = sub[sub["txn_date"].str.startswith(m)]
            out.append(f"  • {m}: {_inr(grp['amount'].abs().sum())} ({len(grp)} payments)")

    out.append("\nRecent payments:")
    for _, r in sub.sort_values("txn_date", ascending=False).head(8).iterrows():
        out.append(f"  • {r['txn_date']} [{r['account']}]: {_inr(abs(r['amount']))} — {r['description'][:50]}")

    return "\n".join(out)


@tool
def bank_loans_tracker(loan_name: str = "") -> str:
    """Track personal loans, NBFC EMIs, monthly loan burden, paid/remaining installments, and payoff dates.
    loan_name = optional filter for a specific loan (e.g. 'Kisetsu', 'IDFC')."""
    loans_df = db.load_bank_loans()
    if loans_df.empty:
        return "No personal or bank loans tracked yet. Go to the Bank Loans tab to add your loans."

    if loan_name:
        q = str(loan_name).strip().upper()
        loans_df = loans_df[loans_df["loan_name"].str.upper().str.contains(q, na=False) |
                            loans_df["lender"].str.upper().str.contains(q, na=False)]
        if loans_df.empty:
            return f"No bank loan found matching '{loan_name}'."

    out = ["**Bank & Personal Loans Overview:**\n"]
    tot_monthly = loans_df["monthly_emi"].sum()
    tot_rem = loans_df["remaining_principal"].sum()

    for _, r in loans_df.iterrows():
        lname = r["loan_name"]
        lender = r["lender"]
        emi = _inr(r["monthly_emi"])
        paid_t = r["paid_tenure"]
        tot_t = r["total_tenure"]
        rem_t = r["remaining_tenure"]
        rem_bal = _inr(r["remaining_principal"])
        deb_d = r.get("debit_day", 3)
        
        out.append(f"• **{lname}** ({lender}):")
        out.append(f"  - Monthly EMI: {emi}/mo (debited on the {deb_d}th of every month)")
        out.append(f"  - Progress: {paid_t} of {tot_t} EMIs Paid | ⏳ **{rem_t} EMIs Remaining**")
        out.append(f"  - Outstanding Balance: {rem_bal}")

    out.append(f"\n**Total Monthly Loan Burden:** {_inr(tot_monthly)}/month")
    out.append(f"**Total Outstanding Loan Debt:** {_inr(tot_rem)}")
    return "\n".join(out)


TOOLS = [
    monthly_overview,
    daily_spend,
    spend_total,
    spend_by_category,
    spend_by_account,
    spend_by_month,
    cc_payments_overview,
    bank_loans_tracker,
    income_summary,
    savings_rate,
    category_spend,
    category_by_month,
    merchant_summary,
    investment_summary,
    cashflow_breakdown,
    compare_months,
    uncategorized_detail,
    top_counterparties,
    find_transactions,
    reconciliation_status,
    account_balances,
]
