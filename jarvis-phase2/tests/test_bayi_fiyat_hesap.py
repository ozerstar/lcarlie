# -*- coding: utf-8 -*-
"""Bayi kademe fiyatı hesabı.

Sahibin kararıyla (25.09.2026) kademe fiyatları artık basılı listeden
OKUNMUYOR, Wix satış fiyatından HESAPLANIYOR. Hesap yanlışsa sahada
yanlış fiyat verilir ve bunu kimse fark etmez -- rakam makul görünür.
Bu yüzden kural burada kilitli.

🔴 YUVARLAMA BURADA KANITLANDI. Kural (tam TL'ye, yarımı yukarı) basılı
listenin çelişkisiz 160 hücresinin hepsini birebir üretti. Aşağıdaki
vakalar o 160'ın içinden, özellikle yarım-TL düşen satırlardan seçildi:
kural sessizce bankacı yuvarlamasına (ROUND_HALF_EVEN) kayarsa 2242,5
-> 2242 olur ve test kırmızı yanar.
"""
import unittest
from decimal import Decimal
from importlib.machinery import SourceFileLoader
from pathlib import Path

_YOL = Path(__file__).resolve().parent.parent / "scripts" / "bayi-fiyat-hesapla.py"
_h = SourceFileLoader("bayi_fiyat_hesapla", str(_YOL)).load_module()

D = Decimal
KADEME = {ad: (carpan, bolen) for ad, _e, carpan, bolen in _h.KADEMELER}


def hesapla(psf, ad):
    carpan, bolen = KADEME[ad]
    return _h.kademe(D(str(psf)), carpan, bolen)


class TestKademeHesabi(unittest.TestCase):
    def test_tam_bolunen(self):
        # 900 her kademede tam bolunur: kural burada tartismasiz.
        self.assertEqual(hesapla(900, "isk30_haric"), 525)
        self.assertEqual(hesapla(900, "isk30_dahil"), 630)
        self.assertEqual(hesapla(900, "isk40_haric"), 450)
        self.assertEqual(hesapla(900, "isk40_dahil"), 540)
        self.assertEqual(hesapla(900, "trendyol"), 1035)

    def test_yarim_yukari_yuvarlanir(self):
        # 1950 x 1,15 = 2242,5. Bankaci yuvarlamasi 2242 derdi;
        # basili liste 2243 diyor. Kural yarimi YUKARI atar.
        self.assertEqual(hesapla(1950, "trendyol"), 2243)
        # 1850 x 1,15 = 2127,5 -> 2128
        self.assertEqual(hesapla(1850, "trendyol"), 2128)
        # 950 x 1,15 = 1092,5 -> 1093
        self.assertEqual(hesapla(950, "trendyol"), 1093)
        # 1950 x 0,70 / 1,2 = 1137,5 -> 1138
        self.assertEqual(hesapla(1950, "isk30_haric"), 1138)

    def test_asagi_yuvarlanan(self):
        # 1250 x 0,70 / 1,2 = 729,166... -> 729
        self.assertEqual(hesapla(1250, "isk30_haric"), 729)
        # 1100 x 0,70 / 1,2 = 641,666... -> 642
        self.assertEqual(hesapla(1100, "isk30_haric"), 642)

    def test_kdv_haric_dahilden_dusuk(self):
        # KDV haric fiyat, KDV dahilden her zaman dusuk olmali.
        for psf in (900, 1020, 1100, 1250, 1850, 1950, 2100, 2400):
            self.assertLess(hesapla(psf, "isk30_haric"),
                            hesapla(psf, "isk30_dahil"), "PSF %d" % psf)
            self.assertLess(hesapla(psf, "isk40_haric"),
                            hesapla(psf, "isk40_dahil"), "PSF %d" % psf)

    def test_iskonto_arttikca_fiyat_duser(self):
        # %40 iskonto, %30 iskontodan UCUZ olmali. Ters cevrilirse
        # saha pahaliyi "daha iyi fiyat" diye verir.
        for psf in (900, 1100, 1950, 2400):
            self.assertLess(hesapla(psf, "isk40_dahil"),
                            hesapla(psf, "isk30_dahil"), "PSF %d" % psf)

    def test_trendyol_psf_uzerinde(self):
        # Trendyol fiyati PSF'in USTUNDE (komisyon) -- altina duserse
        # kendi sitemizi pazaryerine karsi ucuzlatmis oluruz.
        for psf in (900, 1100, 1950, 2400):
            self.assertGreater(hesapla(psf, "trendyol"), psf, "PSF %d" % psf)


class TestBarkodAyrimi(unittest.TestCase):
    """Barkod şüphesi fiyat çelişkisi DEĞİLDİR."""

    def test_barkod_notu_olan_urunler(self):
        # Uc urunun barkodu supheli; ucunun de FIYATI gecerli.
        self.assertEqual(set(_h.BARKOD_NOTU),
                         {"optywave", "buguard", "softguard"})

    def test_her_notun_gerekcesi_var(self):
        # Gerekcesiz uyari, okuyani yalniz huzursuz eder.
        for slug, notu in _h.BARKOD_NOTU.items():
            self.assertGreater(len(notu.strip()), 40, slug)
            self.assertIn("8684", notu, slug)


if __name__ == "__main__":
    unittest.main()
