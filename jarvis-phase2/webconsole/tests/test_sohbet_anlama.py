"""12.11.2026'da gerçek sorularla ölçülen dört anlama hatası.

Her test, sahibin yazdığı biçimde (Türkçe karakter eksik, ı/i karışık) bir
soruyla kurulur. Model çağrılmaz.
"""
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("JARVIS_STATE_DIR", tempfile.mkdtemp(prefix="jarvis-test-"))
KOK = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(KOK), str(KOK / "webconsole")]

import conversation  # noqa: E402
from jarvis import consensus  # noqa: E402
from jarvis.memory import CompanyMemory  # noqa: E402

BUGUN = date(2026, 11, 12)


class Evidence:
    def __init__(self, source, records):
        self.source, self.records = source, records


class Memory:
    PAZAR = [
        {"kanal": "wix", "siparis_zamani": "2026-11-11T10:49:09+03:00", "tutar": 1470, "durum": "PAID"},
        {"kanal": "trendyol", "siparis_zamani": "2026-11-11T20:55:29+03:00", "tutar": 2560, "durum": "Picking",
         "kalemler": [{"ad": "SUNACNEA SPF 30+ Hassas ve Akne Eğilimli Ciltler İçin Güneş Kremi 50 ml, one size",
                       "adet": 2, "barkod": "8684869609097"}]},
        {"kanal": "trendyol", "siparis_zamani": "2026-11-10T12:31:52+03:00", "tutar": 2685, "durum": "Shipped"},
        {"kanal": "wix", "siparis_zamani": "2026-10-22T23:05:55+03:00", "tutar": 2100, "durum": "PAID"},
    ]

    SAGLIK = [
        {"entity_id": "hepsiburada", "etkin": False, "ardisik_hata": 12312},
        {"entity_id": "trendyol", "etkin": True, "ardisik_hata": 0},
    ]

    def _fetch(self, name):
        veri = {"operations_marketplace_orders": self.PAZAR,
                "operations_channel_health": self.SAGLIK,
                "sales_orders": [{"olcumde": True, "ciro_dogrulanmis_net": 100}],
                "sales_items": []}
        return Evidence("postgres:" + name, veri[name])

    def get_system_status(self):
        return Evidence("postgres:system", [{"pending_actions": 19}])


class DonemTesti(unittest.TestCase):
    def test_donemler(self):
        ornekler = {
            "bugun kac sıparıs geldı": (date(2026, 11, 12), date(2026, 11, 12)),
            "dun satıs oldu mu": (date(2026, 11, 11), date(2026, 11, 11)),
            "bu ay cıro ne kadar": (date(2026, 11, 1), date(2026, 11, 12)),
            "gecen ay kac sıparıs": (date(2026, 10, 1), date(2026, 10, 31)),
            "bu hafta satıslar": (date(2026, 11, 9), date(2026, 11, 12)),
            "son 7 gunde ne sattık": (date(2026, 11, 6), date(2026, 11, 12)),
        }
        for soru, (bas, son) in ornekler.items():
            donem = conversation._donem(soru, BUGUN)
            self.assertIsNotNone(donem, soru)
            self.assertEqual(donem[:2], (bas, son), soru)

    def test_donemsiz_soru(self):
        self.assertIsNone(conversation._donem("kac siparisimiz var", BUGUN))


class DonemliSatisTesti(unittest.TestCase):
    def cevap(self, soru):
        asil = conversation._donem
        with patch.object(conversation, "_donem", lambda m, b=None: asil(m, BUGUN)):
            return conversation._sales_answer(soru, [], Memory())

    def test_satilan_urunler_yazilir(self):
        cevap = self.cevap("bu hafta en cok ne sattık")
        self.assertIn("Satılanlar: SUNACNEA ×2", cevap)

    def test_kalemsiz_siparis_bozmaz(self):
        self.assertEqual(conversation._satilan_urunler([{"kalemler": None}, {}]), "")

    def test_bu_ay_yalniz_bu_ayi_sayar(self):
        cevap = self.cevap("bu ay kac sıparıs geldı ve cıro ne kadar")
        self.assertIn("3 sipariş", cevap)
        self.assertIn("Trendyol 2 sipariş", cevap)
        self.assertIn("Wix 1 sipariş", cevap)
        self.assertNotIn("39", cevap)

    def test_bos_donem_acikca_soylenir(self):
        self.assertIn("hiçbir kanalda sipariş görünmüyor", self.cevap("bugun kac sıparıs geldı"))

    def test_donemsiz_cevap_pazaryerini_de_soyler(self):
        cevap = conversation._sales_answer("kac siparisimiz var", [{"olcumde": True}], Memory())
        self.assertIn("pazaryerlerinden ayrıca 2 sipariş", cevap)

    def test_kapali_kanal_soylenir(self):
        cevap = conversation._sales_answer("hepsıburadadan sıparıs gelıyor mu", [], Memory())
        self.assertIn("Hepsiburada: bağlantı kurulmadı", cevap)
        self.assertIn("Kayıtlı sipariş yok", cevap)

    def test_kanal_ve_donem_birlikte(self):
        cevap = self.cevap("trendyoldan dun satıs oldu mu")
        self.assertIn("Trendyol: bağlantı çalışıyor", cevap)
        self.assertIn("Dün 1 sipariş", cevap)
        self.assertIn("en yenisi 11.11", cevap)

    def test_satis_kaniti_pazaryerini_icerir(self):
        self.assertIn("operations_marketplace_orders", CompanyMemory.DOMAIN_QUERIES["sales"])
        self.assertIn("operations_channel_health", CompanyMemory.DOMAIN_QUERIES["sales"])


class KanitOzetTesti(unittest.TestCase):
    def test_kapali_kanal_hata_sayilmaz(self):
        ozet = conversation._summarize("operations_channel_health", [
            {"entity_id": "hepsiburada", "etkin": False, "ardisik_hata": 12312,
             "son_hata": "/etc/lcarlie/hepsiburada.env yok"},
            {"entity_id": "trendyol", "etkin": True, "ardisik_hata": 0,
             "son_basarili": "2026-11-12T01:23:13"},
            {"entity_id": "n11", "etkin": True, "ardisik_hata": 3, "son_hata": "HTTP 500"}])
        self.assertIn("hepsiburada: bağlı değil", ozet)
        self.assertNotIn("12312", ozet)
        self.assertIn("trendyol: çalışıyor", ozet)
        self.assertIn("n11: 3 ardışık hata", ozet)

    def test_pazaryeri_ozeti_kanallari_sayar(self):
        ozet = conversation._summarize("operations_marketplace_orders", Memory.PAZAR)
        self.assertIn("trendyol 2", ozet)
        self.assertIn("wix 2", ozet)


class OnayTesti(unittest.TestCase):
    def test_onay_sorusu_onaya_gider(self):
        for soru in ("onay bekleyen ne var", "onayımı bekleyen işler", "bekleyen onaylar"):
            karar = conversation.classify(soru)
            self.assertEqual((karar.intent, karar.domain), ("COMPANY_QUERY", "onay"), soru)

    def test_onay_sayisi_dogru_soylenir(self):
        cevap = conversation._company("onay bekleyen ne var", "onay", Memory(), 0.0)
        self.assertIn("19 öneri onayınızı bekliyor", cevap["answer"])


class DogrulamaTesti(unittest.TestCase):
    def test_madde_numarasi_iddia_sayilmaz(self):
        metin = "1. Logları inceleyin\n2) Kanalı kontrol edin\n- 3. Bekleyin"
        self.assertEqual(consensus.numeric_claims(metin), {})

    def test_dogrulama_ilk_cevabi_degistirmez(self):
        ilk = "Bu ay 3 sipariş geldi, toplam 6.715 TL. Ayrıntı: Trendyol 2, Wix 1."
        kisa = "Bu ay 4 sipariş."
        sahte = type("R", (), {"answer": kisa})()
        with patch.object(conversation, "CONSENSUS_ON", True), \
             patch.object(conversation, "CONSENSUS_SAMPLES", 3), \
             patch.object(conversation, "_router") as router:
            router.return_value.synthesize.return_value = sahte
            sonuc = conversation._verify("bu ay kac siparis", ilk, [], [], True)
        self.assertEqual(sonuc["answer"], ilk)
        self.assertTrue(sonuc["disputed_claims"])
        self.assertEqual(router.return_value.synthesize.call_count, 2)


if __name__ == "__main__":
    unittest.main()
