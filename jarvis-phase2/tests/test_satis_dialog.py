"""satis_dialog: musteriye giden cevabin uretim ve denetim kurallari.

BU DOSYANIN VAR OLMA SEBEBI BIR OLCUMDUR
20.09.2026 ilk canli denemede model, INTIMBLANC'in ICINDEKILER listesini
sifirdan uydurdu ("niasinamid, arbutin, traneksamik asit, kojik asit
dipalmitat") -- cunku o alan urun kartinda BOSTU. Mevzuat taramasi metni
TEMIZ gecirdi ve dogru davrandi: o katman yasak IDDIA arar, uydurma OLGU
aramaz. Kozmetikte uydurma bilesen listesi musteriye gidemez.

Buradaki testler o kapiyi kilitler. Istem yazarak cozulmedi ve
cozulemez: 4B yerel model kurali tutmadi. Cozum yapisal -- olgu yoksa
model HIC cagrilmaz.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis import satis_dialog as sd  # noqa: E402


def _kart(**kwargs):
    taban = dict(urun_id="u1", ad="TEST ÜRÜN", satis_fiyat=1200.0,
                 liste_fiyat=2400.0, stokta=True, aciklama="",
                 icindekiler="Saf Su, Gliserin", kullanim="Günde 2 kez")
    taban.update(kwargs)
    return sd.UrunKarti(**taban)


class PatlarsaModelHicCagrilmaz(unittest.TestCase):
    """Cagrilan model = uydurma firsati. Olgu yoksa firsat verilmez."""

    class _PatlayanModel:
        def __init__(self):
            self.cagrildi = False

        def generate(self, *a, **k):
            self.cagrildi = True
            raise AssertionError("olgu eksikken model CAGRILMAMALI")

    def test_icindekiler_bos_ise_model_cagrilmaz(self):
        layer = self._PatlayanModel()
        cevap = sd.cevap_uret("içindekiler nelerdir", _kart(icindekiler=""), layer)
        self.assertFalse(layer.cagrildi)
        self.assertEqual(cevap.mevzuat, "OLGU_EKSIK")
        self.assertFalse(cevap.gonderilebilir)

    def test_fiyat_yoksa_model_cagrilmaz(self):
        layer = self._PatlayanModel()
        cevap = sd.cevap_uret("fiyatı nedir", _kart(satis_fiyat=None), layer)
        self.assertFalse(layer.cagrildi)
        self.assertEqual(cevap.mevzuat, "OLGU_EKSIK")

    def test_olgu_eksik_cevabi_uydurmuyor_insana_aktariyor(self):
        cevap = sd.cevap_uret("içindekiler nelerdir", _kart(icindekiler=""),
                              self._PatlayanModel())
        self.assertIn("doğrulayamadım", cevap.metin)
        self.assertNotIn("niasinamid", cevap.metin.casefold())


class UydurmaSayiGecemez(unittest.TestCase):
    OLGULAR = ["Fiyat: 1.200 TL", "Stok durumu: var"]

    def test_olgudaki_sayi_gecer_ayrac_farki_onemsiz(self):
        self.assertEqual(sd.uydurma_sayi("Fiyat 1.200 TL.", self.OLGULAR), [])
        self.assertEqual(sd.uydurma_sayi("Fiyat 1200 TL.", self.OLGULAR), [])

    def test_olguda_olmayan_fiyat_yakalanir(self):
        self.assertEqual(sd.uydurma_sayi("Sadece 899 TL!", self.OLGULAR), ["899"])

    def test_uretilen_cevapta_uydurma_sayi_varsa_gonderilmez(self):
        class SahteModel:
            def generate(self, *a, **k):
                return ({"text": "Sadece 899 TL, 45 gunde sonuc.",
                         "model": "sahte"}, "LOCAL", 1)
        cevap = sd.cevap_uret("fiyatı nedir", _kart(), SahteModel())
        self.assertEqual(cevap.mevzuat, "UYDURMA_SAYI")
        self.assertFalse(cevap.gonderilebilir)


class UrunTahminEdilmez(unittest.TestCase):
    """Yanlis urunun fiyatini soylemek, fiyat soylememekten pahalidir."""

    KAYITLAR = [
        {"urun_id": "1", "urun_adi": "VIREON FOR MEN · Erkek Bakım Kremi",
         "aciklama_duz": "", "wix_satis": 1200, "wix_liste": 2400,
         "wix_stok": 10, "wix_yayinda": True},
        {"urun_id": "2", "urun_adi": "INTIMBLANC (Hassas Bölge)",
         "aciklama_duz": "", "wix_satis": 2100, "wix_liste": 2100,
         "wix_stok": 5, "wix_yayinda": True},
    ]

    def test_adla_bulunur(self):
        self.assertIsNotNone(sd.urun_bul(self.KAYITLAR, "VIREON"))
        self.assertIsNotNone(sd.urun_bul(self.KAYITLAR, "intimblanc"))

    def test_bulunamazsa_en_yakinina_DUSMEZ(self):
        self.assertIsNone(sd.urun_bul(self.KAYITLAR, "DERMAVASC"))
        self.assertIsNone(sd.urun_bul(self.KAYITLAR, ""))

    def test_urun_bilinmiyorsa_fiyat_soylenmez_dogal_sorulur(self):
        class PatlayanModel:
            def generate(self, *a, **k):
                raise AssertionError("urun yokken model cagrilmamali")
        cevap = sd.cevap_uret("fiyatı nedir", None, PatlayanModel())
        self.assertIsNone(cevap.urun)
        self.assertIn("hangi", cevap.metin.casefold())
        # Uydurulmus bir rakam gecmemeli.
        self.assertEqual(sd.uydurma_sayi(cevap.metin, []), [])


class SoruTipiTurkceyeUyar(unittest.TestCase):
    def test_temel_tipler(self):
        self.assertEqual(sd.soru_tipi("fiyatı nedir"), sd.FIYAT)
        self.assertEqual(sd.soru_tipi("kaç para"), sd.FIYAT)
        self.assertEqual(sd.soru_tipi("İçindekiler nelerdir?"), sd.ICERIK)
        self.assertEqual(sd.soru_tipi("nasıl sipariş verebilirim"), sd.SIPARIS)
        self.assertEqual(sd.soru_tipi("kargo ne zaman gelir"), sd.KARGO)
        self.assertEqual(sd.soru_tipi("merhaba"), sd.GENEL)

    def test_unsuz_yumusamasi_kacirmaz(self):
        # "icerik" -> "icerigi": k->g. Bu tuzak projede daha once yasandi.
        self.assertEqual(sd.soru_tipi("icerigi nedir acaba"), sd.ICERIK)

    def test_buyuk_I_turkce_yerelde_bozmaz(self):
        # "I".lower() Turkce yerelde noktasiz i uretir ve hicbir sey eslesmez.
        self.assertEqual(sd.soru_tipi("İÇİNDEKİLER NELERDİR"), sd.ICERIK)


class IfsaKuraliniTasir(unittest.TestCase):
    """Meta otomatik yanit deneyiminin bildirilmesini sart kosuyor."""

    def test_ilk_cevapta_ifsa_var(self):
        cevap = sd.cevap_uret("fiyatı nedir", None, object(), ilk_cevap=True)
        self.assertIn(sd.IFSA_SATIRI, cevap.metin)

    def test_sonraki_cevaplarda_ifsa_tekrarlanmaz(self):
        cevap = sd.cevap_uret("fiyatı nedir", None, object(), ilk_cevap=False)
        self.assertNotIn(sd.IFSA_SATIRI, cevap.metin)


class KesikCevapGitmez(unittest.TestCase):
    def test_token_sinirinda_kesilen_cevap_gonderilmez(self):
        class KesenModel:
            def generate(self, *a, **k):
                return ({"text": "Fiyat 1.200 TL ve bu üründe", "model": "s",
                         "truncated": True}, "LOCAL", 1)
        cevap = sd.cevap_uret("fiyatı nedir", _kart(), KesenModel())
        self.assertEqual(cevap.mevzuat, "KESIK")
        self.assertFalse(cevap.gonderilebilir)


class ModulDisariyaMesajGONDERMEZ(unittest.TestCase):
    """Bu modulun disariya hicbir yolu olmamali."""

    def test_kaynakta_gonderim_cagrisi_yok(self):
        kaynak = (Path(__file__).resolve().parent.parent
                  / "jarvis" / "satis_dialog.py").read_text(encoding="utf-8")
        for yasak in ("urllib.request", "requests.", "graph.facebook.com",
                      "/messages", "socket."):
            self.assertNotIn(yasak, kaynak,
                             f"{yasak} -- bu modul mesaj gondermemeli")


if __name__ == "__main__":
    unittest.main()
