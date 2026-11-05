"""Branded customer documents: genuine XLSX with logo, PDF builds, no DB."""
import sys
import unittest
import re
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
            # =OPTYWAVE düz metin kalır; formül yalnız bizim yazdığımız toplamlarda olur.
            self.assertRegex(sheet, r'<c r="A7" s="\d+" t="inlineStr"><is><t xml:space="preserve">=OPTYWAVE</t>')
            self.assertEqual(sorted(set(re.findall(r'<f>([A-Z]+)\(', sheet))), ['SUM'])
            self.assertIn('<f>SUM(H7:H7)</f><v>660</v>', sheet)
            self.assertNotIn('i̇', sheet)  # büyük İ küçültülünce bozulan nokta
            self.assertIn('s="9"', sheet)  # total row style
            self.assertIn('<autoFilter ref="A6:H7"/>', sheet)
            self.assertIn('orientation="landscape"', sheet)

    def test_seller_block_only_from_owner_file(self):
        import tempfile
        from unittest.mock import patch as mock_patch
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cari_firma.json'
            with mock_patch.object(cari_export, 'FIRM_FILE', path):
                self.assertEqual(cari_export.firm(), {})
                path.write_text('{"unvan": "Örnek Ltd.", "iban": "TR00 0000", "banka": ""}', encoding='utf-8')
                self.assertEqual(cari_export.firm(), {'unvan': 'Örnek Ltd.', 'iban': 'TR00 0000'})

    def test_pdf_and_excel_share_one_preparation_time(self):
        meta = cari_export.report_meta('Mcaris', [('Cari özeti', [['Alan', 'Bilgi'], ['Hazırlanma', '01.02.2026 09:30']])])
        self.assertEqual(meta['stamp'], '01.02.2026 09:30')
        with zipfile.ZipFile(BytesIO(cari_export.xlsx(TABLES, 'Mcaris', meta))) as z:
            self.assertIn('01.02.2026 09:30', z.read('xl/worksheets/sheet1.xml').decode())

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
