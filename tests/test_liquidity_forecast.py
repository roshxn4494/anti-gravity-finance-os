"""Unit tests for the 30-Day Proactive Liquidity & Cashflow Simulator Engine."""

import unittest
from datetime import date
from finance.forecast import liquidity
from finance import db


class TestLiquidityForecast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.set_db_path("data/finance.db")

    def test_simulate_cashflow_structure(self):
        res = liquidity.simulate_cashflow(start_date="2026-08-21", horizon_days=30)
        self.assertIn("daily_df", res)
        self.assertIn("events", res)
        self.assertIn("alerts", res)
        self.assertIn("recommended_transfers", res)
        self.assertIn("summary", res)

        df = res["daily_df"]
        self.assertEqual(len(df), 31) # 30 days + start day
        self.assertIn("axis_balance", df.columns)
        self.assertIn("kotak_total", df.columns)
        self.assertIn("sbi_balance", df.columns)
        self.assertIn("total_liquid", df.columns)

    def test_salary_and_ashwin_inflows_scheduled(self):
        res = liquidity.simulate_cashflow(start_date="2026-08-21", horizon_days=30)
        events = res["events"]
        
        salary_events = [e for e in events if e["type"] == "salary"]
        self.assertGreaterEqual(len(salary_events), 1)
        self.assertGreater(salary_events[0]["amount"], 100000.0)

        ashwin_events = [e for e in events if e["type"] == "friend_deposit"]
        self.assertGreaterEqual(len(ashwin_events), 1)
        self.assertGreater(ashwin_events[0]["amount"], 90000.0)

    def test_smart_fd_auto_sweep_preserves_solvency(self):
        res = liquidity.simulate_cashflow(
            start_date="2026-08-21",
            horizon_days=30,
            daily_burn=1000.0
        )
        df = res["daily_df"]
        # Total liquid net worth remains positive throughout
        self.assertTrue((df["total_liquid"] > 0).all())


if __name__ == "__main__":
    unittest.main()
