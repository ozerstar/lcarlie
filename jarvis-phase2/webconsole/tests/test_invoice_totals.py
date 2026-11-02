"""Fatura tutarları faturanın kendisini tutar (sahip, 02.11.2026: "rakamlarda hata istemiyorum")."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import invoice_analysis  # noqa: E402
import invoice_pdf  # noqa: E402


def line(doc, name, net, payable, tax):
    return {"document_id": doc, "box": "in", "issue_date": date(2026, 9, 1), "party": "P", "payable_cents": payable,
            "tax_cents": tax, "itheme": "", "ibusiness": "", "name": name, "theme": "diger", "business": "ortak",
            "product": "", "net_cents": net, "quantity": 1}


class InvoicePartsTest(unittest.TestCase):
    def test_lines_that_add_up_are_kept(self):
        parts = list(invoice_analysis.invoice_parts([line("a", "x", 600000, 1200000, 200000),
                                                     line("a", "y", 400000, 1200000, 200000)]))
        self.assertEqual([p["net"] for p in parts], [600000, 400000])

    def test_invoice_level_discount_is_taken_from_the_lines(self):
        # Kaya Turistik K242026000000348: kalemler 40.301,59, "SATIR İSK." 1.000, KDV 73,41, ödenecek 39.375
        parts = list(invoice_analysis.invoice_parts([line("k", "konaklama", 3956750, 3937500, 7341),
                                                     line("k", "komisyon", 73409, 3937500, 7341)]))
        self.assertEqual(sum(p["net"] for p in parts), 3930159)

    def test_vat_included_single_line_becomes_net(self):
        # TT Mobil GB32026008056273: tek kalem 1.936,25 (KDV dahil), KDV 277,16 → gider 1.659,09 (ÖİV dahil)
        parts = list(invoice_analysis.invoice_parts([line("t", "hat", 193625, 193625, 27716)]))
        self.assertEqual([p["net"] for p in parts], [165909])

    def test_vat_included_amount_adds_up_to_payable(self):
        # Mete Mustafa Ateş: 2.500 (%20) + 2.500 (%20) + 5.396,04 (%1), ödenecek 11.450,00
        rows = [line("m", "VİREAN", 250000, 1145000, 105396), line("m", "FEMISIA", 250000, 1145000, 105396),
                line("m", "GIDA TAKVİYESİ", 539604, 1145000, 105396)]
        parts = list(invoice_analysis.invoice_parts(rows))
        self.assertEqual(sum(p["net"] for p in parts), 1039604)
        self.assertEqual(sum(p["gross"] for p in parts), 1145000)

    def test_lineless_invoice_counts_without_vat(self):
        row = line("d", None, None, 6150000, 1025000)
        parts = list(invoice_analysis.invoice_parts([row]))
        self.assertEqual((parts[0]["net"], parts[0]["read"]), (5125000, False))


class TaxOfTest(unittest.TestCase):
    def test_two_vat_rates_are_added(self):
        # Mete Mustafa Ateş LMS2026000000001: %20 1.000,00 + %1 53,96 (önce yalnız 53,96 okunuyordu)
        text = ("Mal Hizmet Toplam Tutarı\n10.396,04 TL\nToplam İskonto\n0,00 TL\nHesaplanan KDV(%20)\n1.000,00 TL\n"
                "Hesaplanan KDV(%1)\n53,96 TL\nVergiler Dahil Toplam Tutar\n11.450,00 TL\nÖdenecek Tutar\n11.450,00 TL")
        self.assertEqual(invoice_pdf.tax_of(text, 1145000), (105396, "kdv"))

    def test_gercek_wording(self):
        text = ("Mal Hizmet Toplam Tutarı\n50.000,00 TL\nToplam İndirim\n0,00 TL\nHesaplanan KDV GERÇEK (%20.0)\n"
                "10.000,00 TL\nVergiler Dahil Toplam Tutar\n60.000,00 TL")
        self.assertEqual(invoice_pdf.tax_of(text, 6000000), (1000000, "kdv"))

    def test_two_column_layout_falls_back_to_the_difference(self):
        # GS1 GSF2026000007033: etiketler bir sütunda, tutarlar yanda — KDV satırı okunamaz
        text = ("Mal / Hizmet Toplam Tutarı\n3.745,00 TL\nHesaplanan KDV (% 20,00 )\nVergiler Dahil Toplam Tutar\n"
                "4.494,00 TL\nÖdenecek Tutar\n4.494,00 TL")
        self.assertEqual(invoice_pdf.tax_of(text, 449400), (74900, "fark"))

    def test_rate_in_parentheses_is_not_read_as_an_amount(self):
        text = "Mal Hizmet Toplam Tutarı\n100,00 TL\nHesaplanan KDV (% 20,00 )\n20,00 TL\nÖdenecek Tutar\n120,00 TL"
        self.assertEqual(invoice_pdf.tax_of(text, 12000), (2000, "kdv"))

    def test_mobile_operator_vat(self):
        text = ("KDV (20%) (Matrah 1385.79 TL )\n277.16\nÖzel İletişim Vergisi (10%) (Matrah 1385.79 TL )\n138.58\n"
                "ÖDENECEK TOPLAM TUTAR\n1936.25 TL")
        self.assertEqual(invoice_pdf.tax_of(text, 193625), (27716, "kdv"))


class QuantityAndTesterTest(unittest.TestCase):
    def test_thousands_in_piece_counts(self):
        import invoice_lines
        # NEVA 26.06.2026: "4.900 Adet" tester, 4,20 TL — dört bin dokuz yüz, 4,9 değil
        self.assertEqual(invoice_lines._quantity("4.900 Adet")[0], 4900)
        self.assertEqual(invoice_lines._quantity("0.152 KGM")[0], Decimal("0.152"))
        self.assertEqual(invoice_lines._quantity("12,5 Adet")[0], Decimal("12.5"))

    def test_tester_is_not_a_product(self):
        import invoice_topics
        # sahip: "testerlar dağıtılıyor, onlar ürün olarak sayılmaz"
        self.assertEqual(invoice_topics.classify("in", "L'Carlié Vireon Tester", "NEVA"), ("numune_tester", "lcarlie", ""))
        self.assertEqual(invoice_topics.classify("in", "L'Carlié Vireon", "NEVA")[2], "Vireon")

    def test_bank_line_is_not_the_seller(self):
        lines = ["SAYIN", "LEMOS MEDİKAL A.Ş.", "T.C. Ziraat Bankası AŞ", "NEVA INOVASYON VE KIMYA ANONIM SIRKETI", "ÇANKAYA/ ANKARA"]
        self.assertEqual(invoice_pdf._seller(lines, lines[:2]), "NEVA INOVASYON VE KIMYA ANONIM SIRKETI")


class SellerTest(unittest.TestCase):
    def test_invoice_note_is_not_the_seller(self):
        # GLY2026000000006: not satırı satıcı sanılmıştı ("iletilmiştir" içinde "ŞTİ" var)
        lines = ["SAYIN", "LEMOS MEDİKAL A.Ş.", "Not: Yazı ile: # Dört Bin İki Yüz TL #",
                 "e-Arşiv izni kapsamında elektronik ortamda iletilmiştir.", "İrsaliye yerine geçerlidir.",
                 "SÜMEYRA GÜLYAVŞAN", "ERENLER MAH. TEŞHİS SK. 2 A"]
        self.assertNotIn("iletilmiştir", invoice_pdf._seller(lines, lines[:2]))


if __name__ == "__main__":
    unittest.main()
