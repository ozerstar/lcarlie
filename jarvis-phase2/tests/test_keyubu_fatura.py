"""Keyubu sunucu faturasi nobeti: posta okuma + ne zaman haber verilir."""
import importlib.util
import unittest
from datetime import date
from pathlib import Path

_yol = Path(__file__).resolve().parents[1] / "scripts" / "keyubu-fatura.py"
_spec = importlib.util.spec_from_file_location("keyubu_fatura", _yol)
kf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kf)

FATURA = """Bu, 5 Kasım 2026 tarihinde bir faturanın oluşturulduğuna dair bir bildirimdir.
Ödeme yönteminiz: Kredi Kartı / Banka Kartı
Fatura #390603
Ödenecek Tutar: 1625.88 ₺
Son Ödeme Tarihi: 12 Kasım 2026
Fatura Öğeleri"""
ODEME = "Bu, 5 Kasım 2026 tarihinde gönderilen 390603 Faturası için bir ödeme bildirimidir."


class PostaOkuma(unittest.TestCase):
    def test_fatura(self):
        self.assertEqual(kf.fatura_oku(FATURA),
                         {"no": "390603", "tutar": 1625.88, "son_odeme": date(2026, 11, 12)})

    def test_odeme(self):
        self.assertEqual(kf.odeme_oku(ODEME), "390603")

    def test_fatura_olmayan_posta(self):
        self.assertIsNone(kf.fatura_oku("Giriş doğrulama kodu"))


class HaberZamani(unittest.TestCase):
    F = {"no": "1", "tutar": 10.0, "son_odeme": date(2026, 11, 12)}

    def test_fatura_geldigi_gun_bir_kez(self):
        self.assertEqual(kf.haber_gerekli(self.F, date(2026, 11, 5), []), "yeni")
        self.assertIsNone(kf.haber_gerekli(self.F, date(2026, 11, 6), ["2026-11-05"]))

    def test_son_uc_gun_her_gun(self):
        self.assertEqual(kf.haber_gerekli(self.F, date(2026, 11, 10), ["2026-11-05"]), "son-gunler")
        self.assertIsNone(kf.haber_gerekli(self.F, date(2026, 11, 10), ["2026-11-10"]))

    def test_gecikince(self):
        self.assertEqual(kf.haber_gerekli(self.F, date(2026, 11, 13), ["2026-11-12"]), "gecikti")

    def test_eski_acik_fatura_iptal_sayilir(self):
        self.assertIsNone(kf.haber_gerekli(self.F, date(2026, 11, 20), []))


if __name__ == "__main__":
    unittest.main()
