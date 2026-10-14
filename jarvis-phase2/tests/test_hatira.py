"""Hatıra katmanı: sınırlar, yumuşak bozulma ve anlamsal geri çağırma.

Çevrimdışı testler veritabanı istemez -- modülün SÖZLEŞMESİNİ sınarlar:
dışarı ne gidebilir, arıza halinde ne döner, telemetri gerçekten kapalı mı.
Canlı blok (JARVIS_LIVE_TEST=1) gerçek postgres ve gerçek gömme ile
anlamsal geri çağırmayı sınar -- asıl iddia orada kanıtlanır.
"""
import os
import unittest
from unittest import mock

from jarvis import hatira


class SinirTests(unittest.TestCase):
    """Dışarı ne gidebilir -- kod neye izin VERMİYOR."""

    def test_ham_sohbet_kabul_eden_bir_yol_yok(self):
        """kaydet() düz metin alır; rol/mesaj listesi alan bir giriş yoktur.

        Sahip kararı (20.09.2026): şirket kanıtı dış sağlayıcıya gitmez.
        Sınırı dikkat değil KOD tutmalı: transkript geçirecek kapı yoksa
        kazayla da geçirilemez.
        """
        import inspect
        imza = inspect.signature(hatira.kaydet)
        self.assertEqual(list(imza.parameters), ["not_metni", "thread"])
        # hatira.py'de `from __future__ import annotations` var, bu yuzden
        # aciklamalar DIZGI olarak gelir -- sinifla karsilastirmak patlar.
        self.assertEqual(imza.parameters["not_metni"].annotation, "str")

    def test_uzun_not_kirpilir(self):
        with mock.patch.object(hatira, "_bellegi_al", return_value=None):
            # Bellek yokken False döner ama kırpma mantığı yine de geçilir;
            # asıl sınanan sabitin makul ve tanımlı olması.
            self.assertFalse(hatira.kaydet("x" * 5000))
        self.assertGreater(hatira.MAX_NOT_KARAKTER, 0)
        self.assertLessEqual(hatira.MAX_NOT_KARAKTER, 1000)

    def test_bos_not_yazilmaz(self):
        self.assertFalse(hatira.kaydet(""))
        self.assertFalse(hatira.kaydet("   "))

    def test_infer_kapali_cagriliyor(self):
        """mem0 normalde metni bir LLM'e gönderip 'ne hatırlanmalı' diye sorar.

        O yol kapalı olmalı: metni yalnız gömme çağrısı görsün. infer=True
        sızarsa not metni ikinci bir dış servise daha giderdi.
        """
        sahte = mock.MagicMock()
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            hatira.kaydet("bir not")
        _, kwargs = sahte.add.call_args
        self.assertIs(kwargs["infer"], False)


class YumusakBozulmaTests(unittest.TestCase):
    """Arıza = boş sonuç, asla istisna. Bir konuşma hafıza yüzünden ölmemeli."""

    def test_bellek_yokken_ara_bos_doner(self):
        with mock.patch.object(hatira, "_bellegi_al", return_value=None):
            self.assertEqual(hatira.ara("herhangi bir soru"), [])

    def test_bellek_yokken_kaydet_false_doner(self):
        with mock.patch.object(hatira, "_bellegi_al", return_value=None):
            self.assertFalse(hatira.kaydet("bir not"))

    def test_arama_patlarsa_bos_doner_istisna_sizmaz(self):
        sahte = mock.MagicMock()
        sahte.search.side_effect = RuntimeError("postgres kapali")
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            self.assertEqual(hatira.ara("soru"), [])

    def test_kayit_patlarsa_false_doner_istisna_sizmaz(self):
        sahte = mock.MagicMock()
        sahte.add.side_effect = RuntimeError("ag yok")
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            self.assertFalse(hatira.kaydet("bir not"))

    def test_bos_soru_arama_yapmaz(self):
        sahte = mock.MagicMock()
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            self.assertEqual(hatira.ara("  "), [])
        sahte.search.assert_not_called()


class ApiAdlariTests(unittest.TestCase):
    """mem0 2.1.0'da ölçülen iki tuzak geri gelmesin."""

    def test_arama_top_k_kullanir_limit_degil(self):
        """'limit' **kwargs'a düşüp SESSİZCE yok sayılıyordu: limit=2 istedik,
        5 sonuç geldi. Doğru ad 'top_k'."""
        sahte = mock.MagicMock()
        sahte.search.return_value = {"results": []}
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            hatira.ara("soru", limit=2)
        _, kwargs = sahte.search.call_args
        self.assertEqual(kwargs["top_k"], 2)
        self.assertNotIn("limit", kwargs)

    def test_arama_filters_kullanir_user_id_degil(self):
        """add() user_id'yi doğrudan alır, search() reddedip filters ister."""
        sahte = mock.MagicMock()
        sahte.search.return_value = {"results": []}
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            hatira.ara("soru", thread="operator")
        _, kwargs = sahte.search.call_args
        self.assertEqual(kwargs["filters"], {"user_id": "operator"})
        self.assertNotIn("user_id", kwargs)

    def test_esik_geciriliyor(self):
        sahte = mock.MagicMock()
        sahte.search.return_value = {"results": []}
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            hatira.ara("soru")
        _, kwargs = sahte.search.call_args
        self.assertEqual(kwargs["threshold"], hatira.BENZERLIK_ESIGI)


class TelemetriTests(unittest.TestCase):
    def test_telemetri_ortam_degiskeni_kapali(self):
        self.assertEqual(os.environ.get("MEM0_TELEMETRY"), "false")

    def test_telemetri_acikken_calismayi_reddeder(self):
        """Kapatmayı unutmak sessiz bir sızıntı olurdu; gürültülü olsun."""
        with mock.patch.object(hatira, "_telemetri_kapali", return_value=False), \
             mock.patch.object(hatira, "_yapilandirma", return_value={"x": 1}):
            hatira._bellek = None
            self.assertIsNone(hatira._bellegi_al())
            self.assertIn("telemetri", (hatira._kurulum_hatasi or "").lower())
        hatira._bellek = None


class BoyutTests(unittest.TestCase):
    def test_boyut_semadakiyle_ayni(self):
        """ai_semantic.memory_embedding vector(1024). Farklı boyut seçmek
        iki katmanı ileride karşılaştırma imkânını kapatırdı."""
        self.assertEqual(hatira.BOYUT, 1024)


class KirlenmeTests(unittest.TestCase):
    """Testler canli dizine yazmasin.

    test_conversation_memory gecici bir JARVIS_STATE_DIR ile calisiyor;
    dosya katmani boylece izole. Ama dizin ORTAK postgres'te durdugu icin
    izolasyon orada kiriliyordu -- olculdu: uretim dizininde biriken 17
    satirin hepsi test metniydi. Bu testler o kapinin acik kalmasini
    engelliyor.
    """

    def test_gecici_durum_dizininde_indeksleme_kapalidir(self):
        import importlib
        import os
        import tempfile
        from jarvis import conversation_memory as cm

        with tempfile.TemporaryDirectory() as tmp:
            onceki = os.environ.get("JARVIS_STATE_DIR")
            os.environ["JARVIS_STATE_DIR"] = tmp
            try:
                gecici = importlib.reload(cm)
                self.assertFalse(gecici._dizin_acik(),
                                 "gecici dizinde indeksleme ACIK -- testler "
                                 "canli dizini kirletir")
            finally:
                if onceki is None:
                    os.environ.pop("JARVIS_STATE_DIR", None)
                else:
                    os.environ["JARVIS_STATE_DIR"] = onceki
                importlib.reload(cm)

    def test_gercek_durum_dizininde_indeksleme_aciktir(self):
        """Kapiyi kapatirken uretimde de kapatmis olmayalim."""
        import importlib
        import os
        from jarvis import conversation_memory as cm

        onceki = os.environ.pop("JARVIS_STATE_DIR", None)
        try:
            gercek = importlib.reload(cm)
            self.assertTrue(gercek._dizin_acik(),
                            "gercek dizinde indeksleme KAPALI -- hatira hic "
                            "dolmaz")
        finally:
            if onceki is not None:
                os.environ["JARVIS_STATE_DIR"] = onceki
            importlib.reload(cm)

    def test_gecici_dizinde_remember_hatiraya_dokunmaz(self):
        import importlib
        import os
        import tempfile
        from jarvis import conversation_memory as cm

        with tempfile.TemporaryDirectory() as tmp:
            onceki = os.environ.get("JARVIS_STATE_DIR")
            os.environ["JARVIS_STATE_DIR"] = tmp
            try:
                gecici = importlib.reload(cm)
                with mock.patch.object(hatira, "kaydet") as sahte:
                    self.assertTrue(gecici.remember("gecici bir not"))
                sahte.assert_not_called()
            finally:
                if onceki is None:
                    os.environ.pop("JARVIS_STATE_DIR", None)
                else:
                    os.environ["JARVIS_STATE_DIR"] = onceki
                importlib.reload(cm)


class TekrarTests(unittest.TestCase):
    def test_ayni_not_iki_kez_yazilmaz(self):
        """Ayni cumle dizinde cogalirsa top_k butcesini kopyalari yer.

        remember() dosyada ayni notu silip yeniden ekliyor; dizin de ayni
        davranmali. Olculdu: ayni cumleden ucer kopya birikmisti.
        """
        sahte = mock.MagicMock()
        sahte.get_all.return_value = {"results": [
            {"id": "a1", "memory": "ayni cumle"},
            {"id": "a2", "memory": "baska cumle"},
        ]}
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            hatira.kaydet("ayni cumle")
        sahte.delete.assert_called_once_with("a1")
        sahte.add.assert_called_once()

    def test_tekrar_taramasi_patlarsa_kayit_yine_yapilir(self):
        """Tekrar temizligi bir KOLAYLIK; notu kaybettirmemeli."""
        sahte = mock.MagicMock()
        sahte.get_all.side_effect = RuntimeError("postgres kapali")
        with mock.patch.object(hatira, "_bellegi_al", return_value=sahte):
            self.assertTrue(hatira.kaydet("bir not"))
        sahte.add.assert_called_once()


@unittest.skipUnless(os.environ.get("JARVIS_LIVE_TEST") == "1",
                     "canli test: JARVIS_LIVE_TEST=1 gerekir")
class CanliTests(unittest.TestCase):
    """Asıl iddia: kelimesi tutmayan soru, doğru notu bulur."""

    THREAD = "test-hatira"

    @classmethod
    def setUpClass(cls):
        if hatira._bellegi_al() is None:
            raise unittest.SkipTest(f"hatira kurulamadi: {hatira._kurulum_hatasi}")
        hatira.kaydet(
            "Fiyat otoritesi Wix'tir; diger platformlar Wix fiyatindan tureyecek.",
            thread=cls.THREAD)

    @classmethod
    def tearDownClass(cls):
        hatira.unut("Fiyat otoritesi", thread=cls.THREAD)

    def test_baska_kelimelerle_sorulan_soru_notu_bulur(self):
        sonuc = hatira.ara("hangi sistem fiyatta son sozu soyluyor",
                           thread=self.THREAD)
        self.assertTrue(sonuc, "anlamsal arama notu bulamadi")
        self.assertIn("otoritesi", sonuc[0].lower())

    def test_ilgisiz_soru_hicbir_sey_dondurmez(self):
        """Eşiğin varlık sebebi: alakasız notlar bağlam bütçesini yemesin."""
        self.assertEqual(
            hatira.ara("yarin hava nasil olacak", thread=self.THREAD), [])

    def test_unutulan_not_aramada_cikmaz(self):
        hatira.kaydet("Gecici bir karar: kargo firmasi degistirilecek.",
                      thread=self.THREAD)
        self.assertTrue(hatira.ara("kargo firmasi", thread=self.THREAD))
        hatira.unut("kargo firmasi", thread=self.THREAD)
        self.assertEqual(hatira.ara("kargo firmasi", thread=self.THREAD), [])


if __name__ == "__main__":
    unittest.main()
