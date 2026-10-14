# -*- coding: utf-8 -*-
"""Konsept kapısı sözleşmesi.

Bu kapı, modelin kendi ürettiğini beğenmesine karşı duruyor. İlk gerçek
koşuda işe yaradığı ölçüldü: model "Karanlık Botanik" konseptine 28/30
verdi, kapı metinde "dekoratif taş" ve "dekoratif yaprak" bulup TERK etti.
Kapı kalkarsa o konsept 28 puanla kazanır ve reddedilmiş klişe reklama
çıkar.

🔴 TÜRKÇE EŞLEŞME TUZAĞI BURADA CAN YAKAR. İlk hâli kelimeyi olduğu gibi
arıyordu; sınadığımda "sıçraması" kelimesi "sıçrama" anahtarına
eşleşmedi ve klişe TEMİZ göründü. Model çekimli yazar: "çiçekler",
"taşları", "kaidenin". Gövde eşleşmesine geçildi.

Ters tuzak da test ediliyor: **"tasarım" kelimesi "taş" klişesine
takılmamalı.** Önek eşleşmesi kullanılsaydı her sanat yönetimi metni
"dekoratif taş" diye reddedilirdi.
"""
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_k = SourceFileLoader(
    "kreatif_konsept_uret",
    str(_KOK / "scripts" / "kreatif-konsept-uret.py")).load_module()


class TestKliseKapisi(unittest.TestCase):
    def test_cekimli_hal_yakalanir(self):
        # Model duz hali degil, cekimli hali yazar.
        for metin, beklenen in (
                ("Ürün kaidenin üstünde duruyor", "kaide üstünde ürün"),
                ("Masada çiçekler var", "rastgele çiçek"),
                ("Çakıl taşları diziliyor", "dekoratif taş"),
                ("Camda su sıçraması", "su sıçraması"),
                ("Arkada yapraklar", "dekoratif yaprak")):
            self.assertIn(beklenen, _k.klise_bul(metin), metin)

    def test_tasarim_tasa_takilmaz(self):
        # 🔴 Ters tuzak: "tasarim" kelimesi "tas" klisesine EŞLEŞMEMELİ.
        for metin in ("Tasarım ızgarasına oturuyor",
                      "Tasarımcı kadrajı böldü",
                      "Plastik ambalajın makro dokusu"):
            self.assertEqual(_k.klise_bul(metin), [], metin)

    def test_temiz_konsept_gecer(self):
        temiz = ("Brütalist beton yüzey, sert yan ışık, sağ alt köşede "
                 "tipografi için negatif alan")
        self.assertEqual(_k.klise_bul(temiz), [])

    def test_cok_kelimeli_kalip(self):
        self.assertIn("havada uçuşan bileşen",
                      _k.klise_bul("Havada uçuşan bileşen zerreleri"))
        self.assertIn("jenerik kadın yüzü",
                      _k.klise_bul("Merkezde jenerik kadın yüzü"))

    def test_bos_metin_bos_doner(self):
        self.assertEqual(_k.klise_bul(""), [])
        self.assertEqual(_k.klise_bul(None, None), [])

    def test_birden_cok_alan_taranir(self):
        # Klise gorsel metaforda degil, sanat yonetiminde saklanabilir.
        b = _k.klise_bul("Temiz bir fikir", "Kadraj sade", "bej fon arkada")
        self.assertIn("bej fon", b)


class TestEsikler(unittest.TestCase):
    def test_en_az_uc_konsept(self):
        # "Tek fikirden secim yapilmaz" kurali sayida yasiyor.
        self.assertGreaterEqual(_k.EN_AZ_KONSEPT, 3)

    def test_secim_esigi_ortalamanin_ustunde(self):
        # 6 eksen x 1-5 = 6..30. Esik 18 (ortalama 3) olsaydi "idare
        # eder" konsept secilirdi.
        self.assertGreater(_k.SECIM_ESIGI, 18)
        self.assertLessEqual(_k.SECIM_ESIGI, 30)

    def test_eksen_tabani_var(self):
        # Toplami yuksek ama tek ekseni 1 olan konsept kurtarilmamali.
        self.assertGreaterEqual(_k.EKSEN_TABANI, 2)

    def test_alti_eksen(self):
        self.assertEqual(len(_k.PUAN_EKSENLERI), 6)
        adlar = {e for e, _ in _k.PUAN_EKSENLERI}
        self.assertIn("p_ozgunluk", adlar)
        self.assertIn("p_durdurma_gucu", adlar)


class TestDogrulama(unittest.TestCase):
    TAM = {
        "ad": "X", "ana_fikir": "x", "gorsel_metafor": "x",
        "kompozisyon": "x", "odak": "x", "duygu": "x", "urunle_iliski": "x",
        "neden_durdurur": "x", "amac_iletisim": "x", "hedef_kitle": "x",
        "istenen_tepki": "x", "ana_mesaj": "x",
        "puan": {e: 4 for e, _ in _k.PUAN_EKSENLERI},
    }

    def test_tam_konsept_gecer(self):
        tam, eksik = _k.dogrula(dict(self.TAM))
        self.assertTrue(tam, eksik)

    def test_eksik_alan_reddedilir(self):
        # Gercekte olan buydu: model ucunde de istenen_tepki'yi atladi.
        k = dict(self.TAM)
        del k["istenen_tepki"]
        tam, eksik = _k.dogrula(k)
        self.assertFalse(tam)
        self.assertIn("istenen_tepki", eksik)

    def test_aralik_disi_puan_reddedilir(self):
        k = dict(self.TAM, puan=dict(self.TAM["puan"], p_ozgunluk=9))
        tam, eksik = _k.dogrula(k)
        self.assertFalse(tam)
        self.assertTrue(any("p_ozgunluk" in e for e in eksik))

    def test_puan_yoksa_reddedilir(self):
        k = dict(self.TAM)
        del k["puan"]
        self.assertFalse(_k.dogrula(k)[0])


if __name__ == "__main__":
    unittest.main()
