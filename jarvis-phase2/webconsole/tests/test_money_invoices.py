import os
import sys
import unittest
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import money_invoices  # noqa: E402

UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>KEY2026000000123</cbc:ID>
 <cac:TaxTotal><cbc:TaxAmount currencyID="TRY">75.00</cbc:TaxAmount></cac:TaxTotal>
 <cac:InvoiceLine><cbc:ID>1</cbc:ID><cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="TRY">300.00</cbc:LineExtensionAmount>
  <cac:TaxTotal><cbc:TaxAmount currencyID="TRY">60.00</cbc:TaxAmount>
   <cac:TaxSubtotal><cbc:Percent>20</cbc:Percent></cac:TaxSubtotal></cac:TaxTotal>
  <cac:Item><cbc:Name>.com.tr alan adı (1 yıl)</cbc:Name></cac:Item></cac:InvoiceLine>
 <cac:InvoiceLine><cbc:ID>2</cbc:ID><cbc:InvoicedQuantity unitCode="MON">3</cbc:InvoicedQuantity>
  <cbc:LineExtensionAmount currencyID="TRY">75.50</cbc:LineExtensionAmount>
  <cac:Item><cbc:Description>SSL sertifikası</cbc:Description></cac:Item></cac:InvoiceLine>
</Invoice>""".encode("utf-8")


def _inv(doc, day, party, cents, box="in"):
    return {"document_id": doc, "box": box, "issue_date": day, "party": party, "payable_cents": cents}


def _mov(mid, day, party, cents, direction="out"):
    return {"movement_id": mid, "direction": direction, "tx_date": day, "party": party, "amount_cents": cents}


class UblTest(unittest.TestCase):
    def test_lines_with_vat(self):
        lines = money_invoices.parse_ubl(UBL)
        self.assertEqual([(l["name"], l["quantity"], l["unit"], l["net_cents"], l["vat_percent"], l["vat_cents"]) for l in lines],
                         [(".com.tr alan adı (1 yıl)", Decimal(1), "C62", 30000, Decimal(20), 6000),
                          ("SSL sertifikası", Decimal(3), "MON", 7550, None, 0)])

    def test_category_guess_and_owner_rule(self):
        lines = money_invoices.parse_ubl(UBL)
        self.assertEqual(money_invoices.guess_category("KEYUBU İNTERNET VE BİLİŞİM TİCARET", lines), "yazilim")
        self.assertEqual(money_invoices.guess_category("ENERJİSA BAŞKENT ELEKTRİK PERAKENDE", []), "faturalar")
        self.assertEqual(money_invoices.guess_category("FİL GRUP DİJİTAL REKLAM LİMİTED", []), "reklam")
        self.assertEqual(money_invoices.guess_category("ALPER İNCU", []), "diger")
        # 02.11.2026: "DİJİTAL BASKI" was filed as a water bill ("b-aski")
        self.assertEqual(money_invoices.guess_category("FİL GRUP DİJİTAL REKLAM LİMİTED", [{"name": "DİJİTAL BASKI"}]), "reklam")
        self.assertEqual(money_invoices.guess_category("ASKİ GENEL MÜDÜRLÜĞÜ", []), "faturalar")
        self.assertEqual(money_invoices.guess_category("ALPER İNCU", [], {"alperincu": "hizmet"}), "hizmet")


class PaymentTest(unittest.TestCase):
    """02.11.2026 dry run: 9 amount matches, 3 were other firms — the name must meet too."""

    def test_same_amount_name_and_date(self):
        found = money_invoices.find_payments(
            [_inv("k1", date(2026, 9, 24), "KEYUBU İNTERNET VE BİLİŞİM TİCARET", 21600)],
            [_mov("m1", date(2026, 9, 24), "KEYUBU INTERNET", 21600)])
        self.assertEqual(found, [{"document_id": "k1", "movement_id": "m1"}])

    def test_amount_alone_is_a_coincidence(self):
        found = money_invoices.find_payments(
            [_inv("c1", date(2026, 9, 15), "ÇTN GRUP TURİZM LTD ŞTİ", 26093)],
            [_mov("a1", date(2026, 9, 29), "APPLE.COM/BILL", 26093)])
        self.assertEqual(found, [])

    def test_enerjisa_card_line_with_subscriber_number(self):
        found = money_invoices.find_payments(
            [_inv("e1", date(2026, 9, 29), "ENERJİSA BAŞKENT ELEKTRİK PERAKENDE SATIŞ A.Ş.", 200500)],
            [_mov("m9", date(2026, 10, 9), "ENERJISA BASKENT", 200500)])
        self.assertEqual(len(found), 1)

    def test_one_movement_pays_one_invoice_closest_date_wins(self):
        invoices = [_inv("a", date(2026, 9, 23), "KEYUBU İNTERNET", 123200), _inv("b", date(2026, 9, 23), "KEYUBU İNTERNET", 123200)]
        moves = [_mov("late", date(2026, 10, 20), "KEYUBU INTERNET", 123200), _mov("near", date(2026, 9, 24), "KEYUBU INTERNET", 123200)]
        found = money_invoices.find_payments(invoices, moves)
        self.assertEqual(found, [{"document_id": "a", "movement_id": "near"}, {"document_id": "b", "movement_id": "late"}])

    def test_window_tolerance_direction_and_rejections(self):
        inv = [_inv("k", date(2026, 9, 1), "KEYUBU İNTERNET", 10000)]
        self.assertEqual(money_invoices.find_payments(inv, [_mov("x", date(2026, 11, 15), "KEYUBU", 10000)]), [])  # 75 days
        self.assertEqual(money_invoices.find_payments(inv, [_mov("x", date(2026, 9, 2), "KEYUBU", 10250)]), [])   # 2,50 TL off
        self.assertEqual(money_invoices.find_payments(inv, [_mov("x", date(2026, 9, 2), "KEYUBU", 10000, "in")]), [])
        self.assertEqual(len(money_invoices.find_payments(inv, [_mov("x", date(2026, 9, 2), "KEYUBU", 10080)])), 1)
        rejected = [{"document_id": "k", "movement_id": "x", "status": "rejected"}]
        self.assertEqual(money_invoices.find_payments(inv, [_mov("x", date(2026, 9, 2), "KEYUBU", 10000)], rejected), [])

    def test_outgoing_invoices_are_not_paid_by_us(self):
        found = money_invoices.find_payments([_inv("o", date(2026, 9, 1), "TEC DYNASTY", 5000, box="out")],
                                             [_mov("m", date(2026, 9, 1), "TEC DYNASTY", 5000)])
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
