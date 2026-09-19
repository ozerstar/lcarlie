"""Ajans fikri -> onaylanabilir öneri köprüsü, ve kelime çarpışması regresyonları.

Çarpışma testleri gerçek metinden geldi: ajans kendi konseptinde "iddia sınırı"
yazıyordu ve tarayıcı bunu "sinir" (nerve) sanıp bloklamıştı.
"""
import unittest

from jarvis.action_contract import build_contract
from jarvis.agency_proposal import (BLOCKED, NO_TEXT, PROPOSABLE,
                                    publishable_text, screen)
from jarvis.compliance import review

# Sozlesme, gercek eslemeden turetilir. Elle yazilan bir tip listesi
# INTENT_TO_CANONICAL ile ayrisinca firewall hakli olarak CONTRACT_DRIFT der
# ve test, mevzuat kapisi yerine kendi fiksturunu olcmus olur -- bir kez oldu.
from jarvis.action_contract import INTENT_TO_CANONICAL  # noqa: E402

LIVE_ROWS = [
    {"action_type": t, "risk_class": "MEDIUM", "approval_mode": "ONE_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"}
    for t in sorted(set(INTENT_TO_CANONICAL.values()))
]


def contract():
    return build_contract(LIVE_ROWS, source="test")


TEMIZ = {"name": "Rutin", "hook": "Bakım rutini neden düzenli olmalı?",
         "caption_direction": "Cilt görünümünü destekleyen sade adımlar",
         "cta": "Detayları incele"}
IHLALLI = {"name": "Isı", "hook": "Dolaşımı destekler",
           "caption_direction": "Kas rahatlatıcı etki", "cta": "Keşfet"}


class KelimeCarpismasiTests(unittest.TestCase):
    """Kısa terimlerin masum kelimelere çarpması -- ölçülmüş vakalar."""

    def test_iddia_siniri_bloklanmaz(self):
        """deaccent ı->i çevirdiği için 'sınır' -> 'sinir' oluyordu."""
        self.assertFalse(review("Kozmetik bakım sınırını anlat").blocked)

    def test_sinir_sistemi_hala_bloklu(self):
        self.assertTrue(review("Sinir sistemi üzerinde etkilidir").blocked)

    def test_kasa_ve_kasim_bloklanmaz(self):
        """'kas' üç harf; alt dize arandığında 'kasa'/'kasım'a çarpıyordu."""
        self.assertFalse(review("Kasa işlemleri ve kasım ayı raporu").blocked)

    def test_gercek_kas_iddialari_hala_bloklu(self):
        for cumle in ("Kas zarı besleyici", "Kas liflerini onarıcı",
                      "Kas rahatlatıcı", "Kasları rahatlatır"):
            self.assertTrue(review(cumle).blocked, cumle)

    def test_vireon_kalibi_korunuyor(self):
        self.assertTrue(review("Dolaşımı destekler").blocked)


class PublishableTextTests(unittest.TestCase):
    def test_yalnizca_yayimlanacak_alanlar_alinir(self):
        text = publishable_text(TEMIZ)
        self.assertIn("Bakım rutini", text)
        self.assertNotIn("Rutin\n", text.split("\n")[0] + "\n")  # name alani degil

    def test_metinsiz_konsept_bos_doner(self):
        self.assertEqual(publishable_text({"name": "x", "day": 3}), "")


class KopruTests(unittest.TestCase):
    def _result(self, concepts, objective="CAMPAIGN_PROPOSAL"):
        return {"task": "kampanya hazırla", "objective": objective,
                "creative_concepts": concepts, "evidence_refs": ["postgres:x"],
                "data_gaps": ["ga4_site_traffic"]}

    def test_temiz_konsept_onerilebilir_olur(self):
        out = screen(self._result([TEMIZ]), contract())
        self.assertEqual(out.concepts[0].status, PROPOSABLE)
        self.assertEqual(len(out.proposable), 1)

    def test_temiz_konsept_gercek_firewall_zarfi_uretir(self):
        out = screen(self._result([TEMIZ]), contract())
        envelope = out.concepts[0].envelope
        self.assertEqual(envelope["status"], "PROPOSED")
        self.assertTrue(envelope["human_approval_required"])
        self.assertEqual(envelope["action_type"], "META_CAMPAIGN_CHANGE")

    def test_ihlalli_konsept_bloklanir_ve_zarf_uretilmez(self):
        out = screen(self._result([IHLALLI]), contract())
        self.assertEqual(out.concepts[0].status, BLOCKED)
        self.assertIsNone(out.concepts[0].envelope)
        self.assertTrue(out.concepts[0].blocked)

    def test_bloklu_konsept_digerlerini_dusurmez(self):
        out = screen(self._result([IHLALLI, TEMIZ]), contract())
        self.assertEqual(len(out.blocked), 1)
        self.assertEqual(len(out.proposable), 1)

    def test_metinsiz_konsept_isaretlenir(self):
        out = screen(self._result([{"name": "bos", "day": 1}]), contract())
        self.assertEqual(out.concepts[0].status, NO_TEXT)

    def test_sozlesme_yoksa_tarama_yine_calisir(self):
        out = screen(self._result([TEMIZ]), contract=None)
        self.assertEqual(out.concepts[0].status, PROPOSABLE)
        self.assertIsNone(out.concepts[0].envelope)

    def test_sosyal_plan_da_taranir(self):
        result = {"task": "sosyal plan", "objective": "SOCIAL_PLAN",
                  "social_plan": [dict(IHLALLI, topic="Isı")], "creative_concepts": []}
        out = screen(result, contract())
        self.assertEqual(out.concepts[0].status, BLOCKED)

    def test_dogrulama_bulgusu_onermeyi_engellemez(self):
        concept = dict(TEMIZ, hook="Kampanya 14 günde sonuçlanır")
        out = screen(self._result([concept]), contract())
        self.assertEqual(out.concepts[0].status, PROPOSABLE)
        self.assertTrue(out.concepts[0].verify)

    def test_cikti_hicbir_sey_yayimlamadigini_soyler(self):
        payload = screen(self._result([TEMIZ]), contract()).to_dict()
        self.assertEqual(payload["external_actions"], 0)
        self.assertTrue(payload["human_approval_required"])
        self.assertIn("yayımlanmaz", payload["note"])


class AjansKendiDenetiminiYapiyorTests(unittest.TestCase):
    """Ajans artık gerçekten denetliyor.

    Bu testler kaynak metninde dize aramaz -- bir kez denendi ve kendi
    açıklama yorumundaki kelimeye takıldı. Davranış ölçülür: ihlalli bir
    konsept içeri verilir, dışarı ne çıktığına bakılır.
    """

    def _agency(self):
        from jarvis import agency
        return agency

    def test_ihlalli_konsept_none_detected_donmez(self):
        agency = self._agency()
        enriched = agency._enrich_concepts([dict(IHLALLI)], {"rows": 1}, {"rows": 1})
        self.assertEqual(enriched[0]["regulatory_risk"], "BLOCKED")
        self.assertTrue(enriched[0]["regulatory_findings"])

    def test_temiz_konsept_tier1_temiz_isaretlenir(self):
        agency = self._agency()
        enriched = agency._enrich_concepts([dict(TEMIZ)], {"rows": 1}, {"rows": 1})
        self.assertEqual(enriched[0]["regulatory_risk"], "NONE_DETECTED_TIER1")

    def test_nesne_kurali_devrede_kelime_listesi_degil(self):
        """Eski 11 ifadelik liste bu cümleyi kaçırıyordu -- ölçüldü."""
        agency = self._agency()
        kacan = {"name": "x", "hook": "Dolaşımı destekler"}
        risks, objections = agency._regulatory_review([kacan])
        self.assertTrue(risks, "nesne kuralı devrede değil")
        self.assertTrue(any(o.get("basis") for o in objections),
                        "bulgu dayanağını taşımıyor")

    def test_eski_liste_bu_cumleyi_gercekten_kaciriyor(self):
        """Karşılaştırma: iyileştirmenin ölçülebilir olduğunu sabitler."""
        agency = self._agency()
        text = "Dolaşımı destekler".casefold()
        self.assertFalse(any(p in text for p in agency.PROHIBITED_CLAIMS))


if __name__ == "__main__":
    unittest.main()
