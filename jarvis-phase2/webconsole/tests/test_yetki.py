"""Rol kapısı ve ek hesaplar.

Kapının asıl güvencesi "varsayılan kapalı": ofise açık her adres burada adıyla
sınanır, kapalı kalması gereken hassas adresler de ayrıca sınanır.
"""
import importlib
import os
import pathlib
import tempfile
import unittest

WEBCONSOLE = pathlib.Path(__file__).resolve().parents[1]


class YetkiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["JARVIS_WEB_STATE_DIR"] = cls.tmp.name
        import auth
        import yetki
        cls.auth = importlib.reload(auth)
        cls.yetki = importlib.reload(yetki)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def ofis(self, yontem, yol):
        return self.yetki.izinli(self.auth.ROLE_OFIS, yontem, yol)

    def test_ofis_hassas_adreslere_ulasamaz(self):
        kapali = [
            ("GET", "/api/chat"), ("POST", "/api/chat"), ("POST", "/api/chat/stream"),
            ("POST", "/api/ekip/sor"), ("GET", "/api/hafiza"),
            ("GET", "/api/money/overview"), ("GET", "/api/expenses"),
            ("GET", "/api/money/product-profit"), ("GET", "/api/fiyat-matrisi"),
            ("GET", "/api/panel/holding"), ("GET", "/api/satislar"), ("GET", "/api/gelenkutusu"),
            ("POST", "/api/kargo/barkod"), ("GET", "/api/sistem"), ("POST", "/api/sistem/anahtar"),
            ("GET", "/api/saha/konum"), ("GET", "/api/saha/konum/gecmis"), ("POST", "/api/saha/konum"),
            ("POST", "/api/cari/entries"), ("POST", "/api/cari/drafts/post"),
            ("POST", "/api/cari/reverse"), ("POST", "/api/cari/correct"),
            ("POST", "/api/cari/discount"), ("POST", "/api/cari/documents/approve"),
            ("POST", "/api/cari/reconciliation/update"), ("GET", "/api/cari/channels"),
            ("POST", "/api/voice/agent-turn"), ("POST", "/api/voice/realtime/session"),
            ("GET", "/kreatif/a.png"), ("GET", "/tarayici/x"), ("GET", "/google/start"),
            ("GET", "/katalog-pdf/baski"), ("GET", "/api/yeni-eklenecek-bir-uc"),
        ]
        for yontem, yol in kapali:
            with self.subTest(yol=yol, yontem=yontem):
                self.assertFalse(self.ofis(yontem, yol))

    def test_ofis_isini_yapabilir(self):
        acik = [
            ("GET", "/api/session"), ("GET", "/api/saha"), ("GET", "/api/saha/filtreler"),
            ("POST", "/api/saha/ziyaret"), ("POST", "/api/saha/bilgi"), ("POST", "/api/saha/rota"),
            ("GET", "/api/cari/accounts"), ("POST", "/api/cari/accounts"),
            ("POST", "/api/cari/drafts/create"), ("GET", "/api/katalog"),
            ("GET", "/api/office/events"), ("GET", "/api/panel/ofis"),
            ("POST", "/api/account/password"), ("POST", "/api/logout"),
            ("GET", "/"), ("GET", "/cari.html"), ("GET", "/office.html"), ("GET", "/app.js"),
            ("GET", "/karo/14/1/2.png"), ("GET", "/katalog-gorsel/x.webp"),
        ]
        for yontem, yol in acik:
            with self.subTest(yol=yol, yontem=yontem):
                self.assertTrue(self.ofis(yontem, yol))

    def test_yontem_karismaz(self):
        # GET ile açık olan, POST ile açık sayılmaz (ve tersi).
        self.assertFalse(self.ofis("POST", "/api/saha"))
        self.assertFalse(self.ofis("GET", "/api/saha/ziyaret"))

    def test_yonetici_her_yere_rolsuz_hicbir_yere(self):
        self.assertTrue(self.yetki.izinli(self.auth.ROLE_ADMIN, "POST", "/api/cari/reverse"))
        self.assertFalse(self.yetki.izinli(None, "GET", "/api/saha"))
        self.assertFalse(self.yetki.izinli("BILINMEYEN", "GET", "/api/saha"))

    def test_ofise_acik_her_adres_sunucuda_gercekten_var(self):
        # Yazım hatası ofise "açık" sanılan ama aslında var olmayan bir adres
        # bırakır; kapı geçer ama ekran çalışmaz. Kaynakta adıyla aranır.
        kaynak = (WEBCONSOLE / "app.py").read_text(encoding="utf-8")
        for yol in sorted(self.yetki.OFIS_GET | self.yetki.OFIS_POST):
            with self.subTest(yol=yol):
                # /api/cari/* ve /api/panel/* önekle yönlendirilir.
                self.assertTrue('"%s"' % yol in kaynak or yol.startswith(("/api/cari/", "/api/panel/")), yol)


class HesapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["JARVIS_WEB_STATE_DIR"] = self.tmp.name
        import auth
        self.auth = importlib.reload(auth)
        self.auth.ensure_operator_account("operator")

    def tearDown(self):
        self.tmp.cleanup()

    def test_operator_yonetici(self):
        self.assertEqual(self.auth.role_of("operator"), self.auth.ROLE_ADMIN)

    def test_ofis_hesabi_acilir_ve_giris_yapar(self):
        parola = self.auth.add_user("lcarlie12345", self.auth.ROLE_OFIS)
        hesap = self.auth.find_account("lcarlie12345")
        self.assertEqual(hesap["role"], self.auth.ROLE_OFIS)
        self.assertTrue(hesap["must_change"])
        self.assertTrue(self.auth.verify_password(parola, hesap["password_hash"], hesap["salt"]))
        self.auth.set_user_password("lcarlie12345", "yeni-parola-123")
        hesap = self.auth.find_account("lcarlie12345")
        self.assertFalse(hesap["must_change"])
        self.assertFalse(self.auth.verify_password(parola, hesap["password_hash"], hesap["salt"]))

    def test_kapatilan_hesap_giremez(self):
        self.auth.add_user("ofis1", self.auth.ROLE_OFIS)
        self.auth.set_disabled("ofis1", True)
        self.assertIsNone(self.auth.find_account("ofis1"))
        self.assertIsNone(self.auth.role_of("ofis1"))

    def test_ek_hesap_yonetici_olamaz_ve_operatoru_ezemez(self):
        with self.assertRaises(ValueError):
            self.auth.add_user("baska", self.auth.ROLE_ADMIN)
        with self.assertRaises(ValueError):
            self.auth.add_user("operator", self.auth.ROLE_OFIS)
        with self.assertRaises(ValueError):
            self.auth.add_user("bo şluk", self.auth.ROLE_OFIS)

    def test_ofis_parolasi_operator_dosyasina_dokunmaz(self):
        once = (pathlib.Path(self.tmp.name) / "auth.json").read_text(encoding="utf-8")
        self.auth.add_user("ofis2", self.auth.ROLE_OFIS)
        self.auth.set_user_password("ofis2", "baska-parola-99")
        self.assertEqual(once, (pathlib.Path(self.tmp.name) / "auth.json").read_text(encoding="utf-8"))

    def test_bilinmeyen_kullanici_yok(self):
        self.assertIsNone(self.auth.find_account("yok"))


if __name__ == "__main__":
    unittest.main()
