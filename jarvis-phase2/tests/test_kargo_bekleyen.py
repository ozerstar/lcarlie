import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jarvis import kargo_bekleyen as kb


def paket(**ek):
    p = {"kanal": "Trendyol", "no": "11822830108", "kargo": "Sürat Kargo",
         "kod": "7270039039479965", "musteri": "Ayşe Örnek", "urunler": "HYDRAVIE x1",
         "alici": "Ayşe Örnek", "adres": "Çiçek Mah. Gül Sok. No 1 D 2",
         "ilce": "Çankaya", "il": "Ankara", "telefon": "5550000000",
         "paket_no": "1", "durum": "Picking"}
    p.update(ek)
    return p


def code128_coz(genislikler):
    """Çizilen genişliklerden sembol değerlerini geri okur (bağımsız doğrulama)."""
    from reportlab.graphics.barcode.code128 import _patterns
    ters = {v: k for k, v in _patterns.items()}
    harf = "".join(chr(64 + g) if i % 2 == 0 else chr(96 + g)
                   for i, g in enumerate(genislikler))
    semboller, i = [], 0
    while i < len(harf):
        parca = harf[i:i + 6]
        if parca not in ters:           # dur işareti 7 öğelidir
            parca = harf[i:i + 7]
        semboller.append(ters[parca])
        i += len(parca)
    return semboller


class Barkod(unittest.TestCase):
    def test_rakam_kodu_c_kumesiyle_ve_dogru_saglamayla_kodlanir(self):
        s = code128_coz(kb.code128_cubuklar("7270039039479965"))
        self.assertEqual(s[0], 105)                 # C kümesi başlangıcı
        self.assertEqual(s[-1], 106)                # dur
        veri, saglama = s[1:-2], s[-2]
        self.assertEqual("".join("%02d" % v for v in veri), "7270039039479965")
        beklenen = (105 + sum((i + 1) * v for i, v in enumerate(veri))) % 103
        self.assertEqual(saglama, beklenen)

    def test_cubukla_baslar_ve_cubukla_biter(self):
        g = kb.code128_cubuklar("340064018315")
        self.assertEqual(len(g) % 2, 1)
        self.assertTrue(all(1 <= x <= 4 for x in g))


class Etiket(unittest.TestCase):
    def test_etiket_hb1006_hucresinin_oranindadir(self):
        from PIL import Image
        im = Image.open(io.BytesIO(kb.etiket_png(paket())))
        en, boy = im.size
        self.assertAlmostEqual(en / boy, 99.06 / 93.13, places=2)

    def test_barkod_satiri_cizilen_genisliklerle_ayni(self):
        from PIL import Image
        im = Image.open(io.BytesIO(kb.etiket_png(paket()))).convert("L")
        satir = [im.getpixel((x, 290)) < 128 for x in range(60, im.width - 60)]
        kosular, onceki, uzunluk = [], None, 0
        for siyah in satir:
            if siyah == onceki:
                uzunluk += 1
            else:
                if onceki is not None:
                    kosular.append((onceki, uzunluk))
                onceki, uzunluk = siyah, 1
        kosular.append((onceki, uzunluk))
        while kosular and not kosular[0][0]:
            kosular.pop(0)
        while kosular and not kosular[-1][0]:
            kosular.pop()
        modul = min(u for _s, u in kosular)
        self.assertGreaterEqual(modul, 3)
        self.assertEqual([u // modul for _s, u in kosular],
                         kb.code128_cubuklar("7270039039479965"))

    def test_kodsuz_paket_etiketlenmez(self):
        self.assertFalse(kb.etiketlenebilir(paket(kod="kod yok")))
        self.assertFalse(kb.etiketlenebilir(paket(kanal="Wix")))
        with self.assertRaises(kb.EtiketHatasi):
            kb.etiket_png(paket(kod="kod yok"))


class Dosya(unittest.TestCase):
    def setUp(self):
        self.dizin = tempfile.TemporaryDirectory()
        self.yama = mock.patch.object(kb, "DOSYA", Path(self.dizin.name) / "b.json")
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        self.dizin.cleanup()

    def test_dosya_yokken_paket_yok_denmez(self):
        ozet = kb.panel_ozet()
        self.assertIn("hata", ozet)
        self.assertEqual(ozet["paketler"], [])

    def test_panel_ozeti_adres_ve_telefon_tasimaz(self):
        kb.yaz([paket()], ["n11 (URLError)"])
        ozet = kb.panel_ozet()
        metin = json.dumps(ozet, ensure_ascii=False)
        self.assertNotIn("Gül Sok", metin)
        self.assertNotIn("5550000000", metin)
        self.assertEqual(ozet["okunamayan"], ["n11 (URLError)"])
        p = ozet["paketler"][0]
        self.assertEqual(p["anahtar"], "PZ:trendyol:11822830108")
        self.assertTrue(p["etiket"])
        self.assertFalse(ozet["bayat"])

    def test_dosya_panel_kullanicisina_okunur_yazilir(self):
        yol = kb.yaz([paket()], [])
        if os.name == "posix":
            self.assertEqual(yol.stat().st_mode & 0o777, 0o640)

    def test_paket_anahtarla_bulunur(self):
        kb.yaz([paket(), paket(kanal="İdefix", no="IDE6af60", kod="340064018315")], [])
        self.assertEqual(kb.paket_bul("PZ:idefix:IDE6af60")["kod"], "340064018315")
        with self.assertRaises(kb.EtiketHatasi):
            kb.paket_bul("PZ:trendyol:yok")


if __name__ == "__main__":
    unittest.main()
