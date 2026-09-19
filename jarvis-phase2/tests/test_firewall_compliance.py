"""Action Firewall'un mevzuat kapısı.

Kapatılan boşluk: firewall sözleşmeyi, anahtar adlarını ve yükün ŞEKLİNİ
denetliyordu; metnin İÇERİĞİNİ denetlemiyordu. {"reason": "dolaşımı destekler"}
yükü buradan sorunsuz geçip müşteriye gidecek bir taslağa dönüşebiliyordu.
"""
import unittest

from jarvis.action_contract import build_contract
from jarvis.compliance import (PUBLISHED_TEXT_ACTIONS, ComplianceBlocked,
                               TEXT_FIELDS, gate_payload)
from jarvis.firewall import FirewallError, validate_proposal

LIVE_ROWS = [
    {"action_type": "DRAFT_CUSTOMER_REPLY", "risk_class": "MEDIUM", "approval_mode": "ONE_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"},
    {"action_type": "META_CAMPAIGN_CHANGE", "risk_class": "HIGH", "approval_mode": "ONE_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"},
    {"action_type": "PRICE_CHANGE", "risk_class": "CRITICAL", "approval_mode": "TWO_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"},
    {"action_type": "REQUEST_HUMAN_REVIEW", "risk_class": "LOW", "approval_mode": "ONE_PERSON",
     "proposal_enabled": True, "execution_enabled": True, "schema_version": "v1"},
    {"action_type": "WHATSAPP_SEND_TEMPLATE", "risk_class": "HIGH", "approval_mode": "ONE_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"},
    {"action_type": "WIX_PUBLISH", "risk_class": "CRITICAL", "approval_mode": "TWO_PERSON",
     "proposal_enabled": True, "execution_enabled": False, "schema_version": "v1"},
]

TEMIZ = "Hafif dokulu, cilt görünümünü destekleyen bir üründür."
IHLALLI = "Bu ürün dolaşımı destekler ve kızarıklığı azaltır."


def contract():
    return build_contract(LIVE_ROWS, source="postgres:action_contract")


class KapiFirewalldaCalisirTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()

    def test_ihlalli_musteri_taslagi_oneri_olmadan_reddedilir(self):
        with self.assertRaises(FirewallError) as ctx:
            validate_proposal("CUSTOMER_REPLY_DRAFT",
                              {"subject_ref": "k1", "reason": IHLALLI}, self.contract)
        self.assertIn("COMPLIANCE_BLOCKED", str(ctx.exception))

    def test_temiz_musteri_taslagi_gecer_ve_zarfa_islenir(self):
        result = validate_proposal("CUSTOMER_REPLY_DRAFT",
                                   {"subject_ref": "k1", "reason": TEMIZ}, self.contract)
        self.assertEqual(result["status"], "PROPOSED")
        self.assertTrue(result["compliance"]["checked"])
        self.assertTrue(result["compliance"]["clean_tier1"])

    def test_temiz_metin_bile_insan_onayi_ister(self):
        result = validate_proposal("CUSTOMER_REPLY_DRAFT",
                                   {"subject_ref": "k1", "reason": TEMIZ}, self.contract)
        self.assertTrue(result["human_approval_required"])
        self.assertIn("insana ait", result["compliance"]["note"])

    def test_whatsapp_sablonu_da_taranir(self):
        with self.assertRaises(FirewallError):
            validate_proposal("WHATSAPP_TEMPLATE_SEND",
                              {"subject_ref": "k1", "reason": IHLALLI}, self.contract)

    def test_wix_yayini_da_taranir(self):
        with self.assertRaises(FirewallError):
            validate_proposal("WIX_PUBLISH",
                              {"subject_ref": "s1", "reason": IHLALLI}, self.contract)


class KapsamDisiTests(unittest.TestCase):
    """Kapının dar tutulması kasıtlı: her tipi taramak gürültü üretir."""

    def setUp(self):
        self.contract = contract()

    def test_ic_inceleme_talebi_taranmaz(self):
        """REQUEST_HUMAN_REVIEW müşteriye gitmez; içeriği iddia değildir."""
        result = validate_proposal("HUMAN_REVIEW_REQUEST",
                                   {"subject_ref": "x", "reason": IHLALLI}, self.contract)
        self.assertEqual(result["status"], "PROPOSED")
        self.assertFalse(result["compliance"]["checked"])

    def test_fiyat_degisikligi_taranmaz(self):
        result = validate_proposal("PRICE_CHANGE",
                                   {"subject_ref": "p", "reason": IHLALLI}, self.contract)
        self.assertFalse(result["compliance"]["checked"])

    def test_subject_ref_metin_sayilmaz(self):
        """Kimlik alanı taranırsa 'coding-task:akne-fix' hastalık adı sayılır."""
        result = validate_proposal("CUSTOMER_REPLY_DRAFT",
                                   {"subject_ref": "coding-task:akne-fix"}, self.contract)
        self.assertFalse(result["compliance"]["checked"])


class GatePayloadTests(unittest.TestCase):
    def test_bloklu_iddia_yukselir(self):
        with self.assertRaises(ComplianceBlocked) as ctx:
            gate_payload("DRAFT_CUSTOMER_REPLY", {"reason": IHLALLI})
        self.assertTrue(ctx.exception.findings)

    def test_dogrulama_bulgusu_engellemez_ama_iletilir(self):
        out = gate_payload("DRAFT_CUSTOMER_REPLY",
                           {"reason": "Kampanya 14 günde sonuçlanır."})
        self.assertTrue(out["checked"])
        self.assertTrue(out["verify"])

    def test_kapsam_disi_tip_hic_taranmaz(self):
        out = gate_payload("REQUEST_HUMAN_REVIEW", {"reason": IHLALLI})
        self.assertFalse(out["checked"])

    def test_butun_metin_alanlari_birlestirilir(self):
        with self.assertRaises(ComplianceBlocked):
            gate_payload("WIX_PUBLISH", {"body": "Temiz cümle.", "caption": IHLALLI})

    def test_tanimli_alan_listesi_bos_degil(self):
        self.assertIn("reason", TEXT_FIELDS)
        self.assertNotIn("subject_ref", TEXT_FIELDS)

    def test_dort_musteriye_giden_tip_kapsamda(self):
        self.assertEqual(PUBLISHED_TEXT_ACTIONS, {
            "DRAFT_CUSTOMER_REPLY", "WHATSAPP_SEND_TEMPLATE",
            "WIX_PUBLISH", "META_CAMPAIGN_CHANGE"})


if __name__ == "__main__":
    unittest.main()
