"""Unit tests for automated Email Statement Ingestion Engine."""

import unittest
from finance.ingest import email_sync


class TestEmailSync(unittest.TestCase):
    def test_email_client_initialization(self):
        client = email_sync.EmailSyncClient(provider="gmail", username="test@gmail.com", password="app password 1234")
        self.assertEqual(client.host, "imap.gmail.com")
        self.assertEqual(client.port, 993)
        self.assertEqual(client.username, "test@gmail.com")
        self.assertEqual(client.password, "apppassword1234") # spaces stripped

    def test_card_detection_from_meta(self):
        self.assertEqual(
            email_sync.detect_card_from_meta("alerts@axisbank.com", "Your Axis Bank Credit Card e-Statement"),
            "Axis Bank Credit Card"
        )
        self.assertEqual(
            email_sync.detect_card_from_meta("statement@americanexpress.com", "Your Amex Statement is Ready"),
            "American Express"
        )
        self.assertEqual(
            email_sync.detect_card_from_meta("ebills@idfcfirstbank.com", "IDFC FIRST Credit Card Monthly Bill"),
            "IDFC FIRST Credit Card"
        )
        self.assertEqual(
            email_sync.detect_card_from_meta("scapia@federalbank.co.in", "Scapia Credit Card e-Statement"),
            "Scapia Federal Credit Card"
        )
        self.assertEqual(
            email_sync.detect_card_from_meta("yesbank@yesbank.in", "YES Bank Card e-Statement for Aug 2026"),
            "YES Bank Credit Card"
        )

    def test_sync_without_credentials_fails_gracefully(self):
        res = email_sync.sync_statements_from_email(provider="gmail", username="", password="")
        self.assertFalse(res["success"])
        self.assertIn("Missing username or app password", res["message"])


if __name__ == "__main__":
    unittest.main()
