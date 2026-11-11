import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

YOL = Path(__file__).resolve().parent.parent / "scripts" / "kampanya-izle.py"
spec = importlib.util.spec_from_file_location("kampanya_izle", YOL)
ki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ki)

TR = timezone(timedelta(hours=3))
K = {"ad": "Test", "baslangic": "2026-11-11T14:00:00+03:00", "urunler": {"LUCIDERM": "111"},
     "onceki_14_gun_siparis": 1,
     "esikler": {"inceleme_saat": 3, "teslim_saat": 4, "en_az_gosterim": 2000, "ctr_alt": 0.8,
                 "tbm_ust": 6, "frekans_ust": 2.5, "satissiz_tik": 300}}
SIMDI = datetime(2026, 11, 12, 14, 0, tzinfo=TR)


def reklam(kimlik, durum="ACTIVE"):
    return {"id": kimlik, "name": "R" + kimlik, "effective_status": durum,
            "adset": {"name": "AS1", "daily_budget": "40000"}}


class KampanyaIzleTest(unittest.TestCase):
    def anahtarlar(self, m, satis):
        uyari, _ = ki.degerlendir(K, m, satis, SIMDI)
        return {u["anahtar"].split("-")[0] for u in uyari}

    def test_red_ve_zayif_ctr_ve_satissiz_tik(self):
        m = {"reklamlar": [reklam("1", "DISAPPROVED"), reklam("2")],
             "toplam": {"2": {"spend": "120", "impressions": "5000", "inline_link_clicks": "320",
                              "inline_link_click_ctr": "0.5", "cost_per_inline_link_click": "0.4",
                              "frequency": "1.2"}},
             "bugun": {}}
        self.assertEqual(self.anahtarlar(m, []), {"red", "ctr", "satissiz"})

    def test_harcamasiz_set_teslim_uyarisi(self):
        m = {"reklamlar": [reklam("1")], "toplam": {}, "bugun": {}}
        self.assertIn("teslim", self.anahtarlar(m, []))

    def test_okunamayan_kaynak_sifir_sayilmaz(self):
        uyari, satir = ki.degerlendir(K, None, None, SIMDI)
        self.assertEqual({u["anahtar"].split("-")[0] for u in uyari}, {"meta", "trendyol"})
        self.assertIn("Trendyol satış: OKUNAMADI", satir)

    def test_satis_sayilir(self):
        m = {"reklamlar": [reklam("1")],
             "toplam": {"1": {"spend": "100", "impressions": "100", "inline_link_clicks": "10"}},
             "bugun": {}}
        _, satir = ki.degerlendir(K, m, [{"siparis": "9", "barkod": "111", "adet": 2, "tutar": 500.0}], SIMDI)
        metin = "\n".join(satir)
        self.assertIn("1 sipariş, 2 adet", metin)
        self.assertIn("LUCIDERM 2", metin)
        self.assertIn("5.00", metin)

    def test_ozet_veri_okunamayani_sifir_saymaz(self):
        v = ki.ozet_veri(K, None, None)
        self.assertIsNone(v["harcama"])
        self.assertIsNone(v["satis"])
        m = {"reklamlar": [reklam("1"), reklam("2")],
             "toplam": {"1": {"spend": "10.5", "inline_link_clicks": "4"},
                        "2": {"spend": "2", "inline_link_clicks": "1"}},
             "bugun": {"1": {"spend": "3"}}}
        v = ki.ozet_veri(K, m, [{"siparis": "9", "barkod": "111", "adet": 2, "tutar": 500.0}])
        self.assertEqual((v["harcama"], v["tik"]), (12.5, 5))
        self.assertEqual(v["setler"]["AS1"], {"butce": 400.0, "harcama": 12.5, "bugun": 3.0})
        self.assertEqual(v["satis"], {"siparis": 1, "adet": 2, "ciro": 500.0, "urunler": {"LUCIDERM": 2}})


if __name__ == "__main__":
    unittest.main()
