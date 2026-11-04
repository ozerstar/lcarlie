"""PDF invoice boundary checks, without customer documents."""
import sys
import unittest
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari
import cari_invoice


def pdf_with_numbers(numbers):
    document = fitz.open()
    for number in numbers:
        page = document.new_page()
        page.insert_text((60, 60), f"Fatura No:\n{number}\n" + "Sample invoice. " * 12)
    data = document.tobytes()
    document.close()
    return data


class InvoicePdfTests(unittest.TestCase):
    def test_one_invoice_can_have_multiple_pages(self):
        text, image = cari_invoice._pdf_text(pdf_with_numbers(["ABC2026000000001"] * 2))
        self.assertIn("ABC2026000000001", text)
        self.assertIsNone(image)

    def test_merged_invoices_are_rejected(self):
        with self.assertRaisesRegex(cari.CariError, "birden fazla fatura"):
            cari_invoice._pdf_text(pdf_with_numbers(["ABC2026000000001", "ABC2026000000002"]))


if __name__ == "__main__":
    unittest.main()
