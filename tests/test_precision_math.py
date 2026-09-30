"""Test precision math and integer paise conversions.

Tests:
1. rupees_to_paise and paise_to_rupees accuracy on fractional float values.
2. In-memory & SQLite auto-backfill of amount_paise and balance_paise.
3. Matching engine running exact paise arithmetic with zero binary drift.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance import config, db, pipeline
from finance.ui.format import inr_paise, paise_to_rupees, rupees_to_paise


class TestPrecisionMath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_precision.db")
        db.set_db_path(self.db_path)
        db.init_db()

    def test_rupees_paise_conversion(self):
        # Standard values
        self.assertEqual(rupees_to_paise(1.0), 100)
        self.assertEqual(rupees_to_paise(0.50), 50)
        self.assertEqual(rupees_to_paise(123.45), 12345)
        self.assertEqual(rupees_to_paise(-25000.0), -2500000)

        # Tricky float binary rounding numbers
        self.assertEqual(rupees_to_paise(0.29), 29)
        self.assertEqual(rupees_to_paise(19.99), 1999)
        self.assertEqual(rupees_to_paise(0.07), 7)
        self.assertEqual(rupees_to_paise("1500.50"), 150050)
        self.assertEqual(rupees_to_paise(None), 0)

        # Inverse conversion
        self.assertEqual(paise_to_rupees(12345), 123.45)
        self.assertEqual(paise_to_rupees(-2500000), -25000.0)
        self.assertEqual(paise_to_rupees(0), 0.0)

        # inr_paise formatting
        self.assertEqual(inr_paise(15000000), "₹1,50,000")
        self.assertEqual(inr_paise(-50000), "-₹500")

    def test_db_paise_columns_and_backfill(self):
        # Insert row without amount_paise (simulating legacy data)
        conn = db.connect()
        with conn:
            conn.execute(
                """INSERT INTO transactions (id, account, txn_date, description, amount, classification)
                   VALUES ('legacy_txn', 'axis', '2026-06-01', 'GROCERY TEST', -499.75, 'spend')"""
            )
        conn.close()

        # Re-run init_db() to trigger backfill
        db.init_db()

        df = db.load_all()
        row = df[df["id"] == "legacy_txn"].iloc[0]
        self.assertEqual(row["amount_paise"], -49975)

    def test_upsert_stores_paise_automatically(self):
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-02",
                "description": "RESTAURANT PAYMENT",
                "amount": -1425.50,
                "balance": 85000.25,
                "classification": "spend",
                "category": "Food & Dining",
            }
        ]
        db.upsert_many(rows)
        tid = rows[0]["id"]

        df = db.load_all()
        row = df[df["id"] == tid].iloc[0]
        self.assertEqual(row["amount_paise"], -142550)
        self.assertEqual(row["balance_paise"], 8500025)

    def test_exact_paise_matching_with_drift(self):
        # 4999.50 debit <-> 5000.00 credit (difference 50 paise <= 100 paise tolerance)
        rows = [
            {
                "account": "axis",
                "txn_date": "2026-06-05",
                "description": "CC BILL PAYMENT",
                "amount": -4999.50,
                "classification": config.CLASSIFICATION_CC_PAYMENT,
                "category": "Credit Card",
            },
            {
                "account": "axis",
                "txn_date": "2026-06-06",
                "description": "UPI/ASHWIN",
                "amount": 5000.0,
                "classification": config.CLASSIFICATION_FRIEND_DEPOSIT,
                "category": "Ashwin",
            },
        ]
        db.upsert_many(rows)
        debit_id = rows[0]["id"]
        credit_id = rows[1]["id"]

        pipeline.reconcile()
        df = db.load_all()
        d_row = df[df["id"] == debit_id].iloc[0]
        self.assertEqual(d_row["match_status"], "matched")
        self.assertEqual(d_row["matched_with"], credit_id)


if __name__ == "__main__":
    unittest.main()
