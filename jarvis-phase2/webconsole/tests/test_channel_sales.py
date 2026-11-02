import os
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import channel_sales  # noqa: E402


class WixTest(unittest.TestCase):
    """CR-012: Wix 'toplam' includes VAT; lines share the order's own net/gross ratio."""

    def test_lines_shipping_and_vat(self):
        order = {"siparis_id": "a", "siparis_no": 1012, "olusturma": datetime(2026, 9, 3, tzinfo=timezone.utc),
                 "odeme_durumu": "PAID", "toplam": Decimal("1260.00"), "kdv": Decimal("210.00"), "kargo_bedeli": Decimal("60.00"),
                 "ham": {"billingInfo": {"contactDetails": {"firstName": "Aysun", "lastName": "Evliyaoğlu"}}}}
        items = [{"siparis_id": "a", "sira": 1, "urun_adi": "L'Carlié Vireon", "adet": 2, "toplam": 800, "net_toplam": 800},
                 {"siparis_id": "a", "sira": 2, "urun_adi": "L'Carlié Femisia", "adet": 1, "toplam": 400, "net_toplam": 400}]
        rows = channel_sales.wix_rows([order], items)
        self.assertEqual([(r["kind"], r["gross"], r["net"]) for r in rows],
                         [("sale", 80000, 66666), ("sale", 40000, 33333), ("shipping", 6000, 5000)])
        self.assertEqual(rows[0]["customer"], "Aysun Evliyaoğlu")
        self.assertEqual(rows[0]["order_no"], "1012")

    def test_unpaid_archived_internal_are_left_out(self):
        base = {"siparis_id": "b", "siparis_no": 2, "olusturma": datetime(2026, 9, 3, tzinfo=timezone.utc), "toplam": 100,
                "kdv": 16.67, "kargo_bedeli": 0, "ham": {}}
        for extra in ({"odeme_durumu": "NOT_PAID"}, {"odeme_durumu": "PAID", "arsivlendi": True},
                      {"odeme_durumu": "PAID", "ic_siparis": True}):
            self.assertEqual(channel_sales.wix_rows([{**base, **extra}], []), [])


class TrendyolTest(unittest.TestCase):
    def test_sale_return_and_coupon(self):
        ms = int(datetime(2026, 1, 10, tzinfo=timezone.utc).timestamp() * 1000)
        rows = channel_sales.trendyol_rows([
            ("Sale", {"id": 1, "orderNumber": "T1", "orderDate": ms, "credit": 1500, "debt": 0, "barcode": "8684869609110"}),
            ("Return", {"id": 2, "orderNumber": "T1", "orderDate": ms, "credit": 0, "debt": 1500, "barcode": "8684869609110"}),
            ("Coupon", {"id": 3, "orderNumber": "T2", "orderDate": ms, "credit": 0, "debt": 50})],
            {"8684869609110": "L'Carlié Vireon"})
        self.assertEqual([(r["kind"], r["gross"], r["net"], r["item"]) for r in rows],
                         [("sale", 150000, 125000, "L'Carlié Vireon"), ("return", -150000, -125000, "L'Carlié Vireon"),
                          ("discount", -5000, -4166, "")])
        self.assertTrue(all(r["vat_assumed"] for r in rows))


class InvoiceMatchTest(unittest.TestCase):
    """02.11.2026: 29 of 33 paid Wix orders already had a Lemos e-arşiv invoice — never count twice."""

    INV = [{"document_id": "lem1", "issue_date": date(2026, 9, 4), "party": "AYSUN EVLİYAOĞLU", "payable_cents": 126000},
           {"document_id": "lem2", "issue_date": date(2026, 9, 4), "party": "NİLÜFER ATACAN", "payable_cents": 126000}]

    def test_named_order_meets_its_own_invoice(self):
        order = {"channel": "wix", "order_no": "1012", "day": date(2026, 9, 3), "gross": 126000, "customer": "Nilüfer Atacan"}
        self.assertEqual(channel_sales.find_invoices([order], self.INV), {("wix", "1012"): "lem2"})

    def test_named_order_with_other_name_is_not_taken(self):
        order = {"channel": "wix", "order_no": "9", "day": date(2026, 9, 3), "gross": 126000, "customer": "Banu Kaya"}
        self.assertEqual(channel_sales.find_invoices([order], self.INV), {})

    def test_order_number_on_the_invoice_wins(self):
        inv = self.INV + [{"document_id": "tya1", "issue_date": date(2026, 1, 5), "party": "Ozer Ercag", "payable_cents": 285000,
                           "order_no": "10593412345"}]
        order = {"channel": "trendyol", "order_no": "10593412345", "day": date(2026, 1, 2), "gross": 290000, "customer": ""}
        self.assertEqual(channel_sales.find_invoices([order], inv), {("trendyol", "10593412345"): "tya1"})

    def test_schussler_on_trendyol_is_the_clinics_and_the_coupon_follows(self):
        rows = [{"channel": "trendyol", "order_no": "T1", "kind": "sale", "item": "Dr. Tuzları Nr:7 400 Tablet Gıda Takviyesi", "gross": 300000},
                {"channel": "trendyol", "order_no": "T1", "kind": "discount", "item": "", "gross": -15000},
                {"channel": "wix", "order_no": "9", "kind": "sale", "item": "L'Carlié Vireon", "gross": 100000}]
        self.assertEqual([r["business"] for r in channel_sales.business_of(rows)], ["lemos", "lemos", "lcarlie"])

    def test_nameless_order_needs_exact_amount_and_window(self):
        order = {"channel": "trendyol", "order_no": "T1", "day": date(2026, 9, 3), "gross": 126000, "customer": ""}
        self.assertEqual(len(channel_sales.find_invoices([order], self.INV)), 1)
        late = {**order, "day": date(2026, 7, 1)}
        self.assertEqual(channel_sales.find_invoices([late], self.INV), {})


if __name__ == "__main__":
    unittest.main()
