"""Failure-boundary regressions. No network, Docker or production state."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from jarvis import whatsapp, haberci
from jarvis.improvement import Store
from jarvis.is_uretici import IsUretici
import test_is_uretici as producer_fixture


class SendOutcomeTests(unittest.TestCase):
    def setUp(self):
        tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.ledger = Path(tmp) / "send.jsonl"
        self.enterContext(patch.object(whatsapp, "DEFTER", self.ledger))
        self.enterContext(patch.dict(os.environ, {"EXTERNAL_ACTIONS": "true", "JARVIS_WHATSAPP_GONDER": "1"}))
        self.enterContext(patch.object(whatsapp, "_env", return_value="fake-token"))
        self.enterContext(patch.object(whatsapp, "denetle", return_value=[]))

    def send(self, template=False, key=None, message="Merhaba"):
        if template:
            return whatsapp.sablon_gonder("905550000000", "order", [message],
                                          onay_kaynagi=whatsapp.ONAY_INSAN, is_anahtari=key)
        return whatsapp.gonder("905550000000", message,
                               onay_kaynagi=whatsapp.ONAY_INSAN, is_anahtari=key)

    def test_empty_or_malformed_response_never_means_accepted(self):
        for template in (False, True):
            for response in ({}, [], {"messages": []}, {"messages": "wrong"},
                             {"messages": [{}]}, {"messages": [{"id": 1}]}):
                with self.subTest(template=template, response=response), \
                     patch.object(whatsapp, "_meta_cagir", return_value=(response, "", None)):
                    with self.assertRaises(whatsapp.GonderimBelirsiz):
                        self.send(template)
                    self.assertEqual(json.loads(self.ledger.read_text().splitlines()[-1])["sonuc"], "BELIRSIZ")

    def test_timeout_and_server_failure_block_replay_for_both_paths(self):
        for template in (False, True):
            for error in ("ag hatasi: TimeoutError", "Meta HTTP 408", "Meta HTTP 500"):
                key = f"order:{template}:{error}"
                with self.subTest(template=template, error=error), \
                     patch.object(whatsapp, "_meta_cagir", return_value=({}, error, None)) as network:
                    for _ in range(2):
                        with self.assertRaises(whatsapp.GonderimBelirsiz):
                            self.send(template, key)
                    network.assert_called_once()

    def test_bad_json_response_is_uncertain_and_does_not_leak_exception(self):
        with patch.object(whatsapp, "_meta_cagir", side_effect=ValueError("fake-sensitive-payload")):
            with self.assertRaises(whatsapp.GonderimBelirsiz) as err:
                self.send(key="decode")
        self.assertNotIn("fake-sensitive-payload", str(err.exception) + self.ledger.read_text())

    def test_confirmed_rejection_can_retry_with_same_business_key(self):
        for template in (False, True):
            with self.subTest(template=template), patch.object(whatsapp, "_meta_cagir", side_effect=[
                ({}, "Meta HTTP 400", None), ({"messages": [{"id": "wamid.retry"}]}, "", None)
            ]) as network:
                key = f"rejected:{template}"
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    self.send(template, key)
                self.assertEqual(self.send(template, key)["wamid"], "wamid.retry")
                self.assertEqual(network.call_count, 2)

    def test_concurrent_and_later_replays_only_accept_one_request(self):
        for template in (False, True):
            with self.subTest(template=template), patch.object(whatsapp, "_meta_cagir", return_value=(
                {"messages": [{"id": "wamid.once"}]}, "", None)) as network:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(lambda _: self.send(template, f"once:{template}"), range(4)))
                self.assertEqual({r["wamid"] for r in results}, {"wamid.once"})
                self.assertEqual(sum(not r["tekrar"] for r in results), 1)
                self.assertTrue(all(r["teslim_edildi"] is None for r in results))
                network.assert_called_once()
                with self.assertRaises(whatsapp.GonderimBelirsiz):
                    self.send(template, f"once:{template}", "Changed content")
                network.assert_called_once()
        self.assertNotIn("905550000000", self.ledger.read_text())
        self.assertNotIn("Merhaba", self.ledger.read_text())

    def test_crash_after_intent_is_not_replayed(self):
        with patch.object(whatsapp, "_meta_cagir", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self.send(key="crashed")
        with patch.object(whatsapp, "_meta_cagir") as network:
            with self.assertRaises(whatsapp.GonderimBelirsiz):
                self.send(key="crashed")
            network.assert_not_called()

    def test_post_acceptance_audit_failure_is_visible_and_blocks_replay(self):
        write = whatsapp._defter_yaz
        def failing_result(row):
            return False if row.get("sonuc") == "GONDERILDI" else write(row)
        with patch.object(whatsapp, "_defter_yaz", side_effect=failing_result), \
             patch.object(whatsapp, "_meta_cagir", return_value=({"messages": [{"id": "wamid.accepted"}]}, "", None)) as network, \
             patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = self.send(key="audit-failed")
            self.assertTrue(result["gonderildi"])
            self.assertTrue(result["uzlastirma_gerekli"])
            self.assertIn("uzlastirma gerekli", stderr.getvalue())
            with self.assertRaises(whatsapp.GonderimBelirsiz):
                self.send(key="audit-failed")
            network.assert_called_once()

    def test_unreadable_history_fails_closed(self):
        self.ledger.write_text("incomplete-json\n")
        with patch.object(whatsapp, "_meta_cagir") as network:
            with self.assertRaises(whatsapp.GonderimBelirsiz):
                self.send(key="unreadable")
            network.assert_not_called()


class SenderRecoveryTests(unittest.TestCase):
    def test_order_confirmation_keeps_uncertain_send_out_of_retry_state(self):
        path = Path(__file__).resolve().parents[1] / "scripts/siparis-teyit-tarama.py"
        spec = importlib.util.spec_from_file_location("confirmation_guard_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        order = {"number": "17", "dateCreated": "2026-11-03T09:00:00Z",
                 "billingInfo": {"paymentMethod": "PayTR"}, "paymentStatus": "PAID"}
        state = {}
        def claim(*args):
            if state.get("status") == "GONDERILIYOR":
                return False
            state["status"] = "GONDERILIYOR"
            return True
        def close(no, status, *args):
            state["status"] = status
        with patch.object(mod, "normal_degerler", return_value=(["A", "17", "item", "1", "address", "phone"], "905550000000", "item")), \
             patch.object(mod, "baslik_gorseli", return_value=""), \
             patch.object(mod, "kilit_al", side_effect=claim), \
             patch.object(mod, "kilit_kapat", side_effect=close), \
             patch.object(mod, "_alarm") as alarm, \
             patch.object(whatsapp, "sablon_gonder", side_effect=whatsapp.GonderimBelirsiz("timeout")) as send:
            for _ in range(2):
                mod.isle(order, gonder=True, baslangic=datetime(2026, 11, 1, tzinfo=timezone.utc))
            send.assert_called_once()
            self.assertEqual(send.call_args.kwargs["is_anahtari"], "siparis-teyit:17")
            self.assertEqual(state["status"], "GONDERILIYOR")
            alarm.assert_called_once()

    def test_owner_notification_does_not_convert_uncertainty_to_retryable_failure(self):
        with patch.object(haberci, "kilit_al", return_value=True), \
             patch.object(haberci, "kilit_kapat") as close, \
             patch.object(haberci, "whatsapp_gonder", side_effect=whatsapp.GonderimBelirsiz("timeout")):
            result = haberci.bildir(17, kanal="wix", siparis_no="17", tutar="1", musteri="A", urunler="item", yollar=("whatsapp",))
        self.assertIn("BELIRSIZ", result["whatsapp"])
        self.assertEqual(close.call_args.args[2], "GONDERILIYOR")


class DeliveryReconciliationTests(unittest.TestCase):
    def test_direct_runner_recovers_ledger_failure_without_regenerating_delivery(self):
        fixture = producer_fixture.Test()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        store = Store(Path(fixture.tmp.name) / "improvement/ledger.sqlite3")
        fixture.o.defter = store
        iu = IsUretici(fixture.o, gunluk_tavan=50)
        iu.gunluk()
        with patch.object(store, "apply", side_effect=OSError("disk unavailable")):
            result = iu.yurut()
            self.assertEqual(result["recovered_evidence"], 0)
        calls = len(fixture.model.cagri)
        artifact = Path(fixture.agac()["departmanlar"]["SEO"]["gorevler"][0]["teslim"]["yol"])
        content = artifact.read_bytes()
        result = IsUretici(fixture.o, gunluk_tavan=50).yurut()
        self.assertEqual(result["recovered_evidence"], 1)
        self.assertEqual(len(fixture.model.cagri), calls)
        self.assertEqual(artifact.read_bytes(), content)
        self.assertEqual(IsUretici(fixture.o).yurut()["recovered_evidence"], 0)
        with store.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM application").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE operation='application'").fetchone()[0], 1)

    def test_reconciler_never_credits_explicitly_unapproved_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "improvement/ledger.sqlite3")
            work = store.work(source_key="test", domain="test", objective="report", owner="test", metric="test", unit="item", source="test")
            artifact = root / "is-uretici/teslimler/report.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("Report")
            for decision in ("RED", "DUZELT", "INCELEME_BEKLIYOR"):
                tree = {"departmanlar": {"SEO": {"gorevler": [{"work_id": work, "durum": "TESLIM_EDILDI", "teslim": {
                    "kalite": "GECTI", "yonetici": decision, "yol": str(artifact)}}]}}}
                (root / "is-uretici/agac.json").write_text(json.dumps(tree))
                self.assertEqual(store.reconcile_team_deliveries(), 0)

