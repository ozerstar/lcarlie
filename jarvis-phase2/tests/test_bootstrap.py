import unittest

from jarvis.benchmark import run_fake
from jarvis.capabilities import resolve
from jarvis.firewall import validate_proposal
from jarvis.runtime import Mode, build_plan, respond


class BootstrapTests(unittest.TestCase):
    def test_deterministic_fast_route(self):
        result = respond("bugunku sirket gundemi nedir?", {"agenda": []})
        self.assertEqual(result["mode"], Mode.FAST.value)
        self.assertEqual(result["route"], "deterministic-local-first")
        self.assertFalse(result["external_action_executed"])

    def test_risky_action_is_proposed(self):
        self.assertEqual(build_plan("send whatsapp message").status, "PROPOSED")

    def test_unknown_action_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown action"):
            validate_proposal("RUN_SHELL", {})

    def test_forbidden_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "forbidden payload"):
            validate_proposal("CRM_REPLY_DRAFT", {"shell": "whoami"})

    def test_known_action_stays_proposed(self):
        result = validate_proposal("CRM_REPLY_DRAFT", {"text": "draft"})
        self.assertEqual(result["status"], "PROPOSED")

    def test_capability_gap_creates_benchmark_plan(self):
        self.assertEqual(resolve("new_tool")["next"], "benchmark_plan")

    def test_fake_benchmark(self):
        self.assertEqual(run_fake(10)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
