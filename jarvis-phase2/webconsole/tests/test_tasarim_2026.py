# -*- coding: utf-8 -*-
"""Panel tasarım sistemi 2026 (25.11.2026) — yazıyla değil testle korunur.

Sahip: "jarvis panelini biraz geliştir, zaten çok eski kaldı." Bu takım,
yeniden yazılan görsel katmanın geri kaymasını engeller:
- renk jetonları tek yerde (lcarlie-theme.css başı), iki temada da metin >= 4,5:1
- eski "botanik" sabit renkler ve çizim bitki geri gelmez
- yeni katmanda yazı 11 px altına inmez, satır içi stil yok
- masaüstündeki her sekmeye telefondan da ulaşılır
- Instagram'da gizlenen yorum "cevapsız" sayılmaz
"""
import re
import sys
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
STATIC = WEB / "static"
KOK = WEB.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(WEB))

TEMA = (STATIC / "lcarlie-theme.css").read_text(encoding="utf-8")
TASARIM = (STATIC / "tasarim-2026.css").read_text(encoding="utf-8")
MOBIL_CSS = (STATIC / "mobile" / "tasarim-2026.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
MOBIL = (STATIC / "mobile" / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
KIMLIK = (STATIC / "lcarlie-identity.js").read_text(encoding="utf-8")


def _kanal(v):
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _parlak(h):
    r, g, b = (_kanal(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a, b):
    x, y = sorted((_parlak(a), _parlak(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def blok(secici):
    m = re.search(re.escape(secici) + r"\s*\{(.*?)\n\}", TEMA, re.S)
    assert m, secici + " bulunamadı"
    return dict(re.findall(r"(--p-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", m.group(1)))


ACIK = blok(":root")
KOYU = blok(':root[data-theme="dark"]')
METIN = ("--p-text", "--p-text-2", "--p-text-3")
ZEMIN = ("--p-bg", "--p-surface", "--p-surface-2", "--p-fill")
DURUM = (("--p-ok", "--p-ok-bg"), ("--p-warn", "--p-warn-bg"),
         ("--p-crit", "--p-crit-bg"), ("--p-info", "--p-info-bg"))


class Jetonlar(unittest.TestCase):
    def test_iki_temada_da_metin_her_zeminde_okunur(self):
        for ad, tema in (("açık", ACIK), ("koyu", KOYU)):
            for m in METIN:
                for z in ZEMIN:
                    oran = kontrast(tema[m], tema[z])
                    self.assertGreaterEqual(oran, 4.5, f"{ad}: {m} / {z} = {oran:.2f}")

    def test_durum_renkleri_kendi_zemininde_ve_kartta_okunur(self):
        for ad, tema in (("açık", ACIK), ("koyu", KOYU)):
            for on, arka in DURUM:
                for z in (arka, "--p-surface"):
                    oran = kontrast(tema[on], tema[z])
                    self.assertGreaterEqual(oran, 4.5, f"{ad}: {on} / {z} = {oran:.2f}")

    def test_birincil_dugme_yazisi_okunur(self):
        for tema in (ACIK, KOYU):
            self.assertGreaterEqual(kontrast(tema["--p-accent-ink"], tema["--p-accent"]), 4.5)

    def test_iki_tema_ayni_jeton_kumesini_tanimlar(self):
        self.assertEqual(set(ACIK), set(KOYU))


class EskiRenklerGeriGelmez(unittest.TestCase):
    """Botanik yeşil sabitler jetona çevrildi; sahip 13.11: yeşil marka rengi değil."""

    def test_tema_katmanlarinda_botanik_sabit_yok(self):
        for ad in ("lcarlie-theme.css", "lcarlie-premium.css", "nav-pro.css"):
            css = (STATIC / ad).read_text(encoding="utf-8").lower()
            for eski in ("#365f49", "#263c33", "#dce8d4", "#e5eddf", "#fffdf8"):
                self.assertNotIn(eski, css, f"{ad}: {eski}")

    def test_cizim_bitki_hicbir_katmanda_yok(self):
        """04.11 sahip: 'arkadaki bitki çok yapay ve amatör'. Telefonda hâlâ çıkıyordu."""
        for yol in list(STATIC.glob("*.css")) + list((STATIC / "mobile").glob("*.css")):
            self.assertNotIn("lcarlie-botanical.svg", yol.read_text(encoding="utf-8"), yol.name)


class YeniKatman(unittest.TestCase):
    def test_yazi_11px_altina_inmez(self):
        for ad, css in (("tasarim-2026.css", TASARIM), ("mobile/tasarim-2026.css", MOBIL_CSS)):
            for deger in re.findall(r"font-size:\s*([0-9.]+)px", css):
                self.assertGreaterEqual(float(deger), 11.0, f"{ad}: {deger}px")
        for ad_j, deger in re.findall(r"(--t-[a-z0-9]+):\s*([0-9.]+)px", TEMA):
            self.assertGreaterEqual(float(deger), 11.0, ad_j)

    def test_ust_cubukta_backdrop_filter_yok(self):
        """Sabit konumlu sol menü üst çubuğun içinde: filtre menüyü 200 px'e sıkıştırdı (ölçüldü)."""
        m = re.search(r"\.app-view \.topbar \{(.*?)\}", TASARIM, re.S)
        self.assertNotIn("backdrop-filter:", m.group(1))

    def test_satir_ici_stil_yok(self):
        for html in (INDEX, MOBIL):
            self.assertNotRegex(html, r"<style|\sstyle=")

    def test_katmanlar_yuklenir_ve_tema_once_gelir(self):
        self.assertIn('data-ui="2026"', INDEX)
        self.assertIn('data-ui="2026"', MOBIL)
        for html in (INDEX, MOBIL):
            self.assertLess(html.index("tema-2026.js"), html.index("stylesheet"),
                            "tema seçimi stillerden önce: koyu temada beyaz yanıp sönme olmasın")
        self.assertGreater(INDEX.index("tasarim-2026.css"), INDEX.index("lcarlie-premium.css"))

    def test_ana_sayfada_bugun_seridi_rakam_gommez(self):
        for kimlik in ("gnSatis", "gnReklam", "gnOnay", "gnUyari"):
            m = re.search(r'id="%s"[^>]*>.*?<strong>(.*?)</strong>' % kimlik, INDEX, re.S)
            self.assertEqual(m.group(1), "—", kimlik)


class Gezinme(unittest.TestCase):
    def _views(self):
        m = re.search(r"const VIEWS = \{(.*?)\};", APP_JS, re.S)
        return set(re.findall(r"(\w+):\s*'view", m.group(1)))

    def test_en_cok_kullanilanlar_ilk_grupta(self):
        ilk = INDEX[INDEX.index('data-group="gunluk"'):INDEX.index('data-group="finans"')]
        for v in ("home", "satislar", "kampanya", "gorevler"):
            self.assertIn('data-view="%s"' % v, ilk)

    def test_menu_etiketleri_buyuk_harf_bagirmaz(self):
        for etiket in re.findall(r'<span class="nav-label">([^<]+)</span>', INDEX):
            self.assertFalse(etiket.isupper() and len(etiket) > 3, etiket)

    def test_her_masaustu_sekmesine_telefondan_ulasilir(self):
        views = self._views()
        self.assertGreater(len(views), 20)
        for v in views:
            erisim = ("['%s'," % v) in KIMLIK or ('/?view=%s"' % v) in MOBIL
            self.assertTrue(erisim, v + " telefondan açılamıyor")


class GizliYorum(unittest.TestCase):
    def test_toplayici_hidden_alanini_ister_ve_yazar(self):
        from jarvis import meta_reklam_detay as m
        self.assertIn("hidden", m.IG_YORUM_ALAN)
        ham = {"comments": {"data": [
            {"id": "1", "text": "a", "username": "x", "hidden": True,
             "replies": {"data": [{"id": "2", "text": "b", "username": "y", "hidden": False}]}},
            {"id": "3", "text": "c", "username": "z"}]}}
        ys = {y["yorum_id"]: y for y in m.ig_yorumlari("med", ham, "lcarlie")}
        self.assertIs(ys["1"]["gizli"], True)
        self.assertIs(ys["2"]["gizli"], False)
        self.assertIsNone(ys["3"]["gizli"], "alan gelmediyse 'gizli değil' denmez, bilinmiyor")

    def test_facebook_yorumu_bilinmiyor_kalir(self):
        from jarvis import meta_reklam_detay as m
        ys = m.fb_yorumlari("g", [{"id": "9", "message": "m", "from": {"id": "u", "name": "n"}}], "s")
        self.assertIsNone(ys[0]["gizli"])

    def test_gizli_yorum_cevapsiz_sayilmaz(self):
        kaynak = (WEB / "reklam_yoneticisi.py").read_text(encoding="utf-8")
        self.assertIn("NOT coalesce(y.gizli, false)", kaynak)
        self.assertIn("cevaplandi, gizli FROM raw.meta_reklam_yorum", kaynak)

    def test_toplayici_sutunu_yazar(self):
        izle = (KOK / "scripts" / "meta-reklam-izle.py").read_text(encoding="utf-8")
        self.assertRegex(izle, r"YORUM_KOLON = \([^)]*gizli boolean")

    def test_goc_sutunu_ve_panel_yetkisini_ekler(self):
        goc = (KOK / "migrations" / "080_meta_yorum_gizli.sql").read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS gizli boolean", goc)
        self.assertIn("TO jarvis_web", goc)
        self.assertNotIn("ai_reader", goc.split("--")[0])

    def test_panel_gizliyi_soluk_gosterir_ve_cevap_beklemez(self):
        self.assertIn("is-gizli", APP_JS)
        self.assertIn("!y.gizli ?", APP_JS)
        self.assertIn(".ry-yorum.is-gizli", TASARIM)


class OzetKesiti(unittest.TestCase):
    def test_ana_sayfa_ozeti_listeleri_tasimaz(self):
        import reklam_yoneticisi as ry
        r = {"durum": "OK", "aralik": {}, "olcum": {}, "uyarilar": [], "platformlar": [],
             "reklamlar": [1] * 50, "setler": [1], "kampanyalar": [1], "trend": [1],
             "ozet": {"harcama": 1.0, "tum_siparis": 2, "durum_sayim": {"acik": 1},
                      "reklamlar": [1]}}
        k = ry.ozet_kesiti(r)
        for a in ("reklamlar", "setler", "kampanyalar", "trend"):
            self.assertNotIn(a, k)
        self.assertEqual(k["ozet"]["tum_siparis"], 2)
        self.assertNotIn("reklamlar", k["ozet"])
        self.assertEqual(k["ozet"]["durum_sayim"], {"acik": 1})


if __name__ == "__main__":
    unittest.main()
