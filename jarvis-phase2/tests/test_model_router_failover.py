"""The GPU box is a desktop, so it is allowed to disappear.

It answers a knowledge-backed question in ~6 s where the server's four cores
take ~60 s, which is why it goes first. It is also switched off at night,
which is why it cannot be the only one. These tests pin the consequence: when
it is gone the server's own model answers, and nothing reaches the external
provider just because a desktop was powered down.
"""
import unittest

from jarvis.model_layer import (AdapterState, ModelRouter, ModelUnavailable,
                                TIER_EXTERNAL, TIER_GPU, TIER_LOCAL)


class _Provider:
    """Minimal stand-in: a tier, a health state, and an answer."""

    def __init__(self, name, tier, state=AdapterState.AVAILABLE, fails=False):
        self.name = name
        self.tier = tier
        self._state = state
        self._fails = fails
        self.calls = 0

    def state(self):
        return self._state

    def complete(self, messages, max_tokens):
        self.calls += 1
        if self._fails:
            raise OSError("provider down mid-request")
        return {"text": f"answer from {self.name}", "model": self.name}

    def stream(self, messages, max_tokens):
        self.calls += 1
        yield f"answer from {self.name}"


def _router(gpu_state=AdapterState.AVAILABLE, gpu_fails=False):
    return ModelRouter(
        gpu=_Provider("gpu", TIER_GPU, gpu_state, gpu_fails),
        local=_Provider("local", TIER_LOCAL),
        external=_Provider("external", TIER_EXTERNAL))


MSG = [{"role": "user", "content": "Intimblanc nedir?"}]


class GpuPreferredTest(unittest.TestCase):

    def test_gpu_answers_when_the_desktop_is_on(self):
        router = _router()
        _result, tier, _calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_GPU)
        self.assertEqual(router.local.calls, 0)
        self.assertEqual(router.external.calls, 0)

    def test_desktop_off_falls_back_to_the_server_not_the_internet(self):
        # The exact night-time case: no tunnel, so no health, so no GPU.
        router = _router(gpu_state=AdapterState.UNAVAILABLE)
        _result, tier, _calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_LOCAL)
        self.assertEqual(router.external.calls, 0,
                         "a powered-down desktop must not push traffic outside")

    def test_desktop_dies_mid_request_and_the_server_finishes_the_job(self):
        # Health said yes, then the tunnel dropped between check and request.
        router = _router(gpu_fails=True)
        result, tier, calls = router.generate(MSG, 64)
        self.assertEqual(tier, TIER_LOCAL)
        self.assertEqual(result["text"], "answer from local")
        self.assertEqual(calls, 2)

    def test_escalation_still_means_the_external_model(self):
        # Both local rungs run the same 4B weights: the GPU is a speed tier,
        # not a capability tier, so "this needs a stronger model" still leaves.
        router = _router()
        _result, tier, _calls = router.generate(MSG, 64, escalate=True)
        self.assertEqual(tier, TIER_EXTERNAL)

    def test_chain_order_is_fast_then_always_on_then_paid(self):
        router = _router()
        self.assertEqual([p.name for p in router._chain(False)],
                         ["gpu", "local", "external"])
        self.assertEqual([p.name for p in router._chain(True)],
                         ["external", "gpu", "local"])

    def test_states_report_all_three_rungs(self):
        router = _router(gpu_state=AdapterState.UNAVAILABLE)
        self.assertEqual(router.provider_states(),
                         {"gpu": "UNAVAILABLE", "local": "AVAILABLE",
                          "external": "AVAILABLE"})

    def test_everything_down_is_an_error_not_a_silent_empty_answer(self):
        router = ModelRouter(
            gpu=_Provider("gpu", TIER_GPU, AdapterState.UNAVAILABLE),
            local=_Provider("local", TIER_LOCAL, AdapterState.UNAVAILABLE),
            external=_Provider("external", TIER_EXTERNAL, AdapterState.UNAVAILABLE))
        with self.assertRaises(ModelUnavailable):
            router.generate(MSG, 64)


class StreamingFollowsTheSameOrderTest(unittest.TestCase):

    def test_streaming_prefers_the_gpu(self):
        router = _router()
        out = "".join(router.stream_text("Intimblanc nedir?", "sistem"))
        self.assertEqual(out, "answer from gpu")
        self.assertEqual(router.local.calls, 0)

    def test_streaming_falls_back_when_the_desktop_is_off(self):
        router = _router(gpu_state=AdapterState.UNAVAILABLE)
        out = "".join(router.stream_text("Intimblanc nedir?", "sistem"))
        self.assertEqual(out, "answer from local")


class SuppliedProviderKeepsItsIdentityTest(unittest.TestCase):

    def test_injected_gpu_is_not_renamed(self):
        # The router labels the provider it builds itself; one handed in by a
        # caller (or a test) keeps the name and tier it arrived with.
        mine = _Provider("custom", "CUSTOM_TIER")
        router = ModelRouter(gpu=mine)
        self.assertEqual(router.gpu.name, "custom")
        self.assertEqual(router.gpu.tier, "CUSTOM_TIER")


if __name__ == "__main__":
    unittest.main()
