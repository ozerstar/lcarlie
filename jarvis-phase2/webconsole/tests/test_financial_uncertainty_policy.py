import unittest
from unittest.mock import patch
from jarvis import model_layer as ml


class FinancialPolicyTests(unittest.TestCase):
    def test_synthesis_default_and_custom_prompts_include_policy(self):
        router = ml.ModelRouter()
        class Captured(Exception):
            pass
        for system in (None, "Synthetic chat"):
            with self.subTest(system=system), patch.object(router, "provider_states", return_value={}), \
                 patch.object(router, "generate", side_effect=Captured) as generate, \
                 patch("jarvis.improvement.Store.context", return_value=""):
                with self.assertRaises(Captured):
                    router.synthesize("synthetic", [{"ref": "fixture", "summary": "VAT unknown"}], system=system)
                self.assertIn(ml.FINANCIAL_UNCERTAINTY_POLICY, generate.call_args.args[0][0]["content"])

    def test_streaming_prompt_includes_same_policy(self):
        router = ml.ModelRouter()
        with patch.object(router, "_stream_text_raw", return_value=iter(["Bu test için gerekli olan veriler henüz tam değil."])) as stream:
            list(router.stream_text("synthetic", "Synthetic system"))
        self.assertIn(ml.FINANCIAL_UNCERTAINTY_POLICY, stream.call_args.args[1])

    def test_policy_requires_all_costs_and_explicit_assumptions(self):
        for required in ("varsayımları rakamdan önce", "genel gider", "nedensellik", "katkı/kâr değil"):
            self.assertIn(required, ml.FINANCIAL_UNCERTAINTY_POLICY)
