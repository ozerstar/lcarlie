"""Alan ICI soru ayrimi: ayni alandaki iki soru ayni cevabi DONMEMELI.

OLCULDU 25.09.2026 (gercek sohbet yolu, 6 soru):
  "en cok satan urun hangisi" -> "bu hafta kac siparis geldi" ile BIREBIR
  AYNI metin dondu ve hicbir urun adi gecmedi.
  "hangi urunun hic reklami yok" -> genel harcama paragrafi dondu.
Veri iki soruda da vardi; soru o veriye baglanmamisti. Bu testler o
baglantinin kopmasini yakalar.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

# Uretim dokumune yazmayi engelleyen kapi, ice aktarmadan ONCE kurulmali.
os.environ["JARVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="cevap-test-")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webconsole import conversation as c  # noqa: E402


class AlgilayiciTests(unittest.TestCase):
    """Algilayicilar DAR olmali: yanlis yakalamak dogru cevabi bozar."""

    def test_kapsama_sorusu_yakalanir(self):
        for s in ("hangi ürünün hiç reklamı yok",
                  "reklamı olmayan ürünler",
                  "reklam kapsaması nedir",
                  "hangi urunun reklami yok"):
            self.assertTrue(c._kapsama_sorusu(s), s)

    def test_kapsama_performans_sorusunu_yakalamaz(self):
        """'Hangi reklam iyi calisiyor' bir KAPSAMA sorusu degildir."""
        for s in ("hangi reklam iyi çalışıyor",
                  "reklam harcamamız ne durumda",
                  "bu ay reklama ne kadar verdik"):
            self.assertFalse(c._kapsama_sorusu(s), s)

    def test_urun_sira_sorusu_yakalanir(self):
        for s in ("en çok satan ürün hangisi",
                  "hangi ürün satıyor",
                  "en az satan ürün",
                  "ürün bazında satış"):
            self.assertTrue(c._urun_sira_sorusu(s), s)

    def test_urun_sira_toplam_sorusunu_yakalamaz(self):
        for s in ("bu hafta kaç sipariş geldi",
                  "toplam ciro ne kadar"):
            self.assertFalse(c._urun_sira_sorusu(s), s)


class KapsamaCevabiTests(unittest.TestCase):
    KAPSAMA = [
        {"urun_adi": "A", "etkin_durum": "CAMPAIGN_PAUSED"},
        {"urun_adi": "A", "etkin_durum": "ACTIVE"},
        {"urun_adi": "B", "etkin_durum": "CAMPAIGN_PAUSED"},
        {"urun_adi": "", "etkin_durum": "ACTIVE"},
    ]
    KATALOG = [{"urun_adi": "A"}, {"urun_adi": "B"}, {"urun_adi": "C"}]

    def test_reklamsiz_urun_adiyla_sayilir(self):
        m = c._kapsama_answer(self.KAPSAMA, self.KATALOG)
        self.assertIn("3 üründen 2 tanesinin", m)
        self.assertIn("1 tanesinin HİÇ reklamı yok", m)
        self.assertIn("C", m)

    def test_duraklatilmis_ile_yok_ayri_sayilir(self):
        """Ikisini karistirmak 'kreatif uretin' onerisini yanlis urune goturur."""
        m = c._kapsama_answer(self.KAPSAMA, self.KATALOG)
        self.assertIn("DURAKLATILMIŞ", m)
        self.assertIn("aynı şey değildir", m)

    def test_urune_baglanmayan_reklam_gizlenmez(self):
        m = c._kapsama_answer(self.KAPSAMA, self.KATALOG)
        self.assertIn("1 reklam hiçbir ürüne bağlanamıyor", m)

    def test_katalog_yoksa_sayi_UYDURULMAZ(self):
        """Katalog olmadan 'hic reklami yok' denemez -- sebebi yazilir."""
        m = c._kapsama_answer(self.KAPSAMA, [])
        self.assertIn("hesaplanamadı", m)
        self.assertNotIn("HİÇ reklamı yok", m)


class UrunSiraCevabiTests(unittest.TestCase):
    ITEMS = [
        {"urun_adi": "COK ADET", "adet": 10, "satir_ciro_net": 100, "brut_marj": 10},
        {"urun_adi": "COK CIRO", "adet": 1, "satir_ciro_net": 5000, "brut_marj": 40},
    ]

    def test_urun_adi_gecer(self):
        m = c._urun_sira_answer("en çok satan ürün hangisi", self.ITEMS)
        self.assertIn("COK ADET", m)
        self.assertIn("COK CIRO", m)

    def test_adet_ve_ciro_AYRI_verilir(self):
        """'En cok satan' iki farkli sey olabilir; birini secmek varsaymaktir."""
        m = c._urun_sira_answer("en çok satan ürün hangisi", self.ITEMS)
        self.assertIn("(adet)", m)
        self.assertIn("Ciroya göre", m)

    def test_lider_farkliysa_acikca_soylenir(self):
        m = c._urun_sira_answer("en çok satan ürün hangisi", self.ITEMS)
        self.assertIn("AYNI DEĞİL", m)

    def test_bos_veri_uydurmaz(self):
        self.assertIn("okunamıyor", c._urun_sira_answer("en çok satan", []))


if __name__ == "__main__":
    unittest.main()
