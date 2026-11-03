"""aksiyon-uygulayici.py: yaz -> GERI OKU -> dogrula sozlesmesi.

Ag ve veritabani hic cagrilmaz; _istek ve _anahtar sahte.
"""
import importlib.util
import unittest
from pathlib import Path

YOL = Path(__file__).resolve().parent.parent / "scripts" / "aksiyon-uygulayici.py"
spec = importlib.util.spec_from_file_location("aksiyon_uygulayici", YOL)
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)

URUN = "5f7dd59c-6910-4088-90d4-af139a01a3c0"


def v3(fiyat, ad="Canta", varyant_sayisi=1):
    """Wix Catalog V3 urun gorunumu: fiyat varyantta, guncelleme revision ister."""
    return {"product": {"name": ad, "revision": "7", "variantsInfo": {"variants": [
        {"id": f"v{i}", "price": {"actualPrice": {"amount": f"{fiyat:.2f}"}}}
        for i in range(varyant_sayisi)]}}}


class SahteAg:
    """GET'te sirayla verilen yanitlari dondurur, yazmalari kaydeder."""

    def __init__(self, okumalar):
        self.okumalar = list(okumalar)
        self.yazmalar = []

    def __call__(self, yontem, url, basliklar, govde=None):
        if yontem == "GET":
            return self.okumalar.pop(0)
        self.yazmalar.append((yontem, url, govde))
        return {}


class Temel(unittest.TestCase):
    def setUp(self):
        self._eski = (au._istek, au._anahtar)
        au._anahtar = lambda ad: "sahte-" + ad

    def tearDown(self):
        au._istek, au._anahtar = self._eski


class MetaKampanya(Temel):
    def test_durdurur_ve_geri_okur(self):
        ag = SahteAg([{"name": "AS1", "status": "ACTIVE"},
                      {"name": "AS1", "status": "PAUSED", "effective_status": "PAUSED"}])
        au._istek = ag
        ozet = au.meta_kampanya({"campaign_ref": "120200", "operation": "PAUSE", "reason": "x"})
        self.assertEqual(len(ag.yazmalar), 1)
        self.assertEqual(ag.yazmalar[0][2], {"status": "PAUSED"})
        self.assertIn("ACTIVE -> PAUSED", ozet)

    def test_zaten_durmussa_yazmaz(self):
        ag = SahteAg([{"name": "AS1", "status": "PAUSED"}])
        au._istek = ag
        au.meta_kampanya({"campaign_ref": "120200", "operation": "PAUSE", "reason": "x"})
        self.assertEqual(ag.yazmalar, [])

    def test_yazildi_ama_degismediyse_basarili_sayilmaz(self):
        # 21.09 Trendyol dersi: SUCCESS donup hicbir sey degistirmemek.
        ag = SahteAg([{"status": "ACTIVE"}, {"status": "ACTIVE"}])
        au._istek = ag
        with self.assertRaises(au.KaliciHata):
            au.meta_kampanya({"campaign_ref": "120200", "operation": "PAUSE", "reason": "x"})

    def test_sozlesme_disi_islem_reddedilir(self):
        au._istek = SahteAg([])
        with self.assertRaises(au.KaliciHata):
            au.meta_kampanya({"campaign_ref": "120200", "operation": "DELETE", "reason": "x"})
        with self.assertRaises(au.KaliciHata):
            au.meta_kampanya({"campaign_ref": "act_1/../x", "operation": "PAUSE", "reason": "x"})


class FiyatDegistir(Temel):
    def test_yazar_ve_geri_okur(self):
        ag = SahteAg([v3(3000), v3(2850)])
        au._istek = ag
        ozet = au.fiyat_degistir({"product_ref": URUN, "proposed_price": 2850,
                                  "currency": "TRY", "reason": "x"})
        self.assertEqual(ag.yazmalar[0][2], {"product": {"revision": "7", "variantsInfo": {
            "variants": [{"id": "v0", "price": {"actualPrice": {"amount": "2850.00"}}}]}}})
        self.assertIn("3000.0 -> 2850.0", ozet)

    def test_buyuk_sicrama_yazim_hatasi_sayilir(self):
        ag = SahteAg([v3(1265)])
        au._istek = ag
        with self.assertRaises(au.KaliciHata):
            au.fiyat_degistir({"product_ref": URUN, "proposed_price": 126.5,
                               "currency": "TRY", "reason": "x"})
        self.assertEqual(ag.yazmalar, [])

    def test_geri_okunan_fiyat_farkliysa_basarisiz(self):
        ag = SahteAg([v3(3000), v3(3000)])
        au._istek = ag
        with self.assertRaises(au.KaliciHata):
            au.fiyat_degistir({"product_ref": URUN, "proposed_price": 2850,
                               "currency": "TRY", "reason": "x"})

    def test_cok_varyantli_urun_reddedilir(self):
        ag = SahteAg([v3(3000, varyant_sayisi=2)])
        au._istek = ag
        with self.assertRaises(au.KaliciHata):
            au.fiyat_degistir({"product_ref": URUN, "proposed_price": 2850,
                               "currency": "TRY", "reason": "x"})
        self.assertEqual(ag.yazmalar, [])

    def test_para_birimi_try_disinda_reddedilir(self):
        au._istek = SahteAg([])
        with self.assertRaises(au.KaliciHata):
            au.fiyat_degistir({"product_ref": URUN, "proposed_price": 10,
                               "currency": "USD", "reason": "x"})


class Kayit(unittest.TestCase):
    def test_her_uygulayici_kayitli(self):
        self.assertEqual(set(au.UYGULAYICILAR), {"META_CAMPAIGN_CHANGE", "PRICE_CHANGE"})


if __name__ == "__main__":
    unittest.main()
