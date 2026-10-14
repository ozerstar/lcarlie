"""Guncel Olaylar departmani: bulten UYDURAMAZ.

Bu sistemde model bugun IKI KEZ olgu uydurdu (INTIMBLANC icindekileri ve
VIREON icin bastan asagi yanlis bir INCI listesi). Guclu model bunu
bitirmiyor, sadece seyreklestiriyor. Haber bulteni ayni riski tasir ve
dahasi bir IS KARARINA girdi olur -- o yuzden kapi istemde degil KODDA.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

_spec = importlib.util.spec_from_file_location(
    "guncel_olaylar", KOK / "scripts" / "guncel-olaylar.py")
go = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(go)

KAYNAKLAR = [
    {"aci": "ekonomi", "baslik": "TUIK enflasyon", "url": "https://aa.com.tr/x",
     "tarih": "2026-09-19", "metin": "yillik yuzde 31,51"},
    {"aci": "duzenleme", "baslik": "e-ticaret kanunu", "url": "https://t24.com.tr/y",
     "tarih": "", "metin": "degisiklik"},
]


class _Model:
    def __init__(self, metin):
        self.metin = metin

    def generate(self, *a, **k):
        return ({"text": self.metin, "model": "sahte"}, "EXTERNAL", 1)


class KaynaksizMaddeYAZILMAZ(unittest.TestCase):
    def test_listede_olmayan_kaynak_no_DUSER(self):
        # Model 99 numarali bir kaynak uydurursa madde kaydedilmemeli.
        model = _Model('{"maddeler":[{"kaynak_no":99,"baslik":"Uydurma",'
                       '"ozet":"yok","neden_onemli":"-","onem":"KRITIK"}]}')
        maddeler, _ = go.madde_uret(KAYNAKLAR, model)
        self.assertEqual(maddeler, [])

    def test_gecerli_kaynak_no_URL_e_baglanir(self):
        model = _Model('{"maddeler":[{"kaynak_no":1,"baslik":"Enflasyon",'
                       '"ozet":"ozet","neden_onemli":"etki","onem":"KRITIK"}]}')
        [madde], _ = go.madde_uret(KAYNAKLAR, model)
        self.assertEqual(madde["kaynak_url"], "https://aa.com.tr/x")
        self.assertEqual(madde["aci"], "ekonomi")

    def test_bos_baslik_veya_ozet_DUSER(self):
        model = _Model('{"maddeler":[{"kaynak_no":1,"baslik":"","ozet":"x"},'
                       '{"kaynak_no":2,"baslik":"y","ozet":""}]}')
        maddeler, _ = go.madde_uret(KAYNAKLAR, model)
        self.assertEqual(maddeler, [])

    def test_bozuk_json_cokmez_bos_doner(self):
        maddeler, _ = go.madde_uret(KAYNAKLAR, _Model("json degil bu"))
        self.assertEqual(maddeler, [])

    def test_gecersiz_onem_BILGI_ye_duser(self):
        model = _Model('{"maddeler":[{"kaynak_no":1,"baslik":"a","ozet":"b",'
                       '"onem":"COK_ACIL"}]}')
        [madde], _ = go.madde_uret(KAYNAKLAR, model)
        self.assertEqual(madde["onem"], "BILGI")


class SosyalMedyaKAYNAK_OLAMAZ(unittest.TestCase):
    """Ilk kosuda (20.09.2026) model enflasyon rakamini bir YOUTUBE videosuna,
    perakende verisini bir FACEBOOK videosuna dayandirdi. Icerik dogru olsa
    bile is bulteninde TUIK verisi icin sosyal medya videosu kaynak
    gosterilemez: okuyan dogrulayamaz, arsivi kaybolur."""

    def test_video_ve_sosyal_alanlar_elenir(self):
        for adres in ("https://www.youtube.com/watch?v=x",
                      "https://youtu.be/x",
                      "https://www.facebook.com/a/videos/1",
                      "https://x.com/biri/status/1",
                      "https://www.instagram.com/p/x/"):
            self.assertFalse(go.alintilanabilir(adres), adres)

    def test_haber_ve_resmi_siteler_gecer(self):
        for adres in ("https://www.aa.com.tr/tr/ekonomi/x",
                      "https://t24.com.tr/ekonomi/y",
                      "https://www.tuik.gov.tr/z",
                      "https://herguner.av.tr/k"):
            self.assertTrue(go.alintilanabilir(adres), adres)


class SorgularSOMUT(unittest.TestCase):
    """'haberleri/sektoru/pazar' gibi genel kelimeler alaka eslesmesini
    sulandiriyor: ilk sektor sorgusu 15 sayfa indirip 15'ini birden eledi,
    iki kosuda da 0 kaynak verdi."""

    def test_acilarda_haberleri_kelimesi_yok(self):
        for _, sorgu in go.ACILAR:
            self.assertNotIn("haberleri", sorgu.lower())

    def test_en_az_dort_aci_var(self):
        # Tek sorgu tek tur kaynak getirir; resim aci cesitliliginden cikar.
        self.assertGreaterEqual(len(go.ACILAR), 4)

    def test_aci_adlari_benzersiz(self):
        adlar = [a for a, _ in go.ACILAR]
        self.assertEqual(len(adlar), len(set(adlar)))


class KaynakYokAYRI_DURUM(unittest.TestCase):
    def test_kaynak_yok_durumu_kodda_var(self):
        # Satirin hic olmamasi "o gun calismadi" demek; KAYNAK_YOK ise
        # "calisti, bulamadi". Ikisi karistirilirsa olu cron fark edilmez.
        kaynak = (KOK / "scripts" / "guncel-olaylar.py").read_text(encoding="utf-8")
        self.assertIn("KAYNAK_YOK", kaynak)
        self.assertIn("uydurma madde yazılmaz", kaynak)


if __name__ == "__main__":
    unittest.main()
