"""Reklam -> urun eslesmesi: yanlis urune baglamak en pahali hata.

Musteri "fiyati nedir?" yaziyor ve urunu SOYLEMIYOR (olculdu: 540 mesajin
0'inda urun adi var). Urun yalnizca geldigi reklamdan bilinir. O eslesme
yanlissa musteriye YANLIS URUNUN FIYATI gider -- fiyat soylememekten cok
daha pahali.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

# Betik tire iceriyor, normal import edilemez.
_spec = importlib.util.spec_from_file_location(
    "reklam_urun_esle", KOK / "scripts" / "reklam-urun-esle.py")
ru = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ru)

from jarvis.satis_dialog import _sade  # noqa: E402

URUNLER = [
    ("1", "VIREON FOR MEN · Erkek Bakım Kremi"),
    ("2", "BABY RESCUE (Anlık Yatıştırıcı)"),
    ("3", "BABYSOL (Güneş Kremi)"),
    ("4", "BABYSHOWER (Şampuan)"),
    ("5", "BABYDENT (Bebek ve Çocuklar İçin Diş Bakım Jeli)"),
    ("6", "HYDRAVIE | Yoğun Nemlendirici Yüz Kremi"),
    ("7", "KINESIS + (Sporcu Bakım Kremi)"),
]


class AyirtEdiciKod(unittest.TestCase):
    def test_cakisan_ilk_kelime_IKI_kelimeye_cikar(self):
        # BABY tek basina BABYSOL/BABYSHOWER/BABYDENT ile cakisirdi.
        kodlar = ru.kod_uret(URUNLER)
        self.assertIn(_sade("BABY RESCUE"), kodlar)
        self.assertNotIn(_sade("BABY"), kodlar)

    def test_benzersiz_ilk_kelime_tek_kalir(self):
        kodlar = ru.kod_uret(URUNLER)
        self.assertIn(_sade("VIREON"), kodlar)
        self.assertIn(_sade("HYDRAVIE"), kodlar)

    def test_kisa_kod_alinmaz(self):
        # 4 harften kisa kod her metne uyar ve her reklami yanlis baglar.
        kodlar = ru.kod_uret([("9", "AB (Test)")])
        self.assertEqual(kodlar, {})


class EnUzunKodKAZANIR(unittest.TestCase):
    def setUp(self):
        self.kodlar = ru.kod_uret(URUNLER)

    def test_baby_rescue_metni_BABYSOL_a_baglanmaz(self):
        sonuc = ru.urun_esle(_sade("BABY RESCUE anlık yatıştırıcı krem"), self.kodlar)
        self.assertIsNotNone(sonuc)
        self.assertEqual(sonuc[1], "BABY RESCUE (Anlık Yatıştırıcı)")

    def test_babysol_metni_kendi_urunune_baglanir(self):
        sonuc = ru.urun_esle(_sade("BABYSOL güneş kremi bebekler için"), self.kodlar)
        self.assertEqual(sonuc[1], "BABYSOL (Güneş Kremi)")

    def test_turkce_buyuk_I_bozmaz(self):
        # "I".lower() Turkce yerelde noktasiz i uretir ve eslesme kacar.
        sonuc = ru.urun_esle(_sade("HYDRAVİE YOĞUN NEMLENDİRİCİ"), self.kodlar)
        self.assertIsNotNone(sonuc)


class UrunYoksaUYDURULMAZ(unittest.TestCase):
    def test_marka_reklaminda_eslesme_yok(self):
        kodlar = ru.kod_uret(URUNLER)
        metin = _sade("Bakım, kendinize ayırdığınız en değerli zamandır. L'CARLIÉ")
        self.assertIsNone(ru.urun_esle(metin, kodlar))

    def test_bos_metin_cokmez(self):
        self.assertIsNone(ru.urun_esle("", ru.kod_uret(URUNLER)))


class ElleKonulanaDOKUNULMAZ(unittest.TestCase):
    """Bu projede kurulum betikleri elle yapilmis degisiklikleri kosulsuz
    ezdigi icin canli bir kez kirildi. Ayni hata tekrarlanmiyor."""

    def test_sql_elle_satirini_disliyor(self):
        kaynak = (KOK / "scripts" / "reklam-urun-esle.py").read_text(encoding="utf-8")
        # Iki ayri koruma olmali: adaylardan cikarma VE ON CONFLICT sarti.
        self.assertIn("kaynak='ELLE'", kaynak)
        self.assertIn("core.reklam_urun.kaynak <> 'ELLE'", kaynak)


if __name__ == "__main__":
    unittest.main()
