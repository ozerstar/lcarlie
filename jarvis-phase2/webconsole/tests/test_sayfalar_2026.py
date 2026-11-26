# -*- coding: utf-8 -*-
"""Ayrı sayfalar tasarım 2026 (26.11.2026) — yazıyla değil testle korunur.

Finans merkezi, Harcamalarım, Cari ekstreler, Fiş ve faturalar, Ofis ve
Görsel işleri panelin 25.11 tasarımına taşındı (sayfalar-2026.css). Bu
takım geri kaymayı engeller:
- her ayrı sayfa yeni katmanı EN SON yükler, satır içi stil/betik yok (CSP)
- katmanda yeni renk icat edilmez: her renk bir jeton değeridir
- yazı 11 px altına inmez; jeton renkleri koyu özet kutusunda okunur
- cari ekstrenin yazdırma görünümü (müşteriye gider) değişmez
- belge önizlemesi kutusundan taşmaz (ölçülen kusur)
- finans modülleri tek sürümle yüklenir (iki sürüm = iki ayrı modül örneği)
"""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
KATMAN = (STATIC / "sayfalar-2026.css").read_text(encoding="utf-8")
TEMA = (STATIC / "lcarlie-theme.css").read_text(encoding="utf-8")

SAYFALAR = {
    "finans.html": "finans",
    "harcamalar.html": "harcamalar",
    "cari.html": "cari",
    "belgeler.html": "belgeler",
    "office.html": "ofis",
    "image-jobs.html": "gorselisleri",
}


def _kanal(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _parlak(h):
    r, g, b = (_kanal(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a, b):
    x, y = sorted((_parlak(a), _parlak(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def jeton_renkleri():
    return {d.lower() for d in re.findall(r"--p-[a-z0-9-]+:\s*(#[0-9a-fA-F]{6})", TEMA)}


class SayfalarYeniKatmaniYukler(unittest.TestCase):
    def test_her_sayfa_isaretli_ve_katman_en_son(self):
        for ad, sayfa in SAYFALAR.items():
            html = (STATIC / ad).read_text(encoding="utf-8")
            self.assertIn('data-ui="2026"', html, ad)
            self.assertIn('data-sayfa="%s"' % sayfa, html, ad)
            self.assertIn("lcarlie-theme.css", html, ad + ": jetonlar bu dosyada")
            sayfalar_css = html.index("/sayfalar-2026.css")
            for m in re.finditer(r'rel="stylesheet"[^>]*href="([^"]+)"', html):
                self.assertLessEqual(html.index(m.group(1)), sayfalar_css, ad + ": " + m.group(1))
            self.assertIn('data-sayfa="%s"' % sayfa, KATMAN, sayfa + " için katmanda kural yok")

    def test_satir_ici_stil_ve_betik_yok(self):
        for ad in SAYFALAR:
            html = (STATIC / ad).read_text(encoding="utf-8")
            self.assertNotRegex(html, r"<style|\sstyle=", ad)
            self.assertNotRegex(html, r"<script(?![^>]*\ssrc=)[^>]*>", ad)

    def test_finans_modulleri_tek_surum(self):
        surumler = set(re.findall(r"/finans/app\.js\?v=(\d+)", (STATIC / "finans.html").read_text(encoding="utf-8")))
        for js in (STATIC / "finans").glob("*.js"):
            surumler |= set(re.findall(r"from '\./[a-z]+\.js\?v=(\d+)'", js.read_text(encoding="utf-8")))
        self.assertEqual(len(surumler), 1, surumler)


class KatmanKurallari(unittest.TestCase):
    def test_yazi_11px_altina_inmez(self):
        for deger in re.findall(r"font-size:\s*([0-9.]+)px", KATMAN):
            self.assertGreaterEqual(float(deger), 11.0, deger + "px")
        for deger in re.findall(r"font:\s*[0-9]+\s+([0-9.]+)px", KATMAN):
            self.assertGreaterEqual(float(deger), 11.0, deger + "px")

    def test_yeni_renk_icat_edilmez(self):
        jetonlar = jeton_renkleri()
        self.assertGreater(len(jetonlar), 20, "jeton okuyucu çalışmıyor")
        for renk in re.findall(r"#[0-9a-fA-F]{3,8}\b", KATMAN):
            renk = renk.lower()
            if len(renk) == 9 and renk.startswith("#ffffff"):
                continue  # beyazın saydam tonu (koyu kutuda çizgi/alan)
            self.assertIn(renk, jetonlar, renk + " bir jeton değeri değil")

    def test_koyu_ozet_kutusunda_metin_okunur(self):
        m = re.search(r'\.fx-hero \{ background: (#[0-9a-f]{6})', KATMAN)
        self.assertIsNotNone(m)
        zemin = m.group(1)
        blok = KATMAN[m.start():KATMAN.index(".fx-hero .big", m.start())]
        renkler = set(re.findall(r"(?:color|fill|stroke): (#[0-9a-f]{6})", blok))
        self.assertGreater(len(renkler), 3)
        for renk in renkler:
            self.assertGreaterEqual(kontrast(renk, zemin), 4.5, renk)

    def test_cari_yazdirma_gorunumune_dokunulmaz(self):
        """Yazdırılan/indirilen ekstre müşteriye gider: cari kuralları yalnız ekranda."""
        bas = KATMAN.index("@media screen {")
        son = KATMAN.index("/* ======================================================= FİŞ VE FATURALAR")
        disarida = KATMAN[:bas] + KATMAN[son:]
        self.assertNotIn('data-sayfa="cari"', disarida)
        self.assertNotIn("@media print", KATMAN)

    def test_belge_onizlemesi_kutudan_tasmaz(self):
        self.assertRegex(KATMAN, r'\.preview \{ position: relative; overflow: hidden;')
        self.assertRegex(KATMAN, r'\.preview img \{ position: absolute; inset: 0;')

    def test_ofis_kapali_ayrinti_paneli_golge_dusurmez(self):
        self.assertRegex(KATMAN, r'\.detail:not\(\.open\) \{ box-shadow: none !important; visibility: hidden; \}')

    def test_gecersiz_sozde_oge_is_icinde_yok(self):
        """:is() içinde ::placeholder gibi sözde öğe tüm kuralı geçersiz kılar."""
        for m in re.finditer(r":is\(([^{]*)\)\s*\{", KATMAN):
            self.assertNotIn("::", m.group(1))


if __name__ == "__main__":
    unittest.main()
