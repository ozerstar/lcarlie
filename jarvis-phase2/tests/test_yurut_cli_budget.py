import importlib.util
from pathlib import Path
import signal
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("is_uretici_cli_budget", Path(__file__).resolve().parents[1] / "scripts/is-uretici.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

class CliBudgetTests(unittest.TestCase):
    def test_sigterm_is_cooperative_and_restores_handler(self):
        old = signal.getsignal(signal.SIGTERM)
        iu = Mock()
        def run(*args, **kwargs):
            self.assertFalse(kwargs["durdur"]())
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
            self.assertTrue(kwargs["durdur"]())
            return {"checkpoint": "finished"}
        iu.yurut.side_effect = run
        self.assertEqual(cli._yurut_guvenli(iu, 12, 1200), {"checkpoint": "finished"})
        self.assertIs(signal.getsignal(signal.SIGTERM), old)

    def test_handler_restored_on_error(self):
        old = signal.getsignal(signal.SIGTERM)
        iu = Mock()
        iu.yurut.side_effect = RuntimeError("failure")
        with self.assertRaises(RuntimeError):
            cli._yurut_guvenli(iu, 12, 1200)
        self.assertIs(signal.getsignal(signal.SIGTERM), old)

    def test_cli_default_budget(self):
        iu = Mock()
        iu.yurut.return_value = {}
        iu.ozet_yaz.return_value = "summary"
        with patch("sys.argv", ["is-uretici.py", "--mod", "yurut", "--kuru"]), patch.object(cli, "_ortam"), patch("jarvis.is_uretici.IsUretici", return_value=iu):
            self.assertEqual(cli.main(), 0)
        self.assertEqual(iu.yurut.call_args.kwargs["sure_sn"], 1200)

    def test_busy_lock_defers_without_environment_or_database_actions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, "DURUM", Path(tmp)):
            owner = cli._kilit()
            try:
                self.assertIsNone(cli._kilit(nonblocking=True))
                with patch("sys.argv", ["is-uretici.py", "--mod", "yurut"]), patch.object(cli, "_ortam") as environment, patch.object(cli, "_suresi_dolanlari_kapat") as cleanup:
                    self.assertEqual(cli.main(), 0)
                environment.assert_not_called()
                cleanup.assert_not_called()
            finally:
                owner.close()
            reacquired = cli._kilit()
            self.assertIsNotNone(reacquired)
            reacquired.close()

    def test_lock_defaults_to_blocking_for_other_modes(self):
        import tempfile
        import fcntl
        with tempfile.TemporaryDirectory() as tmp, patch.object(cli, "DURUM", Path(tmp)), patch("fcntl.flock") as flock:
            owner = cli._kilit()
            try:
                self.assertEqual(flock.call_args.args[1], fcntl.LOCK_EX)
            finally:
                owner.close()

    def test_non_yurut_modes_request_blocking_lock(self):
        for mode in ("gunluk", "haftalik", "aylik"):
            with self.subTest(mode=mode), patch("sys.argv", ["is-uretici.py", "--mod", mode]), patch.object(cli, "_kilit", return_value=None) as lock:
                self.assertEqual(cli.main(), 0)
                lock.assert_called_once_with(nonblocking=False)
