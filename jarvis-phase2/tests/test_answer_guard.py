"""Cevap denetimi. Ağ yok, model yok.

Buradaki metinler uydurma değil: 20.09.2026'da gerçek modelin gerçek
sorulara verdiği cevaplardır. Regresyon vakası olarak durur.
"""
import unittest

from jarvis import answer_guard as ag

KATALOG = ("VIREON FOR MEN", "INTIMBLANC", "HYDRAVIE", "LIFTELLE",
           "DERMAVASC", "KINESIS +", "SUNACNEA +30 SPF", "HAIR NOURISHER")

# Olculen gercek cevap: FEMISIA katalogda YOK.
UYDURMA = ("Son 30 gün içinde en çok satan ürün verilerimizde belirtilmemiştir. "
           "Ancak VIREON FOR MEN ve FEMISIA FOR WOMEN gibi ürünler öne çıkmıştır. "
           "Bu ürünlerin kanal kararı ayrıca değerlendirilmelidir.")

# Olculen gercek cevap: laubali ton.
LAUBALI = "Teşekkür ederim, iyiyim! Seninle konuşmak güzel bir fırsat. 😊"


class UydurmaUrunTests(unittest.TestCase):
    def test_katalogda_olmayan_ad_yakalanir(self):
        self.assertIn("FEMISIA FOR WOMEN", ag.unknown_products(UYDURMA, KATALOG))

    def test_katalogdaki_ad_yakalanmaz(self):
        self.assertNotIn("VIREON FOR MEN", ag.unknown_products(UYDURMA, KATALOG))

    def test_katalog_adinin_parcasi_yakalanmaz(self):
        """Model 'VIREON' yazabilir; katalogda 'VIREON FOR MEN' olarak geçer."""
        self.assertEqual([], ag.unknown_products("VIREON iyi satıyor.", KATALOG))

    def test_kurum_ve_kisaltmalar_urun_sayilmaz(self):
        metin = "TİTCK mevzuatına göre KDV dahil ROAS ve CTR ölçülmelidir."
        self.assertEqual([], ag.unknown_products(metin, KATALOG))

    def test_katalog_bossa_hicbir_sey_uydurma_sayilmaz(self):
        """Ürün listesi okunamadığında her adı uydurma saymak, veri
        yokluğunu hataya çevirmek olurdu."""
        self.assertEqual([], ag.unknown_products(UYDURMA, ()))

    def test_artili_urun_adi_yakalanmaz(self):
        self.assertEqual([], ag.unknown_products("KINESIS + satışta.", KATALOG))


class CumleDusurmeTests(unittest.TestCase):
    def test_uydurma_gecen_cumle_duser(self):
        out, dropped = ag.drop_fabricated(UYDURMA, ["FEMISIA FOR WOMEN"])
        self.assertEqual(1, dropped)
        self.assertNotIn("FEMISIA", out)
        self.assertIn("belirtilmemiştir", out)

    def test_diger_cumleler_korunur(self):
        out, _ = ag.drop_fabricated(UYDURMA, ["FEMISIA FOR WOMEN"])
        self.assertIn("kanal kararı", out)

    def test_hepsi_duserse_metin_korunur(self):
        """Boş cevap, yanlış cevaptan da kötüdür: kullanıcı neyin yanlış
        olduğunu göremez."""
        metin = "FEMISIA FOR WOMEN en çok satan üründür."
        out, dropped = ag.drop_fabricated(metin, ["FEMISIA FOR WOMEN"])
        self.assertEqual(metin, out)
        self.assertEqual(0, dropped)

    def test_uydurma_yoksa_dokunulmaz(self):
        self.assertEqual((UYDURMA, 0), ag.drop_fabricated(UYDURMA, []))


class TonTests(unittest.TestCase):
    def test_emoji_silinir(self):
        self.assertNotIn("😊", ag.formalize(LAUBALI))

    def test_unlem_noktaya_donusur(self):
        self.assertNotIn("!", ag.formalize(LAUBALI))

    def test_samimi_hitap_resmilesir(self):
        out = ag.formalize(LAUBALI)
        self.assertIn("Sizinle", out.replace("sizinle", "Sizinle"))
        self.assertNotIn("Seninle", out)

    def test_bos_acilis_kalibi_silinir(self):
        self.assertTrue(ag.formalize("Tabii ki, satışlar arttı.")
                        .startswith("satışlar"))

    def test_soru_isareti_korunur(self):
        self.assertIn("?", ag.formalize("Hangi ürün? Bilmiyorum."))

    def test_bos_metin_cokmez(self):
        self.assertEqual("", ag.formalize(""))


class SozlesmeTests(unittest.TestCase):
    def test_model_cagrisi_sifir(self):
        self.assertEqual(0, ag.guard(UYDURMA, KATALOG)["model_calls"])

    def test_degisiklik_raporlanir(self):
        out = ag.guard(UYDURMA, KATALOG)
        self.assertTrue(out["changed"])
        self.assertEqual(["FEMISIA FOR WOMEN"], out["invented_products"])
        self.assertEqual(1, out["sentences_dropped"])

    def test_temiz_cevap_degismez(self):
        temiz = "Satışlar arttı. Reklam harcaması sabit kaldı."
        out = ag.guard(temiz, KATALOG)
        self.assertFalse(out["changed"])
        self.assertEqual(temiz, out["text"])


if __name__ == "__main__":
    unittest.main()
