"""Deterministic money tests plus opt-in isolated PostgreSQL integration.

CARI_TEST_DSN must identify a disposable database containing migration 044,
with a non-superuser jarvis_web role granted SELECT/INSERT only. Never point
these tests at the company database: setUp truncates the two ledger tables.
"""
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari


def goods(kind="sale", **changes):
    result = {"kind": kind, "date": "2026-01-10", "request_id": "test-request-000001",
              "items": [{"name": "Deneme ürün", "quantity": 3, "unit_price": "125.50",
                         "discount": "0", "tax_rate": "20"}]}
    result.update(changes)
    return result


def cash(kind="collection", **changes):
    return dict({"kind": kind, "date": "2026-01-11", "amount": "100.00"}, **changes)


class CariCalculationTests(unittest.TestCase):
    def test_discount_then_tax_half_up_and_integer_money(self):
        document = goods()
        document["items"][0].update(quantity=1, unit_price="0.05", discount="10", tax_rate="10")
        result = cari.calculate(document)
        self.assertEqual((result["net_cents"], result["tax_cents"], result["signed_cents"]), (5, 1, 6))
        self.assertIs(type(result["signed_cents"]), int)

    def test_unit_price_is_exclusive_of_tax(self):
        result = cari.calculate(goods())
        self.assertEqual((result["net_cents"], result["tax_cents"], result["signed_cents"]), (37650, 7530, 45180))

    def test_unset_tax_is_not_zero_tax(self):
        missing, zero = goods("purchase"), goods("purchase")
        missing["items"][0]["tax_rate"] = None
        zero["items"][0]["tax_rate"] = "0"
        self.assertTrue(cari.calculate(missing)["unknown_tax"])
        self.assertFalse(cari.calculate(zero)["unknown_tax"])

    def test_psf_sale_without_rate_is_vat_inclusive_not_unknown(self):
        # Sahip kararı 05.11.2026: oranı boş satış satırı PSF'tir, KDV dahildir.
        document = goods()
        document["items"][0]["tax_rate"] = None
        result = cari.calculate(document)
        self.assertFalse(result["unknown_tax"])
        old = dict(result, unknown_tax=True)  # kural öncesi kaydedilmiş satış
        self.assertEqual(cari.summarize([{"payload": old}])["unknown_tax_documents"], 0)
        self.assertFalse(cari._public_entry({"entry_id": "x", "payload": old, "reverses": None,
                                             "created_at": "t"})["payload"]["unknown_tax"])

    def test_unresolved_tax_never_shows_a_zero_account_as_closed(self):
        document = goods("purchase")
        document["items"][0]["tax_rate"] = None
        entries = [{"payload": cari.calculate(document)},
                   {"payload": cari.calculate(cash("payment", amount="376.50"))}]
        result = cari.summarize(entries)
        self.assertEqual(result["balance_cents"], 0)
        self.assertEqual(result["status"], "KDV bekleniyor")

    def test_collection_partial_payment_and_return_recalculate_balance(self):
        sale = cari.calculate(goods())
        collection = cari.calculate(cash())
        returned = goods("sale_return")
        returned["items"][0]["quantity"] = 1
        entries = [{"payload": p} for p in (sale, collection, cari.calculate(returned))]
        result = cari.summarize(entries)
        self.assertEqual(result["balance_cents"], 20120)
        self.assertEqual(result["products"], [{"name": "Deneme ürün", "given": 3, "received": 1}])

    def test_purchase_and_payment_use_company_perspective(self):
        result = cari.summarize([{"payload": cari.calculate(goods("purchase"))},
                                 {"payload": cari.calculate(cash("payment"))}])
        self.assertEqual(result["balance_cents"], -35180)
        self.assertEqual(result["status"], "Borçluyuz")

    def test_gift_tracks_quantity_without_creating_receivable(self):
        document = goods("gift_out")
        document["items"][0].update(unit_price="0", tax_rate="0")
        result = cari.summarize([{"payload": cari.calculate(document)}])
        self.assertEqual(result["balance_cents"], 0)
        self.assertEqual(result["products"][0]["given"], 3)
        document["items"][0]["unit_price"] = "1"
        with self.assertRaises(cari.CariError):
            cari.calculate(document)

    def test_exact_reversal_cancels_money_unknown_tax_and_net_goods(self):
        document = goods()
        document["items"][0]["tax_rate"] = None
        payload = cari.calculate(document)
        result = cari.summarize([{"payload": payload}, {"payload": payload, "reverses": "original"}])
        self.assertEqual((result["balance_cents"], result["unknown_tax_documents"]), (0, 0))
        product = result["products"][0]
        self.assertEqual(product["given"] - product["received"], 0)

    def test_money_inputs_reject_floats_exponents_infinity_and_precision_loss(self):
        for value in (True, -1, 1.1, "1e3", "NaN", "Infinity", "1,000", "1.001", "-1", "9999999999999"):
            with self.subTest(value=value), self.assertRaises(cari.CariError):
                cari.calculate(cash(amount=value))

    def test_invalid_dates_quantities_rates_and_unknown_kinds(self):
        invalid = [goods(date="2026-02-30"), goods(kind="delete"), goods(items=[]),
                   goods(due_date="tomorrow")]
        for field, value in (("quantity", True), ("quantity", 1.5), ("quantity", 0),
                             ("quantity", -1), ("tax_rate", "101"), ("discount", "101")):
            document = goods()
            document["items"][0][field] = value
            invalid.append(document)
        for document in invalid:
            with self.subTest(document=document), self.assertRaises(cari.CariError):
                cari.calculate(document)

    def test_document_limit_and_client_totals_are_not_trusted(self):
        document = goods(signed_cents=1, net_cents=1)
        self.assertEqual(cari.calculate(document)["signed_cents"], 45180)
        document["items"][0].update(quantity=100000, unit_price="999999999.00")
        with self.assertRaises(cari.CariError):
            cari.calculate(document)


@unittest.skipUnless(os.environ.get("CARI_TEST_DSN"), "isolated PostgreSQL not configured")
class CariPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.dsn = os.environ["CARI_TEST_DSN"]
        with psycopg.connect(self.dsn) as conn:
            conn.execute('RESET ROLE')
            if conn.execute('SELECT current_database()').fetchone()[0] != 'jarvis_cari_test':
                raise RuntimeError('Refusing to truncate a database other than jarvis_cari_test')
            conn.execute('TRUNCATE core.jarvis_cari_draft,core.jarvis_cari_document,core.jarvis_cari_entry,core.jarvis_cari_account')

        def connect():
            conn = psycopg.connect(self.dsn, row_factory=dict_row)
            conn.execute('SET ROLE jarvis_web')
            return conn
        patcher = patch.object(cari, "_connect", connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.account = cari.create_account("alice", {"name": "Test account", "role": "both"})["id"]

    def test_persistence_list_statement_and_partial_collection(self):
        cari.post_entry("alice", self.account, goods())
        cari.post_entry("alice", self.account, cash(request_id="payment-request-0001"))
        result = cari.statement("alice", self.account)
        self.assertEqual(len(result["entries"]), 2)
        self.assertEqual(result["summary"]["balance_cents"], 35180)
        accounts = cari.list_accounts("alice")["accounts"]
        self.assertIs(type(accounts[0]["balance_cents"]), int)
        self.assertEqual(accounts[0]["balance_cents"], 35180)

    def test_payment_allocation_is_partial_bounded_and_auditable(self):
        sale = cari.post_entry("alice", self.account, goods())["id"]
        paid = cash(request_id="linked-payment-0001", amount="100.00")
        paid.update(applies_to=sale, payment_method="pos")
        payment = cari.post_entry("alice", self.account, paid)
        self.assertEqual(cari.statement("alice", self.account)["settlements"][sale]["status"], "partial")
        with self.assertRaises(cari.CariConflict):
            cari.post_entry("alice", self.account, dict(paid, request_id="linked-payment-0002", amount="500.00"))
        with self.assertRaises(cari.CariConflict):
            cari.reverse_entry("alice", self.account, {"entry_id": sale,
                "request_id": "linked-reverse-0001", "reason": "test", "date": "2026-01-12"})
        cari.reverse_entry("alice", self.account, {"entry_id": payment["id"],
            "request_id": "linked-reverse-0002", "reason": "test", "date": "2026-01-12"})
        self.assertEqual(cari.statement("alice", self.account)["settlements"][sale]["status"], "unpaid")

    def test_editable_draft_does_not_affect_balance_until_approved_once(self):
        import cari_draft
        with patch.object(cari_draft, "_connect", cari._connect):
            body = goods()
            body["items"][0]["discount"] = "0"
            draft = cari_draft.create("alice", self.account, body)
            self.assertEqual(cari.statement("alice", self.account)["summary"]["balance_cents"], 0)
            drafts = cari_draft.list_drafts("alice", self.account)["drafts"]
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["preview"]["net_cents"], 37650)
            updated = goods()
            updated["items"][0]["discount"] = "50"
            cari_draft.update("alice", self.account, draft["id"], updated)
            with self.assertRaises(cari.CariNotFound):
                cari_draft.post("bob", self.account, draft["id"])
            first = cari_draft.post("alice", self.account, draft["id"])
            second = cari_draft.post("alice", self.account, draft["id"])
            self.assertEqual(first["id"], second["id"])
            self.assertTrue(second["reused"])
            self.assertEqual(cari.statement("alice", self.account)["summary"]["balance_cents"], 22590)
            self.assertEqual(cari_draft.list_drafts("alice", self.account)["drafts"], [])

    def test_invoice_import_creates_account_and_product_once(self):
        import cari_invoice
        from io import BytesIO
        from PIL import Image
        image = BytesIO()
        Image.new("RGB", (10, 10), "white").save(image, format="PNG")
        parsed = {"seller": {"name": "L’CARLIÉ"},
            "buyer": {"name": "Invoice Test Buyer", "tax_id": "1234567890",
                      "tax_office": "Çankaya", "address": "Ankara"},
            "invoice_number": "INV-TEST-001", "date": "2026-01-11", "currency": "TRY",
            "total": "453.60", "items": [{"name": "Test product", "quantity": 3,
                "unit_price": "150.00", "discount": "10", "tax_rate": "12"}],
            "_evidence_text": "Invoice seller L'CARLIE buyer Invoice Test Buyer. Invoice INV-TEST-001. "
                "Test product quantity 3 price 150.00 discount 10 VAT 12 total 453.60 TL."}
        with patch.object(cari_invoice, "_connect", cari._connect), \
             patch.object(cari_invoice, "_ocr", return_value=parsed):
            queued = cari_invoice.upload("alice", image.getvalue(), "fatura.png")
            self.assertEqual(queued["status"], "uploaded")
            result = cari_invoice.process_document("alice", queued["id"])
            self.assertEqual(result["status"], "review")
            self.assertIn("kimlik", result["reason"])
            posted = cari_invoice.approve("alice", queued["id"], parsed)
            self.assertEqual(posted["status"], "posted")
            result = posted
            account = cari.statement("alice", result["account_id"])["account"]
            self.assertEqual(account["tax_id"], "1234567890")
            self.assertEqual(account["tax_office"], "Çankaya")
            self.assertEqual(account["address"], "Ankara")
            self.assertEqual(cari.statement("alice", result["account_id"])["product_tables"]["sale"]["quantity"], 3)
            with self.assertRaises(cari.CariConflict):
                cari_invoice.upload("alice", image.getvalue(), "fatura.png")
            self.assertTrue(cari_invoice.content("alice", result["id"])[1].startswith(b"\x89PNG"))
            with self.assertRaises(cari.CariNotFound):
                cari_invoice.content("bob", result["id"])

    def test_ambiguous_invoice_stays_in_review_until_manually_confirmed(self):
        import cari_invoice
        from io import BytesIO
        from PIL import Image
        image = BytesIO()
        Image.new("RGB", (11, 11), "white").save(image, format="PNG")
        parsed = {"seller": {"name": "L'CARLIE"},
            "buyer": {"name": "Çağrı Test", "tax_id": "1234567890"},
            "invoice_number": "INV-REVIEW-001", "date": "2026-01-11", "currency": "TRY",
            "total": "120.00", "items": [{"name": "Test product", "quantity": 1,
                "unit_price": "100.00", "discount": "0", "tax_rate": "20"}],
            "_evidence_text": "Seller L'CARLIE buyer Cagri Test invoice INV-REVIEW-001 "
                "Test product 1 x 100.00 VAT 20 total 120.00 TRY"}
        with patch.object(cari_invoice, "_connect", cari._connect), \
             patch.object(cari_invoice, "_ocr", return_value=parsed):
            queued = cari_invoice.upload("alice", image.getvalue(), "review.png")
            result = cari_invoice.process_document("alice", queued["id"])
            self.assertEqual(result["status"], "review")
            self.assertEqual(len(cari.list_accounts("alice")["accounts"]), 1)
            posted = cari_invoice.approve("alice", queued["id"], parsed)
            self.assertEqual(posted["status"], "posted")
            self.assertEqual(cari.statement("alice", posted["account_id"])["account"]["tax_id"], "1234567890")

    def test_owners_cannot_read_post_or_reverse_each_others_accounts(self):
        entry = cari.post_entry("alice", self.account, goods())
        self.assertEqual(cari.list_accounts("bob"), {"accounts": []})
        for action in (lambda: cari.statement("bob", self.account),
                       lambda: cari.post_entry("bob", self.account, goods()),
                       lambda: cari.reverse_entry("bob", self.account, {"entry_id": entry["id"],
                           "request_id": "reverse-request-0001", "reason": "Correction", "date": "2026-01-12"})):
            with self.assertRaises(cari.CariNotFound):
                action()

    def test_retries_and_simultaneous_saves_post_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: cari.post_entry("alice", self.account, goods()), range(6)))
        self.assertEqual(len({row["id"] for row in results}), 1)
        self.assertEqual(len(cari.statement("alice", self.account)["entries"]), 1)
        other = goods()
        other["items"][0]["quantity"] = 4
        with self.assertRaises(cari.CariConflict):
            cari.post_entry("alice", self.account, other)

    def test_reversal_is_exact_idempotent_and_cannot_happen_twice(self):
        document = goods()
        document["items"][0]["tax_rate"] = None
        entry = cari.post_entry("alice", self.account, document)
        reversal = {"entry_id": entry["id"], "request_id": "reverse-request-0001",
                    "reason": "Mistaken entry", "date": "2026-01-12"}
        first = cari.reverse_entry("alice", self.account, reversal)
        second = cari.reverse_entry("alice", self.account, reversal)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["reused"])
        with self.assertRaises(cari.CariConflict):
            cari.reverse_entry("alice", self.account, dict(reversal, request_id="reverse-request-0002"))
        result = cari.statement("alice", self.account)
        self.assertEqual(result["summary"]["balance_cents"], 0)
        self.assertEqual(result["summary"]["unknown_tax_documents"], 0)
        with self.assertRaises(cari.CariConflict):
            cari.reverse_entry("alice", self.account, dict(reversal, entry_id=first["id"], request_id="reverse-request-0003"))

    def test_backdated_reversal_and_conflicting_retries_are_rejected(self):
        entry = cari.post_entry("alice", self.account, goods())
        reversal = {"entry_id": entry["id"], "request_id": "reverse-request-0001",
                    "reason": "Correction", "date": "2026-01-09"}
        with self.assertRaises(cari.CariError):
            cari.reverse_entry("alice", self.account, reversal)
        reversal["date"] = "2026-01-12"
        cari.reverse_entry("alice", self.account, reversal)
        with self.assertRaises(cari.CariConflict):
            cari.reverse_entry("alice", self.account, dict(reversal, reason="Different"))

    def test_duplicate_account_and_sql_like_input_remain_safe(self):
        with self.assertRaises(cari.CariConflict):
            cari.create_account("alice", {"name": "TEST ACCOUNT"})
        name = "'); DROP TABLE core.jarvis_cari_entry;--"
        other = cari.create_account("alice", {"name": name})
        self.assertEqual(cari.statement("alice", other["id"])["account"]["name"], name)

    def test_account_details_can_change_without_changing_financial_history(self):
        entry = cari.post_entry("alice", self.account, goods())
        changed = cari.update_account("alice", self.account, {
            "name": "Renamed account", "role": "customer", "contact": "Contact",
            "note": "Updated note", "covers": {}})
        self.assertEqual(changed["id"], self.account)
        statement = cari.statement("alice", self.account)
        self.assertEqual(statement["account"]["name"], "Renamed account")
        self.assertEqual(statement["account"]["note"], "Updated note")
        self.assertEqual(statement["entries"][0]["id"], entry["id"])
        with self.assertRaises(cari.CariNotFound):
            cari.update_account("bob", self.account, {"name": "Wrong owner", "role": "customer"})

    def test_cover_choice_must_belong_to_catalog_product(self):
        with patch('katalog.katalog', return_value={"urunler": [
                {"slug": "optywave", "gorseller": ["optywave.webp"]}]}):
            cari.update_account("alice", self.account, {
                "name": "Test account", "role": "both",
                "covers": {"optywave": "optywave.webp"}})
            self.assertEqual(cari.statement("alice", self.account)["account"]["covers"],
                             {"optywave": "optywave.webp"})
            with self.assertRaises(cari.CariError):
                cari.update_account("alice", self.account, {
                    "name": "Test account", "role": "both",
                    "covers": {"optywave": "unrelated.webp"}})

    def test_atomic_correction_preserves_audit_and_is_idempotent(self):
        original = cari.post_entry("alice", self.account, goods())
        replacement = goods()
        replacement["items"][0]["quantity"] = 1
        request = {"entry_id": original["id"], "request_id": "correct-request-0001",
                   "reason": "Quantity correction", "correction_date": "2026-01-12",
                   "replacement": replacement}
        first = cari.correct_entry("alice", self.account, request)
        second = cari.correct_entry("alice", self.account, request)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["reused"])
        statement = cari.statement("alice", self.account)
        self.assertEqual(len(statement["entries"]), 3)
        self.assertEqual(statement["summary"]["balance_cents"], 15060)
        self.assertEqual(statement["product_tables"]["sale"]["quantity"], 1)
        with self.assertRaises(cari.CariConflict):
            cari.correct_entry("alice", self.account,
                dict(request, request_id="correct-request-0002"))
        with self.assertRaises(cari.CariNotFound):
            cari.correct_entry("bob", self.account,
                dict(request, request_id="correct-request-0003"))

    def test_saved_products_can_be_removed_added_and_rediscounted(self):
        original_body = goods()
        original_body["items"].append({"name": "Çıkarılacak ürün", "quantity": 1,
            "unit_price": "40.00", "discount": "0", "tax_rate": "20"})
        original = cari.post_entry("alice", self.account, original_body)
        replacement = goods()
        replacement["items"][0].update(quantity=2, discount="50")
        replacement["items"].append({"name": "Yeni ürün", "quantity": 1,
            "unit_price": "80.00", "discount": "0", "tax_rate": "20"})
        corrected = cari.correct_entry("alice", self.account, {
            "entry_id": original["id"], "request_id": "correct-products-0001",
            "reason": "Ürün ve iskonto düzeltmesi", "correction_date": "2026-01-12",
            "replacement": replacement})
        result = cari.statement("alice", self.account)
        self.assertEqual(len(result["entries"]), 3)
        self.assertEqual(result["summary"]["balance_cents"], 24660)
        self.assertEqual({row["name"]: row["quantity"] for row in
            result["product_tables"]["sale"]["rows"]},
            {"Deneme ürün": 2, "Yeni ürün": 1})
        self.assertEqual(next(row for row in result["entries"]
            if row["id"] == corrected["id"])["payload"]["items"][0]["discount"], "50")

    def test_bulk_discount_corrects_every_sale_atomically_and_once(self):
        psf = goods()
        psf["items"][0].update(quantity=2, unit_price="1100", discount="70",
                               tax_rate=None, recommended_price="1100")
        cari.post_entry("alice", self.account, psf)
        returned = goods("sale_return", request_id="test-request-000002")
        returned["items"][0].update(quantity=1, unit_price="1100", discount="70",
                                    tax_rate=None, recommended_price="1100")
        cari.post_entry("alice", self.account, returned)
        request = {"request_id": "bulk-discount-000001", "discount": "60"}
        first = cari.apply_discount("alice", self.account, request)
        self.assertEqual((first["changed"], first["skipped"]), (2, 0))
        self.assertTrue(cari.apply_discount("alice", self.account, request)["reused"])
        statement = cari.statement("alice", self.account)
        self.assertEqual(len(statement["entries"]), 6)
        self.assertEqual(statement["summary"]["balance_cents"], 44000)
        row = statement["product_tables"]["sale"]["rows"][0]
        self.assertEqual((row["discount"], row["quantity"], row["unit_incl_cents"]), ("60", 1, 44000))
        again = cari.apply_discount("alice", self.account,
                                    {"request_id": "bulk-discount-000002", "discount": "60"})
        self.assertEqual((again["changed"], again["skipped"]), (0, 2))

    def test_bulk_discount_refuses_when_a_payment_is_matched(self):
        sale = cari.post_entry("alice", self.account, goods())
        cari.post_entry("alice", self.account, cash(request_id="test-request-000003",
                        payment_method="havale", applies_to=sale["id"]))
        with self.assertRaises(cari.CariConflict):
            cari.apply_discount("alice", self.account,
                                {"request_id": "bulk-discount-000003", "discount": "10"})
        self.assertEqual(len(cari.statement("alice", self.account)["entries"]), 2)

    def test_undo_restores_previous_discount_and_keeps_history(self):
        psf = goods()
        psf["items"][0].update(quantity=1, unit_price="1100", discount="70", tax_rate=None)
        cari.post_entry("alice", self.account, psf)
        cari.apply_discount("alice", self.account, {"request_id": "bulk-discount-000010", "discount": "60"})
        self.assertEqual(cari.statement("alice", self.account)["summary"]["balance_cents"], 44000)
        undo = cari.undo_discount("alice", self.account, {"request_id": "bulk-undo-0000000001"})
        self.assertEqual(undo["restored"], 1)
        statement = cari.statement("alice", self.account)
        self.assertEqual(statement["summary"]["balance_cents"], 33000)
        self.assertEqual(len(statement["entries"]), 5)
        with self.assertRaises(cari.CariNotFound):
            cari.undo_discount("alice", self.account, {"request_id": "bulk-undo-0000000002"})

    def test_web_database_role_cannot_overwrite_or_delete_history(self):
        entry = cari.post_entry("alice", self.account, goods())
        for query in ('DELETE FROM core.jarvis_cari_entry',
                      'UPDATE core.jarvis_cari_entry SET signed_cents=1',
                      'TRUNCATE core.jarvis_cari_entry'):
            with self.subTest(query=query), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                with cari._connect() as conn:
                    conn.execute(query)
        self.assertEqual(cari.statement("alice", self.account)["entries"][0]["id"], entry["id"])


if __name__ == '__main__':
    unittest.main()
