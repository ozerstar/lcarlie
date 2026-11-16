# -*- coding: utf-8 -*-
"""Gönderme kapılarının testleri.

🔴 BU TESTLER AĞA ÇIKMAZ. Hiçbiri gerçek mesaj göndermez; kapıların
gönderimi DURDURDUĞUNU kanıtlarlar. Bir kapı sessizce gevşerse müşteriye
yanlış mesaj gider ve geri alınamaz.
"""
import os
import json
import io
import urllib.error
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis import whatsapp


class KapilarKAPATIR(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "gonderim.jsonl"
        self.eski_defter = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        self.eski_env = os.environ.get("JARVIS_WHATSAPP_GONDER")
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski_defter
        if self.eski_env is None:
            os.environ.pop("JARVIS_WHATSAPP_GONDER", None)
        else:
            os.environ["JARVIS_WHATSAPP_GONDER"] = self.eski_env
        self.gecici.cleanup()

    def test_1_onaysiz_gonderilmez(self):
        for onay in ("", None, "rastgele", "SAHIP-PANEL"):
            with self.subTest(onay=onay):
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    whatsapp.gonder("905550000000", "merhaba",
                                    onay_kaynagi=onay)

    def test_2_bos_metin_gonderilmez(self):
        for metin in ("", "   ", "\n"):
            with self.subTest(metin=metin):
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    whatsapp.gonder("905550000000", metin,
                                    onay_kaynagi=whatsapp.ONAY_INSAN)

    def test_2_uzun_metin_gonderilmez(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", "a" * (whatsapp.METIN_SINIRI + 1),
                            onay_kaynagi=whatsapp.ONAY_INSAN)

    def test_4_gonderme_kapaliyken_gonderilmez(self):
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"
        with self.assertRaises(whatsapp.GondermeReddedildi) as kutu:
            whatsapp.gonder("905550000000", "Merhaba, nasil yardimci olabilirim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertIn("KAPALI", str(kutu.exception))

    def test_gecersiz_telefon_gonderilmez(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("123", "Merhaba",
                            onay_kaynagi=whatsapp.ONAY_INSAN)


class MevzuatKapisiINSAN_ONAYIYLA_DA_ASILMAZ(unittest.TestCase):
    """🔴 Sahip yanlislikla onaylasa bile iddia iceren metin gitmemeli."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = Path(self.gecici.name) / "g.jsonl"
        os.environ["JARVIS_WHATSAPP_GONDER"] = "1"  # kapi ACIK olsa bile

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"
        self.gecici.cleanup()

    def test_blocked_metin_insan_onayiyla_da_gitmez(self):
        iddia = "Bu krem egzamayı tedavi eder ve hastalığı geçirir."
        bulgular = whatsapp.denetle(iddia)
        if not bulgular:
            self.skipTest("mevzuat motoru bu ifadeyi BLOCKED saymiyor")
        with self.assertRaises(whatsapp.GondermeReddedildi) as kutu:
            whatsapp.gonder("905550000000", iddia,
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertIn("mevzuat", str(kutu.exception))


class KuruKosuAGA_CIKMAZ(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "g.jsonl"
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        self.gecici.cleanup()

    def test_kuru_kosu_gonderme_kapaliyken_de_calisir(self):
        sonuc = whatsapp.gonder("905550000000", "Merhaba, size nasil yardimci olabilirim",
                                onay_kaynagi=whatsapp.ONAY_INSAN, kuru=True)
        self.assertFalse(sonuc["gonderildi"])
        self.assertTrue(sonuc["kuru"])

    def test_kuru_kosu_da_mevzuattan_gecer(self):
        iddia = "Bu krem egzamayı tedavi eder ve hastalığı geçirir."
        if not whatsapp.denetle(iddia):
            self.skipTest("mevzuat motoru bu ifadeyi BLOCKED saymiyor")
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", iddia,
                            onay_kaynagi=whatsapp.ONAY_INSAN, kuru=True)


class DefterREDDEDILENI_DE_YAZAR(unittest.TestCase):
    """"Hic denenmedi" ile "engellendi" ayni gorunmemeli."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.defter = Path(self.gecici.name) / "g.jsonl"
        self.eski = whatsapp.DEFTER
        whatsapp.DEFTER = self.defter
        os.environ["JARVIS_WHATSAPP_GONDER"] = "0"

    def tearDown(self):
        whatsapp.DEFTER = self.eski
        self.gecici.cleanup()

    def test_reddedilen_deneme_deftere_yazilir(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905550000000", "Merhaba efendim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        self.assertTrue(self.defter.exists(), "reddedilen deneme kaydedilmemis")
        satir = self.defter.read_text(encoding="utf-8").strip()
        self.assertIn("REDDEDILDI", satir)

    def test_defterde_TAM_telefon_YOK(self):
        with self.assertRaises(whatsapp.GondermeReddedildi):
            whatsapp.gonder("905551234567", "Merhaba efendim",
                            onay_kaynagi=whatsapp.ONAY_INSAN)
        satir = self.defter.read_text(encoding="utf-8")
        self.assertNotIn("905551234567", satir, "deftere tam numara yazilmis")
        self.assertIn("4567", satir, "son dort hane de yok, iz surulemez")


class VarsayilanKAPALI(unittest.TestCase):
    def test_anahtar_yoksa_kapali(self):
        eski = os.environ.pop("JARVIS_WHATSAPP_GONDER", None)
        try:
            self.assertFalse(whatsapp.gonderme_acik())
        finally:
            if eski is not None:
                os.environ["JARVIS_WHATSAPP_GONDER"] = eski


class DurableSendGuards(unittest.TestCase):
    """Both send paths must fail closed before I/O, never retry after success."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "audit.jsonl"
        for mock in (
            patch.object(whatsapp, "DEFTER", self.ledger),
            patch.dict(os.environ, {"EXTERNAL_ACTIONS": "true",
                                    "JARVIS_WHATSAPP_GONDER": "1"}),
            patch.object(whatsapp, "_env", return_value="fake-credential"),
            patch.object(whatsapp, "denetle", return_value=[]),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def send(self, template=False, dry=False):
        if template:
            return whatsapp.sablon_gonder(
                "905551234567", "siparis", ["Merhaba"],
                onay_kaynagi=whatsapp.ONAY_INSAN, kuru=dry)
        return whatsapp.gonder("905551234567", "Merhaba",
                               onay_kaynagi=whatsapp.ONAY_INSAN, kuru=dry)

    def test_global_switch_cannot_be_bypassed_by_channel_switch(self):
        for template in (False, True):
            for value in (None, "false", "0", "", "yes"):
                with self.subTest(template=template, value=value), \
                     patch.dict(os.environ), patch.object(whatsapp, "_meta_cagir") as network:
                    if value is None:
                        os.environ.pop("EXTERNAL_ACTIONS", None)
                    else:
                        os.environ["EXTERNAL_ACTIONS"] = value
                    with self.assertRaises(whatsapp.GondermeReddedildi):
                        self.send(template)
                    network.assert_not_called()

    def test_channel_switch_still_required(self):
        with patch.dict(os.environ, {"JARVIS_WHATSAPP_GONDER": "0"}):
            self.assertFalse(whatsapp.gonderme_acik())

    def test_unwritable_ledger_blocks_both_send_paths(self):
        blocker = Path(self.tmp.name) / "not-a-directory"
        blocker.write_text("blocked")
        for template in (False, True):
            with self.subTest(template=template), \
                 patch.object(whatsapp, "DEFTER", blocker / "audit.jsonl"), \
                 patch.object(whatsapp, "_meta_cagir") as network:
                with self.assertRaisesRegex(whatsapp.GondermeReddedildi, "aga cikilmadi"):
                    self.send(template)
                network.assert_not_called()

    def test_fsync_failure_blocks_both_send_paths(self):
        for template in (False, True):
            with self.subTest(template=template), \
                 patch.object(whatsapp.os, "fsync", side_effect=OSError("fake-secret")), \
                 patch("sys.stderr", new_callable=io.StringIO) as stderr, \
                 patch.object(whatsapp, "_meta_cagir") as network:
                with self.assertRaises(whatsapp.GondermeReddedildi):
                    self.send(template)
                network.assert_not_called()
                self.assertNotIn("fake-secret", stderr.getvalue())

    def test_intent_is_durable_before_network_and_correlates_completion(self):
        for template in (False, True):
            with self.subTest(template=template):
                def network(*args):
                    self.assertEqual(sync.call_count, 1)
                    records = [json.loads(line) for line in self.ledger.read_text().splitlines()]
                    self.assertEqual(records[-1]["sonuc"], "GONDERIM_BASLADI")
                    self.assertTrue(records[-1]["deneme_id"])
                    self.assertNotIn("905551234567", self.ledger.read_text())
                    self.assertNotIn("fake-credential", self.ledger.read_text())
                    return {"messages": [{"id": "wamid.test"}]}, "", None
                with patch.object(whatsapp, "_meta_cagir", side_effect=network), \
                     patch.object(whatsapp.os, "fsync", wraps=os.fsync) as sync:
                    result = self.send(template)
                    self.assertTrue(result["gonderildi"])
                    self.assertTrue(result["defter_kaydedildi"])
                    self.assertEqual(sync.call_count, 2)
                records = [json.loads(line) for line in self.ledger.read_text().splitlines()]
                self.assertEqual(records[-1]["sonuc"], "GONDERILDI")
                self.assertEqual(records[-1]["deneme_id"], records[-2]["deneme_id"])

    def test_completion_audit_failure_does_not_claim_unsent(self):
        for template in (False, True):
            with self.subTest(template=template), \
                 patch.object(whatsapp, "_defter_yaz", side_effect=[True, False]), \
                 patch.object(whatsapp, "_meta_cagir", return_value=(
                     {"messages": [{"id": "wamid.sent"}]}, "", None)) as network:
                result = self.send(template)
                self.assertTrue(result["gonderildi"])
                self.assertEqual(result["wamid"], "wamid.sent")
                self.assertFalse(result["defter_kaydedildi"])
                network.assert_called_once()

    def test_dry_runs_ignore_both_switches_and_never_send(self):
        for template in (False, True):
            with self.subTest(template=template), \
                 patch.dict(os.environ, {"EXTERNAL_ACTIONS": "false", "JARVIS_WHATSAPP_GONDER": "0"}), \
                 patch.object(whatsapp, "_meta_cagir") as network:
                result = self.send(template, dry=True)
                self.assertTrue(result["kuru"])
                self.assertFalse(result["gonderildi"])
                network.assert_not_called()

    def test_provider_error_body_is_not_logged(self):
        error = urllib.error.HTTPError("https://example.invalid", 400, "bad", {},
                                       io.BytesIO(b'{"error":{"message":"secret-token"}}'))
        with patch.object(whatsapp.urllib.request, "urlopen", side_effect=error):
            data, reason, detail = whatsapp._meta_cagir("id", "fake-token", {})
        self.assertEqual(reason, "Meta HTTP 400")
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
