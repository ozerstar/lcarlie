# -*- coding: utf-8 -*-
"""Çekim föyü sözleşmesi.

Föy elden ele gidecek bir belge: telefona inecek, portala yapıştırılacak,
belki bir çekimciye yollanacak. İçindeki iki kural sessizce kaybolursa
kimse fark etmez ama sonuç L'CARLIÉ ürünü olmayan bir video olur.

🔴 KORUNAN İKİ KURAL
1. Portalda **image-to-video** yazacak ve text-to-video'nun ambalajı
   uydurduğu AÇIKÇA söylenecek. "AI kullanma" demiyoruz; AI'ya ürünü
   çizdirme diyoruz -- ikisi aynı şey değil ve föy bunu karıştırırsa
   ya gereksiz yere elini bağlar ya da uydurma ambalaja kapı açar.
2. Reels föyünde kare için "kapak karesi" denecek. "Görsel hazır"
   sanılırsa video hiç çekilmez ve paket yayına gider.
"""
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent
_foy = SourceFileLoader(
    "ig_foy", str(_KOK / "webconsole" / "ig_foy.py")).load_module()

PAKET = {
    "plan_id": 11,
    "urun_slug": "babysoft",
    "amac": "TANITIM",
    "bicim": "REELS",
    "kanca": "BABYSOFT nedir, ne için kullanılır?",
    "caption": ("BABYSOFT nedir, ne için kullanılır?\n\n"
                "Shea yağı ve jojoba yağı içeriğiyle cilt bakımına "
                "yumuşak bir his kazandırmaya yardımcı olur.\n"
                "Yulaf ekstresi formülde yer alır."),
    "hashtagler": ["#lcarlie", "#dermokozmetik"],
    "cta": "SEE_DETAILS",
    "cta_gerekce": "ilgi olculuyor",
    "dayanak": "Satisi OLCULMEDI.",
    "gorsel_dosya": "babysoft-reels-20260925T105044.jpg",
}


class TestFoyIcerigi(unittest.TestCase):
    def setUp(self):
        self.metin = _foy.foy_metni(PAKET, {"ad": "BABYSOFT",
                                            "zorunlu_uyarilar": []})

    def test_portal_modu_gorselden_video(self):
        self.assertIn("image-to-video", self.metin)
        self.assertIn("text-to-video", self.metin)
        # Yalniz adini anmak yetmez, YASAK oldugu yazmali.
        self.assertIn("KULLANILMAZ", self.metin)

    def test_baslangic_karesi_paketin_kendi_dosyasi(self):
        # Portala rastgele bir gorsel degil, BU paketin dosyasi yuklenir.
        self.assertIn(PAKET["gorsel_dosya"], self.metin)

    def test_urun_ai_ile_cizdirilmez_uyarisi(self):
        self.assertIn("ambalaj", self.metin.lower())
        self.assertIn("do not redraw", self.metin)

    def test_negatif_istem_ambalaj_bozulmasini_sayar(self):
        for anahtar in ("distorted packaging", "warped label",
                        "invented logo", "misspelled text"):
            self.assertIn(anahtar, self.metin, anahtar)

    def test_yasak_klise_negatif_istemde(self):
        # Sahibin reddettigi sablon: cicek, tas, bej fon.
        for anahtar in ("flowers", "pebbles", "beige gradient"):
            self.assertIn(anahtar, self.metin, anahtar)

    def test_reels_foyunde_sure_ve_altyazi(self):
        self.assertIn("1080x1920", self.metin)
        self.assertIn("altyazı", self.metin)

    def test_plan_saniye_saniye(self):
        for an in ("00:00-00:02", "00:06-00:12", "00:16-00:18"):
            self.assertIn(an, self.metin, an)

    def test_mevzuat_bolumu_compliance_modulunden(self):
        # Elle yazilmis liste degil: compliance'taki gercek ifadeler.
        from jarvis import compliance as c
        self.assertIn(c.SUPERIORITY[0], self.metin)
        self.assertIn(c.AUTHORITY[0], self.metin)

    def test_nesne_kurali_yazili(self):
        # "fiil degil cumlenin nesnesi denetlenir" -- tekrar eden kok hata.
        self.assertIn("NESNES", self.metin.upper())

    def test_zorunlu_ibare_urunden_gelir(self):
        m = _foy.foy_metni(PAKET, {
            "ad": "BABYSOL",
            "zorunlu_uyarilar": ["Güneşte uzun süre kalmak ciddi risk taşır"]})
        self.assertIn("Güneşte uzun süre kalmak", m)

    def test_bos_paket_reddedilir(self):
        with self.assertRaises(ValueError):
            _foy.foy_metni({})


class TestTekGorselFoyu(unittest.TestCase):
    def test_tek_gorsel_plani_cekim_istemez(self):
        p = dict(PAKET, bicim="TEK_GORSEL", plan_id=14)
        m = _foy.foy_metni(p, {"ad": "FEMISIA"})
        self.assertIn("1080x1080", m)
        self.assertIn("Çekim gerekmiyor", m)
        # Reels iskeleti TEK_GORSEL foyune sizmasin.
        self.assertNotIn("00:16-00:18", m)


if __name__ == "__main__":
    unittest.main()
