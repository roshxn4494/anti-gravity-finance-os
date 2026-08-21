"""Finance Tracker — local Streamlit dashboard.

Tabs: Upload · Overview · Transactions · Reconciliation · Chat · Feedback
Run with:  streamlit run app.py
"""
from __future__ import annotations

import json
import math
import os
import re
import textwrap
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from finance import config, db, pipeline
from finance.classify import categories as cat_mod


def _ordinal(n: int) -> str:
    """Format integer as ordinal string (e.g. 1 -> 1st, 2 -> 2nd, 3 -> 3rd, 4 -> 4th)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data",
                       "finance.db")
db.set_db_path(DB_PATH)
db.init_db()

st.set_page_config(
    page_title="Anti Gravity Agent — Finance OS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_custom_css():
    st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300..800;1,300..800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" />
    
    <style>
        html, body, [class*="css"] {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
        }
        
        .stApp {
            background: linear-gradient(135deg, #0b0f19 0%, #0f172a 50%, #111827 100%) !important;
            color: #f8fafc;
        }

        h1, h2, h3, h4 {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-weight: 700 !important;
            color: #f8fafc !important;
            letter-spacing: -0.02em !important;
        }

        .metric-card {
            background: rgba(30, 41, 59, 0.6) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
            border-radius: 16px !important;
            padding: 20px !important;
            box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3) !important;
            transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.25s ease !important;
            margin-bottom: 12px;
        }
        .metric-card:hover {
            transform: translateY(-4px);
            border-color: rgba(99, 102, 241, 0.4) !important;
            box-shadow: 0 16px 36px rgba(99, 102, 241, 0.15) !important;
        }
        .metric-card .icon-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 44px;
            height: 44px;
            border-radius: 12px;
        }
        .metric-card.spend .icon-badge { background: rgba(244, 63, 94, 0.15); color: #f43f5e; }
        .metric-card.income .icon-badge { background: rgba(16, 185, 129, 0.15); color: #10b981; }
        .metric-card.savings .icon-badge { background: rgba(99, 102, 241, 0.15); color: #6366f1; }
        .metric-card.invest .icon-badge { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }

        .metric-title {
            font-size: 12px !important;
            font-weight: 700 !important;
            color: #94a3b8 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.06em !important;
            margin-bottom: 6px;
        }
        .metric-value {
            font-size: 26px !important;
            font-weight: 800 !important;
            color: #f8fafc !important;
            line-height: 1.15;
            letter-spacing: -0.03em !important;
        }
        .metric-sub {
            font-size: 13px !important;
            font-weight: 500 !important;
            color: #cbd5e1 !important;
            margin-top: 8px;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background: rgba(15, 23, 42, 0.6) !important;
            padding: 6px !important;
            border-radius: 16px !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }
        .stTabs [data-baseweb="tab"] {
            height: 44px !important;
            border-radius: 12px !important;
            padding: 0 20px !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            color: #94a3b8 !important;
            border: none !important;
            transition: all 0.2s ease !important;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(79, 70, 229, 0.3) 100%) !important;
            color: #a5b4fc !important;
            border: 1px solid rgba(165, 180, 252, 0.3) !important;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.25) !important;
        }

        [data-testid="stSidebar"] {
            background: rgba(15, 23, 42, 0.95) !important;
            border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
        }

        div[data-baseweb="select"] > div, input {
            background-color: rgba(30, 41, 59, 0.7) !important;
            border-color: rgba(255, 255, 255, 0.1) !important;
            border-radius: 12px !important;
            color: #f8fafc !important;
        }

        .stButton > button {
            border-radius: 12px !important;
            font-weight: 600 !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
            border: none !important;
            box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35) !important;
        }
        .stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4) !important;
        }

        [data-testid="stDataFrame"] {
            border-radius: 14px !important;
            overflow: hidden !important;
            border: 1px solid rgba(255, 255, 255, 0.08) !important;
        }

        [data-testid="stChatMessage"] {
            background: rgba(30, 41, 59, 0.5) !important;
            border-radius: 16px !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
            padding: 16px !important;
            margin-bottom: 12px !important;
        }
    </style>
    """, unsafe_allow_html=True)


inject_custom_css()

# --------------------------------------------------------------------------
# Dataviz tokens (validated default palette)
# --------------------------------------------------------------------------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
          "#008300", "#4a3aa7", "#e34948"]
GRAY = "#a3a29b"
INK = "#0b0b0b"
SECONDARY = "#52514e"
GRID = "#e1e0d9"

GLOBAL_CAT_ORDER = (
    list(config.CATEGORY_KEYWORDS.keys())
    + ["Salary", "Income", "Ashwin", "Credit Card", "Internal Transfer",
       "Other Income", "Other", config.DEFAULT_CATEGORY]
)

# Tab icons using Material Symbols
TAB_ICONS = {
    "upload": ":material/cloud_upload:",
    "overview": ":material/analytics:",
    "transactions": ":material/receipt_long:",
    "reconciliation": ":material/account_tree:",
    "chat": ":material/chat:",
    "feedback": ":material/feedback:",
}


def inr(x: float) -> str:
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


def category_color(cat: str) -> str:
    if cat in (config.DEFAULT_CATEGORY, "Other"):
        return GRAY
    order = GLOBAL_CAT_ORDER
    idx = order.index(cat) if cat in order else len(order)
    return SERIES[idx % len(SERIES)]


def account_color(acct: str) -> str:
    try:
        return SERIES[config.ACCOUNT_ORDER.index(acct)]
    except ValueError:
        return GRAY


def display_categories() -> list[str]:
    specials = ["Salary", "Income", "Ashwin", "Credit Card", "Internal Transfer",
                "Other Income"]
    cats = cat_mod.all_categories() + specials
    seen, out = set(), []
    for c in cats:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _layout(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=45, b=10),
        font=dict(family="'Plus Jakarta Sans', -apple-system, sans-serif",
                  color="#94a3b8", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title_font=dict(color="#f8fafc", size=15, family="'Plus Jakarta Sans', sans-serif"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color="#cbd5e1")),
    )
    return fig


def _aligned_income(df: pd.DataFrame, mk: str) -> float:
    """Calculate salary income for month YYYY-MM using pay-period alignment (salary credited 25th+ belongs to next month)."""
    same_month = df[(df["txn_date"].str[:7] == mk) & (df["classification"] == config.CLASSIFICATION_INCOME)]
    same_early = same_month[same_month["txn_date"].str[8:].astype(int) < 25]["amount"].sum()

    prev_mk = _prev_month(mk)
    prev_month = df[(df["txn_date"].str[:7] == prev_mk) & (df["classification"] == config.CLASSIFICATION_INCOME)]
    prev_late = prev_month[prev_month["txn_date"].str[8:].astype(int) >= 25]["amount"].sum()

    val = same_early + prev_late
    if val == 0:
        val = same_month["amount"].sum()
    return val


# --------------------------------------------------------------------------
# Helpers for the business math
# --------------------------------------------------------------------------

def _spend_df(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["classification"] == config.CLASSIFICATION_SPEND]


def month_key(iso: str) -> str:
    return iso[:7]


def last_months(n: int) -> list[str]:
    end = date.today()
    out = []
    for i in range(n - 1, -1, -1):
        y, m = end.year, end.month
        for _ in range(i):
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def fmt_month(mk: str) -> str:
    return date(int(mk[:4]), int(mk[5:7]), 1).strftime("%b %Y")


# --------------------------------------------------------------------------
# Tab: Upload
# --------------------------------------------------------------------------

def tab_upload():
    st.header("Upload statement", divider=True)
    st.caption("Export CSV or PDF from Axis / SBI / Kotak netbanking or Credit Card PDF statements.")

    # Render previous import summary banner if present
    if "last_import_summary" in st.session_state and st.session_state["last_import_summary"]:
        s = st.session_state["last_import_summary"]
        st.markdown(f"""
        <div class="metric-card income" style="border-color: rgba(16, 185, 129, 0.4); margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 14px;">
                <div class="icon-badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; width: 48px; height: 48px; border-radius: 14px;">
                    <span class="material-symbols-rounded" style="font-size: 28px;">check_circle</span>
                </div>
                <div>
                    <h3 style="margin: 0; font-size: 18px; color: #f8fafc;">Statement Successfully Imported!</h3>
                    <p style="margin: 2px 0 0 0; color: #cbd5e1; font-size: 14px;">
                        File <strong>{s['filename']}</strong> imported into <strong>{s['account_label']}</strong>.
                    </p>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px; background: rgba(15, 23, 42, 0.4); padding: 14px; border-radius: 14px; border: 1px solid rgba(255, 255, 255, 0.05);">
                <div>
                    <div style="font-size: 11px; color: #94a3b8; font-weight: 700; text-transform: uppercase;">Total Parsed</div>
                    <div style="font-size: 22px; font-weight: 800; color: #f8fafc;">{s['total_parsed']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #10b981; font-weight: 700; text-transform: uppercase;">New Inserted</div>
                    <div style="font-size: 22px; font-weight: 800; color: #10b981;">{s['inserted']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #f59e0b; font-weight: 700; text-transform: uppercase;">Duplicates Skipped</div>
                    <div style="font-size: 22px; font-weight: 800; color: #f59e0b;">{s['skipped']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #818cf8; font-weight: 700; text-transform: uppercase;">Date Range</div>
                    <div style="font-size: 13px; font-weight: 700; color: #f8fafc; margin-top: 4px;">{s['date_min']} → {s['date_max']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    stmt_type = st.radio(
        "Statement Target",
        ["🏦 Bank Account Statement", "💳 Credit Card Statement"],
        horizontal=True,
    )

    if stmt_type == "💳 Credit Card Statement":
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            card_name = st.selectbox(
                "Card / Bank Name",
                [
                    "HDFC Credit Card",
                    "ICICI Amazon Pay / Credit Card",
                    "Axis Bank Credit Card",
                    "American Express",
                    "Scapia Federal Credit Card",
                    "YES Bank Credit Card",
                    "IDFC FIRST Credit Card",
                    "SBI Credit Card",
                    "Kotak Credit Card",
                    "IndusInd Credit Card",
                    "RBL Bank Credit Card",
                    "BOB Credit Card",
                    "HSBC Credit Card",
                    "Other Credit Card",
                ]
            )
        with col_c2:
            pdf_password = st.text_input(
                "Statement Password (Optional)",
                type="password",
                help="If your bank PDF is password protected (e.g. DOB + Name or Card Last 4 Digits), enter it here."
            )

        uploaded = st.file_uploader(
            "Credit Card Statement File",
            type=["pdf", "csv"],
            help="PDF credit card statements (HDFC, ICICI, Axis, SBI, Amex, Kotak). Password supported.",
            accept_multiple_files=False,
            key="cc_uploader",
        )

        if uploaded is not None:
            try:
                stmt_info, cc_txns, cc_emis, warnings = pipeline.loader.parse_cc_file(uploaded, card_name=card_name, password=pdf_password)
            except Exception as exc:
                st.error(f"Could not parse credit card statement: {exc}")
                return

            for w in warnings:
                st.warning(w)

            if cc_txns or stmt_info.get("total_due") or cc_emis:
                st.subheader(f"Preview: {card_name}")
                if stmt_info.get("total_due"):
                    st.caption(f"Statement Date: {stmt_info['statement_date'] or '—'} | Total Due: {inr(stmt_info['total_due'])} | Min Due: {inr(stmt_info['min_due'])} | Due Date: {stmt_info['due_date'] or '—'}")
                if cc_emis:
                    st.info(f"⏳ Detected {len(cc_emis)} Active EMIs / Loan Schedules in this statement!")
                if cc_txns:
                    preview_df = pd.DataFrame(cc_txns)[["txn_date", "description", "amount", "category", "counterparty"]]
                    st.dataframe(preview_df, width="stretch", height=280)

                if st.button(f"Import Credit Card Statement ({len(cc_txns)} transactions, {len(cc_emis)} EMIs)", type="primary", width="stretch"):
                    sid = db.save_cc_statement(stmt_info)
                    for t in cc_txns:
                        t["statement_id"] = sid
                    for e in cc_emis:
                        e["statement_id"] = sid
                    inserted, skipped = db.upsert_cc_transactions(cc_txns)
                    if cc_emis:
                        db.upsert_cc_emis(cc_emis)
                    st.session_state["last_import_summary"] = {
                        "filename": uploaded.name,
                        "account_label": f"Credit Card ({stmt_info.get('card_name', card_name)})",
                        "total_parsed": len(cc_txns),
                        "inserted": inserted,
                        "skipped": skipped,
                        "date_min": min(r["txn_date"] for r in cc_txns) if cc_txns else "—",
                        "date_max": max(r["txn_date"] for r in cc_txns) if cc_txns else "—",
                    }
                    st.rerun()
            else:
                st.info("No transaction rows or summary found in this statement.")
        return

    # Bank Account Statement Upload Flow
    uploaded = st.file_uploader(
        "Statement file",
        type=["csv", "pdf"],
        help="CSV is most reliable. PDF layouts vary by bank.",
        accept_multiple_files=False,
    )

    if uploaded is not None:
        detected = pipeline.loader.detect_account(uploaded)
        account = detected if detected else config.ACCOUNT_ORDER[0]

        col1, col2 = st.columns([3, 1])
        with col1:
            if detected:
                st.success(f"Detected **{config.ACCOUNTS[detected]['label']}** ✓")
            else:
                st.warning("Bank not auto-detected — please choose it below.")
        with col2:
            account = st.selectbox(
                "Account",
                config.ACCOUNT_ORDER,
                index=config.ACCOUNT_ORDER.index(account),
                format_func=lambda a: config.ACCOUNTS[a]["label"],
                key=f"acct_{uploaded.name}_{uploaded.size}",
            )

        try:
            rows, warnings = pipeline.loader.parse_file(uploaded, account)
        except Exception as exc:
            st.error(f"Could not parse this file: {exc}")
            return

        for w in warnings:
            st.warning(w)

        if rows:
            preview = pd.DataFrame([
                {"Date": r["txn_date"], "Description": r["description"],
                 "Amount": r["amount"], "Classification": r["classification"],
                 "Category": r["category"], "Counterparty": r["counterparty"]}
                for r in rows])
            st.caption(f"{len(rows)} transactions parsed — preview:")
            st.dataframe(preview, width="stretch", height=320)

            if st.button(f"Import {len(rows)} transactions", type="primary", width="stretch"):
                result = pipeline.run_import(uploaded, account)
                st.session_state["last_import_summary"] = {
                    "filename": uploaded.name,
                    "account_label": config.ACCOUNTS[account]["label"],
                    "total_parsed": len(rows),
                    "inserted": result["inserted"],
                    "skipped": result["skipped"],
                    "date_min": min(r["txn_date"] for r in rows) if rows else "—",
                    "date_max": max(r["txn_date"] for r in rows) if rows else "—",
                }
                st.rerun()
        else:
            st.info("No transaction rows found in this file.")
    else:
        st.info("Drop a CSV or PDF statement above to get started.")

    _render_data_coverage_summary()


def _render_data_coverage_summary():
    st.divider()
    st.subheader("📊 Imported Data Coverage & Statement Inventory")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 🏦 Bank Accounts Coverage")
        df_bank = db.load_all()
        if not df_bank.empty:
            bank_rows = []
            for acct, grp in df_bank.groupby("account"):
                label = config.ACCOUNTS.get(acct, {}).get("label", acct.upper())
                min_d = grp["txn_date"].min()
                max_d = grp["txn_date"].max()
                count = len(grp)
                bank_rows.append({
                    "Account": label,
                    "Total Txns": f"{count:,}",
                    "Oldest Date": min_d,
                    "Latest Date": max_d,
                })
            st.dataframe(pd.DataFrame(bank_rows), width="stretch", hide_index=True)
        else:
            st.info("No bank account statements imported yet.")

    with col2:
        st.markdown("##### 💳 Credit Cards Statement Inventory")
        cc_stmts = db.load_cc_statements()
        cc_txns = db.load_cc_transactions()

        if not cc_stmts.empty or not cc_txns.empty:
            cc_rows = []
            all_cards = set()
            if not cc_stmts.empty:
                all_cards.update(cc_stmts["card_name"].unique())
            if not cc_txns.empty:
                all_cards.update(cc_txns["card_name"].unique())

            for card in sorted(all_cards):
                s_sub = cc_stmts[cc_stmts["card_name"] == card] if not cc_stmts.empty else pd.DataFrame()
                t_sub = cc_txns[cc_txns["card_name"] == card] if not cc_txns.empty else pd.DataFrame()

                last4 = ""
                if not s_sub.empty and s_sub.iloc[0]["card_last4"]:
                    last4 = f"..{s_sub.iloc[0]['card_last4']}"
                elif not t_sub.empty and t_sub.iloc[0]["card_last4"]:
                    last4 = f"..{t_sub.iloc[0]['card_last4']}"

                months = set()
                if not s_sub.empty:
                    months.update(s_sub["statement_date"].dropna().map(lambda d: d[:7]))
                if not t_sub.empty:
                    months.update(t_sub["txn_date"].dropna().map(lambda d: d[:7]))
                months_str = ", ".join(sorted(months, reverse=True)) if months else "—"

                due_info = "—"
                if not s_sub.empty:
                    latest_s = s_sub.sort_values("statement_date").iloc[-1]
                    if latest_s["total_due"]:
                        due_info = f"{inr(latest_s['total_due'])} (due {latest_s['due_date'] or '—'})"

                cc_rows.append({
                    "Card Name": f"{card} {last4}".strip(),
                    "Purchases": f"{len(t_sub):,}",
                    "Covered Months": months_str,
                    "Latest Due": due_info,
                })
            st.dataframe(pd.DataFrame(cc_rows), width="stretch", hide_index=True)
            if st.button("🗑️ Reset All Credit Card Data", key="btn_clear_cc", help="Clear all stored credit card statements and line items"):
                db.clear_cc_data()
                if "last_import_summary" in st.session_state:
                    del st.session_state["last_import_summary"]
                st.success("All credit card data has been cleared from the database.")
                st.rerun()
        else:
            st.info("No credit card statements imported yet.")


# --------------------------------------------------------------------------
# Tab: Overview
# --------------------------------------------------------------------------

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

        prev_mk = _prev_month(this_mk)
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

    # Trend Chart
    fig_t = go.Figure(go.Scatter(
        x=[fmt_month(m) for m in months], y=trend.values,
        mode="lines+markers",
        line=dict(color=SERIES[0], width=3, shape="spline"),
        marker=dict(color=SERIES[0], size=8),
        hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>"))
    fig_t.update_yaxes(title="", gridcolor="rgba(255,255,255,0.06)", zeroline=False, tickprefix="₹")
    fig_t.update_xaxes(gridcolor="rgba(255,255,255,0.06)", showgrid=False)
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
                textposition="outside", textfont=dict(color="#cbd5e1", size=11),
                hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            fig_c.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False, tickprefix="₹")
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
                textposition="outside", textfont=dict(color="#cbd5e1", size=11),
                hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            fig_a.update_xaxes(gridcolor="rgba(255,255,255,0.06)", zeroline=False, tickprefix="₹")
            fig_a.update_yaxes(showgrid=False)
            fig_a.update_layout(title=f"Spend by Account ({period_label})", bargap=0.4)
            _layout(fig_a)
            st.plotly_chart(fig_a, width="stretch")

    # Liquid Savings & Bank Balances Strip
    st.markdown("---")
    st.subheader("🏦 Liquid Savings & Bank Balances")
    try:
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
                st.metric("Kotak 811 (with Smart FD)", inr(kotak_r["total_balance"]), delta=f"Smart FD: {inr(kotak_r['smart_fd_balance'])}", delta_color="off", help="Includes Active Money auto-sweep FD")
        with col_b3:
            if sbi_r is not None:
                st.metric("SBI Savings", inr(sbi_r["total_balance"]), help="Secondary liquid savings")
        with col_b4:
            if axis_r is not None:
                st.metric("Axis Salary Account", inr(axis_r["total_balance"]), delta="~₹1.13L salary on 29th-30th", delta_color="off")


def _prev_month(mk: str) -> str:
    y, m = int(mk[:4]), int(mk[5:7])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}"


# --------------------------------------------------------------------------
# Tab: Transactions
# --------------------------------------------------------------------------

def tab_transactions():
    st.header("Transactions", divider=True)
    df = db.load_all()
    if df.empty:
        st.info("No data yet — go to the **Upload** tab and import a statement.")
        return

    with st.sidebar:
        st.subheader("Filters")
        accts = st.multiselect(
            "Account", config.ACCOUNT_ORDER, default=config.ACCOUNT_ORDER,
            format_func=lambda a: config.ACCOUNTS[a]["label"],
        )
        min_d, max_d = df["txn_date"].min(), df["txn_date"].max()
        drange = st.date_input(
            "Date range", (date.fromisoformat(min_d), date.fromisoformat(max_d)))
        classes = st.multiselect(
            "Classification", config.ALL_CLASSIFICATIONS,
            default=config.ALL_CLASSIFICATIONS)
        cats = st.multiselect("Category", display_categories())
        search = st.text_input("Search description", placeholder="Filter by merchant or note...")
        only_uncat = st.checkbox("Only uncategorized")
        only_recurring = st.checkbox("Only recurring (P2P)")
        remember = st.checkbox(
            "Remember manual tags for this person/merchant", value=True)

    frm = drange[0].isoformat() if isinstance(drange, tuple) else None
    to_ = drange[1].isoformat() if isinstance(drange, tuple) else None
    flags = ["recurring"] if only_recurring else None

    disp = db.load_transactions(account=accts, date_from=frm, date_to=to_,
                                classification=classes, category=cats,
                                search=search, only_uncategorized=only_uncat,
                                only_flags=flags)
    if disp.empty:
        st.info("No transactions match the filters.")
        return

    st.caption(f"{len(disp)} transactions")
    cols = ["txn_date", "account", "description", "amount", "counterparty",
            "classification", "category", "flags"]
    edit = disp[cols].copy()
    edit["account"] = edit["account"].map(lambda a: config.ACCOUNTS[a]["label"])

    edited = st.data_editor(
        edit.set_index(disp["id"]),
        hide_index=True,
        disabled=["txn_date", "account", "description", "amount", "counterparty", "flags"],
        column_config={
            "txn_date": st.column_config.TextColumn("Date"),
            "amount": st.column_config.NumberColumn("Amount", format="₹%f"),
            "classification": st.column_config.SelectboxColumn(
                "Classification", options=config.ALL_CLASSIFICATIONS),
            "category": st.column_config.SelectboxColumn(
                "Category", options=display_categories()),
        },
        width="stretch", height=520)

    # Detect manual changes and apply them.
    changes = []
    for tid in edited.index:
        new_cls = edited.loc[tid, "classification"]
        new_cat = edited.loc[tid, "category"]
        orig_cls = disp.set_index("id").loc[tid, "classification"]
        orig_cat = disp.set_index("id").loc[tid, "category"]
        if new_cls != orig_cls or new_cat != orig_cat:
            changes.append((tid, new_cls, new_cat, disp.set_index("id").loc[tid, "counterparty"]))

    if changes:
        st.caption(f"{len(changes)} row(s) edited — press Apply to save.")
        if st.button("Apply changes", type="primary", width="stretch"):
            for tid, cls, cat, cp in changes:
                cat = _canonical_category(cls, cat)
                pipeline.reclassify(tid, cls, cat,
                                    counterparty=cp if remember else None)
            st.success(f"Applied {len(changes)} change(s).")
            st.rerun()


def _canonical_category(cls: str, cat: str) -> str:
    mapping = {
        config.CLASSIFICATION_INCOME: "Income",
        config.CLASSIFICATION_FRIEND_DEPOSIT: "Ashwin",
        config.CLASSIFICATION_CC_PAYMENT: "Credit Card",
        config.CLASSIFICATION_INTERNAL_TRANSFER: "Internal Transfer",
        config.CLASSIFICATION_OTHER_INCOME: "Other Income",
        config.CLASSIFICATION_FEE: "Fees & Charges",
        config.CLASSIFICATION_INVESTMENT: "Investments",
    }
    if cls in mapping:
        return mapping[cls]
    return cat or config.DEFAULT_CATEGORY


# --------------------------------------------------------------------------
# Tab: Reconciliation
# --------------------------------------------------------------------------

def tab_reconciliation():
    st.header("👥 Ashwin Pass-Through Ledger & Reconciliation", divider=True)
    st.caption("Real-time synchronization of Ashwin's pass-through debt, credit card EMIs, personal loans, and bank statement settlements.")

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
    cc_dues = stmts["total_due"].sum() if not stmts.empty else 0.0
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
    st.subheader("🔄 Bank Internal Transfers Matching")
    
    if st.button("Re-run auto-matching engine", type="secondary", width="stretch"):
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
        show["account"] = show["account"].map(lambda a: config.ACCOUNTS[a]["label"])
        show.columns = ["Date", "Account", "Description", "Amount"]
        st.dataframe(show, width="stretch", height=220)

    left, right = st.columns(2)
    with left:
        _table("Unmatched internal transfers", u_transfer)
        _table("Unmatched credit-card payments", u_cc)
    with right:
        _table("Unmatched Ashwin deposits", u_friend)
        _explain()

    st.caption("Tip: an unmatched transfer OUT usually means that side is on a "
               "statement you haven't imported yet, or it was a payment to a "
               "person, not yourself — reclassify it in the Transactions tab.")


# --------------------------------------------------------------------------
# Tab: Chat (Master Financial AI & Sub-Agents)
# --------------------------------------------------------------------------

MASTER_SUGGESTIONS = [
    "Across all my credit cards and loans, what is my exact monthly debt obligation?",
    "When will I become debt-free and how will my cashflow improve?",
    "Give me a complete financial health checkup for this month",
    "If I have ₹50,000 extra, what should I prepay first to save interest?",
    "What are my upcoming payment due dates and auto-debits in the next 30 days?",
    "Show my credit limits and total card utilization rate",
]

BANK_SUGGESTIONS = [
    "How much did I spend on food last month?",
    "What are my biggest expenses this month?",
    "Show me my savings rate",
    "How much does Ashwin owe me?",
    "Break down my uncategorized spend",
    "Show my account balances",
]

CC_SUGGESTIONS = [
    "When is my credit card bill due?",
    "How many reward points do I have?",
    "Did I get charged any annual fee or interest?",
    "How much did I spend on my credit card this month?",
    "Show line items for Swiggy on credit card",
]


@st.cache_resource(show_spinner=False)
def _get_master_chat_agent():
    """Build the Master Unified LangGraph agent once per app session."""
    from finance.agent import master_graph
    return master_graph.build_master_agent()


@st.cache_resource(show_spinner=False)
def _get_chat_agent():
    """Build the Bank LangGraph agent once per app session."""
    from finance.agent import graph
    return graph.build_agent()


@st.cache_resource(show_spinner=False)
def _get_cc_chat_agent():
    """Build the Credit Card LangGraph agent once per app session."""
    from finance.agent import cc_graph
    return cc_graph.build_cc_agent()


def _render_message(m, idx):
    """Render a chat message with feedback buttons for assistant replies."""
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant" and "feedback_id" not in m:
            col1, col2, _ = st.columns([1, 1, 10])
            with col1:
                if st.button(
                    ":material/thumb_up:",
                    key=f"up_{idx}",
                    help="Good answer",
                    width="content",
                ):
                    db.save_feedback(
                        st.session_state.chat_messages[idx - 1]["content"],
                        m["content"],
                        "up",
                    )
                    m["feedback_id"] = "up"
                    st.rerun()
            with col2:
                if st.button(
                    ":material/thumb_down:",
                    key=f"down_{idx}",
                    help="Bad answer",
                    width="content",
                ):
                    db.save_feedback(
                        st.session_state.chat_messages[idx - 1]["content"],
                        m["content"],
                        "down",
                    )
                    m["feedback_id"] = "down"
                    st.rerun()
            if m.get("feedback_id"):
                st.caption(f"Thanks! Recorded as {m['feedback_id']}")


def _stream_agent_response(agent, history):
    """Stream ONLY the final assistant answer tokens cleanly."""
    try:
        for chunk, metadata in agent.stream(
            {"messages": history},
            stream_mode="messages",
            config={"recursion_limit": 20},
        ):
            if metadata.get("langgraph_node") == "agent":
                if hasattr(chunk, "content") and chunk.content and not getattr(chunk, "tool_calls", None):
                    yield chunk.content
    except Exception as exc:
        yield f"Something went wrong while answering: {exc}"


def tab_chat():
    st.header("🧠 Master Financial Intelligence AI", divider=True)

    # Top KPI Banner for Instant Cross-Domain Context
    loans_df = db.load_bank_loans()
    cc_emis = db.load_cc_emis()
    cc_stmts = db.load_cc_statements()
    
    tot_loan_emi = loans_df["monthly_emi"].sum() if not loans_df.empty else 0.0
    tot_cc_emi = cc_emis["monthly_emi"].sum() if not cc_emis.empty else 0.0
    tot_debt_emi = tot_loan_emi + tot_cc_emi
    tot_cc_lim = cc_stmts["credit_limit"].sum() if not cc_stmts.empty else 0.0
    tot_cc_avail = cc_stmts["available_limit"].sum() if not cc_stmts.empty else 0.0

    st.markdown(textwrap.dedent(f"""
    <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%); border: 1px solid rgba(129, 140, 248, 0.25); border-radius: 16px; padding: 14px 20px; margin-bottom: 20px; box-shadow: 0 4px 16px rgba(0,0,0,0.25); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
        <div>
            <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #818cf8; letter-spacing: 0.08em;">Unified Finance OS</div>
            <div style="font-size: 18px; font-weight: 800; color: #f8fafc; margin-top: 2px;">Chief Financial Officer (CFO) AI</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Synthesizing Bank Statements (3 Accounts), Personal Loans (4 Plans), and Credit Cards (5 Cards).</div>
        </div>
        <div style="display: flex; gap: 20px; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 20px;">
            <div>
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">Total Monthly Debt</div>
                <div style="font-size: 15px; font-weight: 800; color: #f43f5e;">{inr(tot_debt_emi)}/mo</div>
                <div style="font-size: 11px; color: #cbd5e1;">{len(loans_df) + len(cc_emis)} active plans</div>
            </div>
            <div>
                <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">Credit Exposure</div>
                <div style="font-size: 15px; font-weight: 800; color: #38bdf8;">{inr(tot_cc_lim)}</div>
                <div style="font-size: 11px; color: #10b981;">{inr(tot_cc_avail)} free</div>
            </div>
        </div>
    </div>
    """), unsafe_allow_html=True)

    agent_mode = st.radio(
        "Select AI Perspective",
        [
            "🌟 Master Financial AI (Bank + Loans + Cards Combined)",
            "🏦 Bank & Cashflow Specialist",
            "💳 Credit Card Specialist"
        ],
        horizontal=True,
    )

    # Show feedback stats in sidebar
    with st.sidebar:
        st.divider()
        st.subheader(":material/feedback: Feedback")
        counts = db.feedback_counts()
        st.caption(f"👍 {counts['up']}  |  👎 {counts['down']}")

    try:
        if "Master" in agent_mode:
            agent = _get_master_chat_agent()
            suggestions = MASTER_SUGGESTIONS
        elif "Credit Card" in agent_mode:
            agent = _get_cc_chat_agent()
            suggestions = CC_SUGGESTIONS
        else:
            agent = _get_chat_agent()
            suggestions = BANK_SUGGESTIONS
    except Exception as exc:
        st.error(f"Agent is unavailable: {exc}")
        return

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Show suggestion chips on first load
    if len(st.session_state.chat_messages) == 0:
        st.caption("Quick prompts to ask:")
        cols = st.columns(3)
        for i, suggestion in enumerate(suggestions[:6]):
            with cols[i % 3]:
                if st.button(
                    suggestion,
                    key=f"sug_{i}",
                    use_container_width=True,
                ):
                    st.session_state.chat_messages.append(
                        {"role": "user", "content": suggestion}
                    )
                    st.rerun()

    # Check if the last message is from the user and needs a response
    last_msg = st.session_state.chat_messages[-1] if st.session_state.chat_messages else None
    should_respond = (last_msg is not None and last_msg["role"] == "user")

    for idx, m in enumerate(st.session_state.chat_messages):
        _render_message(m, idx)

    # Chat input at the bottom
    prompt = st.chat_input(
        "e.g. How much did I spend on food last month?",
    )
    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        st.rerun()

    # Generate assistant response if needed
    if should_respond:
        history = [
            ("user" if m["role"] == "user" else "assistant", m["content"])
            for m in st.session_state.chat_messages
        ]

        with st.chat_message("assistant"):
            with st.status("🤔 Thinking...", expanded=False) as status:
                response = st.write_stream(_stream_agent_response(agent, history))
                status.update(label="✓ Done", state="complete", expanded=False)

        if response:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response}
            )
            st.rerun()


def tab_feedback():
    """Review captured negative feedback for debugging/training."""
    st.header("Chat Feedback Review", divider=True)
    st.caption("Thumbs-down answers captured for analysis. Use these to improve the agent.")

    down_feedback = db.load_feedback(rating="down", limit=50)
    up_feedback = db.load_feedback(rating="up", limit=20)

    if down_feedback.empty and up_feedback.empty:
        st.info("No feedback recorded yet.")
        return

    if not down_feedback.empty:
        st.subheader(f":material/thumb_down: Needs attention ({len(down_feedback)})")
        for _, row in down_feedback.iterrows():
            with st.expander(f"**Q:** {row['question'][:80]}…", expanded=False):
                st.markdown(f"**Question:** {row['question']}")
                st.markdown(f"**Answer:** {row['answer']}")
                st.caption(f"Recorded: {row['created_at']}")

    if not up_feedback.empty:
        st.divider()
        st.subheader(f":material/thumb_up: Working well ({len(up_feedback)})")
        for _, row in up_feedback.iterrows():
            with st.expander(f"**Q:** {row['question'][:80]}…", expanded=False):
                st.markdown(f"**Question:** {row['question']}")
                st.markdown(f"**Answer:** {row['answer']}")
                st.caption(f"Recorded: {row['created_at']}")


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


# --------------------------------------------------------------------------
# Sidebar & main
# --------------------------------------------------------------------------

def sidebar():
    st.sidebar.markdown("""
    <div style="padding: 8px 0 20px 0; display: flex; align-items: center; gap: 12px;">
        <div style="background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);">
            <span class="material-symbols-rounded" style="color: white; font-size: 26px;">bolt</span>
        </div>
        <div>
            <div style="font-weight: 800; font-size: 18px; color: #f8fafc; letter-spacing: -0.02em;">Anti Gravity</div>
            <div style="font-weight: 600; font-size: 12px; color: #818cf8; text-transform: uppercase; letter-spacing: 0.05em;">Finance OS</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    s = db.stats()
    st.sidebar.caption(
        f"{s['total']} transactions · "
        f"{s['date_min'] or '—'} → {s['date_max'] or '—'}")
    st.sidebar.divider()
    for a in config.ACCOUNT_ORDER:
        label = config.ACCOUNTS[a]["label"]
        st.sidebar.caption(f"· {label}: {s['by_account'].get(a, 0)}")


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
            <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%); border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 16px; padding: 14px 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #818cf8; letter-spacing: 0.08em;">Active Card Profile</div>
                    <div style="font-size: 18px; font-weight: 800; color: #f8fafc; margin-top: 2px;">{sel_card_name}</div>
                    <div style="font-family: monospace; font-size: 14px; font-weight: 700; color: #94a3b8; margin-top: 4px; letter-spacing: 0.1em;">{masked_card_no}</div>
                </div>
                <div style="text-align: right; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 20px;">
                    <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">Total Due / Limit</div>
                    <div style="font-size: 16px; font-weight: 800; color: #f43f5e;">{tot_due_str} <span style="font-size: 12px; font-weight: 500; color: #cbd5e1;">(Limit: {lim_str})</span></div>
                    <div style="font-size: 11px; font-weight: 700; color: #f59e0b; margin-top: 4px;">Payment Due Date: {due_d_str}</div>
                </div>
            </div>
            """), unsafe_allow_html=True)
        else:
            st.markdown(textwrap.dedent(f"""
            <div style="background: rgba(30, 41, 59, 0.5); border: 1px dashed rgba(255, 255, 255, 0.15); border-radius: 16px; padding: 14px 20px; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: #94a3b8; letter-spacing: 0.08em;">Consolidated View</div>
                    <div style="font-size: 18px; font-weight: 800; color: #f8fafc; margin-top: 2px;">All Credit Cards</div>
                    <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">Showing combined metrics across all imported credit cards. Select a card on the left to inspect specific card EMIs & limits.</div>
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
        lim_df = cc_stmts[cc_stmts["credit_limit"] > 0].copy()

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
        bar_color = "#10b981" if util_pct < 30 else ("#f59e0b" if util_pct < 50 else "#ef4444")
        st.markdown(textwrap.dedent(f"""
        <div style="margin: 10px 0 24px 0;">
            <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">
                <span>Credit Utilization Progress</span>
                <span style="color: {bar_color};">{util_pct}% Utilized ({inr(tot_lim - tot_avail)} used of {inr(tot_lim)})</span>
            </div>
            <div style="width: 100%; height: 10px; background: rgba(255, 255, 255, 0.1); border-radius: 6px; overflow: hidden;">
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

            day_str = _ordinal(deb_day)
            card_html = textwrap.dedent(f"""
            <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 18px 22px; margin-bottom: 16px; box-shadow: 0 4px 16px rgba(0,0,0,0.2);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div>
                        <div style="font-size: 11px; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.08em;">{lender}</div>
                        <div style="font-size: 18px; font-weight: 800; color: #f8fafc; margin-top: 2px;">{lname}</div>
                        <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">{notes}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 11px; font-weight: 700; color: #94a3b8;">Monthly EMI</div>
                        <div style="font-size: 20px; font-weight: 800; color: #f43f5e;">{inr(emi_val)}<span style="font-size: 12px; font-weight: 500; color: #cbd5e1;">/mo</span></div>
                        <div style="font-size: 11px; font-weight: 700; color: #fbbf24; margin-top: 2px;">Debited: {day_str} of month</div>
                    </div>
                </div>
                <div style="margin: 14px 0 8px 0;">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #cbd5e1; margin-bottom: 4px;">
                        <span>Tenure Progress: <strong style="color: #f8fafc;">{paid_t} of {tot_t} EMIs Paid</strong></span>
                        <span style="color: {bar_color};">⏳ {rem_t} EMIs Left ({pct}% Complete)</span>
                    </div>
                    <div style="width: 100%; height: 10px; background: rgba(255, 255, 255, 0.1); border-radius: 6px; overflow: hidden;">
                        <div style="width: {min(pct, 100)}%; height: 100%; background: {bar_color}; border-radius: 6px; transition: width 0.4s ease;"></div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 10px; margin-top: 12px;">
                    <div>Original Loan: <strong style="color: #f8fafc;">{inr(tot_amt) if tot_amt > 0 else '—'}</strong></div>
                    <div>Remaining Balance: <strong style="color: #f43f5e;">{inr(rem_bal)}</strong></div>
                    <div>Bank Debits Logged: <strong style="color: #38bdf8;">{matched_count} debits</strong></div>
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


def main():
    sidebar()
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
        [
            f"{TAB_ICONS['overview']} Overview",
            f"{TAB_ICONS['transactions']} Bank Transactions",
            "💳 Credit Cards",
            "🏦 Bank Loans",
            f"{TAB_ICONS['upload']} Upload",
            f"{TAB_ICONS['reconciliation']} Reconciliation",
            "🧠 Master Financial AI",
            f"{TAB_ICONS['feedback']} Feedback",
        ]
    )
    with tab1:
        tab_overview()
    with tab2:
        tab_transactions()
    with tab3:
        tab_credit_cards()
    with tab4:
        tab_bank_loans()
    with tab5:
        tab_upload()
    with tab6:
        tab_reconciliation()
    with tab7:
        tab_chat()
    with tab8:
        tab_feedback()


if __name__ == "__main__":
    main()
