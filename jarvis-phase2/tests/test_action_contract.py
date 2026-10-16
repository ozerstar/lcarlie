"""Phase 2D / F-1: canonical action contract and firewall, including the
adversarial cases that must fail closed."""
import unittest

from jarvis.action_contract import (
    CONTRACT_MAP_VERSION, INTENT_TO_CANONICAL, build_contract,
)
from jarvis.firewall import (
    ContractDriftError, FirewallError, known_internal_intents, validate_proposal,
)

# The six canonical rows exactly as core.ai_action_type holds them.
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

GOOD_PAYLOAD = {"subject_ref": "test", "reason": "unit test"}


def contract(rows=None, source="postgres:action_contract"):
    return build_contract(rows if rows is not None else LIVE_ROWS, source=source)


class ContractTests(unittest.TestCase):
    def test_live_shape_is_valid(self):
        value = contract()
        self.assertTrue(value.valid, value.reason)
        self.assertEqual(value.canonical_action_count, 6)
        # 🔴 10, 9 DEGIL. 21.09.2026'da KREATIF_BRIEF ve KREATIF_INCELEME
        # eklendi; 16.10.2026'da TARAYICI_SONUC eklendi. Ucu de
        # REQUEST_HUMAN_REVIEW'a duser (yeni bir DB action type
        # UYDURULMADI -- ucu de "insan baksin" talebi: uretilen seye
        # sahip GOZUYLE bakip karar verir).
        # Cip sayisi degil, KUMENIN KENDISI kilitleniyor: ciplak bir sayi
        # degisince "9 mu 10 mu olmaliydi" diye bakilacak hicbir sey
        # birakmiyor, bu test 24.09'a kadar tam bu yuzden kirmizi kaldi.
        self.assertEqual(
            set(INTENT_TO_CANONICAL),
            {"CUSTOMER_REPLY_DRAFT", "HUMAN_REVIEW_REQUEST", "CODE_CHANGE_REVIEW",
             "KREATIF_BRIEF", "KREATIF_INCELEME", "TARAYICI_SONUC",
             "WHATSAPP_TEMPLATE_SEND", "META_CAMPAIGN_CHANGE", "PRICE_CHANGE",
             "WIX_PUBLISH"},
            "ic niyet kumesi degisti -- sozlesme tarafi da gozden gecirilmeli")
        self.assertEqual(value.mapped_action_count, 10)
        self.assertEqual(value.unknown_internal, ())
        self.assertEqual(value.unknown_canonical, ())

    def test_every_mapping_target_exists_in_the_live_contract(self):
        names = {row["action_type"] for row in LIVE_ROWS}
        self.assertTrue(set(INTENT_TO_CANONICAL.values()).issubset(names))

    def test_no_second_allowlist_remains(self):
        import jarvis.firewall as firewall
        self.assertFalse(hasattr(firewall, "ALLOWED_ACTIONS"))

    def test_hash_is_stable_and_order_independent(self):
        self.assertEqual(contract().contract_hash, contract(list(reversed(LIVE_ROWS))).contract_hash)

    def test_hash_changes_when_schema_version_changes(self):
        bumped = [dict(row) for row in LIVE_ROWS]
        bumped[0]["schema_version"] = "v2"
        self.assertNotEqual(contract().contract_hash, contract(bumped).contract_hash)

    def test_map_version_is_part_of_the_hash(self):
        self.assertTrue(CONTRACT_MAP_VERSION)
        self.assertIn(CONTRACT_MAP_VERSION, contract().telemetry()["contract_map_version"])

    def test_telemetry_fields(self):
        telemetry = contract().telemetry()
        for field in ("contract_source", "contract_hash", "contract_map_version",
                      "canonical_action_count", "mapped_action_count",
                      "unknown_internal", "unknown_canonical", "contract_valid"):
            self.assertIn(field, telemetry)

    def test_boolean_coercion_from_psql_text(self):
        rows = [dict(row) for row in LIVE_ROWS]
        for row in rows:
            row["proposal_enabled"] = "t"
            row["execution_enabled"] = "f"
        self.assertTrue(contract(rows).valid)


class ContractDriftTests(unittest.TestCase):
    def test_empty_contract_is_invalid(self):
        value = contract([])
        self.assertFalse(value.valid)
        self.assertIn("CONTRACT_DRIFT", value.reason)

    def test_new_database_type_without_mapping_fails_closed(self):
        rows = LIVE_ROWS + [{"action_type": "NEW_RISKY_THING", "risk_class": "HIGH",
                             "approval_mode": "ONE_PERSON", "proposal_enabled": True,
                             "execution_enabled": False, "schema_version": "v1"}]
        value = contract(rows)
        self.assertFalse(value.valid)
        self.assertEqual(value.unknown_canonical, ("NEW_RISKY_THING",))

    def test_removed_database_type_fails_closed(self):
        rows = [row for row in LIVE_ROWS if row["action_type"] != "PRICE_CHANGE"]
        value = contract(rows)
        self.assertFalse(value.valid)
        self.assertIn("PRICE_CHANGE", value.unknown_internal)

    def test_disabled_proposal_type_fails_closed(self):
        rows = [dict(row) for row in LIVE_ROWS]
        rows[2]["proposal_enabled"] = False
        value = contract(rows)
        self.assertFalse(value.valid)

    def test_row_missing_a_field_fails_closed(self):
        rows = [dict(row) for row in LIVE_ROWS]
        del rows[0]["risk_class"]
        value = contract(rows)
        self.assertFalse(value.valid)
        self.assertIn("missing fields", value.reason)

    def test_invalid_contract_blocks_every_proposal(self):
        with self.assertRaises(ContractDriftError):
            validate_proposal("HUMAN_REVIEW_REQUEST", GOOD_PAYLOAD, contract([]))

    def test_absent_contract_blocks_every_proposal(self):
        with self.assertRaises(ContractDriftError):
            validate_proposal("HUMAN_REVIEW_REQUEST", GOOD_PAYLOAD, None)


class IntentSelectionTests(unittest.TestCase):
    def test_risky_request_selects_the_right_internal_intent(self):
        from jarvis.action_contract import propose_intent_for
        self.assertEqual(propose_intent_for("Bu müşteriye WhatsApp mesajı gönder."),
                         "WHATSAPP_TEMPLATE_SEND")
        self.assertEqual(propose_intent_for("VIREON fiyatını 1.200 yap"), "PRICE_CHANGE")
        self.assertEqual(propose_intent_for("siteyi yayınla"), "WIX_PUBLISH")

    def test_no_match_yields_no_action(self):
        from jarvis.action_contract import propose_intent_for
        self.assertIsNone(propose_intent_for("Jarvis, sistem durumu ne?"))
        self.assertIsNone(propose_intent_for(""))
        self.assertIsNone(propose_intent_for(None))

    def test_every_selectable_intent_is_mapped_and_valid(self):
        from jarvis.action_contract import INTENT_TRIGGERS, propose_intent_for
        value = contract()
        for intent, terms in INTENT_TRIGGERS:
            self.assertIn(intent, INTENT_TO_CANONICAL)
            self.assertEqual(propose_intent_for(terms[0]), intent)
            self.assertTrue(value.canonical_for(intent))


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract()

    def test_known_intent_maps_to_canonical_type(self):
        result = validate_proposal("HUMAN_REVIEW_REQUEST", GOOD_PAYLOAD, self.contract)
        self.assertEqual(result["action_type"], "REQUEST_HUMAN_REVIEW")
        self.assertEqual(result["status"], "PROPOSED")
        self.assertEqual(result["risk_class"], "LOW")
        self.assertEqual(result["approval_mode"], "ONE_PERSON")
        self.assertTrue(result["human_approval_required"])

    def test_every_internal_intent_resolves(self):
        for intent in known_internal_intents():
            result = validate_proposal(intent, GOOD_PAYLOAD, self.contract)
            self.assertIn(result["action_type"], {row["action_type"] for row in LIVE_ROWS})

    def test_risk_class_comes_from_the_database_not_python(self):
        result = validate_proposal("PRICE_CHANGE", GOOD_PAYLOAD, self.contract)
        self.assertEqual(result["risk_class"], "CRITICAL")
        self.assertEqual(result["approval_mode"], "TWO_PERSON")

    # --- adversarial ---------------------------------------------------
    def test_unknown_python_action_blocked(self):
        with self.assertRaisesRegex(FirewallError, "unknown internal action"):
            validate_proposal("RUN_SHELL", {}, self.contract)

    def test_retired_phase2c_names_are_blocked(self):
        for retired in ("CRM_REPLY_DRAFT", "META_BUDGET_CHANGE_PROPOSAL",
                        "WIX_PRICE_CHANGE_PROPOSAL", "CONTENT_CHANGE_PROPOSAL",
                        "DATA_QUALITY_INVESTIGATION"):
            with self.assertRaises(FirewallError):
                validate_proposal(retired, GOOD_PAYLOAD, self.contract)

    def test_canonical_name_is_not_an_internal_intent(self):
        # The DB name must not be usable directly; only the mapped intent is.
        with self.assertRaises(FirewallError):
            validate_proposal("DRAFT_CUSTOMER_REPLY", GOOD_PAYLOAD, self.contract)

    def test_case_manipulation_blocked(self):
        for variant in ("price_change", "Price_Change", "pRiCe_ChAnGe"):
            with self.assertRaises(FirewallError):
                validate_proposal(variant, GOOD_PAYLOAD, self.contract)

    def test_whitespace_manipulation_blocked(self):
        for variant in (" PRICE_CHANGE", "PRICE_CHANGE ", "PRICE_CHANGE\n", "PRICE\tCHANGE"):
            with self.assertRaises(FirewallError):
                validate_proposal(variant, GOOD_PAYLOAD, self.contract)

    def test_non_string_intent_blocked(self):
        for variant in (None, 1, ["PRICE_CHANGE"], {"a": 1}):
            with self.assertRaises(FirewallError):
                validate_proposal(variant, GOOD_PAYLOAD, self.contract)

    def test_forbidden_payload_keys_blocked(self):
        for key in ("sql", "shell", "command", "url", "webhook", "token", "secret"):
            with self.assertRaisesRegex(FirewallError, "forbidden payload"):
                validate_proposal("HUMAN_REVIEW_REQUEST", {key: "x"}, self.contract)

    def test_forbidden_key_case_insensitive(self):
        with self.assertRaisesRegex(FirewallError, "forbidden payload"):
            validate_proposal("HUMAN_REVIEW_REQUEST", {"ShElL": "whoami"}, self.contract)

    def test_malformed_payload_blocked(self):
        for payload in (None, "text", 5, ["a"]):
            with self.assertRaises(FirewallError):
                validate_proposal("HUMAN_REVIEW_REQUEST", payload, self.contract)

    def test_oversize_payload_blocked(self):
        with self.assertRaisesRegex(FirewallError, "payload too large"):
            validate_proposal("HUMAN_REVIEW_REQUEST", {"reason": "x" * 20000}, self.contract)

    def test_idempotency_prefix_enforced(self):
        with self.assertRaisesRegex(FirewallError, "idempotency key"):
            validate_proposal("HUMAN_REVIEW_REQUEST", GOOD_PAYLOAD, self.contract,
                              idempotency_key="test-no-prefix")
        result = validate_proposal("HUMAN_REVIEW_REQUEST", GOOD_PAYLOAD, self.contract,
                                   idempotency_key="action:test")
        self.assertEqual(result["idempotency_key"], "action:test")

    def test_firewall_never_returns_approved(self):
        result = validate_proposal("WIX_PUBLISH", GOOD_PAYLOAD, self.contract)
        self.assertEqual(result["status"], "PROPOSED")
        self.assertNotIn("APPROVED", str(result))


if __name__ == "__main__":
    unittest.main()
