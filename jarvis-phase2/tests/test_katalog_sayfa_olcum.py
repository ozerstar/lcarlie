"""Sayfa/acilim olcumu ve tekrar kaniti.

Kritik test: AYNI DUZEN FARKLI GORSEL ile FARKLI DUZEN AYNI RENK
vakalarinin ikisi de yakalanmali. Tek sinyal ikisini de kaciririr.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_sayfa_olcum as so   # noqa: E402

try:
    import pymupdf
    ARAC_VAR = True
except ImportError:                             # pragma: no cover
    ARAC_VAR = False

MM = 72.0 / 25.4
EN = BOY = 216 * MM


def _ttf():
    kok = pathlib.Path("/opt/lcarlie/jarvis-phase2/varliklar/fontlar-ttf")
    if kok.is_dir():
        for p in sorted(kok.rglob("*.ttf")):
            return p
    return None


def _sayfa_ekle(belge, bloklar, renk=(0.2, 0.2, 0.2), ttf=None):
    """bloklar: [(x_mm, y_mm, en_mm, boy_mm, 'G'|'M')]"""
    s = belge.new_page(width=EN, height=BOY)
    for x, y, w, h, tip in bloklar:
        r = pymupdf.Rect(x * MM, y * MM, (x + w) * MM, (y + h) * MM)
        if tip == "G":
            s.draw_rect(r, color=renk, fill=renk)
        else:
            s.insert_textbox(r, ("L'CARLIE ornek govde metni. " * 12),
                             fontsize=9,
                             fontfile=str(ttf) if ttf else None,
                             fontname="gml" if ttf else "helv")
    return s


@unittest.skipUnless(ARAC_VAR, "pymupdf yok")
class SayfaOlcumleri(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)
        self.ttf = _ttf()

    def tearDown(self):
        self.g.cleanup()

    def _pdf(self, sayfalar, ad="t.pdf"):
        b = pymupdf.open()
        for bloklar, renk in sayfalar:
            _sayfa_ekle(b, bloklar, renk, self.ttf)
        p = self.d / ad
        b.save(str(p)); b.close()
        return p

    def test_oranlar_toplami_biri_gecmez(self):
        p = self._pdf([([(20, 20, 170, 90, "G"), (20, 120, 170, 60, "M")], (0.3, 0.3, 0.3))])
        o = so.sayfa_olcumleri(p)[0]
        self.assertLessEqual(o.gorsel_alan_orani + o.metin_alan_orani, 1.0001)
        self.assertGreaterEqual(o.bosluk_orani, 0.0)

    def test_olcu_mm_dogru(self):
        p = self._pdf([([(20, 20, 100, 100, "G")], (0.3, 0.3, 0.3))])
        o = so.sayfa_olcumleri(p)[0]
        self.assertAlmostEqual(o.en_mm, 216.0, delta=0.5)
        self.assertAlmostEqual(o.boy_mm, 216.0, delta=0.5)

    def test_kenar_bosluklari_olculuyor(self):
        p = self._pdf([([(30, 40, 100, 80, "G")], (0.3, 0.3, 0.3))])
        o = so.sayfa_olcumleri(p)[0]
        self.assertAlmostEqual(o.kenar_bosluk_mm[0], 30.0, delta=1.5)
        self.assertAlmostEqual(o.kenar_bosluk_mm[1], 40.0, delta=1.5)

    def test_bos_sayfa_imzasi(self):
        p = self._pdf([([], (0.3, 0.3, 0.3))])
        o = so.sayfa_olcumleri(p)[0]
        self.assertEqual(o.duzen_imzasi, "BOS")
        self.assertAlmostEqual(o.bosluk_orani, 1.0, delta=0.01)


@unittest.skipUnless(ARAC_VAR, "pymupdf yok")
class TekrarUcSinyal(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)
        self.ttf = _ttf()

    def tearDown(self):
        self.g.cleanup()

    def _pdf(self, sayfalar, ad="t.pdf"):
        b = pymupdf.open()
        for bloklar, renk in sayfalar:
            _sayfa_ekle(b, bloklar, renk, self.ttf)
        p = self.d / ad
        b.save(str(p)); b.close()
        return p

    def test_ayni_duzen_tekrari_yakalanir(self):
        duzen = [(20, 20, 170, 90, "G"), (20, 130, 170, 50, "M")]
        p = self._pdf([(duzen, (0.3, 0.3, 0.3)), (duzen, (0.3, 0.3, 0.3))])
        k = so.tekrar_kaniti(p)
        self.assertTrue(k["ardisik_ayni_duzen"], k)
        self.assertEqual(k["benzersiz_duzen_imzasi"], 1)

    def test_ayni_duzen_farkli_gorsel_duzen_imzasiyla_yakalanir(self):
        """Renkler farkli -- algisal karma kacirir, duzen imzasi yakalar."""
        duzen = [(20, 20, 170, 90, "G"), (20, 130, 170, 50, "M")]
        p = self._pdf([(duzen, (0.05, 0.05, 0.05)), (duzen, (0.85, 0.80, 0.70))])
        k = so.tekrar_kaniti(p)
        self.assertTrue(k["ardisik_ayni_duzen"],
                        "duzen imzasi ayni duzeni yakalamali")

    def test_farkli_duzen_tekrar_uretmez(self):
        p = self._pdf([
            ([(20, 20, 170, 90, "G"), (20, 130, 170, 50, "M")], (0.3, 0.3, 0.3)),
            ([(20, 20, 80, 170, "G"), (110, 20, 80, 60, "M")], (0.3, 0.3, 0.3)),
        ])
        k = so.tekrar_kaniti(p)
        self.assertEqual(k["ardisik_ayni_duzen"], [])
        self.assertEqual(k["benzersiz_duzen_imzasi"], 2)

    def test_algisal_karma_ayni_sayfayi_yakalar(self):
        duzen = [(20, 20, 170, 90, "G")]
        p = self._pdf([(duzen, (0.2, 0.2, 0.2)), (duzen, (0.2, 0.2, 0.2))])
        karmalar = so.algisal_karma(p)
        self.assertEqual(len(karmalar), 2)
        self.assertEqual(so.karma_mesafesi(karmalar[0], karmalar[1]), 0)

    def test_algisal_karma_farkli_sayfayi_ayirir(self):
        p = self._pdf([
            ([(20, 20, 170, 90, "G")], (0.1, 0.1, 0.1)),
            ([(20, 120, 170, 60, "G")], (0.1, 0.1, 0.1)),
        ])
        karmalar = so.algisal_karma(p)
        self.assertGreater(so.karma_mesafesi(karmalar[0], karmalar[1]), 3)

    def test_kanit_yargi_icermez(self):
        duzen = [(20, 20, 170, 90, "G")]
        k = so.tekrar_kaniti(self._pdf([(duzen, (0.2, 0.2, 0.2))]))
        metin = " ".join(k.keys()).lower()
        for yasak in ("kotu", "basarisiz", "gecti", "skor", "puan"):
            self.assertNotIn(yasak, metin)


@unittest.skipUnless(ARAC_VAR, "pymupdf yok")
class AcilimVeRitim(unittest.TestCase):
    def setUp(self):
        self.g = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.g.name)
        self.ttf = _ttf()

    def tearDown(self):
        self.g.cleanup()

    def test_acilim_dengesizligi_olculur(self):
        b = pymupdf.open()
        _sayfa_ekle(b, [], (0.2, 0.2, 0.2), self.ttf)                       # kapak
        _sayfa_ekle(b, [(10, 10, 190, 190, "G")], (0.2, 0.2, 0.2), self.ttf)  # dolu
        _sayfa_ekle(b, [], (0.2, 0.2, 0.2), self.ttf)                       # bos
        p = self.d / "acilim.pdf"; b.save(str(p)); b.close()
        ac = so.acilim_olcumleri(so.sayfa_olcumleri(p))
        self.assertEqual(len(ac), 1)
        self.assertGreater(ac[0].kutle_farki, 0.5)

    def test_ritim_dizisi_uretilir(self):
        b = pymupdf.open()
        for _ in range(4):
            _sayfa_ekle(b, [(20, 20, 170, 90, "G")], (0.2, 0.2, 0.2), self.ttf)
        p = self.d / "ritim.pdf"; b.save(str(p)); b.close()
        r = so.ritim_kaniti(so.sayfa_olcumleri(p))
        self.assertEqual(len(r["yogunluk_dizisi"]), 4)
        self.assertTrue(r["ardisik_uc_ayni_kademe"], "ayni yogunluk yakalanmali")


if __name__ == "__main__":
    unittest.main()
