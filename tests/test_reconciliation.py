"""Test reconciliation & smart matching functionality.

Tests:
1. Manual pairing persistence through pipeline.reconcile()
2. Manual unpairing
3. Amount drift tolerance (±₹1.00)
4. Split deposit matching (2 credits cleanly sum to 1 CC payment debit)
5. Re-apply auto-categorization without overriding manual counterparty rules
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance import config, db, pipeline


class TestReconciliation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_reconcile.db")
        db.set_db_path(self.db_path)
        db.init_db()

    def test_manual_pair_and_persistence(self):
        # Insert a CC payment and an Ashwin deposit with wide date gap (beyond auto window)
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-01",
                "description": "CREDIT CARD BILL PAYMENT",
                "amount": -25000.0,
                "classification": config.CLASSIFICATION_CC_PAYMENT,
                "category": "Credit Card",
                "counterparty": None,
                "flags": None,
                "match_status": "unmatched",
                "matched_with": None,
            },
            {
                "account": "axis",
                "txn_date": "2026-06-25",  # 24 days later - beyond auto window
                "description": "UPI/ASHWIN/SETTLEMENT",
                "amount": 25000.0,
                "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
                "category": "Ashwin",
                "counterparty": "ASHWIN",
                "flags": None,
                "match_status": "unmatched",
                "matched_with": None,
            },
        ]
        db.upsert_many(rows)
        debit_id = rows[0]["id"]
        credit_id = rows[1]["id"]

        # 1. Manual pair them
        paired = db.manual_pair(debit_id, [credit_id])
        self.assertTrue(paired)

        matched_pairs = db.load_matched_pairs()
        self.assertEqual(len(matched_pairs), 1)
        self.assertEqual(matched_pairs.iloc[0]["match_status"], "manual_matched")
        self.assertEqual(matched_pairs.iloc[0]["debit_id"], debit_id)
        self.assertEqual(matched_pairs.iloc[0]["credit_id"], credit_id)

        # 2. Run auto-reconciliation and verify manual match is NOT wiped out
        pipeline.reconcile()
        df = db.load_all()
        d_row = df[df["id"] == debit_id].iloc[0]
        c_row = df[df["id"] == credit_id].iloc[0]
        self.assertEqual(d_row["match_status"], "manual_matched")
        self.assertEqual(d_row["matched_with"], credit_id)
        self.assertEqual(c_row["match_status"], "manual_matched")
        self.assertEqual(c_row["matched_with"], debit_id)

        # 3. Test unpair
        unpaired = db.manual_unpair(debit_id)
        self.assertTrue(unpaired)
        df_after = db.load_all()
        d_after = df_after[df_after["id"] == debit_id].iloc[0]
        c_after = df_after[df_after["id"] == credit_id].iloc[0]
        self.assertEqual(d_after["match_status"], "unmatched")
        self.assertIsNone(d_after["matched_with"])
        self.assertEqual(c_after["match_status"], "unmatched")
        self.assertIsNone(c_after["matched_with"])

    def test_tolerance_matching(self):
        # 4999.50 debit <-> 5000.00 credit (difference 0.50 <= 1.00 tolerance)
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-05",
                "description": "CC BILL PAYMENT",
                "amount": -4999.50,
                "classification": config.CLASSIFICATION_CC_PAYMENT,
                "category": "Credit Card",
                "counterparty": None,
                "flags": None,
                "match_status": None,
                "matched_with": None,
            },
            {
                "account": "axis",
                "txn_date": "2026-06-06",
                "description": "UPI/ASHWIN",
                "amount": 5000.0,
                "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
                "category": "Ashwin",
                "counterparty": "ASHWIN",
                "flags": None,
                "match_status": None,
                "matched_with": None,
            },
        ]
        db.upsert_many(rows)
        debit_id = rows[0]["id"]
        credit_id = rows[1]["id"]

        pipeline.reconcile()
        df = db.load_all()
        d_row = df[df["id"] == debit_id].iloc[0]
        c_row = df[df["id"] == credit_id].iloc[0]
        self.assertEqual(d_row["match_status"], "matched")
        self.assertEqual(d_row["matched_with"], credit_id)
        self.assertEqual(c_row["match_status"], "matched")

    def test_split_deposit_matching(self):
        # 1 CC payment of 30,000 <-> 2 Ashwin deposits of 18,000 + 12,000 within 7 days
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-10",
                "description": "CC BILL PAYMENT",
                "amount": -30000.0,
                "classification": config.CLASSIFICATION_CC_PAYMENT,
                "category": "Credit Card",
                "counterparty": None,
                "flags": None,
                "match_status": None,
                "matched_with": None,
            },
            {
                "account": "axis",
                "txn_date": "2026-06-11",
                "description": "UPI/ASHWIN PART 1",
                "amount": 18000.0,
                "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
                "category": "Ashwin",
                "counterparty": "ASHWIN",
                "flags": None,
                "match_status": None,
                "matched_with": None,
            },
            {
                "account": "axis",
                "txn_date": "2026-06-12",
                "description": "UPI/ASHWIN PART 2",
                "amount": 12000.0,
                "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
                "category": "Ashwin",
                "counterparty": "ASHWIN",
                "flags": None,
                "match_status": None,
                "matched_with": None,
            },
        ]
        db.upsert_many(rows)
        debit_id = rows[0]["id"]
        credit1_id = rows[1]["id"]
        credit2_id = rows[2]["id"]

        pipeline.reconcile()
        df = db.load_all()
        d_row = df[df["id"] == debit_id].iloc[0]
        c1 = df[df["id"] == credit1_id].iloc[0]
        c2 = df[df["id"] == credit2_id].iloc[0]

        self.assertEqual(d_row["match_status"], "matched")
        self.assertIn(credit1_id, d_row["matched_with"])
        self.assertIn(credit2_id, d_row["matched_with"])
        self.assertEqual(c1["match_status"], "matched")
        self.assertEqual(c1["matched_with"], debit_id)
        self.assertEqual(c2["match_status"], "matched")
        self.assertEqual(c2["matched_with"], debit_id)

    def test_reclassify_all_unoverridden(self):
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-15",
                "description": "SWIGGY BANGALORE IN",
                "amount": -450.0,
                "classification": "spend",
                "category": "Miscellaneous",  # wrong category
                "counterparty": "SWIGGY",
                "flags": None,
                "match_status": None,
                "matched_with": None,
            }
        ]
        db.upsert_many(rows)
        swiggy_id = rows[0]["id"]

        updated_count = pipeline.reclassify_all_unoverridden()
        self.assertGreaterEqual(updated_count, 1)

        df = db.load_all()
        s_row = df[df["id"] == swiggy_id].iloc[0]
        self.assertEqual(s_row["category"], "Food & Dining")


if __name__ == "__main__":
    unittest.main()
