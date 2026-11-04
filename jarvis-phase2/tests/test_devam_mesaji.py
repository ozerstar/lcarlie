"""Önceki konuşmaya bağlı mesaj konudan kopmamalı. Ağ yok, model yok.

Ölçüldü 04.11.2026: "Bugün hangi işler öncelikli?" (cevap: Wix maliyet maddeleri) ardından
"Finans tarafında tum ürünleri maliyetleti açıkca yazıyor onları kullan" AGENCY_REQUEST'e
düştü; ajans geçmişi görmediği için Meta reklam raporu döndü.
"""
from __future__ import annotations

import importlib
import os
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone


class DevamMesajiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        onceki = os.environ.get("JARVIS_STATE_DIR")
        os.environ["JARVIS_STATE_DIR"] = self.tmp.name

        def geri():
            if onceki is None:
                os.environ.pop("JARVIS_STATE_DIR", None)
            else:
                os.environ["JARVIS_STATE_DIR"] = onceki

        self.addCleanup(geri)
        from jarvis import conversation_memory
        self.mem = importlib.reload(conversation_memory)
        self.addCleanup(lambda: importlib.reload(conversation_memory))
        from webconsole import conversation
        self.conv = importlib.reload(conversation)
        self.addCleanup(lambda: importlib.reload(conversation))

    def test_maliyet_takip_sorusu_devam_sayilir(self):
        self.mem.record("Bugün hangi işler öncelikli?", "[P0] Wix ürün maliyetleri girilmedi", intent="COMPANY_QUERY")
        onceki = self.conv.devam_mesaji("Finans tarafında tum ürünleri maliyetleti açıkca yazıyor onları kullan")
        self.assertEqual("Bugün hangi işler öncelikli?", onceki)

    def test_eski_konusma_devam_sayilmaz(self):
        self.mem.record("Bugün hangi işler öncelikli?", "cevap", intent="COMPANY_QUERY")
        sonra = datetime.now(timezone.utc) + timedelta(hours=2)
        self.assertIsNone(self.conv.devam_mesaji("onları kullan", simdi=sonra))

    def test_gecmis_yoksa_devam_yok(self):
        self.assertIsNone(self.conv.devam_mesaji("onları kullan"))

    def test_uzun_yeni_konu_devam_sayilmaz(self):
        self.mem.record("Bugün hangi işler öncelikli?", "cevap", intent="COMPANY_QUERY")
        self.assertIsNone(self.conv.devam_mesaji(
            "INTIMBLANC için kasım ayına yeni bir Instagram kampanyası hazırla lütfen"))

    def test_devam_ajans_dalina_gitmez_gecmisli_modele_gider(self):
        self.mem.record("Bugün hangi işler öncelikli?", "maliyet maddeleri", intent="COMPANY_QUERY")
        with unittest.mock.patch.object(self.conv, "_synthesize", return_value={"intent": "COMPANY_QUERY"}) as sentez, \
                unittest.mock.patch.object(self.conv, "_agency_request") as ajans, \
                unittest.mock.patch.object(self.conv, "_memory", return_value=None):
            self.conv.route("Finans tarafında maliyetler yazıyor onları kullan", runtime=None)
        ajans.assert_not_called()
        self.assertIn("Bugün hangi işler öncelikli?", sentez.call_args.kwargs["arama"])

    def test_eylem_siniri_devamdan_once_gelir(self):
        self.mem.record("Bugün hangi işler öncelikli?", "cevap", intent="COMPANY_QUERY")
        with unittest.mock.patch.object(self.conv, "_action", return_value={"intent": "ACTION_REQUEST"}) as eylem, \
                unittest.mock.patch.object(self.conv, "_synthesize") as sentez:
            self.conv.route("onların fiyatını düşür", runtime=None)
        eylem.assert_called_once()
        sentez.assert_not_called()


if __name__ == "__main__":
    unittest.main()
