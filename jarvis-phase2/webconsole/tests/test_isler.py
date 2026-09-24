#!/usr/bin/env python3
"""IŞLER kuyruğu: kabul edilen iş ile reddedilen istek arasındaki sınır.

Bu testlerin koruduğu üç şey var ve üçü de daha önce yaşanmış hata
sınıflarından geliyor:

  1. ATOMİK YAZMA. Hakem `bekleyen/*.json` tarayıp gördüğü dosyayı hemen
     okuyor. Yarım yazılmış dosya, işin `hata/` klasörüne düşmesi demek.
  2. SESSİZ BAŞARI YOK. Geçersiz istem kabul edilmiş gibi görünüp kuyruğa
     hiç girmemeli; bu projede panelde "tamam" yazıp hiçbir şey yapmayan
     uç daha önce görüldü.
  3. YOKLUĞUN SEBEBİ. "İş yok" ile "kuyruk okunamadı" ayrı durumlardır;
     hatırlatma da PC-2'nin KAPALI olduğunu iddia etmez, raporunun ESKİ
     olduğunu söyler.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from webconsole import isler  # noqa: E402


class IslerTest(unittest.TestCase):

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.kuyruk = Path(self._t.name) / "gorsel-kuyruk"
        for a in isler.ASAMALAR + ("cikti",):
            (self.kuyruk / a).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._t.cleanup()

    # -- A. kuyruk hali --------------------------------------------------
    def test_kuyruk_dizini_yoksa_ayri_durum(self):
        d = isler.durum(Path(self._t.name) / "olmayan")
        self.assertEqual(d["durum"], "KUYRUK_YOK")
        self.assertEqual(d["isler"], [])

    def test_bos_kuyruk_is_var_demez(self):
        d = isler.durum(self.kuyruk)
        self.assertEqual(d["durum"], "BOS")
        self.assertEqual(d["sayilar"]["bekleyen"], 0)
        self.assertIsNone(d["hatirlatma"])

    # -- B. is ekleme ----------------------------------------------------
    def test_is_eklenir_ve_bekleyende_gorunur(self):
        kayit = isler.is_ekle(self.kuyruk, "beyaz mermer zemin, dogal isik",
                              negatif="sise, kutu", adet=2, isteyen="ozer")
        dosya = self.kuyruk / "bekleyen" / (kayit["id"] + ".json")
        self.assertTrue(dosya.exists())
        okunan = json.loads(dosya.read_text(encoding="utf-8"))
        self.assertEqual(okunan["adet"], 2)
        self.assertEqual(okunan["isteyen"], "ozer")
        self.assertEqual(isler.durum(self.kuyruk)["durum"], "IS_VAR")

    def test_yazma_yarim_dosya_birakmaz(self):
        """Hakem'in gorecegi TEK sey tamamlanmis .json olmali."""
        isler.is_ekle(self.kuyruk, "yeterince uzun bir istem metni")
        kalanlar = list((self.kuyruk / "bekleyen").iterdir())
        self.assertEqual(len(kalanlar), 1)
        self.assertEqual(kalanlar[0].suffix, ".json")
        self.assertFalse(kalanlar[0].name.startswith(".yaziliyor-"))

    # -- C. dogrulama: sessiz basari YOK ---------------------------------
    def test_kisa_istem_reddedilir(self):
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "kisa")
        self.assertEqual(len(list((self.kuyruk / "bekleyen").iterdir())), 0)

    def test_bos_istem_reddedilir(self):
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "   ")

    def test_cok_uzun_istem_reddedilir(self):
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "a" * (isler.EN_COK_ISTEM + 1))

    def test_adet_siniri(self):
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "gecerli uzunlukta istem", adet=0)
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "gecerli uzunlukta istem",
                          adet=isler.EN_COK_ADET + 1)
        with self.assertRaises(isler.IsHatasi):
            isler.is_ekle(self.kuyruk, "gecerli uzunlukta istem", adet="iki")

    # -- D. hatirlatma: iddia degil gozlem -------------------------------
    def test_is_varken_bayat_rapor_hatirlatir(self):
        isler.is_ekle(self.kuyruk, "yeterince uzun bir istem metni")
        d = isler.durum(self.kuyruk, pc2_durum="BAYAT")
        self.assertIsNotNone(d["hatirlatma"])
        self.assertEqual(d["hatirlatma"]["kod"], "PC2_RAPOR_ESKI")
        metin = d["hatirlatma"]["metin"]
        # Cumle GOZLEM + SORU olmali. Teshis koymak ("makine kapali")
        # bilmedigimiz bir seyi soylemektir; sahip zaten yanindaki
        # makineye bakip karar verecek.
        self.assertIn("rapor eski", metin)
        self.assertTrue(metin.rstrip().endswith("?"),
                        "hatirlatma bir SORU ile bitmeli, hukumle degil")
        self.assertNotIn("kapalı", metin.lower(),
                         "makinenin KAPALI oldugu iddia edilemez")

    def test_is_yokken_hatirlatma_yok(self):
        d = isler.durum(self.kuyruk, pc2_durum="BAYAT")
        self.assertIsNone(d["hatirlatma"],
                          "bekleyen is yoksa hatirlatmanin konusu yok")

    def test_pc2_tazeyken_hatirlatma_yok(self):
        isler.is_ekle(self.kuyruk, "yeterince uzun bir istem metni")
        self.assertIsNone(isler.durum(self.kuyruk, pc2_durum="TAZE")["hatirlatma"])

    # -- E. bozuk dosya sessizce kaybolmaz -------------------------------
    def test_bozuk_is_dosyasi_gosterilir(self):
        (self.kuyruk / "bekleyen" / "is-bozuk.json").write_text(
            "{ bu json degil", encoding="utf-8")
        isler_listesi = isler.durum(self.kuyruk)["isler"]
        bozuklar = [i for i in isler_listesi if i.get("bozuk")]
        self.assertEqual(len(bozuklar), 1)
        self.assertEqual(bozuklar[0]["id"], "is-bozuk")

    def test_asama_bilgisi_tasinir(self):
        isler.is_ekle(self.kuyruk, "yeterince uzun bir istem metni")
        (self.kuyruk / "biten" / "is-eski.json").write_text(
            json.dumps({"id": "is-eski", "istem": "onceki is"}), encoding="utf-8")
        asamalar = {i["id"]: i["asama"] for i in isler.durum(self.kuyruk)["isler"]}
        self.assertEqual(asamalar["is-eski"], "biten")
        self.assertEqual(len(asamalar), 2)


if __name__ == "__main__":
    unittest.main()
