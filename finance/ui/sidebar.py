"""Sidebar navigation, database summary, account transaction counts, and global sync controls."""
from __future__ import annotations

import os
import streamlit as st
from .. import config, db
from .format import inr


def sidebar():
    """Render consistent branding, live balances, sync controls, and transaction counts in sidebar."""
    st.sidebar.markdown("""
    <div style="padding: 8px 0 20px 0; display: flex; align-items: center; gap: 12px;">
        <div style="background: #09090b; width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);">
            <span class="material-symbols-rounded" style="color: #ffffff; font-size: 24px;">bolt</span>
        </div>
        <div>
            <div style="font-weight: 800; font-size: 17px; color: #09090b; letter-spacing: -0.02em;">Anti Gravity</div>
            <div style="font-weight: 600; font-size: 11.5px; color: #71717a; text-transform: uppercase; letter-spacing: 0.06em;">Finance OS</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 1. Global 1-Click Sync Controls
    if st.sidebar.button("🔄 Sync & Refresh App", key="sidebar_sync_btn", width="stretch", help="Re-compute all bank balances and reconcile match states across all statements"):
        db.sync_account_balances_from_ledger()
        st.toast("✅ App & balances synchronized with latest statements!", icon="⚡")
        st.rerun()

    # 2. Quick Email Sync Popover
    has_gmail = bool(os.getenv("GMAIL_USER") and os.getenv("GMAIL_APP_PASSWORD"))
    has_yahoo = bool(os.getenv("YAHOO_USER") and os.getenv("YAHOO_APP_PASSWORD"))
    if has_gmail or has_yahoo:
        with st.sidebar.popover("📬 Sync Statements from Email", help="1-click fetch latest statements from Gmail & Yahoo"):
            st.caption("Auto-fetch and decrypt new statements from your connected email accounts.")
            sb_lookback = st.selectbox("Lookback Window", [30, 45, 60, 90], index=1, key="sb_sync_lookback")
            if st.button("Fetch & Sync Now", type="primary", key="sb_btn_fetch_email", width="stretch"):
                with st.spinner("Syncing statements from Gmail & Yahoo..."):
                    from finance.ingest import email_sync
                    from finance import profile
                    pwds = profile.get_pdf_passwords()
                    res = email_sync.sync_all_configured_emails(pdf_passwords=pwds, days_back=int(sb_lookback))
                    db.sync_account_balances_from_ledger()
                if res["success"]:
                    st.success(f"Sync complete! {res['statements_saved']} statement(s) saved.")
                    st.toast("✅ Email statements synced & balances updated!", icon="📬")
                    st.rerun()
                else:
                    st.error(res["message"])

    st.sidebar.divider()

    # 3. Live Account Balances in Sidebar
    try:
        b_df = db.load_account_balances()
    except Exception:
        b_df = None

    if b_df is not None and not b_df.empty:
        tot_b = b_df["total_balance"].sum()
        st.sidebar.markdown(f"""
        <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);">
            <div style="font-size: 11px; font-weight: 700; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em;">Total Liquid Cash</div>
            <div style="font-size: 20px; font-weight: 800; color: #09090b; margin-top: 2px;">{inr(tot_b)}</div>
        </div>
        """, unsafe_allow_html=True)
        for _, r in b_df.iterrows():
            acct_lbl = r["label"]
            st.sidebar.caption(f"· {acct_lbl}: **{inr(r['total_balance'])}** *(as of {r['as_of_date']})*")
        st.sidebar.divider()

    # 4. Transaction Stats
    s = db.stats()
    st.sidebar.caption(
        f"{s['total']} transactions · "
        f"{s['date_min'] or '—'} → {s['date_max'] or '—'}")
    for a in config.ACCOUNT_ORDER:
        label = config.ACCOUNTS[a]["label"]
        st.sidebar.caption(f"· {label}: {s['by_account'].get(a, 0)}")
