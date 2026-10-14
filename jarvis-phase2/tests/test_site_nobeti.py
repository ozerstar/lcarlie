"""site-nobeti.py degerlendirme mantigi.

NEDEN VAR
Bu betik gunde iki kez KENDILIGINDEN kosuyor ve bulgu yaziyor. Sessizce
bozulursa kimse fark etmez: ya gercek bir arizayi kacirir (site coker,
panel sessiz kalir) ya da her kosuda yanlis bulgu uretip onay kuyrugunu
bogar. Iki yon de olculur.

🔴 AG YOK. Yalniz saf degerlendirme fonksiyonu (_bulgular) ve URL
   kodlamasi sinaniyor; testler internete cikmaz, siteyi yormaz ve
   sitenin o anki haline bagli degildir.

🔴 HER OLUMLU TESTIN TERS YONU VAR. "Ariza yakalandi" demek yetmez -
   her seye bulgu yazan bir kod da o testleri gecerdi. Saglikli sayfada
   SUSTUGU ayrica olculur.
"""
from __future__ import annotations
from tests import betik_yolu

import importlib.util
import pathlib
import unittest

BETIK = pathlib.Path(betik_yolu("site-nobeti.py"))


def _yukle():
    """Tireli dosya adi normal import edilemez; yoldan yuklenir."""
    spec = importlib.util.spec_from_file_location("site_nobeti", BETIK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sn = _yukle()


def _saglikli(**degis):
    """Sorunsuz bir olcum. Testler bunun uzerinde TEK sey bozar."""
    olcum = {
        "url": "https://www.lcarlie.shop/urun/vireon",
        "durum": 200,
        "boyut": 120_000,
        "sure": 0.6,
        "baslik": "VIREON FOR MEN",
        "aciklama": "Erkek bakim kremi",
        "canonical": "https://www.lcarlie.shop/urun/vireon",
        "noindex": False,
        "meta_refresh": None,
    }
    olcum.update(degis)
    return olcum


def _kodlar(bulgular):
    return {k for _onem, k, _sebep, _kanit in bulgular}


def _onemler(bulgular):
    return {o for o, _k, _s, _kanit in bulgular}


class SaglikliSayfadaSusar(unittest.TestCase):
    """🔴 TERS YON: her seye bulgu yazan bir kod tum digerlerini gecerdi."""

    def test_saglikli_sayfa_tabansiz_bulgu_uretmez(self):
        self.assertEqual(sn._bulgular(_saglikli(), None), [])

    def test_saglikli_sayfa_ayni_tabanla_bulgu_uretmez(self):
        o = _saglikli()
        taban = {"durum": 200, "boyut": 120_000, "sure": 0.6, "baslik": "VIREON FOR MEN"}
        self.assertEqual(sn._bulgular(o, taban), [])


class ErisimSorunlari(unittest.TestCase):
    def test_ulasilamayan_adres_kritik(self):
        b = sn._bulgular(_saglikli(hata="TimeoutError: zaman asimi"), None)
        self.assertIn("site_erisim", _kodlar(b))
        self.assertIn("CRITICAL", _onemler(b))

    def test_hata_varken_baska_kontrol_kosulmaz(self):
        """Ulasilamayan sayfada 'basligi bos' demek gurultudur."""
        b = sn._bulgular(_saglikli(hata="OSError", baslik=None, aciklama=None), None)
        self.assertEqual(len(b), 1)

    def test_404_kritik(self):
        b = sn._bulgular(_saglikli(durum=404), None)
        self.assertIn("site_erisim", _kodlar(b))
        self.assertIn("CRITICAL", _onemler(b))

    def test_200_kritik_degil(self):
        """TERS YON: her durum kodunu ariza sayan kod yakalanir."""
        self.assertNotIn("CRITICAL", _onemler(sn._bulgular(_saglikli(), None)))


class MetaRefreshYakalanir(unittest.TestCase):
    """Bu testin sebebi olculmus bir vaka.

    lcarlie.com.tr HTTP **200** donuyor ama govdesi bir
    <meta http-equiv="refresh"> sayfasi. Durum koduna bakan her izleme
    'saglikli' der; arama motorlari ise meta-refresh'i 301 gibi saymaz,
    yani o alan adinin SEO degeri aktarilmiyor.
    """

    def test_200_donen_meta_refresh_bulgu_uretir(self):
        b = sn._bulgular(_saglikli(meta_refresh="0; URL='https://www.lcarlie.shop/'"), None)
        self.assertIn("site_seo", _kodlar(b))
        self.assertTrue(any("meta-refresh" in s for _o, _k, s, _kn in b))

    def test_meta_refresh_yokken_bulgu_uretmez(self):
        """TERS YON: her sayfaya SEO bulgusu yazan kod yakalanir."""
        self.assertNotIn("site_seo", _kodlar(sn._bulgular(_saglikli(), None)))


class SeoKontrolleri(unittest.TestCase):
    def test_noindex_kritik(self):
        b = sn._bulgular(_saglikli(noindex=True), None)
        self.assertIn("CRITICAL", _onemler(b))
        self.assertTrue(any("NOINDEX" in s for _o, _k, s, _kn in b))

    def test_bos_baslik_uyari(self):
        b = sn._bulgular(_saglikli(baslik="   "), None)
        self.assertTrue(any("title" in s for _o, _k, s, _kn in b))

    def test_aciklamasiz_sayfa_yalniz_bilgi(self):
        """Eksik description bir ARIZA degil; kritik sayilirsa gurultu olur."""
        b = sn._bulgular(_saglikli(aciklama=None), None)
        self.assertEqual(_onemler(b), {"INFO"})


class GerilemeKarsilastirmasi(unittest.TestCase):
    TABAN = {"durum": 200, "boyut": 120_000, "sure": 0.6, "baslik": "VIREON FOR MEN"}

    def test_durum_degisimi_yakalanir(self):
        b = sn._bulgular(_saglikli(durum=500), self.TABAN)
        self.assertIn("site_erisim", _kodlar(b))

    def test_buyuk_kuculme_yakalanir(self):
        """Sayfa yarilanirsa icerik eksik yukleniyor olabilir."""
        b = sn._bulgular(_saglikli(boyut=50_000), self.TABAN)
        self.assertIn("site_gerileme", _kodlar(b))

    def test_kucuk_dalgalanma_bulgu_uretmez(self):
        """🔴 TERS YON: esik olmadan her bayt farki bulgu olurdu."""
        b = sn._bulgular(_saglikli(boyut=110_000), self.TABAN)
        self.assertNotIn("site_gerileme", _kodlar(b))

    def test_ciddi_yavaslama_yakalanir(self):
        b = sn._bulgular(_saglikli(sure=3.0), self.TABAN)
        self.assertIn("site_gerileme", _kodlar(b))

    def test_hafif_yavaslama_bulgu_uretmez(self):
        b = sn._bulgular(_saglikli(sure=0.9), self.TABAN)
        self.assertNotIn("site_gerileme", _kodlar(b))

    def test_baslik_degisimi_bilgi_olarak_gecer(self):
        b = sn._bulgular(_saglikli(baslik="Bambaska Bir Baslik"), self.TABAN)
        self.assertTrue(any("baslig" in s.lower() or "başlığ" in s.lower()
                            for _o, _k, s, _kn in b))

    def test_taban_yokken_gerileme_aranmaz(self):
        """Ilk kosuda karsilastirilacak bir sey yok; uydurulmamali."""
        b = sn._bulgular(_saglikli(boyut=1_000), None)
        self.assertNotIn("site_gerileme", _kodlar(b))


class UrlKodlamasi(unittest.TestCase):
    """Sitemap Turkce karakterli adres iceriyor; kodlanmazsa istek patlar."""

    def test_turkce_karakter_kodlanir(self):
        cikti = sn._kodla("https://www.lcarlie.shop/category/yüz-bakımı")
        self.assertNotIn("ü", cikti)
        self.assertTrue(cikti.startswith("https://www.lcarlie.shop/category/"))

    def test_zaten_kodlanmis_adres_BOZULMAZ(self):
        """🔴 '%' guvenli birakilmazsa '%20' -> '%2520' olur ve adres bozulur."""
        url = "https://www.lcarlie.shop/a%20b"
        self.assertEqual(sn._kodla(url), url)

    def test_sade_adres_degismez(self):
        url = "https://www.lcarlie.shop/urun/vireon"
        self.assertEqual(sn._kodla(url), url)


if __name__ == "__main__":
    unittest.main()
