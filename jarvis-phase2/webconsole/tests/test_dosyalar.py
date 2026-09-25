"""dosyalar.py testleri -- agirlik YOL KACISI tarafinda.

Bu modul panele dosya sistemi aciyor. Listeleme kusuru rahatsizlik verir;
yol kacisi kusuru sunucudaki HER dosyayi okutur. Testlerin dagilimi da
buna gore: once guvenlik, sonra islevsellik.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

_KOK = Path(tempfile.mkdtemp(prefix="dosyalar-test-"))
os.environ["JARVIS_KOK"] = str(_KOK)

import sys  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webconsole import dosyalar  # noqa: E402

dosyalar.KOK = _KOK
dosyalar.ALANLAR = {
    "sinama": ("veri", "Sinama", "test alani"),
    "yok": ("olmayan", "Yok", "klasor yok"),
}


class Kurulum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _KOK / "veri"
        (d / "alt").mkdir(parents=True, exist_ok=True)
        (d / "birinci.md").write_text("# birinci\nmetin", encoding="utf-8")
        (d / "ikinci.json").write_text('{"a": 1}', encoding="utf-8")
        (d / "bozuk.json").write_text("{yarim", encoding="utf-8")
        (d / "alt" / "ucuncu.txt").write_text("alt klasor", encoding="utf-8")
        (d / "resim.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        (_KOK / "GIZLI.txt").write_text("bu alan DISINDA", encoding="utf-8")


class YolKacisiTests(Kurulum):
    """Tek gercek risk burada. Her vaka REDDEDILMELI."""

    def test_ust_dizine_cikilamaz(self):
        for ad in ("../GIZLI.txt", "..\\GIZLI.txt", "alt/../../GIZLI.txt"):
            with self.assertRaises(dosyalar.GuvensizAd, msg=ad):
                dosyalar.icerik("sinama", ad)

    def test_mutlak_yol_reddedilir(self):
        for ad in ("/etc/passwd", "/opt/lcarlie/n8n/.env"):
            with self.assertRaises(dosyalar.GuvensizAd, msg=ad):
                dosyalar.icerik("sinama", ad)

    def test_gizli_dosya_reddedilir(self):
        with self.assertRaises(dosyalar.GuvensizAd):
            dosyalar.icerik("sinama", ".env")

    def test_bilinmeyen_alan_reddedilir(self):
        with self.assertRaises(dosyalar.AlanYok):
            dosyalar.listele("uydurma")

    def test_alan_disindaki_dosya_bulunmaz(self):
        """GIZLI.txt kokte ama alan icinde degil -- bulunmamali."""
        with self.assertRaises(FileNotFoundError):
            dosyalar.icerik("sinama", "GIZLI.txt")

    def test_gorsel_olmayan_ikili_sunulmaz(self):
        with self.assertRaises(dosyalar.GuvensizAd):
            dosyalar.ikili("sinama", "birinci.md")


class ListelemeTests(Kurulum):
    def test_alt_klasor_dahil_edilir(self):
        r = dosyalar.listele("sinama")
        adlar = {d["ad"] for d in r["dosyalar"]}
        self.assertIn("ucuncu.txt", adlar)
        self.assertEqual(r["durum"], "OK")

    def test_arama_ada_gore_suzer(self):
        r = dosyalar.listele("sinama", ara="birin")
        self.assertEqual([d["ad"] for d in r["dosyalar"]], ["birinci.md"])

    def test_tur_suzgeci(self):
        r = dosyalar.listele("sinama", tur="gorsel")
        self.assertEqual([d["ad"] for d in r["dosyalar"]], ["resim.png"])

    def test_klasor_yoksa_VERI_YOK(self):
        """'Klasor yok' ile 'okunamadi' ayni sey degildir."""
        self.assertEqual(dosyalar.listele("yok")["durum"], "VERI_YOK")

    def test_alanlar_sayar(self):
        alan = {a["alan"]: a for a in dosyalar.alanlar()}
        self.assertEqual(alan["sinama"]["durum"], "OK")
        self.assertEqual(alan["sinama"]["adet"], 5)
        self.assertEqual(alan["yok"]["durum"], "VERI_YOK")


class IcerikTests(Kurulum):
    def test_metin_okunur(self):
        r = dosyalar.icerik("sinama", "birinci.md")
        self.assertEqual(r["durum"], "OK")
        self.assertIn("# birinci", r["metin"])

    def test_json_ayristirilir(self):
        r = dosyalar.icerik("sinama", "ikinci.json")
        self.assertEqual(r["json"], {"a": 1})

    def test_bozuk_json_GIZLENMEZ(self):
        """Dosyanin kendisi bozuksa bu bir bulgudur, sessizce yutulmaz."""
        r = dosyalar.icerik("sinama", "bozuk.json")
        self.assertIn("json_hatasi", r)
        self.assertEqual(r["durum"], "OK")

    def test_kirpma_ACIKCA_soylenir(self):
        eski = dosyalar.AZAMI_METIN
        dosyalar.AZAMI_METIN = 5
        try:
            r = dosyalar.icerik("sinama", "birinci.md")
            self.assertTrue(r["kirpildi"])
            self.assertEqual(len(r["metin"]), 5)
        finally:
            dosyalar.AZAMI_METIN = eski

    def test_gorsel_icerik_cagrisi_metin_degil_der(self):
        self.assertEqual(dosyalar.icerik("sinama", "resim.png")["durum"],
                         "METIN_DEGIL")

    def test_gorsel_baytlari_ve_tipi(self):
        ham, tip = dosyalar.ikili("sinama", "resim.png")
        self.assertTrue(ham.startswith(b"\x89PNG"))
        self.assertEqual(tip, "image/png")

    def test_buyuk_gorsel_reddedilir(self):
        eski = dosyalar.AZAMI_IKILI
        dosyalar.AZAMI_IKILI = 4
        try:
            with self.assertRaises(dosyalar.GuvensizAd):
                dosyalar.ikili("sinama", "resim.png")
        finally:
            dosyalar.AZAMI_IKILI = eski


if __name__ == "__main__":
    unittest.main()
