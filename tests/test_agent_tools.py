"""Unit tests for new finance agent tools: fuzzy category resolution, merchant summary,
investment tracking, cashflow breakdown, month comparison, and relative date scoping.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finance import db, pipeline
from finance.agent import tools
from sample_data import all_files


class Upload:
    def __init__(self, name: str, text: str):
        self.name = name
        self._data = text.encode()

    def getvalue(self):
        return self._data


class TestAgentTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        db.set_db_path(os.path.join(tmp, "test_agent_tools.db"))
        db.init_db()

        for name, text, account in all_files():
            pipeline.run_import(Upload(name, text), account)

    def test_fuzzy_category_spend(self):
        # 'food' should map to 'Food & Dining'
        res_food = tools.category_spend.invoke({"category": "food", "month": "2026-06"})
        self.assertIn("Spend in Food & Dining", res_food)

        # 'travel' should map to 'Transport & Fuel'
        res_travel = tools.category_spend.invoke({"category": "travel", "month": "2026-06"})
        self.assertIn("Spend in Transport & Fuel", res_travel)

    def test_merchant_summary(self):
        res_swiggy = tools.merchant_summary.invoke({"merchant": "Swiggy"})
        self.assertIn("Merchant Summary for 'Swiggy'", res_swiggy)
        self.assertIn("Total Spent", res_swiggy)

    def test_investment_summary(self):
        res_inv = tools.investment_summary.invoke({"month": ""})
        # Should execute cleanly without error
        self.assertTrue("Investments" in res_inv or "No investment" in res_inv)

    def test_cashflow_breakdown(self):
        res_cf = tools.cashflow_breakdown.invoke({"month": "2026-06"})
        self.assertIn("Total Outflow", res_cf)
        self.assertIn("Where your money went", res_cf)

    def test_compare_months(self):
        res_comp = tools.compare_months.invoke({"month1": "2026-05", "month2": "2026-06"})
        self.assertIn("Comparison:", res_comp)
        self.assertIn("Spend:", res_comp)

    def test_relative_date_scoping(self):
        res_last = tools.spend_total.invoke({"month": "last_month"})
        self.assertIn("Real spend", res_last)

        res_3m = tools.spend_total.invoke({"month": "last_3_months"})
        self.assertIn("Real spend", res_3m)


if __name__ == "__main__":
    unittest.main()
