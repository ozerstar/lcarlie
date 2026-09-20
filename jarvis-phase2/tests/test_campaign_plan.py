"""Kampanya bütçesi ve takvimi. Ağ yok, model yok.

Sınanan asıl davranış: plan, BİLİNMEYENİ bilinmiyor diye yazmalı. Sektör
ortalaması uydurup "dönüşüm %2 olur" demek planı dolu gösterirdi ama o rakam
bu şirketin verisi değildir; onunla hesaplanan bütçe ölçülmüş gibi duran bir
tahmindir.
"""
import unittest

from jarvis import campaign_plan as cp

# Olculen gercek degerlere yakin sahte veri
REKLAM = [
    {"pencere": 30, "harcama": 1350.0, "tiklama": 1000, "gosterim": 20000,
     "kampanya_adi": "Kampanya A", "adset_adi": "Kitle 1", "ad_adi": "K7"},
    {"pencere": 30, "harcama": 0.0, "tiklama": 0, "gosterim": 0,
     "kampanya_adi": "Kampanya B", "adset_adi": "Kitle 2", "ad_adi": "V-K1"},
    {"pencere": 7, "harcama": 9999.0, "tiklama": 1, "ad_adi": "eski"},
]
KALEM = [
    {"urun_adi": "INTIMBLANC (Bakım Kremi)", "adet": 4, "brut_marj": 3236.0,
     "maliyeti_biliniyor": True},
    {"urun_adi": "HYDRAVIE (Yüz Kremi)", "adet": 4, "brut_marj": 1000.0,
     "maliyeti_biliniyor": True},
]


class OlcumTests(unittest.TestCase):
    def test_cpc_30_gunluk_pencereden(self):
        """7 günlük satır hesaba girmemeli."""
        cpc, temel = cp.measured_cpc(REKLAM)
        self.assertEqual(1.35, cpc)
        self.assertIn("1,000 tıklama", temel)

    def test_reklam_yoksa_cpc_uydurulmaz(self):
        cpc, temel = cp.measured_cpc([])
        self.assertIsNone(cpc)
        self.assertIn("bilinmiyor", temel)

    def test_birim_marj_urune_gore(self):
        marj, _ = cp.unit_margin(KALEM, ("intimblanc",))
        self.assertEqual(809.0, marj)

    def test_satisi_olmayan_urun_marji_uydurulmaz(self):
        marj, temel = cp.unit_margin(KALEM, ("dermabed",))
        self.assertIsNone(marj)
        self.assertIn("ölçülmüş satışı yok", temel)

    def test_maliyeti_bilinmeyen_kalem_uyarilir(self):
        kalem = [{"urun_adi": "X", "adet": 1, "brut_marj": 100.0,
                  "maliyeti_biliniyor": False}]
        _marj, temel = cp.unit_margin(kalem, ("x",))
        self.assertIn("marj şişik olabilir", temel)


class PlanTests(unittest.TestCase):
    def plan(self, urun="INTIMBLANC", butce=150.0, reklam=None, kalem=None):
        return cp.build(urun, reklam if reklam is not None else REKLAM,
                        kalem if kalem is not None else KALEM,
                        daily_budget=butce)

    def test_basabas_tiklama_hesaplanir(self):
        """809 TL marj / 1,35 TL tıklama = 599 tıklamada 1 satış."""
        self.assertAlmostEqual(599.3, self.plan().breakeven_clicks, places=0)

    def test_test_butcesi_basabasin_kati(self):
        p = self.plan()
        self.assertEqual(int(p.breakeven_clicks * 2), p.test_clicks[0])
        self.assertEqual(int(p.breakeven_clicks * 3), p.test_clicks[1])

    def test_gun_sayisi_gunluk_butceden(self):
        p = self.plan(butce=150.0)
        self.assertTrue(1 <= p.days[0] <= p.days[1])

    def test_gunluk_butce_verilmezse_gun_hesaplanmaz(self):
        self.assertIsNone(self.plan(butce=None).days)

    def test_donusum_orani_her_zaman_bilinmeyen_yazilir(self):
        """Bu planın en önemli bilinmeyeni; gizlenirse plan yanıltıcı olur."""
        p = self.plan()
        self.assertTrue(any("dönüşüm" in b for b in p.unknowns))

    def test_olcum_yoksa_butce_onerilmez(self):
        p = self.plan(urun="DERMABED")
        self.assertIsNone(p.test_budget)
        self.assertIn("rakam uydurmak olurdu", cp.summarize(p))

    def test_ozet_her_sayinin_dayanagini_tasir(self):
        p = self.plan()
        self.assertTrue(p.basis)
        self.assertTrue(any("reklam kaydı" in b for b in p.basis))

    def test_ozet_kar_iddia_etmez(self):
        metin = cp.summarize(self.plan()).casefold()
        self.assertIn("önceden bilinemez", metin)
        for iddia in ("kâr eder", "kazandırır", "kesin"):
            self.assertNotIn(iddia, metin)


class HedeflemeTests(unittest.TestCase):
    def test_gecmis_adlar_kullanilir(self):
        """'held constant' bir metindi; sabit tutulacak şey ADIYLA yazılmalı."""
        h = cp.targeting_from_history(REKLAM)
        self.assertIn("Kampanya A", [c["name"] for c in h["campaigns"]])
        self.assertIn("Kitle 1", [a["name"] for a in h["adsets"]])

    def test_harcamaya_gore_siralanir(self):
        h = cp.targeting_from_history(REKLAM)
        self.assertEqual("Kampanya A", h["campaigns"][0]["name"])

    def test_reklam_yoksa_cokmez(self):
        h = cp.targeting_from_history([])
        self.assertEqual([], h["campaigns"])


if __name__ == "__main__":
    unittest.main()
