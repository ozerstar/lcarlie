"""Varlik siniflandiricisi + kaynak/yerlesim ayrimi + kirpma korunumu.

Fixture'lar sentetik uretilir -- gercek urun gorseline bagimli degil,
CI'da da kosar. Negatif fixture'lar kapinin GERCEKTEN reddettigini
dogrular; yalniz "gecti" testi yeterli degildir.
"""
import pathlib
import sys
import tempfile
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_gorsel_olcum as olcum   # noqa: E402
from jarvis import katalog_varlik as varlik        # noqa: E402

try:
    import numpy as np
    from PIL import Image
    ARAC_VAR = True
except ImportError:                                 # pragma: no cover
    ARAC_VAR = False


# --- fixture ureticileri -------------------------------------------------

def _editoryal(yol, en=1600, boy=1600, seed=7):
    """TYPE A adayi: dokulu arka plan, merkez disi urun, golge, parlama."""
    rng = np.random.default_rng(seed)
    # dokulu, gradyanli zemin
    yy, xx = np.mgrid[0:boy, 0:en].astype("float32")
    zemin = 0.42 + 0.18 * (xx / en) + 0.10 * (yy / boy)
    zemin += rng.normal(0, 0.045, (boy, en))          # malzeme dokusu
    kare = np.clip(np.dstack([zemin * 1.02, zemin, zemin * 0.94]), 0, 1)

    # urun: merkez disi dikey sise, karenin ~%17'si
    u_en, u_boy = int(en * 0.22), int(boy * 0.52)
    x0, y0 = int(en * 0.58), int(boy * 0.24)
    kare[y0:y0 + u_boy, x0:x0 + u_en] = 0.88
    # etiket bandi
    kare[y0 + u_boy // 3: y0 + u_boy // 3 + u_boy // 6, x0:x0 + u_en] = 0.30
    # parlama seridi (dusuk doygunluk, yuksek parlaklik)
    kare[y0:y0 + u_boy, x0 + 2: x0 + 2 + max(3, u_en // 12)] = 0.985
    # temas golgesi: urun altinda koyulasma
    g_boy = int(boy * 0.05)
    for i in range(g_boy):
        k = 1.0 - 0.45 * (1 - i / g_boy)
        ys = y0 + u_boy + i
        if ys < boy:
            kare[ys, max(0, x0 - u_en // 3): min(en, x0 + u_en + u_en // 3)] *= k

    Image.fromarray((np.clip(kare, 0, 1) * 255).astype("uint8")).save(yol)
    return yol


def _studyo(yol, en=1600, boy=1600):
    """TYPE B adayi: duz notr zemin, ortalanmis urun, golge yok."""
    kare = np.full((boy, en, 3), 0.95, dtype="float32")
    u_en, u_boy = int(en * 0.30), int(boy * 0.46)
    x0, y0 = (en - u_en) // 2, (boy - u_boy) // 2
    kare[y0:y0 + u_boy, x0:x0 + u_en] = 0.55
    Image.fromarray((kare * 255).astype("uint8")).save(yol)
    return yol


def _packshot(yol, en=1200, boy=1600):
    """TYPE C: alfa kanalli kesim."""
    kare = np.zeros((boy, en, 4), dtype="uint8")
    u_en, u_boy = int(en * 0.45), int(boy * 0.70)
    x0, y0 = (en - u_en) // 2, (boy - u_boy) // 2
    kare[y0:y0 + u_boy, x0:x0 + u_en, :3] = 210
    kare[y0:y0 + u_boy, x0:x0 + u_en, 3] = 255
    Image.fromarray(kare, mode="RGBA").save(yol)
    return yol


def _minik(yol, en=180, boy=240):
    """TYPE D: mutlak tabanin altinda."""
    Image.fromarray(np.full((boy, en, 3), 128, dtype="uint8")).save(yol)
    return yol


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class KaynakVeYerlesimAyri(unittest.TestCase):
    """OLCULEN HATA: buyutme 'source quality passed' uretiyordu."""

    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def test_kaynak_okunuyor(self):
        p = _studyo(self.d / "a.png")
        k = olcum.kaynak_kalite(p)
        self.assertIsNone(k.okunamadi)
        self.assertEqual((k.genislik_px, k.yukseklik_px), (1600, 1600))
        self.assertFalse(k.alfa_var)

    def test_okunamayan_dosya_kotu_degil_bilinmiyor(self):
        k = olcum.kaynak_kalite(self.d / "olmayan.png")
        self.assertIsNotNone(k.okunamadi)
        self.assertEqual(k.genislik_px, 0)

    def test_buyutme_gecme_sebebi_degildir(self):
        p = _studyo(self.d / "a.png", 1200, 1200)
        k = olcum.kaynak_kalite(p)
        # 1200 px -> 200 mm yerlesim = 152 dpi: esigin altinda
        y = olcum.yerlesim_kalite(k, 200.0, 200.0)
        self.assertFalse(y.gecti)
        self.assertLess(y.efektif_dpi, olcum.ASGARI_DPI)

    def test_esigi_gecen_ama_buyutme_isteyen_gecmez(self):
        p = _studyo(self.d / "a.png", 1200, 1200)
        k = olcum.kaynak_kalite(p)
        # 1200 px -> 105 mm = 290 dpi: esik ustu ama 300 icin buyutme gerekir
        y = olcum.yerlesim_kalite(k, 105.0, 105.0)
        self.assertGreater(y.efektif_dpi, olcum.ASGARI_DPI)
        self.assertTrue(y.buyutuldu)
        self.assertFalse(y.gecti, "buyutme gerektiren yerlesim GECMEMELI")
        self.assertIn("buyutme gecme sebebi degildir", y.gerekce)

    def test_buyutmesiz_yerlesim_gecer(self):
        p = _studyo(self.d / "a.png", 2400, 2400)
        k = olcum.kaynak_kalite(p)
        y = olcum.yerlesim_kalite(k, 200.0, 200.0)   # 2400px/200mm = 305 dpi
        self.assertTrue(y.gecti, y.gerekce)
        self.assertFalse(y.buyutuldu)

    def test_azami_guvenli_yerlesim(self):
        p = _studyo(self.d / "a.png", 3543, 3543)     # 300 dpi'da 300 mm
        k = olcum.kaynak_kalite(p)
        en, boy = olcum.azami_guvenli_yerlesim_mm(k)
        self.assertAlmostEqual(en, 300.0, delta=1.0)
        self.assertAlmostEqual(boy, 300.0, delta=1.0)


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class KirpmaKorunumu(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def test_gercek_kayip_olculur(self):
        """OLCULEN VAKA: ham 1254 px -> kesim 299 px."""
        oz = olcum.kaynak_kalite(_studyo(self.d / "ham.png", 1254, 1254))
        kr = olcum.kaynak_kalite(_studyo(self.d / "kesim.png", 299, 800))
        k = olcum.kirpma_korunumu(oz, kr)
        self.assertLess(k.korunum_orani, 0.16)
        self.assertGreater(k.atilan_alan_px, 1_000_000)
        self.assertTrue(k.en_boy_degisti)

    def test_dusuk_korunum_yargi_uretmez(self):
        """Modul 'kotu' demez -- yalnizca olcer."""
        oz = olcum.kaynak_kalite(_studyo(self.d / "a.png", 1000, 1000))
        kr = olcum.kaynak_kalite(_studyo(self.d / "b.png", 300, 300))
        k = olcum.kirpma_korunumu(oz, kr)
        alanlar = k.sozluk()
        for anahtar in alanlar:
            self.assertNotIn("kotu", anahtar)
            self.assertNotIn("basarisiz", anahtar)


@unittest.skipUnless(ARAC_VAR, "Pillow/numpy yok")
class Siniflandirici(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.d = pathlib.Path(self.gecici.name)

    def tearDown(self):
        self.gecici.cleanup()

    def test_editoryal_fotograf_A_olur(self):
        s = varlik.siniflandir(_editoryal(self.d / "ed.png"))
        self.assertEqual(s.asset_type, "A", "\n".join(s.evidence))

    def test_A_icin_kesim_YASAK(self):
        """TYPE A korumasi -- bu fazin varlik sebebi."""
        s = varlik.siniflandir(_editoryal(self.d / "ed.png"))
        self.assertIn("background_removal", s.forbidden_operations)
        self.assertIn("automatic_crop_to_product", s.forbidden_operations)
        self.assertIn("product_regeneration", s.forbidden_operations)
        with self.assertRaises(varlik.VarlikIhlali):
            varlik.islemi_dogrula(s, "background_removal")

    def test_A_icin_sayfa_yerlesimi_izinli(self):
        s = varlik.siniflandir(_editoryal(self.d / "ed.png"))
        varlik.islemi_dogrula(s, "non_destructive_page_placement")
        self.assertTrue(varlik.islem_izinli_mi(s, "layout_derived_from_photograph"))

    def test_studyo_B_olur(self):
        s = varlik.siniflandir(_studyo(self.d / "st.png"))
        self.assertEqual(s.asset_type, "B", "\n".join(s.evidence))

    def test_packshot_C_olur(self):
        s = varlik.siniflandir(_packshot(self.d / "pk.png"))
        self.assertEqual(s.asset_type, "C", "\n".join(s.evidence))
        self.assertIn("background_removal", s.allowed_operations)

    def test_minik_gorsel_D_olur(self):
        s = varlik.siniflandir(_minik(self.d / "mn.png"))
        self.assertEqual(s.asset_type, "D")
        self.assertEqual(s.allowed_operations, ())

    def test_hedef_olcu_yetmezse_D(self):
        """Yuksek cozunurluklu ama hedef cok buyukse D."""
        s = varlik.siniflandir(_editoryal(self.d / "ed.png", 1600, 1600),
                               hedef_en_mm=300.0, hedef_boy_mm=300.0)
        self.assertEqual(s.asset_type, "D", "\n".join(s.evidence))
        self.assertTrue(any("yetersiz" in e for e in s.evidence))

    def test_hedef_olcu_yetiyorsa_sinif_korunur(self):
        s = varlik.siniflandir(_editoryal(self.d / "ed.png", 2400, 2400),
                               hedef_en_mm=190.0, hedef_boy_mm=190.0)
        self.assertEqual(s.asset_type, "A", "\n".join(s.evidence))

    def test_D_icin_her_islem_reddedilir(self):
        s = varlik.siniflandir(_minik(self.d / "mn.png"))
        for islem in ("non_destructive_page_placement", "background_removal",
                      "color_managed_placement"):
            with self.assertRaises(varlik.VarlikIhlali):
                varlik.islemi_dogrula(s, islem)

    def test_tanimsiz_islem_varsayilan_red(self):
        s = varlik.siniflandir(_packshot(self.d / "pk.png"))
        with self.assertRaises(varlik.VarlikIhlali):
            varlik.islemi_dogrula(s, "uydurma_islem")

    def test_kanit_her_zaman_uretilir(self):
        for uretici in (_editoryal, _studyo, _packshot, _minik):
            s = varlik.siniflandir(uretici(self.d / (uretici.__name__ + ".png")))
            self.assertTrue(s.evidence, "%s icin kanit yok" % uretici.__name__)

    def test_guven_asla_1_degil(self):
        """Sahte kesinlik uretme."""
        for uretici in (_editoryal, _studyo, _packshot):
            s = varlik.siniflandir(uretici(self.d / (uretici.__name__ + "2.png")))
            self.assertLess(s.confidence, 1.0)
            self.assertGreater(s.confidence, 0.0)

    def test_azami_guvenli_yerlesim_her_zaman_var(self):
        s = varlik.siniflandir(_editoryal(self.d / "ed.png"))
        self.assertEqual(len(s.max_safe_placement_mm), 2)
        self.assertGreater(s.max_safe_placement_mm[0], 0)


if __name__ == "__main__":
    unittest.main()
