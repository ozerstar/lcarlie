"""Internal proposal recovery: no Docker/DB/network calls."""
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class OwnerHandoffTests(unittest.TestCase):
    def test_duplicate_readback_is_exact_and_excludes_cancelled_expired(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "is-uretici.py"
        spec = importlib.util.spec_from_file_location("is_uretici_script", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="42\n", stderr="")) as run:
            self.assertEqual(module._oneri_ac("teslim.test", "report", "reason"), 42)
        sql = run.call_args.kwargs["input"]
        self.assertIn("COALESCE(core.ai_sistem_onerisi", sql)
        self.assertIn("idempotency_key='action:sistem:kurul:' || :'a'", sql)
        self.assertIn("payload=jsonb_build_object('subject_ref', :'a', 'reason', :'m')", sql)
        self.assertIn("state='PROPOSED' AND expires_at > clock_timestamp()", sql)
        self.assertIn("state IN ('APPROVED', 'EXECUTING', 'EXECUTED')", sql)
        self.assertNotIn("'REJECTED'", sql)
        self.assertNotIn("'CANCELLED'", sql)
        self.assertNotIn("UPDATE", sql)
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="\n", stderr="")):
            self.assertIsNone(module._oneri_ac("teslim.test", "report", "reason"))
