"""Anti Gravity Finance OS — Unified Streamlit Dashboard.

Run with:  streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path
import streamlit as st

from finance import db
from finance.ui.theme import inject_custom_css, TAB_ICONS
from finance.ui.format import inr
from finance.ui.sidebar import sidebar
from finance.ui.tabs.overview import tab_overview
from finance.ui.tabs.liquidity_radar import tab_liquidity_radar
from finance.ui.tabs.ashwin import tab_reconciliation
from finance.ui.tabs.credit_cards import tab_credit_cards
from finance.ui.tabs.rewards import tab_rewards
from finance.ui.tabs.bank_loans import tab_bank_loans
from finance.ui.tabs.transactions import tab_transactions
from finance.ui.tabs.chat import tab_chat
from finance.ui.tabs.upload import tab_upload
from finance.ui.tabs.feedback import tab_feedback
from finance.ui.tabs.data_health import tab_data_health

# Initialize Database
DB_PATH = Path(__file__).resolve().parent / "data" / "finance.db"
db.set_db_path(str(DB_PATH))
db.init_db()

# Page configuration
st.set_page_config(
    page_title="Anti Gravity Agent — Finance OS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject dark-mode styling
inject_custom_css()


def main():
    sidebar()

    # Query param check: e.g. http://<ip>:8501/?view=mobile or ?mobile=true
    qp = st.query_params
    query_mobile = qp.get("view") == "mobile" or qp.get("mobile") in ("1", "true")
    if query_mobile and "mobile_view_active" not in st.session_state:
        st.session_state["mobile_view_active"] = True

    # Sidebar switch for Mobile / Desktop View
    is_mobile = st.sidebar.toggle(
        "📱 Mobile App View",
        value=st.session_state.get("mobile_view_active", False),
        key="mobile_view_toggle_key",
        help="Switch to a clean, single-column mobile interface optimized for phone screens",
    )
    st.session_state["mobile_view_active"] = is_mobile

    modules = [
        ("overview", f"{TAB_ICONS['overview']} Overview", tab_overview),
        ("radar", "⚡ 30-Day Liquidity Radar", tab_liquidity_radar),
        ("recon", f"{TAB_ICONS['reconciliation']} Ashwin Reconciliation", tab_reconciliation),
        ("cards", "💳 Credit Cards", tab_credit_cards),
        ("rewards", f"{TAB_ICONS['rewards']} Rewards & Miles", tab_rewards),
        ("loans", "🏦 Bank Loans", tab_bank_loans),
        ("txns", f"{TAB_ICONS['transactions']} Bank Transactions", tab_transactions),
        ("health", f"{TAB_ICONS['data_health']} Data Health", tab_data_health),
        ("chat", "🧠 Master Financial AI", tab_chat),
        ("upload", f"{TAB_ICONS['upload']} Upload & Sync", tab_upload),
        ("feedback", f"{TAB_ICONS['feedback']} History & Logs", tab_feedback),
    ]

    if is_mobile:
        # Render clean mobile header with quick cash balance pill
        try:
            b_df = db.load_account_balances()
            tot_cash = b_df["total_balance"].sum() if b_df is not None and not b_df.empty else 0.0
        except Exception:
            tot_cash = 0.0

        st.markdown(f"""
        <div class="mobile-header-card">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="background: #09090b; width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center;">
                    <span class="material-symbols-rounded" style="color: #ffffff; font-size: 20px;">bolt</span>
                </div>
                <span style="font-weight: 800; font-size: 16px; color: #09090b; letter-spacing: -0.02em;">Finance OS</span>
            </div>
            <div style="background: #09090b; border-radius: 20px; padding: 4px 12px; font-size: 12.5px; font-weight: 700; color: #ffffff;">
                {inr(tot_cash)}
            </div>
        </div>
        """, unsafe_allow_html=True)

        module_labels = [m[1] for m in modules]
        current_mod_idx = st.session_state.get("mobile_module_idx", 0)

        # Mobile navigation selector (compact selectbox with prominent styling)
        sel_label = st.selectbox(
            "📍 Navigate Module",
            options=module_labels,
            index=min(current_mod_idx, len(module_labels) - 1),
            key="mobile_module_selector",
            label_visibility="collapsed",
        )
        st.session_state["mobile_module_idx"] = module_labels.index(sel_label)

        st.markdown("<div style='height: 6px;'></div>", unsafe_allow_html=True)

        # Execute the selected module in full mobile view
        chosen_module = modules[st.session_state["mobile_module_idx"]]
        chosen_module[2]()

    else:
        # Standard Desktop Multi-Tab View
        tabs = st.tabs([m[1] for m in modules])
        for i, (_, _, func) in enumerate(modules):
            with tabs[i]:
                func()


if __name__ == "__main__":
    main()
