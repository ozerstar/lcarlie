"""Çoklu cevap doğrulama. Ağ yok, model yok.

Sınanan asıl davranış: ayrışma GİZLENMEMELİ. Bir sistemin en tehlikeli
hatası, kararsız olduğu bir konuda kendinden emin konuşmasıdır.
"""
import unittest

from jarvis import consensus as c


class SayisalIddiaTests(unittest.TestCase):
    def test_turkce_bicimli_sayi_okunur(self):
        claims = c.numeric_claims("Net ciro 27.810,84 TL oldu.")
        self.assertIn("27810.84TL", claims)

    def test_yuzde_ayri_birimdir(self):
        claims = c.numeric_claims("Marj %18,8 arttı.")
        self.assertIn("18.8%", claims)

    def test_birim_sayinin_parcasidir(self):
        """'1.200 TL' ile '1.200 adet' aynı sayı değildir."""
        a = c.numeric_claims("1.200 TL")
        b = c.numeric_claims("1.200 adet")
        self.assertEqual(set(), set(a) & set(b))

    def test_yil_celiski_uretmez(self):
        self.assertEqual(Counter := type(c.numeric_claims("2026 yılında")),
                         type(c.numeric_claims("")))
        self.assertEqual(0, len(c.numeric_claims("2026 yılında rapor çıktı")))

    def test_bos_metin_cokmez(self):
        self.assertEqual(0, len(c.numeric_claims("")))


class KarsilastirmaTests(unittest.TestCase):
    def test_ayni_sayilar_uzlasma(self):
        cevaplar = ["Ciro 27.810,84 TL.", "Net ciro 27.810,84 TL oldu.",
                    "27.810,84 TL ciro var."]
        agreed, disputed, ratio = c.compare(cevaplar)
        self.assertEqual((), disputed)
        self.assertEqual(1.0, ratio)
        self.assertIn("27810.84TL", agreed)

    def test_farkli_sayi_cekismeli_sayilir(self):
        """Kayıtlı vaka: fiyat 1.200 mü 2.400 mü belirsiz kalmıştı."""
        cevaplar = ["Fiyat 1.200 TL.", "Fiyat 2.400 TL.", "Fiyat 1.200 TL."]
        agreed, disputed, _ = c.compare(cevaplar)
        self.assertIn("1200TL", agreed)
        self.assertEqual(["2400TL"], [d["claim"] for d in disputed])

    def test_hepsi_farkliysa_hicbiri_uzlasmaz(self):
        agreed, disputed, ratio = c.compare(
            ["100 TL", "200 TL", "300 TL"])
        self.assertEqual((), agreed)
        self.assertEqual(3, len(disputed))
        self.assertEqual(0.0, ratio)

    def test_sayisiz_cevaplarda_celiski_yok(self):
        agreed, disputed, ratio = c.compare(["Veri yok.", "Bu bilgi mevcut değil."])
        self.assertEqual((), agreed)
        self.assertEqual((), disputed)
        self.assertEqual(1.0, ratio)


class SecimTests(unittest.TestCase):
    def test_cekismeli_sayi_tasiyan_cevap_secilmez(self):
        cevaplar = ["Fiyat 2.400 TL olabilir.", "Fiyat 1.200 TL.", "Fiyat 1.200 TL."]
        agreed, disputed, _ = c.compare(cevaplar)
        secilen = c.select(cevaplar, agreed, disputed)
        self.assertIn("1.200", secilen)
        self.assertNotIn("2.400", secilen)

    def test_esitlikte_kisa_olan_secilir(self):
        """Sahibin talimatı: az, öz ve net."""
        kisa = "Ciro 1.200 TL."
        uzun = "Yaptığımız incelemeye göre ciro tutarı 1.200 TL olarak görünmektedir."
        secilen = c.select([uzun, kisa], ("1200TL",), ())
        self.assertEqual(kisa, secilen)

    def test_bos_listede_cokmez(self):
        self.assertEqual("", c.select([], (), ()))


class CalistirmaTests(unittest.TestCase):
    def test_ayrisma_gizlenmez(self):
        """En tehlikeli hata: kararsızken kendinden emin konuşmak."""
        cevaplar = iter(["Fiyat 1.200 TL.", "Fiyat 2.400 TL."])
        out = c.run(lambda: next(cevaplar), samples=2)
        self.assertTrue(out.disputed)
        self.assertIn("doğrulanmadan", out.note)

    def test_uzlasma_raporlanir(self):
        out = c.run(lambda: "Ciro 1.200 TL.", samples=3)
        self.assertEqual((), out.disputed)
        self.assertIn("uzlaşma", out.note)

    def test_ilk_cevap_tekrar_sorulmaz(self):
        sayac = {"n": 0}

        def ask():
            sayac["n"] += 1
            return "Ciro 1.200 TL."
        out = c.run(ask, first="Ciro 1.200 TL.", samples=3)
        self.assertEqual(2, sayac["n"])
        self.assertEqual(2, out.model_calls)

    def test_ornek_hatasi_dogrulamayi_iptal_etmez(self):
        durum = {"n": 0}

        def ask():
            durum["n"] += 1
            if durum["n"] == 2:
                raise RuntimeError("saglayici dustu")
            return "Ciro 1.200 TL."
        out = c.run(ask, samples=3)
        self.assertTrue(out.errors)
        self.assertTrue(out.answer)

    def test_tek_ornek_alinabilirse_durum_bildirilir(self):
        out = c.run(lambda: (_ for _ in ()).throw(RuntimeError("yok")),
                    first="Ciro 1.200 TL.", samples=3)
        self.assertEqual(1, out.samples)
        self.assertIn("karşılaştırma yapılamadı", out.note)


class TetiklemeTests(unittest.TestCase):
    def test_sayi_varsa_dogrulama_gerekir(self):
        self.assertTrue(c.has_company_numbers("Ciro 27.810,84 TL."))

    def test_sayisiz_cevapta_dogrulama_calismaz(self):
        """Selamlaşmada çalıştırmak süreyi üç katına çıkarır, hiçbir şey korumaz."""
        self.assertFalse(c.has_company_numbers("Merhaba, size nasıl yardımcı olabilirim?"))

    def test_yil_tek_basina_tetiklemez(self):
        self.assertFalse(c.has_company_numbers("2026 planını konuşalım."))


if __name__ == "__main__":
    unittest.main()
