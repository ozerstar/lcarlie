"""Yapısal sınıflandırma. Ağ yok -- sinyaller gerçek sayfalardan kopyalandı.

Buradaki JSON-LD ve og:type şekilleri uydurma değil: 20 Eylül 2026'da yedi
gerçek Türk sitesinden ölçülen biçimlerdir. Ölçümde 7 sayfanın 6'sında
JSON-LD @type bulundu; sınıflandırmanın Türkçe kelime listesi yerine buna
dayanmasının sebebi bu.
"""
import unittest

from jarvis.research_sources import (NON_INDEPENDENT_TYPES, classify_source,
                                     structural_signals)


def sayfa(ld_types=(), og_type="", govde=""):
    ld = ""
    if ld_types:
        icerik = ", ".join(f'{{"@type": "{t}"}}' for t in ld_types)
        ld = f'<script type="application/ld+json">[{icerik}]</script>'
    og = f'<meta property="og:type" content="{og_type}">' if og_type else ""
    return f"<html><head>{ld}{og}</head><body>{govde}</body></html>"


class SinyalTests(unittest.TestCase):
    def test_json_ld_okunur(self):
        sig = structural_signals(sayfa(["BlogPosting"], "article"))
        self.assertEqual(sig["ld_types"], ["blogposting"])
        self.assertEqual(sig["og_type"], "article")

    def test_graph_icindeki_tipler_de_okunur(self):
        html = ('<script type="application/ld+json">'
                '{"@graph":[{"@type":"NewsArticle"}]}</script>')
        self.assertIn("newsarticle", structural_signals(html)["ld_types"])

    def test_bozuk_json_ld_cokmez(self):
        html = '<script type="application/ld+json">{bozuk,,</script>'
        self.assertEqual(structural_signals(html)["ld_types"], [])

    def test_sinyal_yoksa_bos_doner(self):
        sig = structural_signals("<html><body>merhaba</body></html>")
        self.assertEqual(sig["ld_types"], [])
        self.assertEqual(sig["og_type"], "")


class SiniflandirmaTests(unittest.TestCase):
    def test_meslek_birligi_soneki(self):
        """teis.org.tr, uste.org.tr -- ölçümde gelen en değerli kaynaklardı
        ve hepsi UNKNOWN dönüyordu."""
        self.assertEqual(classify_source("www.teis.org.tr", "", ""),
                         "TRADE_PUBLICATION")

    def test_duzenleyici_sonek_birligi_yener(self):
        self.assertEqual(classify_source("www.titck.gov.tr", "", ""), "REGULATOR")

    def test_makale_beyani(self):
        html = sayfa(["Article", "Organization"], "article")
        self.assertEqual(classify_source("ornek.com", "", "", html), "NEWS")

    def test_urun_beyani_makaleyi_yener(self):
        """Bir sayfa hem Product hem Article basarsa mağazadır."""
        html = sayfa(["Product", "Article"], "article")
        self.assertEqual(classify_source("ornek.com", "", "", html), "RETAILER")

    def test_kurumsal_site_sekli_bagimsiz_sayilmaz(self):
        """Organization+WebSite var, makale yok: şirketin kendi sayfası.

        Ölçüldü: dermoeczanem.com ve dermo.com.tr tam bu şekli veriyor ve
        ikisi de UNKNOWN dönüyordu.
        """
        html = sayfa(["Organization", "WebSite", "BreadcrumbList"])
        tip = classify_source("ornek.com", "", "", html)
        self.assertIn(tip, NON_INDEPENDENT_TYPES)

    def test_fiyat_listeleyen_kurumsal_site_magazadir(self):
        govde = " ".join(f"{n}.499,00 TL" for n in range(1, 7))
        html = sayfa(["Organization", "WebSite"], govde=govde)
        self.assertEqual(classify_source("ornek.com", "", govde, html), "RETAILER")

    def test_og_article_tek_basina_yeter(self):
        """Ölçüldü: mağaza ve açılış sayfaları og:type basmıyor, içerik basıyor."""
        self.assertEqual(
            classify_source("ornek.com", "", "", sayfa(og_type="article")), "NEWS")


class GeriyeUyumlulukTests(unittest.TestCase):
    def test_html_verilmezse_eski_yol_calisir(self):
        """Çağıran ham HTML taşımıyorsa davranış eskisiyle aynı kalmalı."""
        govde = "sepete ekle stokta ücretsiz kargo hakkımızda ürünlerimiz"
        self.assertEqual(classify_source("ornek.com", "", govde), "RETAILER")

    def test_bos_html_cokmez(self):
        self.assertEqual(classify_source("ornek.com", "", "", ""), "UNKNOWN")

    def test_pazaryeri_hosti_hala_oncelikli(self):
        html = sayfa(["Article"], "article")
        self.assertEqual(classify_source("www.trendyol.com", "", "", html),
                         "MARKETPLACE")


if __name__ == "__main__":
    unittest.main()
