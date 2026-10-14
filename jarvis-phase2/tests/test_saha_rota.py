#!/usr/bin/env python3
"""Saha rotası: prototipte ÖLÇÜLEN üç kusurun geri gelmemesi.

Bu testlerin hepsi gerçek bir koşudan geliyor. Sincan'da Esenkent
istasyonundan başlatılan ilk prototip şunları gösterdi:

  1. "Reyhan Eczanesi" 5 metre arayla İKİ KEZ listelendi (OSM'de hem nokta
     hem alan). Saha elemanı aynı kapıyı iki kez çalardı.
  2. 15 durak için 13,5 km çıktı -- açgözlü sıralama sokak sonunda karşı
     mahalleye zıplıyor.
  3. İlk durağa 11 km yürünüyordu, çünkü başlangıç istasyonu hedeflere
     bakılmadan seçilmişti.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

from jarvis import saha_rota  # noqa: E402


def nokta(ad, enlem, boylam, **ek):
    k = {"ad": ad, "enlem": enlem, "boylam": boylam}
    k.update(ek)
    return k


class MesafeTest(unittest.TestCase):

    def test_ayni_nokta_sifir(self):
        self.assertEqual(saha_rota.mesafe_m((39.96, 32.58), (39.96, 32.58)), 0.0)

    def test_bilinen_mesafe(self):
        """1 enlem derecesi ~111 km. Birim karismasi en sinsi hatalardan."""
        d = saha_rota.mesafe_m((39.0, 32.0), (40.0, 32.0))
        self.assertGreater(d, 110000)
        self.assertLess(d, 112000)


class KopyaTest(unittest.TestCase):

    def test_ayni_ad_yakin_mesafe_teklesir(self):
        """🔴 Prototipte olctu: Reyhan Eczanesi 5 m arayla iki kez cikti."""
        noktalar = [
            nokta("Reyhan Eczanesi", 39.9700, 32.5800),
            nokta("Reyhan Eczanesi", 39.97004, 32.58003),   # ~5 m
        ]
        temiz, atilan = saha_rota.kopyalari_ayikla(noktalar)
        self.assertEqual(len(temiz), 1)
        self.assertEqual(atilan, 1)

    def test_ayni_ad_uzak_mesafe_TEKLESMEZ(self):
        """Zincir eczaneler var; 300 m otesi ayri isletmedir."""
        noktalar = [
            nokta("Reyhan Eczanesi", 39.9700, 32.5800),
            nokta("Reyhan Eczanesi", 39.9730, 32.5800),     # ~333 m
        ]
        temiz, atilan = saha_rota.kopyalari_ayikla(noktalar)
        self.assertEqual(len(temiz), 2)
        self.assertEqual(atilan, 0)

    def test_adsiz_kayitlar_ASLA_birlestirilmez(self):
        """Bilmedigimiz icin silmek, veriyi kaybetmenin en sessiz yolu."""
        noktalar = [
            nokta(None, 39.9700, 32.5800),
            nokta("", 39.97001, 32.58001),
        ]
        temiz, atilan = saha_rota.kopyalari_ayikla(noktalar)
        self.assertEqual(len(temiz), 2)
        self.assertEqual(atilan, 0)


class RotaTest(unittest.TestCase):

    def test_hedef_yoksa_durum_ayri(self):
        s = saha_rota.rota_kur((39.96, 32.58), [])
        self.assertEqual(s["durum"], "HEDEF_YOK")
        self.assertEqual(s["duraklar"], [])

    def test_sira_ve_adim_mesafesi_yazilir(self):
        noktalar = [nokta("A", 39.9700, 32.5800), nokta("B", 39.9702, 32.5800)]
        s = saha_rota.rota_kur((39.9699, 32.5800), noktalar)
        self.assertEqual([d["sira"] for d in s["duraklar"]], [1, 2])
        for d in s["duraklar"]:
            self.assertIn("onceki_mesafe_m", d)
            self.assertGreaterEqual(d["onceki_mesafe_m"], 0)

    def test_toplam_adimlarin_toplamina_esit(self):
        noktalar = [nokta(c, 39.97 + i * 0.0005, 32.58) for i, c in enumerate("ABCDE")]
        s = saha_rota.rota_kur((39.9695, 32.58), noktalar)
        adimlar = sum(d["onceki_mesafe_m"] for d in s["duraklar"])
        self.assertAlmostEqual(adimlar, s["toplam_m"], delta=1.0)

    def test_durak_tavani_asilmaz(self):
        noktalar = [nokta("N%d" % i, 39.97 + i * 0.0003, 32.58) for i in range(40)]
        s = saha_rota.rota_kur((39.9695, 32.58), noktalar, en_fazla_durak=10)
        self.assertEqual(len(s["duraklar"]), 10)

    def test_zikzak_duzeltilir(self):
        """🔴 Acgozlu siralama sokak sonunda karsi mahalleye ziplayabiliyor.

        Iki kume: yakin dort nokta ve uzakta bir nokta. Acgozlu, uzaga
        gidip geri donebilir; 2-opt bunu duzeltmeli. Olcut: iyilesme
        raporlanir ve toplam, ham acgozluden BUYUK OLAMAZ.
        """
        noktalar = [
            nokta("A", 39.9700, 32.5800), nokta("B", 39.9701, 32.5801),
            nokta("C", 39.9702, 32.5802), nokta("D", 39.9703, 32.5803),
            nokta("UZAK", 39.9760, 32.5860),
        ]
        s = saha_rota.rota_kur((39.9699, 32.5799), noktalar)
        self.assertGreaterEqual(s["iyilesme_m"], 0.0,
                                "iyilestirme rotayi UZATAMAZ")
        self.assertEqual(len(s["duraklar"]), 5)

    def test_kopya_rotada_da_ayiklanir(self):
        noktalar = [
            nokta("X Eczanesi", 39.9700, 32.5800),
            nokta("X Eczanesi", 39.97004, 32.58003),
            nokta("Y Eczanesi", 39.9705, 32.5805),
        ]
        s = saha_rota.rota_kur((39.9699, 32.5799), noktalar)
        self.assertEqual(s["kopya_ayiklanan"], 1)
        self.assertEqual(len(s["duraklar"]), 2)


class BaslangicTest(unittest.TestCase):

    def test_hedeflere_yakin_olan_secilir(self):
        """🔴 Prototipte ilk duraga 11 km yuruyordu: baslangic hedeflere
        bakilmadan secilmisti."""
        adaylar = [
            nokta("UZAK ISTASYON", 39.8000, 32.4000),
            nokta("YAKIN ISTASYON", 39.9698, 32.5798),
        ]
        hedefler = [nokta("A", 39.9700, 32.5800), nokta("B", 39.9702, 32.5802)]
        secim = saha_rota.baslangic_sec(adaylar, hedefler)
        self.assertEqual(secim["ad"], "YAKIN ISTASYON")

    def test_aday_ya_da_hedef_yoksa_none(self):
        self.assertIsNone(saha_rota.baslangic_sec([], [nokta("A", 39.97, 32.58)]))
        self.assertIsNone(saha_rota.baslangic_sec([nokta("A", 39.97, 32.58)], []))


if __name__ == "__main__":
    unittest.main()
