"""Ogrenme dongusu: ne zaman ONERIR, ne zaman SUSAR.

BU DOSYANIN KURDUGU SINIR
Sahibin tarifi "10 kisiye cevaplamis ve 2. mesaj gelmemisse tarzini
degistirecek" idi. Tehlike su: 10 kucuk bir ornektir ve bu projede kucuk
ornekten sonuc cikarip yanildik (GROWTH-004/005). Bu yuzden esik bir
DEGISIKLIK ONERISI tetikler, bir HUKUM degil -- ve hicbir sey kendiliginden
yayina girmez.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis import satis_ogrenme as so  # noqa: E402


def _kohort(donus_var, donus_yok, pencere_acik=0, urun="X", tip="FIYAT"):
    return {"urun": urun, "soru_tipi": tip, "yaklasim_id": 1, "yaklasim_surum": 1,
            "donus_var": donus_var, "donus_yok": donus_yok,
            "pencere_acik": pencere_acik}


class KucukOrneklemdeHUKUM_VERILMEZ(unittest.TestCase):
    def test_esik_altinda_oneri_yok(self):
        [b] = so.degerlendir([_kohort(1, 2)])          # 3 karar, esik 10
        self.assertEqual(b.durum, so.YETERSIZ)
        self.assertFalse(b.oneri_gerekli)

    def test_esik_altinda_oran_yine_de_OKUNUR(self):
        # Gizlemek de yanlis olurdu: sayi gosterilir, hukum verilmez.
        [b] = so.degerlendir([_kohort(1, 2)])
        self.assertAlmostEqual(b.donus_yuzde, 33.3, places=1)

    def test_sifir_karar_cokmez(self):
        [b] = so.degerlendir([_kohort(0, 0, pencere_acik=5)])
        self.assertIsNone(b.donus_yuzde)
        self.assertEqual(b.durum, so.YETERSIZ)
        self.assertFalse(b.oneri_gerekli)


class PencereAcikPAYDAYA_GIRMEZ(unittest.TestCase):
    """Cevabin ustunden yeterli sure gecmeden 'donus yok' denemez.

    Girerse oran olabileceginden dusuk gorunur ve bos yere uslup degistiririz.
    """

    def test_pencere_acik_orani_dusurmez(self):
        [b] = so.degerlendir([_kohort(8, 2, pencere_acik=40)])
        self.assertEqual(b.karar_verilen, 10)
        self.assertAlmostEqual(b.donus_yuzde, 80.0, places=1)
        self.assertEqual(b.durum, so.USTUNDE)


class TabanlaKIYAS(unittest.TestCase):
    def test_belirgin_dusukse_oneri_gerekir(self):
        [b] = so.degerlendir([_kohort(3, 9)])          # %25
        self.assertEqual(b.durum, so.ALTINDA)
        self.assertTrue(b.oneri_gerekli)

    def test_belirgin_yuksekse_DOKUNULMAZ(self):
        [b] = so.degerlendir([_kohort(13, 2)])         # %86,7
        self.assertEqual(b.durum, so.USTUNDE)
        self.assertFalse(b.oneri_gerekli)

    def test_kucuk_fark_dalgalanma_sayilir(self):
        # Her dalgalanmada uslup degistirmek ogrenmek degil, savrulmaktir.
        [b] = so.degerlendir([_kohort(9, 5)])          # %64,3, taban %59,7
        self.assertEqual(b.durum, so.AYNI)
        self.assertFalse(b.oneri_gerekli)

    def test_oneri_gerekenler_basa_siralanir(self):
        bulgular = so.degerlendir([_kohort(13, 2, tip="KARGO"),
                                   _kohort(3, 9, tip="FIYAT")])
        self.assertTrue(bulgular[0].oneri_gerekli)
        self.assertEqual(bulgular[0].soru_tipi, "FIYAT")


class OneriKANITSIZ_ISTENMEZ(unittest.TestCase):
    """Neye bakarak degistirecegini bilmeyen oneri, uslubu rastgele savurur."""

    class _PatlayanModel:
        def generate(self, *a, **k):
            raise AssertionError("ornek yokken model CAGRILMAMALI")

    def test_ornek_yoksa_model_cagrilmaz(self):
        [b] = so.degerlendir([_kohort(3, 9)])
        oneri = so.yaklasim_oner(b, "mevcut", [], self._PatlayanModel())
        self.assertEqual(oneri.yeni_yonerge, "")
        self.assertIn("örnek yok", oneri.hata)

    def test_kanit_oneriye_TASINIR(self):
        class SahteModel:
            def generate(self, *a, **k):
                return ({"text": "Daha kisa yaz.", "model": "s"}, "EXTERNAL", 1)
        [b] = so.degerlendir([_kohort(3, 9)])
        oneri = so.yaklasim_oner(b, "mevcut", ["cevap bir", "cevap iki"], SahteModel())
        self.assertEqual(len(oneri.kanit), 2)
        self.assertEqual(oneri.gerekce, b.aciklama)


class OneriKENDILIGINDEN_YAYINA_GIRMEZ(unittest.TestCase):
    class _SahteModel:
        def generate(self, *a, **k):
            return ({"text": "Daha kisa ve net yaz.", "model": "s"}, "EXTERNAL", 1)

    def test_durum_her_zaman_TASLAK(self):
        [b] = so.degerlendir([_kohort(3, 9)])
        oneri = so.yaklasim_oner(b, "mevcut", ["x"], self._SahteModel())
        self.assertEqual(oneri.to_dict()["durum"], "TASLAK")

    def test_mevzuat_disi_yonerge_UYGUN_sayilmaz(self):
        class MevzuatDisiModel:
            def generate(self, *a, **k):
                return ({"text": "Kesin sonuc garanti ettigini soyle.",
                         "model": "s"}, "EXTERNAL", 1)
        [b] = so.degerlendir([_kohort(3, 9)])
        oneri = so.yaklasim_oner(b, "mevcut", ["x"], MevzuatDisiModel())
        self.assertFalse(oneri.uygun)
        self.assertEqual(oneri.mevzuat, "INCELE")


class OzetHUKUM_VERMEZ(unittest.TestCase):
    def test_bos_kohortta_cokmez(self):
        self.assertIn("ölçecek bir şey", so.ozet([]))

    def test_satis_iddiasinda_BULUNMAZ(self):
        # DONUS_YOK satilmadi demek degildir; ozet bunu ima etmemeli.
        metin = so.ozet(so.degerlendir([_kohort(3, 9), _kohort(1, 2)]))
        for yasak in ("satış düştü", "satış arttı", "satılmadı"):
            self.assertNotIn(yasak, metin)

    def test_small_sample_ozette_SOYLENIR(self):
        metin = so.ozet(so.degerlendir([_kohort(1, 2)]))
        self.assertIn("SMALL_SAMPLE", metin)


if __name__ == "__main__":
    unittest.main()
