"""Test suite for Credit Card PDF Statement Parser and Credit Card Agent Tools."""
from __future__ import annotations

import unittest
import os
import tempfile
import pandas as pd

from finance import db
from finance.agent import cc_tools


class TestCreditCardAgent(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test_cc_finance.db")
        db.set_db_path(self.db_path)
        db.init_db()

    def test_cc_db_and_tools(self):
        # 1. Insert synthetic CC statement
        stmt_info = {
            "card_name": "HDFC Regalia",
            "card_last4": "4321",
            "statement_date": "2026-08-10",
            "due_date": "2026-08-30",
            "total_due": 45800.0,
            "min_due": 2300.0,
            "reward_points_earned": 1250.0,
            "reward_points_balance": 8450.0,
            "finance_charges": 0.0,
            "source_file": "hdfc_regalia_aug2026.pdf",
        }
        sid = db.save_cc_statement(stmt_info)
        self.assertTrue(bool(sid))

        # 2. Insert synthetic CC transactions
        cc_txns = [
            {
                "statement_id": sid,
                "card_name": "HDFC Regalia",
                "card_last4": "4321",
                "txn_date": "2026-08-02",
                "description": "SWIGGY FOOD ORDER NOIDA",
                "amount": 650.0,
                "category": "Food & Dining",
                "counterparty": "SWIGGY",
                "source_file": "hdfc_regalia_aug2026.pdf",
            },
            {
                "statement_id": sid,
                "card_name": "HDFC Regalia",
                "card_last4": "4321",
                "txn_date": "2026-08-05",
                "description": "RELIANCE DIGITAL ELECTRONICS",
                "amount": 24500.0,
                "category": "Shopping",
                "counterparty": "RELIANCE",
                "source_file": "hdfc_regalia_aug2026.pdf",
            },
            {
                "statement_id": sid,
                "card_name": "HDFC Regalia",
                "card_last4": "4321",
                "txn_date": "2026-08-08",
                "description": "ANNUAL MEMBERSHIP FEE RE-INSTATEMENT",
                "amount": 1500.0,
                "category": "Fee",
                "counterparty": "HDFC",
                "source_file": "hdfc_regalia_aug2026.pdf",
            },
        ]
        inserted, skipped = db.upsert_cc_transactions(cc_txns)
        self.assertEqual(inserted, 3)

        # 3. Test db loaders
        stmts_df = db.load_cc_statements()
        self.assertEqual(len(stmts_df), 1)
        self.assertEqual(stmts_df.iloc[0]["total_due"], 45800.0)

        txns_df = db.load_cc_transactions()
        self.assertEqual(len(txns_df), 3)

        # 4. Test cc_tools
        sum_res = cc_tools.cc_statement_summary.invoke({})
        self.assertIn("HDFC Regalia", sum_res)
        self.assertIn("45,800", sum_res)

        pts_res = cc_tools.cc_reward_points.invoke({})
        self.assertIn("8,450", pts_res)

        fee_res = cc_tools.cc_fee_tracker.invoke({})
        self.assertIn("1,500", fee_res)

        spend_res = cc_tools.cc_card_spend.invoke({"card_name": "HDFC"})
        self.assertIn("26,650", spend_res)

        line_res = cc_tools.cc_line_items.invoke({"merchant": "Swiggy"})
        self.assertIn("650", line_res)


if __name__ == "__main__":
    unittest.main()
