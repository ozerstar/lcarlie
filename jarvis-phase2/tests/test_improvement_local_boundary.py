import runpy
import unittest
from pathlib import Path
from unittest.mock import patch
from jarvis.adapter_factory import AdapterState


class LocalEvaluationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.module=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/improvement-model-eval.py'),run_name='evaluation_boundary_test')

    def test_no_external_provider_is_constructed(self):
        with patch('jarvis.model_layer.ExternalProvider',side_effect=AssertionError('external must not be constructed')):
            router=self.module['local_router']()
        self.assertEqual(router.external.state(),AdapterState.UNAVAILABLE)
        self.assertEqual(router.gpu.state(),AdapterState.UNAVAILABLE)

    def test_local_endpoint_is_fixed_loopback(self):
        with patch.dict('os.environ',{'JARVIS_LOCAL_MODEL_URL':'https://invalid.example/v1'}):
            router=self.module['local_router']()
        self.assertEqual(router.local.url,'http://127.0.0.1:8099/v1')

    def test_disabled_provider_cannot_complete(self):
        provider=self.module['DisabledProvider']()
        with self.assertRaises(RuntimeError):provider.complete([],180)
