"""Tab: Bank Transactions ledger and category override editor."""
from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from ... import config, db, pipeline
from ..format import inr, month_key
from ..theme import category_color, display_categories


def _category_label(cls: str, cat: str | None) -> str:
    mapping = {
        config.CLASSIFICATION_INCOME: "Salary",
        config.CLASSIFICATION_OTHER_INCOME: "Other Income",
        config.CLASSIFICATION_FRIEND_DEPOSIT: "Ashwin",
        config.CLASSIFICATION_CC_PAYMENT: "Credit Card",
        config.CLASSIFICATION_INTERNAL_TRANSFER: "Internal Transfer",
        config.CLASSIFICATION_FEE: "Fees & Charges",
        config.CLASSIFICATION_INVESTMENT: "Investments",
    }
    if cls in mapping:
        return mapping[cls]
    return cat or config.DEFAULT_CATEGORY
def tab_transactions():
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1:
        st.header("Transactions", divider=True)
    with t_col2:
        st.write("")  # visual spacing
        if st.button("⚡ Re-apply Auto-Categorization", help="Re-apply keyword classification rules to all transactions without manual overrides", key="recat_txns_btn", width="stretch"):
            n = pipeline.reclassify_all_unoverridden()
            st.toast(f"Updated {n} transactions based on rules.")
            st.rerun()

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

