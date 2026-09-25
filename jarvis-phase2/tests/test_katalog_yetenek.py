"""Katalog yetenek kutugu: kutuk kendi kurallarini ihlal etmiyor mu."""
import pathlib
import sys
import unittest

KOK = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import katalog_yetenek as ky  # noqa: E402


class KutukButunlugu(unittest.TestCase):
    def test_dogrulama_temiz(self):
        sorunlar = ky.dogrula()
        self.assertEqual(sorunlar, [], "kutuk kendi kurallarini ihlal ediyor:\n" + "\n".join(sorunlar))

    def test_18_yetenek(self):
        # 15 rol -> 18: 09 bolundu (09A/09B), 07A eklendi, HUMAN ayri kayit.
        self.assertEqual(len(ky.kayitlar()), 18)

    def test_kimlikler_benzersiz(self):
        kimlikler = [y.id for y in ky.kayitlar()]
        self.assertEqual(len(kimlikler), len(set(kimlikler)))

    def test_deterministik_model_istemez(self):
        for y in ky.tipe_gore("DETERMINISTIC"):
            self.assertFalse(y.vision_required, "%s vision istiyor" % y.id)
            self.assertFalse(y.llm_required, "%s llm istiyor" % y.id)

    def test_urun_butunlugu_asilamaz(self):
        y = ky.getir("C12")
        self.assertIsNotNone(y)
        self.assertIn("HARD_REJECT", y.authority)
        self.assertEqual(y.type, "DETERMINISTIC")
        self.assertTrue(y.measurements_required)

    def test_hard_reject_olcume_dayanir(self):
        for y in ky.yetkiye_gore("HARD_REJECT"):
            if y.type == "HUMAN":
                continue
            self.assertTrue(y.measurements_required,
                            "%s HARD_REJECT veriyor ama olcumu yok" % y.id)

    def test_dongu_yok(self):
        self.assertNotIn("dongu", " ".join(ky.dogrula()))

    def test_tiyatro_uyarisi_yok(self):
        bulgular = ky.tiyatro_taramasi()
        self.assertEqual(bulgular, [], "agent theater adayi: %s" % bulgular)

    def test_json_dokulebiliyor(self):
        import json
        veri = json.loads(ky.json_dok())
        self.assertEqual(len(veri), 18)
        self.assertIn("acceptance_conditions", veri[0])


class TiyatroDedektoruCalisiyor(unittest.TestCase):
    """Dedektor gercekten yakaliyor mu -- negatif fixture."""

    def test_bos_rol_yakalanir(self):
        sahte = ky._y(
            id="SAHTE", name="Fikir Danismani", type="CREATIVE",
            purpose="Gorus bildirir.",
            inputs=list(ky.getir("C07").inputs),          # baskasinin girdisi
            measurements_required=list(ky.getir("C07").measurements_required),
            authority=["ADVISE"],                          # gercek yetki yok
        )
        eski = ky.KUTUK
        try:
            ky.KUTUK = eski + (sahte,)
            bulgular = ky.tiyatro_taramasi()
            kimlikler = [b["id"] for b in bulgular]
            self.assertIn("SAHTE", kimlikler)
        finally:
            ky.KUTUK = eski

    def test_olcup_yetkisiz_kalan_yakalanir(self):
        sahte = ky._y(
            id="OLCER", name="Olcer ama susar", type="DETERMINISTIC",
            purpose="Olcer.",
            measurements_required=["tasma"],
            authority=[],
        )
        eski = ky.KUTUK
        try:
            ky.KUTUK = eski + (sahte,)
            sorunlar = ky.dogrula()
            self.assertTrue(any("GATEKEEPER degil" in s for s in sorunlar), sorunlar)
        finally:
            ky.KUTUK = eski


if __name__ == "__main__":
    unittest.main()
