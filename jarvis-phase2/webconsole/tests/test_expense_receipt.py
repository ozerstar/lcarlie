#!/usr/bin/env python3
"""Fiş fotoğrafı okuma: yazarkasa fişinden tutar, KDV, tarih çıkarma.

Korunan iki hata (31.10.2026'da ölçüldü, 9 fişin hiçbirinde tutar yoktu):

  1. YÖN. Telefon fotoğrafı yönünü EXIF'te tutar; uygulanmazsa tesseract
     ters metin okur ("SVYNYg SAMANI") ve çıkarıcı boş döner.
  2. FİŞ ≠ FATURA. Çıkarıcı yalnız e-fatura biçimini tanıyordu; "TOPLAM
     *350,00", "TOPKDV *31,82", "30/10/26" hiç eşleşmiyor, "$" gürültüsü
     para birimini USD yapıyordu.

Metinler gerçek fişlerin tesseract çıktısından kısaltıldı; OCR hataları
("700 , 20", "350,08") bilerek bırakıldı.
"""
from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import expense_vault  # noqa: E402

LAHMACUN = """OVALI DÖNER LAHMACUN
BONE GID.TIC.LTD. $11.
YENİMAHALLE ANKARA
0063 o TARİH: 30/10/26
13:06:15
BAMYA ÇORBASI TAM x10 o *175,00
AD LAHMACUN + Tec 416 *175,08
TOPKDV *31,82
TOPLAM *350,00
BANKA/KREDİ KARTI *350,08
Garanti BBVA
EMV SATIŞ TUTARI z
350,00
"""

SAPKA = """Cc ,
YAPKACI ÜMİT
UMİT CİRİTCİOĞLU
24026 FİŞ NO: 0029
ŞAPKA 7 700,090
KDV *63,64
TOP «700 , 20
EFT-POS 4700, @
TARIH: 31.16.2626 SAAT: 19:61
Mastercard/Kredi/Yurt İçi
İŞLEM TUTARI
700,00 t
"""

SALON = """m
BİLGİN pipe SALON
#555, 00
«50,45
TOPKDV
*555,00
TOPLAM
KREDI #555, 00
«#** oe: $
"""


class ReceiptExtractTest(unittest.TestCase):
    def test_total_tax_date_from_clean_slip(self):
        got = expense_vault._receipt_extract(LAHMACUN)
        self.assertEqual(got["gross"], "350.00")
        self.assertEqual(got["tax"], "31.82")
        self.assertEqual(got["date"], "2026-10-30")
        self.assertEqual(got["supplier"], "OVALI DÖNER LAHMACUN")
        self.assertEqual(got["currency"], "TRY")

    def test_vat_consistency_beats_misread_total(self):
        # "TOP «700 , 20" iki kez oy alıyor ama KDV 63,64 yalnız 700,00 ile tutuyor
        got = expense_vault._receipt_extract(SAPKA)
        self.assertEqual(got["gross"], "700.00")
        self.assertEqual(got["tax"], "63.64")
        self.assertEqual(got["invoice_number"], "0029")
        self.assertNotIn("date", got)  # 31.16.2626 geçersiz: uydurulmaz

    def test_amount_on_neighbour_line_and_dollar_noise(self):
        got = expense_vault._receipt_extract(SALON)
        self.assertEqual(got["gross"], "555.00")
        self.assertEqual(got["tax"], "50.45")
        self.assertEqual(got["currency"], "TRY")

    def test_invoice_path_unchanged(self):
        # Fatura yolunda fiş çıkarıcısı devreye girmez
        text = "Fatura Tarihi\n2026-10-20\nFatura No: ABC2026000001\nToplam 1.200,00 TL\n" + "x" * 120
        got = expense_vault._quick_extract(text)
        self.assertEqual(got["date"], "2026-10-20")
        self.assertEqual(got["invoice_number"], "ABC2026000001")


class DuplicateTest(unittest.TestCase):
    reason = staticmethod(expense_vault._duplicate_reason)

    def test_same_slip_number_is_sure(self):
        # Ayabakan 235,00 fiş no 000011 üç kez yüklenmişti
        self.assertEqual(self.reason({"number": "000011"}, {"number": "000011"}), (True, "aynı fiş/fatura no 000011"))

    def test_different_numbers_are_separate_documents(self):
        # Aynı gün 360,00 TL'lik altı ayrı fatura (379828…379833) tekrar sayılmaz
        self.assertIsNone(self.reason({"number": "379828"}, {"number": "379829"}))

    def test_time_decides_when_number_missing(self):
        self.assertEqual(self.reason({"time": "13:06"}, {"time": "13:06"}), (True, "aynı saat 13:06"))
        self.assertIsNone(self.reason({"time": "13:06"}, {"time": "19:01"}))

    def test_only_amount_and_date_is_a_warning(self):
        self.assertEqual(self.reason({"supplier": "OVALI DÖNER"}, {"supplier": "Ovalı Döner Lahmacun"}),
                         (False, "aynı tutar ve tarih"))
        self.assertIsNone(self.reason({"supplier": "Bilgin Pide"}, {"supplier": "Ayabakan"}))

    def test_slip_time_is_read(self):
        self.assertEqual(expense_vault._receipt_extract(LAHMACUN)["time"], "13:06")
        self.assertEqual(expense_vault._receipt_extract("SAAT: 19 01\nTOPLAM *10,00")["time"], "19:01")


class PhotoOrientationTest(unittest.TestCase):
    def test_exif_rotation_is_applied(self):
        from PIL import Image
        image = Image.new("RGB", (400, 200), "white")
        exif = Image.Exif()
        exif[274] = 6  # telefon: 90° saat yönünde döndür
        buffer = BytesIO()
        image.save(buffer, "JPEG", exif=exif.tobytes())
        fixed = expense_vault._prepare_image(buffer.getvalue(), 2400)
        self.assertEqual(fixed.size, (200, 400))

    def test_gallery_heic_becomes_jpeg(self):
        # Galeriden seçilen iPhone/Samsung fotoğrafı HEIC gelir; eskiden "Görsel okunamadı" 400 dönüyordu
        import pillow_heif
        from PIL import Image
        buffer = BytesIO()
        pillow_heif.from_pillow(Image.new("RGB", (300, 200), "white")).save(buffer, format="HEIF")
        converted = expense_vault._heic_to_jpeg(buffer.getvalue())
        self.assertEqual(expense_vault._mime(converted), "image/jpeg")

    def test_iphone_hdr_jpeg_is_accepted(self):
        # IMG_4719.jpeg: iPhone HDR JPEG'i Pillow'da "MPO"; "JPG yükleyin" diye reddediliyordu
        from PIL import Image
        buffer = BytesIO()
        Image.new("RGB", (400, 300), "white").save(buffer, "MPO", save_all=True,
                                                    append_images=[Image.new("RGB", (200, 150))])
        self.assertEqual(expense_vault._mime(buffer.getvalue()), "image/jpeg")

    def test_non_heic_passes_through(self):
        self.assertEqual(expense_vault._heic_to_jpeg(b"%PDF-1.7 x"), b"%PDF-1.7 x")

    def test_large_photo_is_shrunk(self):
        from PIL import Image
        buffer = BytesIO()
        Image.new("RGB", (4032, 3024), "white").save(buffer, "JPEG")
        fixed = expense_vault._prepare_image(buffer.getvalue(), 1280)
        self.assertEqual(max(fixed.size), 1280)


if __name__ == "__main__":
    unittest.main()
