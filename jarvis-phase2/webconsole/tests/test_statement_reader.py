import unittest
from datetime import date

import money_ledger as ml

# owner's Enpara statement, 02.11.2026: rows whose description holds a card-screenshot noise word
# ("kredi kartı borcu", "Premium") or "LİMİTED" were silently dropped — 13 rows, 232.750 TL in.
TEXT = "\n".join([
    "Enpara.com Hesap Hareketleri", "Tarih", "Hareket tipi", "Açıklama", "İşlem Tutarı", "Bakiye",
    "16.09.2026", "Gelen Transfer", "MUHARREM MURAT YILDIZ, kredi kartı borcu", "30.000,00 TL", "45.000,00 TL",
    "05.10.2026", "Diğer", "Ayin Enparalisi oldugunuz icin Netflix, Spotify ve Youtube Premium kampanyasindan kazandiginiz iade",
    "150,00 TL", "45.150,00 TL",
    "19.04.2025", "Gelen Transfer", "KCC KAFE RESTORAN GIDA TURİZM Tİ CARET LİMİTED ŞİR, must.fazla cekilen",
    "2.000,00 TL", "47.150,00 TL",
])


class StatementReaderTest(unittest.TestCase):
    def test_account_rows_with_noise_words_are_kept(self):
        moves = ml.parse_statement(TEXT, today=date(2026, 11, 2))
        self.assertEqual([(m["date"], m["direction"], m["amount"]) for m in moves],
                         [(date(2026, 9, 16), "in", 3000000), (date(2026, 10, 5), "in", 15000),
                          (date(2025, 4, 19), "in", 200000)])
        self.assertEqual(moves[0]["party"], "MUHARREM MURAT YILDIZ")
        self.assertEqual(moves[1]["kind"], "iade")
        self.assertTrue(moves[2]["party"].startswith("KCC KAFE"))


    def test_merchant_named_limit_is_not_card_limit(self):
        text = ("Kart limiti 150.000,00 TL\n"
                "Kullanilabilir kart limiti 12.000,00 TL\n"
                "03.11.2026 LIMIT RESTORAN GIDA ANKARA TR 3.000,00 TL\n")
        moves = ml.parse_statement(text, today=date(2026, 11, 14))
        self.assertEqual([m["amount"] for m in moves], [300000])
        self.assertIn("LIMIT RESTORAN", moves[0]["party"].upper())


if __name__ == "__main__":
    unittest.main()
