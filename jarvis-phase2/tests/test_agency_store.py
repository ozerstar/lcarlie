"""Ajans teslimatının saklanması ve şartname üretimi. Ağ yok, veritabanı yok.

Sınanan asıl davranış: onay kuyruğuna GERÇEK metin gitmeli. İçeriği
görünmeyen bir öneriyi onaylamak, onay değil imza atmaktır.
"""
import json
import tempfile
import unittest
from pathlib import Path


def teslimat(product="INTIMBLANC (Test)", statuses=("PROPOSABLE",) * 2):
    concepts = [
        {"name": f"Konsept {i + 1}", "hook": f"kanca {i + 1}",
         "headline": f"başlık {i + 1}", "primary_text": f"gövde metni {i + 1}",
         "cta": "Daha Fazla Bilgi", "product": product,
         "regulatory_risk": "NONE_DETECTED_TIER1"}
        for i in range(len(statuses))]
    return {
        "task": "test kampanyası", "objective": "CAMPAIGN_PROPOSAL",
        "product": product, "creative_concepts": concepts,
        "proposals": {"concepts": [{"status": s} for s in statuses]},
    }


class AgencyStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        import os
        os.environ["JARVIS_STATE_DIR"] = self._tmp.name
        import importlib

        from jarvis import agency_store
        self.store = importlib.reload(agency_store)

    def tearDown(self):
        self._tmp.cleanup()

    # --- saklama
    def test_teslimat_diske_yazilir(self):
        out = self.store.save(teslimat())
        self.assertTrue(Path(out["path"]).exists())
        geri = self.store.get(out["id"])
        self.assertEqual("test kampanyası", geri["deliverable"]["task"])

    def test_ayni_teslimat_ayni_kimlik(self):
        """İçerik hashi: aynı istek iki kez kaydedilip çoğalmamalı."""
        self.assertEqual(self.store.save(teslimat())["id"],
                         self.store.save(teslimat())["id"])

    def test_farkli_urun_farkli_kimlik(self):
        self.assertNotEqual(self.store.save(teslimat("A"))["id"],
                            self.store.save(teslimat("B"))["id"])

    # --- sartname
    def test_her_onerilebilir_konsept_icin_sartname(self):
        out = self.store.save(teslimat(statuses=("PROPOSABLE", "PROPOSABLE")))
        self.assertEqual(2, len(out["specs"]))

    def test_bloklu_konsept_sartname_uretmez(self):
        """Firewall zaten reddederdi; dosya ortada kalmamalı."""
        out = self.store.save(teslimat(statuses=("PROPOSABLE", "BLOCKED")))
        self.assertEqual(1, len(out["specs"]))

    def test_sartname_gercek_metni_tasir(self):
        """Asıl mesele bu: onaylayan insan reklamı görebilmeli."""
        out = self.store.save(teslimat())
        spec = json.loads(Path(out["specs"][0]["spec_path"]).read_text(encoding="utf-8"))
        self.assertEqual("gövde metni 1", spec["payload"]["primary_text"])
        self.assertEqual("kanca 1", spec["payload"]["hook"])

    def test_ic_alanlar_yuke_girmez(self):
        """name ve regulatory_risk müşteriye ulaşmaz; yükte işleri yok."""
        out = self.store.save(teslimat())
        spec = json.loads(Path(out["specs"][0]["spec_path"]).read_text(encoding="utf-8"))
        self.assertNotIn("regulatory_risk", spec["payload"])
        self.assertNotIn("name", spec["payload"])

    def test_komut_insana_verilir_calistirilmaz(self):
        """Görevi İNSAN açar. Bu modül veritabanına yazmaz."""
        out = self.store.save(teslimat())
        self.assertTrue(out["specs"][0]["command"].startswith(
            "jarvis-operator create-task META_CAMPAIGN_CHANGE "))

    def test_sosyal_plan_farkli_niyete_duser(self):
        d = teslimat()
        d["objective"] = "SOCIAL_PLAN"
        out = self.store.save(d)
        self.assertIn("DRAFT_CUSTOMER_REPLY", out["specs"][0]["command"])

    # --- okuma
    def test_sartname_slug_ile_okunur(self):
        out = self.store.save(teslimat())
        spec = self.store.load_spec(out["specs"][0]["slug"])
        self.assertEqual("Konsept 1", spec["concept_name"])

    def test_olmayan_sartname_none(self):
        """Uydurmaz: bilinmeyen slug None döner."""
        self.assertIsNone(self.store.load_spec("boyle-bir-sey-yok"))

    def test_gecmis_yeniden_eskiye(self):
        self.store.save(teslimat("A"))
        self.store.save(teslimat("B"))
        self.assertEqual("B", self.store.recent(5)[0]["product"])

    def test_konsepti_olmayan_teslimat_cokmez(self):
        d = teslimat()
        d["creative_concepts"] = []
        d["proposals"] = {"concepts": []}
        out = self.store.save(d)
        self.assertEqual([], out["specs"])


if __name__ == "__main__":
    unittest.main()
