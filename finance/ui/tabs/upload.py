"""Tab: Upload bank and credit card statements."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

from ... import config, db, pipeline
from ...classify import categories as cat_mod
from ..format import inr, ordinal, mask_card
from ..theme import display_categories
def tab_upload():
    st.header("Upload statement", divider=True)
    st.caption("Export CSV or PDF from Axis / SBI / Kotak netbanking or Credit Card PDF statements.")

    # Render previous import summary banner if present
    if "last_import_summary" in st.session_state and st.session_state["last_import_summary"]:
        s = st.session_state["last_import_summary"]
        grid_cols = "repeat(5, 1fr)" if s.get("latest_balance") else "repeat(4, 1fr)"
        bal_html = f"""
            <div>
                <div style="font-size: 11px; color: #71717a; font-weight: 700; text-transform: uppercase;">Updated Balance</div>
                <div style="font-size: 20px; font-weight: 800; color: #09090b;">{s['latest_balance']}</div>
            </div>
        """ if s.get("latest_balance") else ""

        st.markdown(f"""
        <div class="metric-card" style="border: 1px solid #18181b; margin-bottom: 24px;">
            <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 14px;">
                <div class="icon-badge" style="background: #09090b; color: #ffffff; width: 44px; height: 44px; border-radius: 12px;">
                    <span class="material-symbols-rounded" style="font-size: 26px; color: #ffffff;">check_circle</span>
                </div>
                <div>
                    <h3 style="margin: 0; font-size: 17px; font-weight: 800; color: #09090b;">Statement Successfully Imported & Synchronized!</h3>
                    <p style="margin: 2px 0 0 0; color: #52525b; font-size: 13.5px;">
                        File <strong>{s['filename']}</strong> imported into <strong>{s['account_label']}</strong>.
                    </p>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: {grid_cols}; gap: 12px; margin-top: 12px; background: #f4f4f5; padding: 14px; border-radius: 12px; border: 1px solid #e4e4e7;">
                <div>
                    <div style="font-size: 11px; color: #71717a; font-weight: 700; text-transform: uppercase;">Total Parsed</div>
                    <div style="font-size: 22px; font-weight: 800; color: #09090b;">{s['total_parsed']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #71717a; font-weight: 700; text-transform: uppercase;">New Inserted</div>
                    <div style="font-size: 22px; font-weight: 800; color: #09090b;">{s['inserted']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #71717a; font-weight: 700; text-transform: uppercase;">Duplicates Skipped</div>
                    <div style="font-size: 22px; font-weight: 800; color: #71717a;">{s['skipped']}</div>
                </div>
                <div>
                    <div style="font-size: 11px; color: #71717a; font-weight: 700; text-transform: uppercase;">Date Range</div>
                    <div style="font-size: 13px; font-weight: 700; color: #09090b; margin-top: 4px;">{s['date_min']} → {s['date_max']}</div>
                </div>
                {bal_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Account Coverage & Next Upload Date Intelligence
    # --------------------------------------------------------------------------
    all_db_txns = db.load_all()
    all_cc_stmts = db.load_cc_statements()

    bank_coverage = {}
    for acct_key in config.ACCOUNT_ORDER:
        sub_df = all_db_txns[all_db_txns["account"] == acct_key]
        if not sub_df.empty:
            d_min = str(sub_df["txn_date"].min())
            d_max = str(sub_df["txn_date"].max())
            try:
                next_start = (pd.to_datetime(d_max) + timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                next_start = d_max
            bank_coverage[acct_key] = {
                "label": config.ACCOUNTS[acct_key]["label"],
                "min": d_min,
                "max": d_max,
                "next": next_start,
                "count": len(sub_df)
            }
        else:
            bank_coverage[acct_key] = {
                "label": config.ACCOUNTS[acct_key]["label"],
                "min": "—",
                "max": "No data yet",
                "next": "Any date",
                "count": 0
            }

    st.markdown("""
    <div style="margin-top: 6px; margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 14px; font-weight: 800; color: #f8fafc; text-transform: uppercase; letter-spacing: 0.5px;">
                📅 Current Data Coverage & Next Export Windows
            </div>
            <div style="font-size: 12px; color: #94a3b8;">Know exactly which dates to download from NetBanking before uploading</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    cov_cols = st.columns(len(config.ACCOUNT_ORDER))
    for idx, acct_key in enumerate(config.ACCOUNT_ORDER):
        c_info = bank_coverage[acct_key]
        with cov_cols[idx]:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 14px 16px; min-height: 110px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="font-size: 14px; font-weight: 800; color: #09090b;">🏦 {c_info['label']} Bank</div>
                    <span style="font-size: 11px; background: #f4f4f5; color: #09090b; padding: 2px 8px; border-radius: 8px; font-weight: 700; border: 1px solid #e4e4e7;">{c_info['count']} txns</span>
                </div>
                <div style="font-size: 12px; color: #71717a; margin-top: 6px;">
                    Ledger available through: <strong style="color: #09090b;">{c_info['max']}</strong>
                </div>
                <div style="margin-top: 8px; font-size: 12px; background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px; padding: 5px 8px; color: #09090b;">
                    👉 Next export: <strong>{c_info['next']}</strong> onwards
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    stmt_type = st.radio(
        "Statement Target",
        ["🏦 Bank Account Statement", "💳 Credit Card Statement", "📬 Auto-Sync from Email (Gmail / Yahoo)"],
        horizontal=True,
    )

    if stmt_type == "📬 Auto-Sync from Email (Gmail / Yahoo)":
        from finance.ingest import email_sync
        
        st.subheader("📬 1-Click Automated Statement Sync (Gmail & Yahoo)")
        st.caption("Auto-fetches, decrypts, and parses all monthly Credit Card PDF statements across your configured email accounts in a single click.")

        # Display pre-configured connection status
        from finance import profile
        g_user = os.getenv("GMAIL_USER", "ronaldoroshan@gmail.com")
        y_user = os.getenv("YAHOO_USER", "ronaldoroshan@yahoo.in")
        pdf_pwds_list = profile.get_pdf_passwords()
        pdf_pwds_default = ", ".join(pdf_pwds_list) if pdf_pwds_list else ""

        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 16px;">
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="font-size: 12px; font-weight: 800; color: #09090b; letter-spacing: 0.04em;">🟢 GMAIL CONNECTED</div>
                    <span style="font-size: 11px; color: #71717a; background: #f4f4f5; padding: 2px 7px; border-radius: 6px;">SSL IMAP : 993</span>
                </div>
                <div style="font-size: 15px; font-weight: 700; color: #09090b; margin-top: 6px;">{g_user}</div>
                <div style="font-size: 12px; color: #71717a; margin-top: 4px;">Scapia Federal, IDFC FIRST Mayura, Jupiter Edge, Amex</div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 14px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="font-size: 12px; font-weight: 800; color: #09090b; letter-spacing: 0.04em;">🟢 YAHOO MAIL CONNECTED</div>
                    <span style="font-size: 11px; color: #71717a; background: #f4f4f5; padding: 2px 7px; border-radius: 6px;">SSL IMAP : 993</span>
                </div>
                <div style="font-size: 15px; font-weight: 700; color: #09090b; margin-top: 6px;">{y_user}</div>
                <div style="font-size: 12px; color: #71717a; margin-top: 4px;">YES Bank ELITE, Indian Oil Axis Bank</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_s1, col_s2 = st.columns([3, 1])
        with col_s1:
            scapia_monthly_pwd = st.text_input(
                "This Month's Dynamic Scapia Password (Optional)",
                value=os.getenv("SCAPIA_PASSWORD", "dn8tqg82as"),
                placeholder="e.g. dn8tqg82as (from Scapia App ➔ Card Controls)",
                help="Scapia generates a dynamic password each month. Leave as is or update when a new statement arrives."
            )
        with col_s2:
            lookback_days = st.selectbox("Lookback Window", [30, 45, 60, 90], index=1, key="sync_all_lookback")

        if st.button("⚡ 1-Click Sync All Statements (Gmail & Yahoo Mail)", type="primary", width="stretch"):
            with st.spinner("Connecting to Gmail & Yahoo Mail, discovering statements, and auto-decrypting..."):
                # Combine standard passwords with Scapia dynamic password
                pwds = list(pdf_pwds_list)
                if scapia_monthly_pwd and scapia_monthly_pwd not in pwds:
                    pwds.insert(0, scapia_monthly_pwd.strip())

                res = email_sync.sync_all_configured_emails(
                    pdf_passwords=pwds,
                    days_back=int(lookback_days)
                )

            if res["success"]:
                db.sync_account_balances_from_ledger()
                pipeline.reconcile()
                st.success(f"🎉 Email Sync Complete & Balances Updated! {res['message']}")
                st.toast("✅ Email statements synced & bank balances updated!", icon="📬")

                # Live updated balances strip
                b_df = db.load_account_balances()
                if not b_df.empty:
                    st.markdown("##### 🏦 Real-Time Synchronized Bank Balances")
                    b_cols = st.columns(len(b_df))
                    for idx, (_, r) in enumerate(b_df.iterrows()):
                        with b_cols[idx]:
                            st.metric(r["label"], inr(r["total_balance"]), delta=f"As of {r['as_of_date']}")

                txns_cnt = res.get("txns_saved", 0)
                emis_cnt = res.get("emis_saved", 0)
                st.metric("Statements Processed", res["statements_saved"], delta=f"{txns_cnt} Line Items & {emis_cnt} EMIs Ingested", delta_color="normal")
                if res["details"]:
                    st.subheader("📑 Ingested Statements Details")
                    st.dataframe(pd.DataFrame(res["details"]), width="stretch", hide_index=True)
            else:
                st.error(res["message"])

        with st.expander("⚙️ Advanced / Edit Credentials & Passwords", expanded=False):
            st.caption("Credentials and passwords are permanently saved in your local `.env` file (protected from Git).")
            e_col1, e_col2 = st.columns(2)
            with e_col1:
                st.text_input("Gmail App Password", value="••••••••••••••••", disabled=True)
                st.text_input("Yahoo App Password", value="••••••••••••••••", disabled=True)
            with e_col2:
                st.text_input("Configured PDF Passwords", value=pdf_pwds_default, disabled=True)
                st.info("To modify, edit the `.env` file in the project root.")

        return

    if stmt_type == "💳 Credit Card Statement":
        if not all_cc_stmts.empty:
            st.markdown("##### 💳 Current Credit Card Statement Coverage")
            latest_cc = all_cc_stmts.sort_values("statement_date").groupby("card_name", as_index=False).last()
            cc_cols = st.columns(min(len(latest_cc), 5))
            for i, (_, r) in enumerate(latest_cc.iterrows()):
                col_target = cc_cols[i % len(cc_cols)]
                with col_target:
                    l4 = f" (..{r['card_last4']})" if r.get('card_last4') else ""
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1px solid #e4e4e7; border-radius: 12px; padding: 10px 12px; min-height: 100px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
                        <div style="font-size: 13px; font-weight: 800; color: #09090b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{r['card_name']}">{r['card_name']}{l4}</div>
                        <div style="font-size: 11px; color: #71717a; margin-top: 4px;">Latest Stmt: <strong style="color: #09090b;">{r['statement_date']}</strong></div>
                        <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Bill Due: <strong style="color: #09090b;">₹{float(r['total_due']):,.2f}</strong></div>
                        <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Due Date: <strong style="color: #09090b;">{r.get('due_date') or '—'}</strong></div>
                    </div>
                    """, unsafe_allow_html=True)

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            card_name = st.selectbox(
                "Card / Bank Name",
                [
                    "Axis Bank Credit Card",
                    "American Express",
                    "Scapia Federal Credit Card",
                    "YES Bank Credit Card",
                    "IDFC FIRST Credit Card",
                    "HDFC Credit Card",
                    "ICICI Amazon Pay / Credit Card",
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

        # Show existing statement status for selected card
        if not all_cc_stmts.empty:
            c_search = card_name.replace(" Credit Card", "").replace(" Card", "")
            match_stmt = all_cc_stmts[all_cc_stmts["card_name"].str.contains(c_search[:10], case=False, na=False)]
            if not match_stmt.empty:
                l_s = match_stmt.sort_values("statement_date").iloc[-1]
                st.markdown(f"""
                <div style="background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; font-size: 13px; color: #09090b;">
                    📑 <strong>Latest statement on file:</strong> {l_s['statement_date']} (Payment Due: <strong style="color: #09090b;">{l_s['due_date']}</strong>, Total Due: <strong style="color: #09090b;">₹{l_s['total_due']:,.2f}</strong>).
                </div>
                """, unsafe_allow_html=True)

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
                    db.sync_account_balances_from_ledger()
                    pipeline.reconcile()
                    tot_due_str = inr(stmt_info.get("total_due", 0.0)) if stmt_info.get("total_due") else None
                    st.session_state["last_import_summary"] = {
                        "filename": uploaded.name,
                        "account_label": f"Credit Card ({stmt_info.get('card_name', card_name)})",
                        "total_parsed": len(cc_txns),
                        "inserted": inserted,
                        "skipped": skipped,
                        "date_min": min(r["txn_date"] for r in cc_txns) if cc_txns else "—",
                        "date_max": max(r["txn_date"] for r in cc_txns) if cc_txns else "—",
                        "latest_balance": f"{tot_due_str} (Due)" if tot_due_str else "Reconciled",
                    }
                    st.toast("✅ Credit card statement imported & ledger synchronized!", icon="💳")
                    st.rerun()
            else:
                st.info("No transaction rows or summary found in this statement.")
        return

    # Bank Account Statement Upload Flow
    st.markdown("""
    <div style="background: #f4f4f5; border: 1px solid #e4e4e7; border-radius: 12px; padding: 12px 16px; margin-bottom: 14px;">
        <div style="font-size: 13px; color: #09090b;">
            💡 <strong>Next Export Windows for NetBanking:</strong>
            <span style="margin-left: 10px;">🔵 <strong>Axis:</strong> from <code>2026-09-07</code> to Today</span>
            <span style="margin-left: 14px;">🟣 <strong>Kotak 811:</strong> from <code>2026-08-21</code> to Today</span>
            <span style="margin-left: 14px;">🟢 <strong>SBI:</strong> from <code>2026-07-31</code> to Today</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Statement file",
        type=["csv", "pdf"],
        help="CSV or PDF statements (Axis, SBI, Kotak, HDFC). Password unlocking supported.",
        accept_multiple_files=False,
    )

    if uploaded is not None:
        is_pdf = uploaded.name.lower().endswith(".pdf")
        bank_pdf_password = None
        if is_pdf:
            bank_pdf_password = st.text_input(
                "Statement Password (if encrypted)",
                type="password",
                help="If your netbanking PDF is password-protected (e.g. DOB DDMMYYYY or registered mobile number / PAN), enter it here.",
                key="bank_pdf_pwd"
            )

        detected = pipeline.loader.detect_account(uploaded, password=bank_pdf_password)
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
            rows, warnings = pipeline.loader.parse_file(uploaded, account, password=bank_pdf_password)
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
                result = pipeline.run_import(uploaded, account, password=bank_pdf_password)
                b_df = db.load_account_balances()
                latest_acct_b = b_df[b_df["account"] == account]
                new_bal_str = inr(latest_acct_b.iloc[0]["total_balance"]) if not latest_acct_b.empty else None
                st.session_state["last_import_summary"] = {
                    "filename": uploaded.name,
                    "account_label": config.ACCOUNTS[account]["label"],
                    "total_parsed": len(rows),
                    "inserted": result["inserted"],
                    "skipped": result["skipped"],
                    "date_min": min(r["txn_date"] for r in rows) if rows else "—",
                    "date_max": max(r["txn_date"] for r in rows) if rows else "—",
                    "latest_balance": new_bal_str,
                }
                st.toast(f"✅ Statement imported & {config.ACCOUNTS[account]['label']} balance synced to {new_bal_str}!", icon="⚡")
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

            with st.popover("🗑️ Reset All Credit Card Data"):
                st.warning("⚠️ This will permanently delete all credit card statements, line items, and active EMIs from SQLite.")
                confirm = st.checkbox("I understand and want to wipe all credit card records", key="confirm_wipe_cc")
                if st.button("Confirm Wipe", type="primary", disabled=not confirm, key="btn_confirm_clear_cc"):
                    db.clear_cc_data()
                    if "last_import_summary" in st.session_state:
                        del st.session_state["last_import_summary"]
                    st.success("All credit card data has been cleared from the database.")
                    st.rerun()
        else:
            st.info("No credit card statements imported yet.")
