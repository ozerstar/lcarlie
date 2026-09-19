"""Geçmiş kararlardan ders çıkarma. Veritabanı yok, model yok."""
import unittest

from jarvis import learning


def karar(durum, red_team="CHALLENGE", hazirlik="NO_ACTION",
          tip="MEDIA_BUDGET", kanit="LOW"):
    return {"durum": durum, "red_team_sonucu": red_team,
            "onay_hazirligi": hazirlik, "karar_tipi": tip, "kanit_kalitesi": kanit}


def codes(report):
    return {lesson.code for lesson in report.lessons}


class SayimTests(unittest.TestCase):
    def test_onay_orani_karara_baglananlar_uzerinden(self):
        rows = [karar("APPROVED"), karar("APPROVED"), karar("CANCELLED"),
                karar("PROPOSED")]
        report = learning.analyze(rows)
        lesson = next(x for x in report.lessons if x.code == "red_team_sonucu:CHALLENGE")
        self.assertEqual(lesson.decided, 3)
        self.assertEqual(lesson.approved, 2)
        self.assertAlmostEqual(lesson.approval_rate, 2 / 3, places=2)

    def test_proposed_karar_sayilmaz_orani_sismesin(self):
        """PROPOSED henüz karar değil; sonuç sayılırsa oran yanlış çıkar."""
        rows = [karar("APPROVED")] + [karar("PROPOSED") for _ in range(5)]
        lesson = next(x for x in learning.analyze(rows).lessons
                      if x.code == "red_team_sonucu:CHALLENGE")
        self.assertEqual(lesson.decided, 1)
        self.assertEqual(lesson.stuck, 5)
        self.assertEqual(lesson.approval_rate, 1.0)

    def test_concluded_olumlu_sayilir(self):
        rows = [karar("CONCLUDED") for _ in range(3)]
        lesson = learning.analyze(rows).lessons[0]
        self.assertEqual(lesson.approved, 3)


class OrneklemTests(unittest.TestCase):
    def test_kucuk_ornekemden_ders_uretilmez(self):
        rows = [karar("APPROVED"), karar("APPROVED")]
        report = learning.analyze(rows)
        self.assertEqual(report.lessons, ())
        self.assertTrue(report.skipped)

    def test_atlanan_gerekcesiyle_raporlanir(self):
        report = learning.analyze([karar("APPROVED")])
        self.assertIn("vaka", report.skipped[0]["reason"])

    def test_esik_degeri_belgelenmis(self):
        self.assertGreaterEqual(learning.MIN_SAMPLE, 3)


class SerbestMetinTests(unittest.TestCase):
    def test_uzun_serbest_metin_boyut_olmaz(self):
        """risk alanı serbest metin: her satır kendi değeri olur, sayım anlamsızlaşır."""
        uzun = "Marka görünürlüğü sıfırlanır ve rakipler boşluğu doldurabilir" * 2
        rows = [dict(karar("APPROVED"), karar_tipi=uzun) for _ in range(5)]
        report = learning.analyze(rows)
        self.assertNotIn(f"karar_tipi:{uzun}", codes(report))

    def test_bos_deger_boyut_olmaz(self):
        rows = [dict(karar("APPROVED"), karar_tipi="") for _ in range(4)]
        self.assertNotIn("karar_tipi:", codes(learning.analyze(rows)))


class SiralamaTests(unittest.TestCase):
    def test_hic_karara_baglanmayan_once_gelir(self):
        rows = ([karar("APPROVED", red_team="SUPPORT") for _ in range(6)]
                + [karar("PROPOSED", red_team="INSUFFICIENT_EVIDENCE") for _ in range(4)])
        report = learning.analyze(rows)
        self.assertEqual(report.lessons[0].value, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(report.lessons[0].decided, 0)

    def test_beklemede_olan_ders_bunu_soyler(self):
        rows = [karar("PROPOSED", red_team="INSUFFICIENT_EVIDENCE") for _ in range(4)]
        self.assertIn("HİÇBİRİ", learning.analyze(rows).lessons[0].summary)

    def test_dusuk_onay_orani_yuksekten_once(self):
        rows = ([karar("APPROVED", tip="MEDIA_BUDGET") for _ in range(5)]
                + [karar("CANCELLED", tip="CREATIVE_TEST") for _ in range(4)])
        tipler = [x.value for x in learning.analyze(rows).lessons
                  if x.dimension == "karar_tipi"]
        self.assertEqual(tipler[0], "CREATIVE_TEST")


class SozlesmeTests(unittest.TestCase):
    def test_model_cagrisi_ve_dis_aksiyon_sifir(self):
        payload = learning.analyze([karar("APPROVED") for _ in range(3)]).to_dict()
        self.assertEqual(payload["model_calls"], 0)
        self.assertEqual(payload["external_actions"], 0)

    def test_neden_sonuc_iddia_edilmedigi_yazili(self):
        payload = learning.analyze([karar("APPROVED") for _ in range(3)]).to_dict()
        self.assertIn("Neden-sonuç iddia etmez", payload["note"])

    def test_her_ders_ornekem_buyuklugunu_tasir(self):
        for lesson in learning.analyze([karar("APPROVED") for _ in range(4)]).lessons:
            self.assertGreaterEqual(lesson.sample, learning.MIN_SAMPLE)

    def test_bos_veri_cokmez(self):
        report = learning.analyze([])
        self.assertEqual(report.lessons, ())
        self.assertEqual(report.decisions, 0)


class SaglayiciTests(unittest.TestCase):
    def test_kucuk_ornekem_isaretlenir(self):
        rows = [{"provider": "x", "model": "m", "karar_sayisi": 2, "olumlu": 2,
                 "olumsuz": 0, "is_puani": 60}]
        self.assertTrue(learning.provider_outcomes(rows)[0]["low_sample"])

    def test_karar_sayisina_gore_siralanir(self):
        rows = [{"provider": "a", "karar_sayisi": 1}, {"provider": "b", "karar_sayisi": 9}]
        self.assertEqual(learning.provider_outcomes(rows)[0]["provider"], "b")


class MemoryEntegrasyonTests(unittest.TestCase):
    class FakeMemory:
        def __init__(self, fail=False):
            self.fail = fail

        def get_decision_outcomes(self):
            if self.fail:
                raise RuntimeError("izin yok")
            from jarvis.memory import Evidence
            return Evidence("postgres:decision_outcomes", "C", "t",
                            [karar("APPROVED") for _ in range(4)], 1.0)

        def get_learning_loop(self):
            from jarvis.memory import Evidence
            return Evidence("postgres:learning_loop", "C", "t",
                            [{"provider": "p", "model": "m", "karar_sayisi": 5,
                              "olumlu": 3, "olumsuz": 1, "is_puani": 60}], 1.0)

        def get_evidence_readiness(self):
            from jarvis.memory import Evidence
            return Evidence("postgres:evidence_readiness", "C", "t",
                            [{"karar_tipi": "X", "readiness": "WAITING_DATA",
                              "kanit_sinifi": "LOW"}], 1.0)

    def test_okunabildiginde_ders_uretir(self):
        out = learning.run(self.FakeMemory())
        self.assertEqual(out["status"], "OK")
        self.assertTrue(out["lessons"])
        self.assertTrue(out["providers"])

    def test_okunamazsa_ders_uydurmaz(self):
        out = learning.run(self.FakeMemory(fail=True))
        self.assertEqual(out["status"], "UNAVAILABLE")
        self.assertNotIn("lessons", out)
        self.assertIn("okunamadı", out["note"])


if __name__ == "__main__":
    unittest.main()
