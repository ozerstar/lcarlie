"""Branded customer documents: genuine XLSX with logo, PDF builds, no DB."""
import sys
import unittest
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.dom.minidom import parseString

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cari_export

TABLES = [
    ('Cari özeti', [['Alan', 'Bilgi'], ['Cari', 'Mcaris'], ['Adres', ''], ['Bakiye TL', Decimal('660.00')]]),
    ('Satılan ürünler', [
        ['Ürün', 'Adet', 'PSF (KDV dahil) TL', 'İskonto', 'İskontolu birim KDV hariç TL',
         'İskontolu birim KDV dahil TL', 'Tutar KDV hariç TL', 'Tutar KDV dahil TL'],
        ['=OPTYWAVE', 2, Decimal('1100'), '%70', Decimal('275'), Decimal('330'), Decimal('550'), Decimal('660')],
        ['GENEL TOPLAM', 2, '', '', '', '', Decimal('550'), Decimal('660')]]),
    ('Bedelsiz ürünler', [['Ürün', 'Adet']]),
]


class BrandedExportTests(unittest.TestCase):
    def test_xlsx_is_valid_branded_and_skips_empty_sheets(self):
        data = cari_export.xlsx(TABLES, 'Mcaris')
        with zipfile.ZipFile(BytesIO(data)) as z:
            names = set(z.namelist())
            for name in names:
                if name.endswith(('.xml', '.rels')):
                    parseString(z.read(name))
            self.assertIn('xl/media/logo.png', names)
            self.assertIn('xl/drawings/drawing1.xml', names)
            self.assertNotIn('xl/worksheets/sheet3.xml', names)
            sheet = z.read('xl/worksheets/sheet2.xml').decode()
            self.assertIn('Mcaris', sheet)
            self.assertNotIn('<f>', sheet)  # =OPTYWAVE stays inert text
            self.assertIn('=OPTYWAVE', sheet)
            self.assertIn('s="9"', sheet)  # total row style
            self.assertIn('<autoFilter ref="A5:H7"/>', sheet)

    def test_seller_block_only_from_owner_file(self):
        import tempfile
        from unittest.mock import patch as mock_patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cari_firma.json'
            with mock_patch.object(cari_export, 'FIRM_FILE', path):
                self.assertEqual(cari_export.firm(), {})
                path.write_text('{"unvan": "Örnek Ltd.", "iban": "TR00 0000", "banka": ""}', encoding='utf-8')
                self.assertEqual(cari_export.firm(), {'unvan': 'Örnek Ltd.', 'iban': 'TR00 0000'})

    def test_pdf_builds_with_logo(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest('reportlab yok')
        data = cari_export.pdf('Mcaris', TABLES)
        self.assertTrue(data.startswith(b'%PDF'))
        self.assertGreater(len(data), 3000)


if __name__ == '__main__':
    unittest.main()
