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

    print(f"\n===== {PASS} passed, {FAIL} failed =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
