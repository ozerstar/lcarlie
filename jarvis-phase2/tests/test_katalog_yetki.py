"""Yetki grafigi: siddet kazanir, oy cokluğu degil."""
import pathlib
import sys
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_yetenek as yt   # noqa: E402
from jarvis import katalog_yetki as yk     # noqa: E402


def _k(cap, yetki, gerekce="test"):
    return yk.Karar(cap, yetki, gerekce, {"olcum": 1})


class YetkiDogrulamasi(unittest.TestCase):
    def test_sahip_olmadigi_yetki_reddedilir(self):
        # C05 Copywriter'in hicbir ret yetkisi yok
        with self.assertRaises(yk.YetkiIhlali):
            yk.yetki_dogrula(_k("C05", "HARD_REJECT"))

    def test_bilinmeyen_capability_reddedilir(self):
        with self.assertRaises(yk.YetkiIhlali):
            yk.yetki_dogrula(_k("C99", "REJECT"))

    def test_sahip_oldugu_yetki_gecer(self):
        yk.yetki_dogrula(_k("C12", "HARD_REJECT"))
        yk.yetki_dogrula(_k("C07", "REJECT"))


class Cozumleme(unittest.TestCase):
    def test_oylama_yok_siddet_kazanir(self):
        """Uc onay bir HARD_REJECT'i yenemez."""
        kararlar = [
            _k("C15", "APPROVE"),
            _k("C09A", "ADVISE"),
            _k("C07", "REVISE"),
            _k("C12", "HARD_REJECT", "uretken islem urun pikseline uygulanmis"),
        ]
        s = yk.cozumle(kararlar)
        self.assertEqual(s["sonuc"], "HARD_REJECT")
        self.assertEqual(s["belirleyen"], "C12")
        self.assertFalse(s["asilabilir"])

    def test_hard_reject_asilamaz(self):
        s = yk.cozumle([_k("C06", "HARD_REJECT")])
        self.assertFalse(s["asilabilir"])

    def test_reject_yalniz_insan_asar(self):
        s = yk.cozumle([_k("C07", "REJECT")])
        self.assertEqual(s["sonuc"], "REJECT")
        self.assertTrue(s["asilabilir"])
        self.assertTrue(s["yalniz_insan_asar"])

    def test_karar_yoksa_KANIT_YOK(self):
        """Bos liste 'gecti' anlamina GELMEZ."""
        s = yk.cozumle([])
        self.assertEqual(s["sonuc"], "KANIT_YOK")
        self.assertFalse(s["asilabilir"])

    def test_ucuncu_turda_insana_tasinir(self):
        s = yk.cozumle([_k("C07", "REJECT")], tur=3)
        self.assertEqual(s["sonuc"], "ESCALATE_TO_HUMAN")
        self.assertTrue(s["tur_siniri_asildi"])

    def test_tur_siniri_hard_rejecti_yumusatmaz(self):
        s = yk.cozumle([_k("C12", "HARD_REJECT")], tur=5)
        self.assertEqual(s["sonuc"], "HARD_REJECT")

    def test_advise_akisi_degistirmez(self):
        s = yk.cozumle([_k("C09A", "ADVISE")])
        self.assertEqual(s["sonuc"], "ADVISE")


class Grafik(unittest.TestCase):
    def test_grafik_dogrulamasi_temiz(self):
        g = yk.grafik()
        self.assertEqual(g["dogrulama"], [], g["dogrulama"])
        self.assertFalse(yk.ozet()["dongu_var_mi"])

    def test_durdurabilenler_beklenen_kume(self):
        g = yk.grafik()
        for kimlik in ("C12", "C06", "C09B", "C07A"):
            self.assertIn(kimlik, g["durdurabilen"])

    def test_yetkisiz_capability_bilinir(self):
        """C05 ve C08 uretir, reddetmez -- bu bilincli bir karardir."""
        g = yk.grafik()
        self.assertIn("C05", g["yetkisiz"])
        self.assertIn("C08", g["yetkisiz"])


class AgentTheaterKorumasi(unittest.TestCase):
    def test_bos_persona_eklenmez(self):
        aday = yt._y(
            id="YENI", name="Kreatif Danisman", type="CREATIVE",
            purpose="Gorus bildirir.",
            inputs=list(yt.getir("C07").inputs),
            measurements_required=list(yt.getir("C07").measurements_required),
            authority=["ADVISE"],
        )
        s = yk.yeni_capability_denetle(aday)
        self.assertEqual(s["uyari"], "POTENTIAL_AGENT_THEATER")
        self.assertEqual(s["karar"], "EKLEME")
        self.assertIn("C07", s["ayni_veriyi_okuyan"])

    def test_gercek_yetenek_eklenebilir(self):
        aday = yt._y(
            id="YENI2", name="Cilt Payi Denetcisi", type="DETERMINISTIC",
            purpose="Cilt payinin formata uygunlugunu olcer.",
            inputs=["cilt_sartnamesi"],
            measurements_required=["cilt_payi_mm", "creep"],
            authority=["REJECT"],
        )
        s = yk.yeni_capability_denetle(aday)
        self.assertIsNone(s["uyari"])
        self.assertEqual(s["karar"], "EKLENEBILIR")
        self.assertTrue(s["benzersiz_olcum"])

    def test_yalniz_yetkiyle_de_eklenebilir(self):
        """Ozgun olcumu olmayan ama gercek ret yetkisi olan rol gecerlidir."""
        aday = yt._y(
            id="YENI3", name="Insan onaycisi", type="HUMAN",
            purpose="Onaylar.",
            inputs=list(yt.getir("C15").inputs),
            authority=["APPROVE"],
        )
        s = yk.yeni_capability_denetle(aday)
        self.assertIsNone(s["uyari"])


if __name__ == "__main__":
    unittest.main()
