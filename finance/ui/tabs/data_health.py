"""Data Health, Statement Validation & Review Queue UI Tab (Change 29).

Provides 360° visibility into dataset completeness, statement balance integrity,
interactive review queue resolution, and comprehensive audit trail.
"""
from __future__ import annotations

import json
from datetime import datetime
import pandas as pd
import streamlit as st

from ... import db
from ...security import sanitize_html
from ...services.statement_validator import audit_account_statements, validate_statement
from ...services.timescope import get_timescope_service
from ...money import format_inr_paise, paise_to_rupees


def tab_data_health():
    st.markdown("""
    <div style="margin-bottom: 20px;">
        <h2 style="font-weight: 800; font-size: 24px; color: #09090b; margin: 0 0 6px 0; letter-spacing: -0.02em;">
            🛡️ Data Health & Review Queue
        </h2>
        <p style="color: #71717a; font-size: 14px; margin: 0;">
            Real-time data completeness indicators, statement balance variance math, and human-in-the-loop review queue.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 1. High-Level Summary Metrics
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM transactions")
    tot_txns = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM canonical_events")
    tot_can = cur.fetchone()[0]
    conn.close()

    pending_reviews_df = db.load_review_queue(status="pending")
    num_pending = len(pending_reviews_df) if not pending_reviews_df.empty else 0

    validations_df = db.load_statement_validations()
    num_balanced = len(validations_df[validations_df["status"] == "balanced"]) if not validations_df.empty else 0
    num_variance = len(validations_df[validations_df["status"] == "variance_detected"]) if not validations_df.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Transactions", f"{tot_txns:,}", f"{tot_can:,} canonical events")
    with c2:
        st.metric("Pending Review Queue", f"{num_pending}", "Requires human review" if num_pending > 0 else "All cleared", delta_color="inverse")
    with c3:
        st.metric("Validated Statements", f"{num_balanced}", "0 variance")
    with c4:
        st.metric("Variances Detected", f"{num_variance}", "Review required" if num_variance > 0 else "None", delta_color="inverse")

    st.markdown("---")

    # Sub-tabs
    t1, t2, t3, t4 = st.tabs([
        "📊 Statement Coverage",
        "⚖️ Balance Variance Monitor",
        "📥 Review Queue",
        "📜 Audit Trail",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Statement Coverage & Freshness
    # -------------------------------------------------------------------------
    with t1:
        st.markdown("### 📊 Ingestion Coverage & Statement Freshness")
        ts = get_timescope_service()
        latest_date = ts.get_latest_data_date()

        st.info(
            f"**Latest Ingested Transaction Date**: `{latest_date.isoformat() if latest_date else 'None'}` "
            f"— *Data coverage across calendar year 2026 is actively monitored.*"
        )

        # Accounts breakdown
        accs_df = db.load_accounts()
        if accs_df.empty:
            db.seed_default_accounts()
            accs_df = db.load_accounts()

        if not accs_df.empty:
            rows = []
            conn = db.connect()
            for _, acc in accs_df.iterrows():
                aid = str(acc["id"])
                aname = str(acc["name"])
                atype = str(acc["account_type"])

                cur = conn.cursor()
                cur.execute("SELECT COUNT(*), MIN(txn_date), MAX(txn_date) FROM transactions WHERE account = ?", (aid,))
                cnt, mind, maxd = cur.fetchone()

                rows.append({
                    "Account ID": aid,
                    "Name": aname,
                    "Type": atype.replace("_", " ").title(),
                    "Status": acc.get("status", "active").title(),
                    "Transactions": cnt or 0,
                    "Earliest Date": mind or "N/A",
                    "Latest Date": maxd or "N/A",
                })
            conn.close()

            cov_df = pd.DataFrame(rows)
            st.dataframe(cov_df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 2: Statement Balance Variance Monitor
    # -------------------------------------------------------------------------
    with t2:
        st.markdown("### ⚖️ Statement Balance Validation ($Opening + Credits - Debits \\approx Closing$)")
        st.caption("Validates mathematical statement consistency. Any drift beyond ±₹1.00 is flagged.")

        col_a, col_b = st.columns([3, 1])
        with col_b:
            if st.button("⚡ Audit All Bank Accounts", use_container_width=True):
                for acc_id in ["axis", "sbi", "kotak"]:
                    audit_account_statements(acc_id)
                st.success("Re-audited bank statements!")
                st.rerun()

        vals = db.load_statement_validations()
        if vals.empty:
            st.info("No statement validation records yet. Click '⚡ Audit All Bank Accounts' to run balance verification.")
        else:
            display_rows = []
            for _, r in vals.iterrows():
                open_r = paise_to_rupees(int(r["opening_balance_paise"]))
                close_r = paise_to_rupees(int(r["closing_balance_paise"]))
                cred_r = paise_to_rupees(int(r["credits_paise"]))
                deb_r = paise_to_rupees(int(r["debits_paise"]))
                calc_r = paise_to_rupees(int(r["calculated_closing_paise"]))
                var_r = paise_to_rupees(int(r["variance_paise"]))

                display_rows.append({
                    "Account": str(r["account_id"]).upper(),
                    "Period": f"{r['statement_period_start']} to {r['statement_period_end']}",
                    "Opening (₹)": f"₹{open_r:,.2f}",
                    "Credits (₹)": f"+₹{cred_r:,.2f}",
                    "Debits (₹)": f"-₹{deb_r:,.2f}",
                    "Expected Closing": f"₹{calc_r:,.2f}",
                    "Actual Closing": f"₹{close_r:,.2f}",
                    "Variance": f"₹{var_r:,.2f}",
                    "Status": "✅ Balanced" if r["status"] == "balanced" else "⚠️ Variance Detected",
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 3: Interactive Review Queue
    # -------------------------------------------------------------------------
    with t3:
        st.markdown("### 📥 Interactive Review Queue")
        st.caption("Human-in-the-loop review for ambiguous classifications, multi-match transfers, and anomalies.")

        rq_df = db.load_review_queue(status="pending")
        if rq_df.empty:
            st.success("🎉 All clean! No pending items in the review queue.")
        else:
            st.warning(f"**{len(rq_df)} items** require review:")
            for _, item in rq_df.iterrows():
                iid = str(item["id"])
                itype = str(item["item_type"]).replace("_", " ").title()
                reason = str(item["reason"])
                created = str(item["created_at"])
                target_item_id = str(item["item_id"])

                with st.expander(f"📌 [{itype}] {reason} ({created})", expanded=True):
                    st.write(f"**Item ID**: `{target_item_id}`")
                    cdata_raw = item.get("candidate_data_json")
                    if cdata_raw:
                        try:
                            cdata = json.loads(cdata_raw)
                            st.json(cdata)
                        except Exception:
                            st.code(cdata_raw)

                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        if st.button("✅ Accept / Resolve", key=f"btn_acc_{iid}"):
                            db.resolve_review_item(iid, "resolved", resolution={"action": "accepted_by_user"})
                            st.success("Item resolved!")
                            st.rerun()
                    with col_r2:
                        if st.button("❌ Dismiss / Ignore", key=f"btn_dism_{iid}"):
                            db.resolve_review_item(iid, "rejected", resolution={"action": "dismissed_by_user"})
                            st.info("Item dismissed.")
                            st.rerun()
                    with col_r3:
                        if st.button("➕ Create Rule", key=f"btn_rule_{iid}"):
                            st.info("Navigating to rule creation...")

    # -------------------------------------------------------------------------
    # TAB 4: Audit Trail
    # -------------------------------------------------------------------------
    with t4:
        st.markdown("### 📜 System & User Audit Trail")
        st.caption("Immutable record of financial modifications, classifications, reconciliations, and review resolutions.")

        audits_df = db.load_audit_events(limit=50)
        if audits_df.empty:
            st.info("No audit events recorded yet.")
        else:
            display_audits = []
            for _, a in audits_df.iterrows():
                display_audits.append({
                    "Timestamp": a["created_at"],
                    "Entity Type": str(a["entity_type"]).title(),
                    "Entity ID": str(a["entity_id"]),
                    "Action": str(a["action"]).title(),
                    "Actor": str(a["actor"]).title(),
                    "Reason": str(a.get("reason") or ""),
                })
            st.dataframe(pd.DataFrame(display_audits), use_container_width=True, hide_index=True)
