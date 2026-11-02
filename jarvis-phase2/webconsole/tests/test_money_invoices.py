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

    def test_sales_invoice_is_collected_by_money_coming_in(self):
        inv = [_inv("o", date(2026, 9, 1), "AYSUN EVLİYAOĞLU", 200000, box="out")]
        self.assertEqual(money_invoices.find_payments(inv, [_mov("m", date(2026, 9, 1), "AYSUN EVLİYAOĞLU", 200000)]), [])
        self.assertEqual(money_invoices.find_payments(inv, [_mov("m", date(2026, 9, 1), "Aysun Evliyaoğlu", 200000, "in")]),
                         [{"document_id": "o", "movement_id": "m"}])



class PdfDirectionTest(unittest.TestCase):
    """Owner, 02.11.2026: "gelen ve gidenleri karıştırma" — two witnesses must agree."""
    LEMOS = "1234567890"
    SELL = "\n".join(["SAYIN", "AYSUN EVLİYAOĞLU", "TCKN: 11111111111", "Fatura No:", "LEM2026000000123", "Fatura Tarihi:",
                      "31-10-2026", "LEMOS MEDİKAL SAĞLIK", "VKN: 1234567890", "ETTN: 0f0e0d0c-0b0a-0908-0706-050403020100",
                      "Ödenecek Tutar", "2.000,00 TL"])
    BUY = "\n".join(["TT MOBİL İletişim Hizmetleri A.Ş.", "Vergi No: 9999999999", "Sayın,", "LEMOS MEDİKAL SAĞLIK İŞ GÜVENLİĞİ",
                     "Vergi No: 1234567890", "Fatura No: GB32026000000001", "Fatura Tarihi:", "31 - 10 - 2026",
                     "ETTN: 1f0e0d0c-0b0a-0908-0706-050403020100", "Ödenecek Tutar", ": 1936.25 TL"])

    def test_own_series_is_a_sale(self):
        import invoice_pdf
        row = invoice_pdf.read({"ettn": "x", "text": self.SELL}, self.LEMOS)
        self.assertEqual((row["box"], row["party"], row["payable_cents"], row["date"]),
                         ("out", "AYSUN EVLİYAOĞLU", 200000, date(2026, 10, 31)))

    def test_lemos_as_buyer_is_a_purchase(self):
        import invoice_pdf
        row = invoice_pdf.read({"ettn": "y", "text": self.BUY}, self.LEMOS)
        self.assertEqual((row["box"], row["party"], row["payable_cents"], row["date"]),
                         ("in", "TT MOBİL İletişim Hizmetleri A.Ş.", 193625, date(2026, 10, 31)))

    def test_disagreeing_witnesses_are_never_filed(self):
        import invoice_pdf
        text = self.SELL.replace("AYSUN EVLİYAOĞLU", "LEMOS MEDİKAL SAĞLIK")  # own series but Lemos is the buyer
        self.assertIsNone(invoice_pdf.read({"ettn": "z", "text": text}, self.LEMOS)["box"])



class TopicTest(unittest.TestCase):
    """Owner, 02.11.2026: Lemos and L'CARLIÉ are two businesses — split by what the line says."""

    def test_products_by_name_barcode_or_brand(self):
        import invoice_topics as t
        self.assertEqual(t.classify("out", "L'Carlié Hydravie Herbal Moisturizing Cream", ""), ("lcarlie_urun", "lcarlie", "Hydravie"))
        self.assertEqual(t.classify("out", "VİREAN", ""), ("lcarlie_urun", "lcarlie", "Vireon"))
        self.assertEqual(t.classify("out", "8684869609271 dermavasc", ""), ("lcarlie_urun", "lcarlie", "Dermavasc"))
        self.assertEqual(t.classify("out", "L'Carlié Babysol SPF50+ Natural Sunscreen", "")[2], "Babysol")

    def test_printing_for_lcarlie_is_not_a_product(self):
        import invoice_topics as t
        self.assertEqual(t.classify("in", "DTF BASKI DTF L CARLIE (15METRE 15CM)", "PRO BASKI"), ("promosyon_matbaa", "lcarlie", ""))

    def test_costs_go_to_the_right_business(self):
        import invoice_topics as t
        self.assertEqual(t.classify("in", "Platform Hizmet Bedeli", "DSM Grup Danışmanlık")[:2], ("pazaryeri", "lcarlie"))
        self.assertEqual(t.classify("in", "GIDA TAKVİYESİ", "ECZANE")[:2], ("takviye_ilac", "lemos"))
        self.assertEqual(t.classify("in", "Mobil hat faturası", "TT MOBİL")[:2], ("iletisim", "ortak"))
        self.assertEqual(t.classify("in", "Mehmet Akif Ersoy Mah. 325 Sok", "MOY DANIŞMANLIK")[:2], ("grup_ici", "grup"))

    def test_bare_supplement_sale_is_the_clinics(self):
        import invoice_topics as t  # owner: L'CARLIÉ products are always named on the invoice
        self.assertEqual(t.classify("out", "GIDA TAKVİYESİ", "AYSUN EVLİYAOĞLU")[:2], ("takviye_ilac", "lemos"))


class LinesAddUpTest(unittest.TestCase):
    def test_vat_rate_or_vat_amount(self):
        import invoice_lines as l
        self.assertTrue(l.adds_up([{"net_cents": 400000}], 440000, 0))     # %10, VAT not printed
        self.assertTrue(l.adds_up([{"net_cents": 1099}], 1319, 220))
        self.assertFalse(l.adds_up([{"net_cents": 80000}], 480000, 0))     # half the invoice is missing
        self.assertFalse(l.adds_up([], 1000, 0))


if __name__ == "__main__":
    unittest.main()
