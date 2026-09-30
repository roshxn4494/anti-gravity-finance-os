"""End-to-end test: import the synthetic statements into a temp DB and assert
classification, matching, recurring detection, KPIs and dedup.

Run:  .venv/bin/python tests/run_tests.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance import config, db, pipeline  # noqa: E402
from finance.ingest import loader  # noqa: E402
from sample_data import (EXPECTED_JUNE_INCOME, EXPECTED_JUNE_SPEND,  # noqa: E402
                         RENT_COUNTERPARTY, all_files, sbi_real_format)


class Upload:
    def __init__(self, name: str, text: str):
        self.name = name
        self._data = text.encode()

    def getvalue(self):
        return self._data


PASS = 0
FAIL = 0


def check(cond: bool, label: str, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        print(f"  ✗ {label}  {detail}")


def main():
    tmp = tempfile.mkdtemp()
    db.set_db_path(os.path.join(tmp, "test.db"))
    db.init_db()

    print("\nImporting synthetic statements…")
    for name, text, account in all_files():
        result = pipeline.run_import(Upload(name, text), account)
        print(f"  {name}: parsed={result['rows_parsed']} "
              f"inserted={result['inserted']} skipped={result['skipped']}")

    df = db.load_all()
    print(f"\nTotal rows in DB: {len(df)}\n")

    by_class = df.groupby("classification").size()

    print("Classification coverage:")
    check(df["classification"].notna().all(), "every row classified")
    for cls in config.ALL_CLASSIFICATIONS:
        check(cls in by_class.index, f"has classification: {cls}",
              by_class.to_dict())

    print("\nBank auto-detection:")
    for name, text, account in all_files():
        got = loader.detect_account(Upload(name, text))
        check(got == account, f"{name} → {account}",
              f"detected {got}")

    # Real SBI layout: preamble + multiline quoted narrations.
    sbi_real = sbi_real_format()
    check(loader.detect_account(Upload("sbi_real.csv", sbi_real)) == "sbi",
          "sbi_real.csv (multiline SBI) → sbi")
    from finance.ingest import csv_parsers  # noqa: E402
    rows, _ = csv_parsers.parse_csv(sbi_real.encode(), "sbi_real.csv", "sbi")
    desc = rows[0]["description"] if rows else ""
    clean = bool(rows and "SWIGGY" in desc.upper()
                 and "\n" not in desc)
    check(clean,
          "real SBI layout parses to a clean one-line narration",
          f"rows={len(rows)} desc={repr(desc)}")

    print("\nSpot checks (find by description):")
    find = lambda kw: df[df["description"].str.contains(kw, case=False, na=False)]

    s = find("INCOMEPAY")
    check(len(s) == 3 and (s["classification"] == "income").all(),
          "salary → income")

    s = find("SWIGGY")
    check((s["classification"] == "spend").all()
          and (s["category"] == "Food & Dining").all(),
          "Swiggy → spend / Food & Dining")

    s = find("BIGBASKET")
    check((s["category"] == "Groceries").all(), "BigBasket → Groceries")

    s = find("UBER")
    check((s["category"] == "Transport & Fuel").all(), "Uber → Transport & Fuel")

    s = find("AMAZON PAY")
    check((s["category"] == "Shopping").all(), "Amazon Pay → Shopping")

    s = find("ELECTRICITY")
    check((s["category"] == "Utilities & Bills").all(), "Electricity → Utilities")

    s = find("PHARMEASY")
    check((s["category"] == "Healthcare").all(), "PharmEasy → Healthcare")

    s = find("ATM WITHDRAWAL")
    check((s["classification"] == "fee").all(), "ATM → fee")

    s = find("REFUND")
    check((s["classification"] == "other_income").all(), "Refund → other_income")

    s = find("ASHWIN")
    check((s["classification"] == "friend_deposit").all(), "Ashwin → friend_deposit")

    s = find("CREDIT CARD PAYMENT")
    check((s["classification"] == "cc_payment").all(), "CC payment → cc_payment")

    # Transfers (Axis→SBI and Axis→Kotak) both directions
    s = find("Axis to SBI")
    check((s["classification"] == "internal_transfer").all(),
          "Axis→SBI → internal_transfer")
    s = find("Axis to Kotak")
    check((s["classification"] == "internal_transfer").all(),
          "Axis→Kotak → internal_transfer")
    s = find("TO SELF")
    check((s["classification"] == "internal_transfer").all(),
          "SBI/Kotak credit → internal_transfer")

    print("\nMatching:")
    sbi_in = find("TO SELF").iloc[0]
    axis_sbi = find("Axis to SBI").iloc[0]
    check(axis_sbi["match_status"] == "matched"
          and axis_sbi["matched_with"] == sbi_in["id"],
          "Axis→SBI 20,000 paired with SBI credit")
    kotak_in = df[df["description"].str.contains("NEFT/AXIS/TO SELF", na=False)].iloc[0]
    axis_kotak = find("Axis to Kotak").iloc[0]
    check(axis_kotak["match_status"] == "matched"
          and axis_kotak["matched_with"] == kotak_in["id"],
          "Axis→Kotak 15,000 paired with Kotak credit")

    ash = find("ASHWIN").iloc[0]
    cc = find("CREDIT CARD PAYMENT").iloc[0]
    check(ash["match_status"] == "matched" and ash["matched_with"] == cc["id"],
          "Ashwin 12,000 paired with CC payment")

    unmatched = df[df["match_status"] == "unmatched"]
    check(len(unmatched) == 0, f"no unmatched candidates ({len(unmatched)})")

    print("\nRecurring P2P (rent):")
    rent = find("9494012345")
    check(len(rent) == 3, f"rent appears 3 months (got {len(rent)})")
    check((rent["flags"].fillna("").str.contains("recurring")).all(),
          "rent flagged recurring")

    print("\nJune 2026 KPIs:")
    spend = df[(df["classification"] == "spend")
               & (df["txn_date"].str.startswith("2026-06"))]
    income = df[(df["classification"] == "income")
                & (df["txn_date"].str.startswith("2026-06"))]
    check(abs(spend["amount"].abs().sum() - EXPECTED_JUNE_SPEND) < 0.01,
          f"June spend = {EXPECTED_JUNE_SPEND}",
          f"got {spend['amount'].abs().sum()}")
    check(abs(income["amount"].sum() - EXPECTED_JUNE_INCOME) < 0.01,
          f"June income = {EXPECTED_JUNE_INCOME}",
          f"got {income['amount'].sum()}")

    print("\nDedup (re-import axis June):")
    axis_jun = [f for f in all_files() if f[0] == "axis_06_2026.csv"][0]
    name, text, account = axis_jun
    result = pipeline.run_import(Upload(name, text), account)
    check(result["inserted"] == 0, "re-import inserts 0",
          f"inserted {result['inserted']}")
    check(result["skipped"] == result["rows_parsed"],
          f"all {result['rows_parsed']} skipped as duplicates")

    print("\nCredit Card Persistence & Limit Updates:")
    sid = db.save_cc_statement({
        "card_name": "Test Axis Card",
        "card_last4": "9788",
        "statement_date": "2026-07-20",
        "due_date": "2026-08-14",
        "total_due": 22702.23,
        "min_due": 22702.23,
        "credit_limit": 516000.0,
        "available_limit": 92554.29,
        "cash_limit": 0.0,
        "reward_points_balance": 0.0,
        "source_file": "test.pdf"
    })
    check(bool(sid), "save_cc_statement succeeds")
    cc_stmts = db.load_cc_statements()
    check(len(cc_stmts) == 1, "load_cc_statements returns 1 row")
    check(cc_stmts.iloc[0]["credit_limit"] == 516000.0, "credit_limit preserved correctly")

    db.update_cc_limits("Test Axis Card", card_last4="9788", available_limit=95000.0)
    cc_stmts_up = db.load_cc_statements()
    check(cc_stmts_up.iloc[0]["available_limit"] == 95000.0, "update_cc_limits correctly updates available_limit")

    # Upsert CC EMIs
    ins_emi, _ = db.upsert_cc_emis([{
        "statement_id": sid,
        "card_name": "Test Axis Card",
        "card_last4": "9788",
        "merchant_name": "Amazon EMI",
        "loan_amount": 30000.0,
        "monthly_emi": 2500.0,
        "total_tenure": 12,
        "paid_tenure": 4,
        "remaining_tenure": 8,
        "source_file": "test.pdf"
    }])
    check(ins_emi == 1, "upsert_cc_emis inserts 1 EMI")
    emis = db.load_cc_emis()
    check(len(emis) == 1 and emis.iloc[0]["remaining_tenure"] == 8, "load_cc_emis retrieves active EMI")

    print("\nBank Loans CRUD & Progress Tracker:")
    lid = db.upsert_bank_loan({
        "loan_name": "Test Kisetsu Loan",
        "lender": "Kisetsu Saison Finance",
        "account": "axis",
        "monthly_emi": 5592.0,
        "total_loan_amount": 132730.0,
        "total_tenure": 30,
        "paid_tenure": 26,
        "remaining_tenure": 4,
        "remaining_principal": 22368.0,
        "match_keyword": "KISETSU",
        "match_amount": 5592.0,
        "debit_day": 3,
        "notes": "Test notes"
    })
    check(bool(lid), "upsert_bank_loan succeeds")
    loans = db.load_bank_loans()
    check(len(loans) == 1, "load_bank_loans returns 1 loan")
    check(loans.iloc[0]["remaining_tenure"] == 4, "loan remaining_tenure is 4")
    check(loans.iloc[0]["remaining_principal"] == 22368.0, "loan remaining_principal is 22368.0")

    del_ok = db.delete_bank_loan(lid)
    check(del_ok, "delete_bank_loan succeeds")
    loans_after = db.load_bank_loans()
    check(len(loans_after) == 0, "load_bank_loans returns 0 after deletion")

    print("\nDatabase Integrity & WAL Mode:")
    conn = db.connect()
    journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    check(journal.lower() == "wal", f"SQLite journal_mode is WAL (got {journal})")
    conn.close()

    print("\nLiquidity Forecast & Simulator Engine:")
    from finance.forecast import liquidity
    sim = liquidity.simulate_cashflow(start_date="2026-08-21", horizon_days=30)
    check("daily_df" in sim, "simulate_cashflow returns daily_df")
    check(len(sim["daily_df"]) == 31, "simulate_cashflow returns 31 daily projection points")
    check("recommended_transfers" in sim, "simulate_cashflow computes transfer recommendations")
    
    # What-if scenario test
    sim_whatif = liquidity.simulate_cashflow(
        start_date="2026-08-21", horizon_days=30,
        custom_expenses=[{"title": "Test Laptop Purchase", "amount": 75000.0, "date": "2026-08-25", "account": "axis"}]
    )
    whatif_diff = sim["summary"]["ending_liquid"] - sim_whatif["summary"]["ending_liquid"]
    check(abs(whatif_diff - 75000.0) < 1.0, "what-if discretionary expense accurately reflects on ending liquidity (-₹75,000)")

    print("\nEmail & PDF Statement Ingestion Engine:")
    from finance.ingest import email_sync, pdf_parsers
    card_detected = email_sync.detect_card_from_meta("alerts@axisbank.com", "Axis Bank Credit Card e-Statement")
    check(card_detected == "Axis Bank Credit Card", f"detect_card_from_meta detects Axis (got {card_detected})")
    
    # PDF bank detection test
    from tests.test_pdf_ingest import make_test_pdf
    pdf_axis = make_test_pdf(["AXIS BANK LIMITED", "MONTHLY ACCOUNT STATEMENT"])
    pdf_detected = pdf_parsers.detect_pdf_account(pdf_axis)
    check(pdf_detected == "axis", f"detect_pdf_account accurately detects Axis from PDF (got {pdf_detected})")

    print("\nReconciliation & Smart Matching Upgrade:")
    # 1. Manual pairing persistence
    m_rows = [
        {
            "account": "axis", "txn_date": "2026-06-01", "description": "MANUAL CC BILL",
            "amount": -14500.0, "classification": config.CLASSIFICATION_CC_PAYMENT,
            "category": "Credit Card"
        },
        {
            "account": "axis", "txn_date": "2026-06-28", "description": "UPI/ASHWIN LATE",
            "amount": 14500.0, "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
            "category": "Ashwin"
        }
    ]
    db.upsert_many(m_rows)
    d_id, c_id = m_rows[0]["id"], m_rows[1]["id"]
    db.manual_pair(d_id, [c_id])
    pipeline.reconcile()
    d_check = db.load_all()
    check(d_check[d_check["id"] == d_id].iloc[0]["match_status"] == "manual_matched", "manual pair preserved across auto-reconcile")
    
    # 2. Unpair
    db.manual_unpair(d_id)
    d_unpaired = db.load_all()
    check(d_unpaired[d_unpaired["id"] == d_id].iloc[0]["match_status"] == "unmatched", "manual unpair resets to unmatched")

    # 3. Tolerance matching (±₹1.00)
    tol_rows = [
        {
            "account": "axis", "txn_date": "2026-06-05", "description": "CC BILL DRIFT",
            "amount": -7999.40, "classification": config.CLASSIFICATION_CC_PAYMENT,
            "category": "Credit Card"
        },
        {
            "account": "axis", "txn_date": "2026-06-06", "description": "UPI/ASHWIN DRIFT",
            "amount": 8000.0, "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
            "category": "Ashwin"
        }
    ]
    db.upsert_many(tol_rows)
    pipeline.reconcile()
    tol_check = db.load_all()
    check(tol_check[tol_check["id"] == tol_rows[0]["id"]].iloc[0]["match_status"] == "matched", "drift tolerance (±₹1.00) pairs successfully")

    # 4. Split deposit matching
    split_rows = [
        {
            "account": "axis", "txn_date": "2026-06-10", "description": "CC BILL SPLIT TARGET",
            "amount": -22000.0, "classification": config.CLASSIFICATION_CC_PAYMENT,
            "category": "Credit Card"
        },
        {
            "account": "axis", "txn_date": "2026-06-11", "description": "ASHWIN PART A",
            "amount": 10000.0, "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
            "category": "Ashwin"
        },
        {
            "account": "axis", "txn_date": "2026-06-12", "description": "ASHWIN PART B",
            "amount": 12000.0, "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
            "category": "Ashwin"
        }
    ]
    db.upsert_many(split_rows)
    pipeline.reconcile()
    print("\nPrecision Math & Integer Paise Engine:")
    from finance.ui.format import rupees_to_paise, paise_to_rupees, inr_paise
    check(rupees_to_paise(0.29) == 29, "rupees_to_paise handles binary floating drift (0.29 -> 29)")
    check(rupees_to_paise(19.99) == 1999, "rupees_to_paise handles 19.99 -> 1999")
    check(paise_to_rupees(12345) == 123.45, "paise_to_rupees handles 12345 -> 123.45")
    check(inr_paise(15000000) == "₹1,50,000", "inr_paise formats Indian digits correctly")
    
    # Check that rows in DB have amount_paise populated
    all_df = db.load_all()
    check(all_df["amount_paise"].notna().all(), "every row has amount_paise integer populated")
    check((all_df["amount_paise"] == (all_df["amount"] * 100).round().astype(int)).all(), "amount_paise exactly matches amount * 100")

    print("\nConversation Logging & History Engine:")
    test_sid = "test-run-session"
    m_u = db.save_chat_message(test_sid, "user", "What is my total loan liability?", agent_mode="Master Financial AI")
    m_a = db.save_chat_message(test_sid, "assistant", "Your remaining loan balance is ₹22,368.", agent_mode="Master Financial AI")
    check(bool(m_u and m_a), "save_chat_message persists user and assistant turns")
    
    sess_list = db.load_chat_sessions()
    target_sess = [s for s in sess_list if s["session_id"] == test_sid]
    check(len(target_sess) == 1, "load_chat_sessions finds newly created session")
    check(target_sess[0]["session_title"] == "What is my total loan liability?", "session_title is automatically derived from first user question")
    check(target_sess[0]["message_count"] == 2, "session message_count is accurate (got 2)")
    
    sess_msgs = db.load_chat_messages(test_sid)
    check(len(sess_msgs) == 2 and sess_msgs[0]["role"] == "user" and sess_msgs[1]["role"] == "assistant", "load_chat_messages returns dialogue in order")
    
    search_res = db.search_chat_messages("liability")
    check(len(search_res) >= 1 and any(r["session_id"] == test_sid for r in search_res), "search_chat_messages finds turn by substring match")
    
    exp_md = db.export_chat_markdown(test_sid)
    check("Financial AI Conversation Transcript" in exp_md and "₹22,368" in exp_md, "export_chat_markdown renders complete transcript")
    
    db.delete_chat_session(test_sid)
    after_del = [s for s in db.load_chat_sessions() if s["session_id"] == test_sid]
    check(len(after_del) == 0, "delete_chat_session removes conversation completely")

    print("\nRewards & Miles Optimizer Engine:")
    from finance.rewards import evaluate_card_portfolio, optimize_flight_booking
    from finance.agent.master_tools import recommend_points_redemption

    # 1. Rewards ledger CRUD
    db.upsert_card_reward({
        "card_id": "test_axis_atlas",
        "card_name": "Axis Bank Credit Card",
        "card_variant": "Axis Atlas",
        "card_last4": "9788",
        "points_balance": 25000.0,
        "source": "user_manual"
    })
    r_df = db.load_card_rewards()
    check(len(r_df) >= 1 and any(r["card_id"] == "test_axis_atlas" for _, r in r_df.iterrows()), "upsert_card_reward persists points and variant")

    # 2. Portfolio valuation
    port_res = evaluate_card_portfolio(r_df)
    check(port_res["total_points"] >= 25000, "evaluate_card_portfolio calculates total points correctly")
    check(port_res["total_optimal_val_inr"] > port_res["total_baseline_val_inr"], "portfolio unlocks significant uplift over baseline cashback")

    # 3. Flight booking optimization
    fl_res = optimize_flight_booking("India ⇄ Singapore / SE Asia", "Economy", 28000, r_df)
    check(fl_res["top_award"] is not None and fl_res["top_award"]["has_enough"] is True, "flight booking optimizer recommends top award seat with sufficient points")
    check(fl_res["best_cash_card"]["flight_earn_rate_pct"] >= 4.0, "optimizer identifies accelerated return card for cash bookings")

    # 4. Agent tool integration
    tool_reply = recommend_points_redemption.invoke({"query": "flight to Singapore"})
    check("Rewards & Miles Optimization" in tool_reply and "Axis Atlas" in tool_reply, "recommend_points_redemption agent tool returns authoritative strategic advice")

    # Cleanup test card
    db.delete_card_reward("test_axis_atlas")

    print("\nPhase 1: User Profile & Security Hardening:")
    from tests.test_profile_and_security import (
        test_profile_loading, test_security_masking,
        test_security_html_sanitization, test_privacy_modes
    )
    test_profile_loading(); check(True, "user profile loads dynamically without source-code hardcoding")
    test_security_masking(); check(True, "account identifiers masked to last 4 digits")
    test_security_html_sanitization(); check(True, "HTML content sanitized to prevent injection")
    test_privacy_modes(); check(True, "privacy modes enforce LOCAL and CLOUD_AI constraints")

    print("\nPhase 2: Canonical Ledger, Money & Account Model:")
    from tests.test_canonical_ledger import (
        test_exact_money_class, test_accounts_model,
        test_canonical_ledger_sync, test_audit_and_provenance
    )
    test_exact_money_class(); check(True, "Money class maintains exact integer paise arithmetic")
    test_accounts_model(); check(True, "accounts model persists accounts with ownership & institution")
    test_canonical_ledger_sync(); check(True, "sync_canonical_ledger syncs transactions to canonical_events")
    test_audit_and_provenance(); check(True, "audit_events and provenance tracking recorded accurately")

    print("\nPhase 3: Entity Resolution & Database Classification Rules:")
    from tests.test_entity_resolution import (
        test_entity_resolver, test_rule_engine_evaluation, test_db_rule_persistence
    )
    test_entity_resolver(); check(True, "entity resolver recognizes Swiggy, Uber, BigBasket, Amazon")
    test_rule_engine_evaluation(); check(True, "rule engine evaluates salary, rent, and manual overrides")
    test_db_rule_persistence(); check(True, "classification_rules persist and prioritize in SQLite")

    print("\nPhase 4: Multi-Factor Reconciliation, Review Queue & Statement Validation:")
    from tests.test_reconciliation_and_review import (
        test_reconciliation_scoring, test_review_queue_lifecycle, test_statement_validation_math
    )
    test_reconciliation_scoring(); check(True, "multi-factor candidate scoring evaluates amount, date & direction")
    test_review_queue_lifecycle(); check(True, "review queue lifecycle handles filing and resolution")
    test_statement_validation_math(); check(True, "statement balance validator computes exact variance in paise")

    print("\nPhase 5: TimeScopeService, Deterministic Financial Metrics & Liabilities:")
    from tests.test_timescope_and_metrics import (
        test_timescope_service, test_metrics_cash_flow_and_investment_separation,
        test_metrics_liquid_balances_and_net_worth, test_recurring_and_anomalies
    )
    test_timescope_service(); check(True, "TimeScopeService resolves explicit date boundaries & coverage")
    test_metrics_cash_flow_and_investment_separation(); check(True, "metrics engine separates investments from consumption spend")
    test_metrics_liquid_balances_and_net_worth(); check(True, "metrics engine calculates liquid assets and net worth accurately")
    test_recurring_and_anomalies(); check(True, "recurring obligations and anomaly detection engines execute cleanly")

    print("\nPhase 6: AI Runtime, Typed Tool Outputs & Guardrails:")
    from tests.test_ai_runtime_and_guardrails import (
        test_local_privacy_mode_deterministic_response, test_fact_verification
    )
    test_local_privacy_mode_deterministic_response(); check(True, "LOCAL privacy mode returns deterministic response without cloud LLM")
    test_fact_verification(); check(True, "fact verification flags unverified numerical claims")

    print(f"\n===== {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
