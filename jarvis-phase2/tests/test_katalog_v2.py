"""Creative Department V2 -- butunluk, ekip ve baski kademesi testleri."""
from __future__ import annotations

import json
import pathlib
import unittest

from jarvis import katalog_aset_v2 as av2
from jarvis import katalog_dna as dna
from jarvis import katalog_ekip_v2 as ek2
from jarvis import katalog_icerik_v2 as ic2
from jarvis import katalog_referans as ref

INDEKS = pathlib.Path(
    "/opt/lcarlie/output/creative-asset-library/index-v2.json")


def _indeks():
    if not INDEKS.exists():
        raise unittest.SkipTest("index-v2.json yok")
    return json.loads(INDEKS.read_text(encoding="utf-8"))


class ManifestButunlugu(unittest.TestCase):
    """V1'in kusuru: manifest uretimin kullandigi aseti kapsamiyordu."""

    def test_human_subject_ve_rights_celisemez(self):
        hata = av2.dogrula(_indeks())
        self.assertEqual(hata, [], "manifest celiskisi: %s" % hata[:3])

    def test_human_subject_ayri_alan(self):
        k = _indeks()
        self.assertIn("human_subject", k[0])
        self.assertIn("rights_status", k[0])
        self.assertNotEqual(k[0]["human_subject"], k[0]["rights_status"])

    def test_insanli_kare_rights_unknown_human(self):
        for r in _indeks():
            if r["human_subject"] == "EVET":
                self.assertEqual(r["rights_status"], "UNKNOWN_HUMAN_SUBJECT")

    def test_photo_role_gecerli(self):
        for r in _indeks():
            self.assertIn(r["photo_role"], av2.FOTO_ROLLERI)

    def test_coklu_kok_taraniyor(self):
        kokler = {r["source_root"] for r in _indeks()}
        self.assertGreaterEqual(len(kokler), 2,
                                "manifest tek kok tariyor -- V1 kusuru")

    def test_kapsama_denetimi_eksigi_bildirir(self):
        k = _indeks()
        eksik = av2.kapsama_denetimi(k, ["/olmayan/aset.png"])
        self.assertEqual(eksik, ["/olmayan/aset.png"])

    def test_karantina_manifestte_degil(self):
        for r in _indeks():
            self.assertNotIn("ham-kaynak--IMG_", r["source_path"])


class BaskiKademesi(unittest.TestCase):
    """150 PPI premium standart DEGILDIR."""

    def test_uc_kademe(self):
        from scripts.katalog_v2 import baski_kademesi
        self.assertEqual(baski_kademesi(310)["tier"],
                         "PREFERRED_HIGH_QUALITY")
        self.assertEqual(baski_kademesi(260)["tier"], "PRINT_QUALITY_TARGET")
        self.assertEqual(baski_kademesi(180)["tier"],
                         "DESIGN_PROTOTYPE_FLOOR")
        self.assertEqual(baski_kademesi(120)["tier"],
                         "BELOW_PROTOTYPE_FLOOR")

    def test_150_249_arasi_istisna_kaydi_acar(self):
        from scripts.katalog_v2 import baski_kademesi
        k = baski_kademesi(180)
        self.assertIsNotNone(k["exception"])
        self.assertFalse(k["final_print_ready"])

    def test_250_ustu_final_print_ready(self):
        from scripts.katalog_v2 import baski_kademesi
        self.assertTrue(baski_kademesi(255)["final_print_ready"])
        self.assertIsNone(baski_kademesi(255)["exception"])


class EkipV2(unittest.TestCase):
    def test_onsekiz_rol_korundu(self):
        self.assertEqual(len(ek2.matris()), 18)

    def test_her_asamanin_sahibi_var(self):
        k = ek2.kapsama()
        self.assertEqual(k["sahipsiz"], [])

    def test_unbound_rol_bildiriliyor(self):
        k = ek2.kapsama()
        self.assertIn("HUMAN", k["unbound_rol"])

    def test_maker_judge_ayrimi_tanimli(self):
        for x in ek2.matris():
            self.assertIn(x["maker_or_judge"], ("MAKER", "JUDGE"))

    def test_kritik_kapilar_judge(self):
        m = {x["id"]: x for x in ek2.matris()}
        for rid in ("C06", "C09B", "C12", "C13", "C15"):
            self.assertEqual(m[rid]["maker_or_judge"], "JUDGE", rid)


class HandoffSozlesmesi(unittest.TestCase):
    def test_kanitsiz_handoff_gecersiz(self):
        h = ek2.Handoff(task="x", input="y", evidence=[], constraints=[],
                        decision="z", output="o", open_risk=[],
                        next_owner="C01")
        self.assertIn("EVIDENCE bos -- kanitsiz handoff gecersiz",
                      h.dogrula())

    def test_bos_onay_kalibi_theater_sayilir(self):
        h = ek2.Handoff(task="bak", input="y", evidence=["e"],
                        constraints=[], decision="katiliyorum",
                        output="", open_risk=[], next_owner="C01")
        self.assertTrue(any("AGENT_THEATER" in x for x in h.dogrula()))

    def test_gecerli_handoff_temiz(self):
        h = ek2.Handoff(
            task="Tipografi QA kapisini calistir", input="5 PDF",
            evidence=["durduran ihlal 0"], constraints=["punto tabani 5.5"],
            decision="GECTI", output="qa raporu", open_risk=[],
            next_owner="C12", owner="C09B", stage="TECHNICAL_QA")
        self.assertEqual(h.dogrula(), [])

    def test_maker_judge_ihlali_yakalanir(self):
        h = ek2.Handoff(task="kompozisyon kur", input="x", evidence=["e"],
                        constraints=[], decision="d", output="o",
                        open_risk=[], next_owner="C08", owner="C13",
                        stage="COMPOSITION")
        self.assertTrue(ek2.maker_judge_denetimi([h]))

    def test_maker_kendi_isini_yargilayamaz(self):
        h = ek2.Handoff(task="qa", input="x", evidence=["e"], constraints=[],
                        decision="d", output="o", open_risk=[],
                        next_owner="C12", owner="C08", stage="TECHNICAL_QA")
        self.assertTrue(ek2.maker_judge_denetimi([h]))

    def test_maker_judge_ayni_asamada_duplicate_degil(self):
        a = ek2.Handoff(task="koreografi kur", input="x", evidence=["e"],
                        constraints=[], decision="d", output="o1",
                        open_risk=[], next_owner="C14", owner="C04",
                        stage="INFORMATION_CHOREOGRAPHY")
        b = ek2.Handoff(task="koreografiyi yargila", input="o1",
                        evidence=["e"], constraints=[], decision="d",
                        output="o2", open_risk=[], next_owner="SON",
                        owner="C14", stage="INFORMATION_CHOREOGRAPHY")
        t = ek2.theater_taramasi([a, b])
        self.assertFalse([x for x in t["bulgular"]
                          if x["tip"] == "DUPLICATE_CAPABILITY"])

    def test_ayni_durusta_iki_rol_duplicate(self):
        a = ek2.Handoff(task="t1", input="x", evidence=["e"], constraints=[],
                        decision="d", output="o1", open_risk=[],
                        next_owner="SON", owner="C13", stage="REMOVE_TEST")
        b = ek2.Handoff(task="t2", input="x", evidence=["e"], constraints=[],
                        decision="d", output="o2", open_risk=[],
                        next_owner="SON", owner="C14", stage="REMOVE_TEST")
        t = ek2.theater_taramasi([a, b])
        self.assertTrue([x for x in t["bulgular"]
                         if x["tip"] == "DUPLICATE_CAPABILITY"])


class IcerikGercekligi(unittest.TestCase):
    """Uydurma YOK: alan kutu gercegin de yoksa UNKNOWN doner."""

    def test_kinesis_eksik_alanlar_unknown(self):
        d = ic2.yukle("kinesis+")
        self.assertEqual(d["tanim"], ic2.BILINMIYOR)
        self.assertEqual(d["uyari"], ic2.BILINMIYOR)
        self.assertEqual(d["inci"], ic2.BILINMIYOR)

    def test_kinesis_kullanim_var(self):
        self.assertNotEqual(ic2.yukle("kinesis+")["kullanim"], ic2.BILINMIYOR)

    def test_babysol_net_miktar_celiski(self):
        d = ic2.yukle("babysol")
        self.assertEqual(d["net_miktar_durum"], "CELISKI")
        self.assertEqual(d["net_miktar"], ic2.BILINMIYOR)

    def test_femisia_tam_inci_var(self):
        d = ic2.yukle("femisia")
        self.assertNotEqual(d["inci"], ic2.BILINMIYOR)
        self.assertIn("Aqua", d["inci"])

    def test_kaynak_onayli_kutu_metni(self):
        for a in ("hydravie", "femisia", "babysol"):
            self.assertEqual(ic2.yukle(a)["kaynak_tur"], "onayli_kutu_metni")

    def test_kisalt_kelime_ortasindan_kesmez(self):
        m = "Birinci cumle burada. Ikinci cumle de burada devam ediyor."
        k = ic2.kisalt(m, 30)
        self.assertTrue(k.endswith(".") or k.endswith("…"))


class DnaVeKernel(unittest.TestCase):
    def test_bes_kernel_var(self):
        self.assertEqual(len(dna.KERNEL), 5)

    def test_kernel_renk_tarifi_degil(self):
        for _k, v in dna.KERNEL.items():
            c = v["kernel"].lower()
            for renk in ("mavi sayfa", "sarı sayfa", "kırmızı sayfa"):
                self.assertNotIn(renk, c)

    def test_bilinmeyen_dna_alani_isaretli(self):
        o = dna.dna_ozet()
        self.assertIn("kinesis+.BOTANICAL", o["UNKNOWN_alanlar"])

    def test_mekanik_renk_eslesmesi_reddedilir(self):
        with self.assertRaises(dna.IliskiIhlali):
            dna.iliski_dogrula("COMPLEMENTARY_CONTRAST",
                               (200, 200, 200), (202, 201, 200))

    def test_no_repetition_yakin_renk_reddeder(self):
        with self.assertRaises(dna.IliskiIhlali):
            dna.iliski_dogrula("NO_REPETITION", (200, 180, 90),
                               (205, 185, 95))

    def test_gecerli_iliski_gecer(self):
        dna.iliski_dogrula("COMPLEMENTARY_CONTRAST", (230, 190, 45),
                           (30, 40, 60))


class ReferansVeHata(unittest.TestCase):
    def test_dis_referans_uydurulmadi(self):
        self.assertEqual(ref.DIS_REFERANS_DURUMU["uydurma_yapildi_mi"],
                         "HAYIR")

    def test_her_prensibin_kaniti_var(self):
        for p in ref.PRENSIPLER:
            self.assertTrue(p["kanit"].strip(), p["eksen"])
            self.assertTrue(p["uygulama"].strip(), p["eksen"])

    def test_her_hatanin_nedeni_var(self):
        for h in ref.HATA_KUTUGU:
            self.assertTrue(h["neden_basarisiz"].strip(), h["kod"])

    def test_manifest_korlugu_hata_kutugunde(self):
        self.assertIsNotNone(ref.hata_ara("MANIFEST_BLIND_SPOT"))

    def test_ppi_taban_hatasi_kutukte(self):
        self.assertIsNotNone(ref.hata_ara("PPI_FLOOR_AS_QUALITY"))


if __name__ == "__main__":
    unittest.main()
