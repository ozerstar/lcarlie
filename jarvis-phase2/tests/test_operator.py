"""Minimum human proposal surface: authority separation, structural checks."""
import unittest
from unittest.mock import patch

from jarvis.operator import OperatorSession


class OperatorAuthorityTests(unittest.TestCase):
    def test_list_runs_as_human_approver_never_ai_writer(self):
        # core.ai_get_pending_actions() is granted to human_approver only
        # (verified against the live database); ai_reader has no access.
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[]) as run_mock:
            session.list_pending()
        sql = run_mock.call_args[0][0]
        self.assertIn("SET SESSION AUTHORIZATION human_approver", sql)
        self.assertNotIn("ai_writer", sql)
        self.assertIn("ROLLBACK", sql)

    def test_inspect_finds_a_pending_action_by_id(self):
        session = OperatorSession(host=None)
        with patch.object(session, "list_pending",
                          return_value=[{"action_id": 5}, {"action_id": 7}]):
            self.assertEqual(session.inspect(7), {"action_id": 7})
            self.assertIsNone(session.inspect(99))

    def test_decide_runs_as_human_approver_only_never_ai_writer(self):
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[]) as run_mock:
            result = session.decide(1, "APPROVED", "test reason", "a" * 32)
        sql = run_mock.call_args[0][0]
        self.assertIn("SET SESSION AUTHORIZATION human_approver", sql)
        self.assertNotIn("ai_writer", sql)
        self.assertIn("COMMIT", sql)
        self.assertTrue(result["confirmed"])  # empty pending-list result = decided

    def test_decide_reports_unconfirmed_if_still_pending(self):
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[{"action_id": 1}]):
            result = session.decide(1, "APPROVED", "test reason", "a" * 32)
        self.assertFalse(result["confirmed"])
        self.assertTrue(result["still_pending"])

    def test_displayed_fingerprint_uses_bound_company_decision(self):
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[]) as run_mock:
            session.decide(5, "APPROVED", "reviewed", expected_hash="a" * 32)
        sql = run_mock.call_args[0][0]
        self.assertIn("core.jarvis_decide_company_action", sql)
        self.assertIn("'" + "a" * 32 + "'", sql)
        with self.assertRaises(ValueError):
            session.decide(5, "APPROVED", "reviewed", expected_hash="wrong")

    def test_create_task_runs_as_human_approver_never_ai_writer(self):
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[42]) as run_mock:
            result = session.create_task("HUMAN_REVIEW_REQUEST", "demo-1")
        sql = run_mock.call_args[0][0]
        self.assertIn("SET SESSION AUTHORIZATION human_approver", sql)
        self.assertNotIn("ai_writer", sql)
        self.assertEqual(result["idempotency_key"], "jarvis:HUMAN_REVIEW_REQUEST:demo-1")

    def test_decide_rejects_unknown_decision(self):
        session = OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.decide(1, "MAYBE", "reason", "a" * 32)

    def test_decide_requires_a_reason(self):
        session = OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.decide(1, "APPROVED", "", "a" * 32)
        with self.assertRaises(ValueError):
            session.decide(1, "APPROVED", "   ", "a" * 32)

    def test_create_task_rejects_unknown_intent(self):
        session = OperatorSession(host=None)
        with self.assertRaises(ValueError):
            session.create_task("DELETE_EVERYTHING", "x")

    def test_create_task_rejects_malformed_slug(self):
        session = OperatorSession(host=None)
        for bad_slug in ("with space", "semi;colon", "quote'here", "$(injection)", ""):
            with self.assertRaises(ValueError):
                session.create_task("HUMAN_REVIEW_REQUEST", bad_slug)

    def test_inspect_rejects_non_integer_action_id(self):
        session = OperatorSession(host=None)
        with self.assertRaises((ValueError, TypeError)):
            session.inspect("1; DROP TABLE core.ai_action_proposal")

    def test_decide_rejects_non_integer_action_id(self):
        session = OperatorSession(host=None)
        with self.assertRaises((ValueError, TypeError)):
            session.decide("1 OR 1=1", "APPROVED", "reason", "a" * 32)

    def test_reason_is_sql_escaped(self):
        session = OperatorSession(host=None)
        with patch.object(session, "_run", return_value=[{}]) as run_mock:
            session.decide(1, "APPROVED", "it's a test", "a" * 32)
        sql = run_mock.call_args[0][0]
        self.assertIn("it''s a test", sql)


if __name__ == "__main__":
    unittest.main()
