"""Unit tests for conversation logging, session management, and chat history."""
import os
import unittest
import tempfile
from finance import db


class TestChatHistory(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_finance.db")
        db.set_db_path(self.db_path)
        db.init_db()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load_chat_messages(self):
        sid = "sess-100"
        m1 = db.save_chat_message(sid, "user", "How much did I spend on dining?", agent_mode="Bank Specialist")
        m2 = db.save_chat_message(sid, "assistant", "You spent ₹14,200 on dining.", agent_mode="Bank Specialist")

        self.assertTrue(m1)
        self.assertTrue(m2)

        messages = db.load_chat_messages(sid)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "How much did I spend on dining?")
        self.assertEqual(messages[0]["agent_mode"], "Bank Specialist")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "You spent ₹14,200 on dining.")

    def test_session_listing_and_auto_title(self):
        sid = "sess-200"
        db.save_chat_message(sid, "user", "What are my upcoming loan EMIs?", agent_mode="Master Financial AI")
        db.save_chat_message(sid, "assistant", "Your next EMI is on 3rd.", agent_mode="Master Financial AI")

        sessions = db.load_chat_sessions()
        self.assertEqual(len(sessions), 1)
        s = sessions[0]
        self.assertEqual(s["session_id"], sid)
        self.assertEqual(s["session_title"], "What are my upcoming loan EMIs?")
        self.assertEqual(s["message_count"], 2)
        self.assertEqual(s["agent_mode"], "Master Financial AI")

    def test_search_chat_messages(self):
        sid1 = "sess-ashwin"
        db.save_chat_message(sid1, "user", "What is the total amount Ashwin has sent to me?", agent_mode="Master Financial AI")
        db.save_chat_message(sid1, "assistant", "Ashwin transferred ₹7,29,459 this year.", agent_mode="Master Financial AI")

        sid2 = "sess-swiggy"
        db.save_chat_message(sid2, "user", "How much on Swiggy?", agent_mode="Bank Specialist")
        db.save_chat_message(sid2, "assistant", "Swiggy total is ₹4,200.", agent_mode="Bank Specialist")

        matches = db.search_chat_messages("Ashwin")
        self.assertEqual(len(matches), 2)  # matches both user question & assistant answer
        self.assertEqual(matches[0]["session_id"], sid1)

        swiggy_matches = db.search_chat_messages("Swiggy")
        self.assertEqual(len(swiggy_matches), 2)

    def test_export_and_delete_session(self):
        sid = "sess-export"
        db.save_chat_message(sid, "user", "What is my credit limit?", agent_mode="Credit Card Specialist")
        db.save_chat_message(sid, "assistant", "Your total credit limit is ₹5,00,000.", agent_mode="Credit Card Specialist")

        md = db.export_chat_markdown(sid)
        self.assertIn("Financial AI Conversation Transcript", md)
        self.assertIn(sid, md)
        self.assertIn("What is my credit limit?", md)
        self.assertIn("₹5,00,000", md)

        # Delete session
        deleted = db.delete_chat_session(sid)
        self.assertTrue(deleted)
        self.assertEqual(len(db.load_chat_messages(sid)), 0)
        self.assertEqual(len(db.load_chat_sessions()), 0)


if __name__ == "__main__":
    unittest.main()
