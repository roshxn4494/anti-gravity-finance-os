"""Tests for word-boundary token matching and classification priority ordering."""
from __future__ import annotations

import unittest
from finance import config
from finance.classify import categories, rules


class TestClassification(unittest.TestCase):

    def test_no_false_positive_substrings(self):
        # "FLAT" should not match inside "FLAT 50% DISCOUNT AT SUPERMARKET"
        cat = categories.categorize("FLAT 50% DISCOUNT AT SUPERMARKET")
        self.assertNotEqual(cat, "Rent", "FLAT discount should not be categorized as Rent")

        # "GAME" inside "BIGAME" or generic text
        cat_game = categories.categorize("PAYMENT TO BIGAME INC")
        self.assertIsNone(cat_game, "Partial word BIGAME should not match GAME")

    def test_longest_specific_keyword_wins(self):
        # "AMAZON PRIME" should categorize as Entertainment, beating shorter "AMAZON" (Shopping)
        cat = categories.categorize("UPI/AMAZON PRIME VIDEO/MEMBER")
        self.assertEqual(cat, "Entertainment", "AMAZON PRIME should match Entertainment over AMAZON")

        # "BURGER KING" should match Food & Dining
        cat_bk = categories.categorize("POS/BURGER KING STORE/BANGALORE")
        self.assertEqual(cat_bk, "Food & Dining")

    def test_investment_priority_over_fees(self):
        # Narration containing both an investment keyword and fee keyword (e.g. GST)
        txn = {
            "description": "ACH-DR-TP ACH INDIANESIGN GST CHARGES",
            "amount": -1000.0,
            "account": "axis",
        }
        rules.classify_txn(txn)
        self.assertEqual(txn["classification"], config.CLASSIFICATION_INVESTMENT,
                         "Investment SIP with GST should be classified as investment, not fee")
        self.assertEqual(txn["category"], "Investments")

    def test_salary_protection_from_override(self):
        # If an override exists for employer counterparty, credit salary should still be Income
        overrides = {"counterparty:TCS": {"classification": "spend", "category": "Shopping"}}
        txn = {
            "description": "SALARY CREDIT FOR AUGUST TCS",
            "amount": 112729.0,
            "account": "axis",
        }
        rules.classify_txn(txn, overrides=overrides)
        self.assertEqual(txn["classification"], config.CLASSIFICATION_INCOME,
                         "Salary credits must be protected from counterparty spend overrides")
        self.assertEqual(txn["category"], "Salary")


if __name__ == "__main__":
    unittest.main()
