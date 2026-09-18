import unittest

from jarvis.benchmark import run_fake
from jarvis.capabilities import BENCHMARK_REQUIRED, resolve
from jarvis.firewall import validate_proposal
from jarvis.runtime import Mode, build_plan, respond

from test_action_contract import LIVE_ROWS
from jarvis.action_contract import build_contract


def contract():
    return build_contract(LIVE_ROWS, source="postgres:action_contract")


class BootstrapTests(unittest.TestCase):
    def test_deterministic_fast_route(self):
        result = respond("bugunku sirket gundemi nedir?", {"agenda": []})
        self.assertEqual(result["mode"], Mode.FAST.value)
        self.assertEqual(result["route"], "deterministic-local-first")
        self.assertFalse(result["external_action_executed"])

    def test_risky_action_is_proposed(self):
        self.assertEqual(build_plan("send whatsapp message").status, "PROPOSED")

    def test_unknown_action_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown internal action"):
            validate_proposal("RUN_SHELL", {}, contract())

    def test_forbidden_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "forbidden payload"):
            validate_proposal("CUSTOMER_REPLY_DRAFT", {"shell": "whoami"}, contract())

    def test_known_action_stays_proposed(self):
        result = validate_proposal("CUSTOMER_REPLY_DRAFT", {"text": "draft"}, contract())
        self.assertEqual(result["status"], "PROPOSED")
        # Phase 2D: the canonical name now comes from the database contract.
        self.assertEqual(result["action_type"], "DRAFT_CUSTOMER_REPLY")

    def test_capability_gap_creates_benchmark_plan(self):
        self.assertEqual(resolve("new_tool")["next"], BENCHMARK_REQUIRED)

    def test_fake_benchmark(self):
        self.assertEqual(run_fake(10)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
