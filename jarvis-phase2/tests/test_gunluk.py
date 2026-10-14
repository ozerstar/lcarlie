"""gunluk.py testleri.

Bu modulun tek isi kaydetmek, ama kaydin KENDISI bir arizayi gizlerse
gunluk hicbir ise yaramaz. O yuzden testler sunu sinar: yazma basarisiz
olsa bile cagiran DUSMEZ, ve durum ayrimi (VERI_YOK / OKUNAMADI) korunur.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# 🔴 Uretim dosyasina yazmamak icin ice aktarmadan ONCE yonlendir. Bu
# projede ayni hata iki kez yasandi (kademe gunlugu ve sohbet dokumu).
_GECICI = tempfile.mkdtemp(prefix="gunluk-test-")
os.environ["JARVIS_STATE_DIR"] = _GECICI

from jarvis import gunluk  # noqa: E402 - ortam degiskeni once kurulmali


class _YalitilmisGunluk(unittest.TestCase):
    """Her test KENDI dosyasina yazar.

    🔴 JARVIS_STATE_DIR'i yonlendirmek TEK BASINA YETMEZ ve bu olculdu:
    tum takim kosarken agency / specialist_pool / conversation modulleri
    de artik gercek `gunluk.yut()` cagriyor ve ayni dosyaya yaziyorlar.
    Bu testler o satirlari kendi satirlari sanip yanlis sayiyordu --
    9 test bu yuzden dustu. `JARVIS_GUNLUK_LOG` acik gecersiz kilmasi
    her testi kendi dosyasina baglar; komsu modulun yazmasi artik
    bu olcumu kirletemez.
    """

    def setUp(self):
        self._dizin = tempfile.mkdtemp(prefix="gunluk-vaka-")
        self.yol = Path(self._dizin) / "gunluk.jsonl"
        os.environ["JARVIS_GUNLUK_LOG"] = str(self.yol)

    def tearDown(self):
        os.environ.pop("JARVIS_GUNLUK_LOG", None)


class YazmaTests(_YalitilmisGunluk):

    def test_satir_yazilir_ve_alanlari_tam(self):
        gunluk.yut("test_modul", "test_islev", ValueError("bozuk deger"),
                   neden="sinama")
        kayitlar = gunluk.son_kayitlar()
        self.assertEqual(len(kayitlar), 1)
        k = kayitlar[0]
        self.assertEqual(k["modul"], "test_modul")
        self.assertEqual(k["islev"], "test_islev")
        self.assertEqual(k["tip"], "ValueError")
        self.assertEqual(k["mesaj"], "bozuk deger")
        self.assertEqual(k["neden"], "sinama")
        self.assertEqual(k["agirlik"], gunluk.AGIRLIK_YUTULDU)

    def test_uzun_mesaj_kirpilir(self):
        """Bazi saglayicilar tum HTML govdesini istisna metnine koyuyor."""
        gunluk.yut("m", "i", ValueError("x" * 5000), neden="sinama")
        self.assertEqual(len(gunluk.son_kayitlar()[0]["mesaj"]), 500)

    def test_ayni_saniyede_iki_kayit_ayirt_edilir(self):
        """kademe.jsonl'de olculdu: 350 kaydin 86'si tek satira inmisti."""
        gunluk.yut("m", "i", ValueError("a"), neden="n")
        gunluk.yut("m", "i", ValueError("a"), neden="n")
        siralar = {k["sira"] for k in gunluk.son_kayitlar()}
        self.assertEqual(len(siralar), 2)

    def test_yazma_hatasi_cagirani_dusurmez(self):
        """Gunluk kaybi, cevabin kaybindan iyidir."""
        onceki = os.environ["JARVIS_GUNLUK_LOG"]
        os.environ["JARVIS_GUNLUK_LOG"] = "/proc/olmayan/dizin/gunluk.jsonl"
        try:
            gunluk.yut("m", "i", ValueError("a"), neden="n")  # patlamamali
        finally:
            os.environ["JARVIS_GUNLUK_LOG"] = onceki

    def test_bozuk_satir_okumayi_durdurmaz(self):
        gunluk.yut("m", "i", ValueError("a"), neden="n")
        with self.yol.open("a", encoding="utf-8") as d:
            d.write("{yarim yazilmis\n")
        self.assertEqual(len(gunluk.son_kayitlar()), 1)


class DurumAyrimiTests(_YalitilmisGunluk):
    """Yoklugu sebebinden ayirmak bu projenin tekrar eden kok hatasi."""

    def test_dosya_yoksa_veri_yok(self):
        self.assertEqual(gunluk.ozet()["durum"], "VERI_YOK")

    def test_kayit_varsa_ok_ve_moduller_sayilir(self):
        gunluk.yut("a", "f", ValueError("x"), neden="n")
        gunluk.yut("a", "f", ValueError("x"), neden="n")
        gunluk.yut("b", "g", ValueError("x"), neden="n",
                   agirlik=gunluk.AGIRLIK_ARIZA)
        o = gunluk.ozet()
        self.assertEqual(o["durum"], "OK")
        self.assertEqual(o["toplam"], 3)
        self.assertEqual(o["arizalar"], 1)
        self.assertEqual(o["moduller"]["a.f"], 2)


class IzleyiciTests(_YalitilmisGunluk):

    def test_istisnayi_yutar_ve_kaydeder(self):
        with gunluk.izle("m", "i", neden="sinama"):
            raise RuntimeError("ic hata")
        kayitlar = gunluk.son_kayitlar()
        self.assertEqual(len(kayitlar), 1)
        self.assertEqual(kayitlar[0]["tip"], "RuntimeError")
        self.assertIn("iz", kayitlar[0])

    def test_hatasiz_blok_kayit_birakmaz(self):
        with gunluk.izle("m", "i", neden="sinama"):
            pass
        self.assertEqual(gunluk.son_kayitlar(), [])

    def test_durdurma_emri_yutulmaz(self):
        """KeyboardInterrupt bir ariza degil, birinin durdurma emridir.

        Yutmak, durdurulamayan surec demektir.
        """
        with self.assertRaises(KeyboardInterrupt):
            with gunluk.izle("m", "i", neden="sinama"):
                raise KeyboardInterrupt
        self.assertEqual(gunluk.son_kayitlar(), [])


class DevirTests(_YalitilmisGunluk):
    def test_sinir_asilinca_devredilir(self):
        yol = self.yol
        eski = gunluk.AZAMI_BAYT
        gunluk.AZAMI_BAYT = 200
        try:
            for _ in range(20):
                gunluk.yut("m", "i", ValueError("x" * 50), neden="n")
            self.assertTrue(yol.with_suffix(yol.suffix + ".1").exists())
            # Devirden sonra yazmaya devam edilmeli, kaybolmamali.
            self.assertTrue(yol.exists() and yol.stat().st_size > 0)
        finally:
            gunluk.AZAMI_BAYT = eski


if __name__ == "__main__":
    unittest.main()
