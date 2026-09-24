"""Gömme zinciri: PC-1 açıksa hızlı yol, kapalıysa VDS işlemcisi.

İki uç AYNI modeli aynı havuzlamayla çalıştırıyor, bu yüzden vektörler aynı
uzayda ve biri diğerinin yerine geçebilir. Ölçüldü 24.09.2026:
    PC-1 RX 6600   55,5 ms tek tek   10,49/sn toplu    1.799 lead  2,9 dk
    VDS işlemci   136,8 ms tek tek    0,71/sn toplu    1.799 lead 42,1 dk
PC-1 14,7 kat hızlı ama VDS de yeterli -- bu yüzden PC-1'in 7/24 açık olması
gerekmiyor (ayda ~360 ₺ elektrik).
"""
import unittest
from unittest import mock

from jarvis import hatira


class ZincirSirasi(unittest.TestCase):
    def test_ilk_saglikli_uc_secilir(self):
        with mock.patch.object(hatira, "GOMME_UCLARI", ("A", "B")), \
             mock.patch.object(hatira, "_uc_saglikli", lambda u: True):
            self.assertEqual(hatira.calisan_gomme_ucu(), "A")

    def test_ilk_uc_oluyse_ikinciye_duser(self):
        with mock.patch.object(hatira, "GOMME_UCLARI", ("A", "B")), \
             mock.patch.object(hatira, "_uc_saglikli", lambda u: u == "B"):
            self.assertEqual(hatira.calisan_gomme_ucu(), "B")

    def test_hicbiri_yoksa_None(self):
        """None = kullanılamıyor. "Boş sonuç" ile karıştırılmamalı."""
        with mock.patch.object(hatira, "GOMME_UCLARI", ("A", "B")), \
             mock.patch.object(hatira, "_uc_saglikli", lambda u: False):
            self.assertIsNone(hatira.calisan_gomme_ucu())
            self.assertFalse(hatira.yerel_gomme_saglikli())

    def test_saglikli_uc_varsa_true(self):
        with mock.patch.object(hatira, "GOMME_UCLARI", ("A",)), \
             mock.patch.object(hatira, "_uc_saglikli", lambda u: True):
            self.assertTrue(hatira.yerel_gomme_saglikli())


class UcListesi(unittest.TestCase):
    def test_varsayilan_iki_uc(self):
        """PC-1 önce (hızlı), VDS sonra (her zaman açık)."""
        self.assertGreaterEqual(len(hatira.GOMME_UCLARI), 2)
        self.assertIn("8096", hatira.GOMME_UCLARI[0])

    def test_uclar_ayni_boyutu_hedefler(self):
        """BGE-M3 doğal boyutu 1024; şema da 1024. Uyuşmazsa sessizce bozulur."""
        self.assertEqual(hatira.BOYUT, 1024)

    def test_esik_saglayiciya_bagli(self):
        """Eşiği sağlayıcıdan ayrı değiştirmek hafızayı sessizce bozardı."""
        self.assertEqual(hatira.GOMME_ESIKLERI["gemini"], 0.60)
        self.assertLess(hatira.GOMME_ESIKLERI["yerel"],
                        hatira.GOMME_ESIKLERI["gemini"])


class YoklugunSebebi(unittest.TestCase):
    """Tekrar eden kök hata: yokluğu SEBEBİNİ bilmeden cümleye çevirmek."""

    def setUp(self):
        hatira._sifirla()
        hatira._kurulum_hatasi = None

    def tearDown(self):
        hatira._sifirla()
        hatira._kurulum_hatasi = None

    def test_uc_yoksa_yapilandirma_suclanmaz(self):
        with mock.patch.object(hatira, "GOMME_UCLARI", ("http://yok/v1",)), \
             mock.patch.object(hatira, "_uc_saglikli", lambda u: False), \
             mock.patch.object(hatira, "_postgres_ip", lambda: "1.2.3.4"), \
             mock.patch.dict("os.environ", {"MEM0_PG_PASSWORD": "x",
                                            "GEMINI_API_KEY": "y"}):
            self.assertIsNone(hatira._yapilandirma())
            self.assertIn("gomme ucu yok", hatira._kurulum_hatasi)
            self.assertNotIn("yapilandirma eksik", hatira._kurulum_hatasi)


if __name__ == "__main__":
    unittest.main()
