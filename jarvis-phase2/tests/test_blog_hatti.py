# -*- coding: utf-8 -*-
"""Blog hattı kapı testleri (ağsız). Çalıştır: venv/bin/python -m unittest tests.test_blog_hatti"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis import blog_hatti as bh  # noqa: E402

ADLAR = ["hydravie", "sunacnea", "l'carlié", "babysoft"]


def _govde(kelime: int, ek: str = "") -> str:
    p = "<p>" + " ".join(["nem"] * kelime) + "</p>"
    return ("<p>İlk paragraf doğrudan cevap.</p>" + p + ek +
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
            "<h2>Kaynaklar</h2><ul><li>x</li></ul>")



def _kaynakli(maddeler):
    return "<p>gövde</p><h2>Kaynaklar</h2><ul>" + "".join("<li>%s</li>" % m for m in maddeler) + "</ul>"


GERCEK = {
    "11712033": "When should sunscreen be reapplied?",
    "10.1111/phpp.12099": "Application of sunscreen--theory and reality",
}


def sahte_servis(f):
    f = mock.patch.object(bh, "pmid_baslik", lambda p: GERCEK.get(p))(f)
    f = mock.patch.object(bh, "doi_baslik", lambda d: GERCEK.get(d))(f)
    return mock.patch.object(bh, "url_canli", lambda u: "titck.gov.tr" in u)(f)


class BlogHattiKapilari(unittest.TestCase):

    def test_kelime_kapisi_kaynaklari_saymaz(self):
        html = _govde(1100) + "<ul>" + "<li>kaynak kelimesi</li>" * 400 + "</ul>"
        assert bh.kelime_kapisi(html), "Kaynaklar bölümü kelime sayısına katılmamalı"
        assert not bh.kelime_kapisi(_govde(1300))


    def test_yapi_kapisi_tablo_ve_kaynak_ister(self):
        assert bh.yapi_kapisi(_govde(10)) == []
        assert "tablo/adım listesi yok" in bh.yapi_kapisi("<p>a</p><h2>Kaynaklar</h2><ul><li>x</li></ul>")
        assert "Kaynaklar bölümü yok" in bh.yapi_kapisi("<p>a</p><table></table>")


    # ---------------------------------------------------------------------- iddia
    def test_sert_yasak_her_yerde(self):
        r = bh.iddia_kapisi("<p>Bu yağ mucize gibi etki gösterir.</p>", "tr", ADLAR)
        assert r["red"]


    def test_hekim_onerisiyle_kullanim_uyarisi_serbest(self):
        r = bh.iddia_kapisi("<p>Yenidoğanda herhangi bir ürün hekim önerisiyle kullanılmalıdır.</p>", "tr", ADLAR)
        assert not [x for x in r["red"] if x["kural"] == "sert yasak"]


    def test_dermatolog_onerir_yasak(self):
        r = bh.iddia_kapisi("<p>Dermatologlar öneriyor ve bu krem çok sevilir.</p>", "tr", ADLAR)
        assert r["red"]


    def test_urun_cumlesinde_hastalik_nesnesi_red(self):
        r = bh.iddia_kapisi("<p>HYDRAVIE egzama görünümünü azaltır.</p>", "tr", ADLAR)
        assert any(x["kural"] == "ürün cümlesinde yasak nesne" for x in r["red"])


    def test_kelime_ici_eslesme_yok(self):
        # "markası" içindeki "kas" kas (fizyolojik işlev) sayılmamalı
        r = bh.iddia_kapisi("<p>L'CARLIÉ hangi firmanın markası?</p>", "tr", ADLAR)
        self.assertEqual(r["red"], [])
        r = bh.iddia_kapisi("<p>HYDRAVIE kasları gevşetir.</p>", "tr", ADLAR)
        self.assertTrue(r["red"])

    def test_genel_bilim_cumlesi_engellenmez(self):
        r = bh.iddia_kapisi("<p>Bir çalışmada niasinamidin egzama hastalarında bariyer ölçümlerini değiştirdiği "
                            "raporlanmıştır.</p>", "tr", ADLAR)
        assert not [x for x in r["red"] if x["kural"] != "sert yasak"]


    def test_egilimli_cilt_serbest(self):
        r = bh.iddia_kapisi("<p>SUNACNEA akneye eğilimli ciltler için hafif dokulu bir güneş kremidir.</p>", "tr", ADLAR)
        assert not [x for x in r["red"] if x["kural"] == "ürün cümlesinde yasak nesne"]


    def test_ceviri_iddia_kapisi(self):
        for dil, cumle in (("en", "HYDRAVIE treats eczema."), ("de", "HYDRAVIE heilt die Haut."),
                           ("ru", "HYDRAVIE лечит кожу."), ("ar", "HYDRAVIE يعالج البشرة.")):
            assert bh.iddia_kapisi("<p>%s</p>" % cumle, dil, ADLAR)["red"], dil


    def test_ceviri_temiz_cumle_gecer(self):
        r = bh.iddia_kapisi("<p>HYDRAVIE leaves skin feeling soft and moisturised.</p>", "en", ADLAR)
        assert not r["red"]


    # ------------------------------------------------------------- güneş ibaresi
    def test_gunes_ibaresi_eklenir_ve_kapi_kapanir(self):
        from jarvis import compliance
        html = "<p>Güneş koruyucu her sabah sürülür; SPF değeri koruma düzeyidir.</p><h2>Kaynaklar</h2><ul><li>x</li></ul>"
        yeni, eklendi = bh.gunes_uyarisi_ekle(html)
        assert eklendi
        govde, kaynak = bh.govde_kaynaksiz(yeni)
        assert not compliance._sunscreen_findings(bh.duz_metin(govde))
        assert kaynak.startswith("<h2>Kaynaklar")


    # ------------------------------------------------------------------ kaynak
    def _kaynakli(maddeler: list[str]) -> str:
        return "<p>gövde</p><h2>Kaynaklar</h2><ul>" + "".join("<li>%s</li>" % m for m in maddeler) + "</ul>"


    GERCEK = {
        "11712033": "When should sunscreen be reapplied?",
        "10.1111/phpp.12099": "Application of sunscreen--theory and reality",
    }


    def sahte_servis(f):
        f = mock.patch.object(bh, "pmid_baslik", lambda p: GERCEK.get(p))(f)
        f = mock.patch.object(bh, "doi_baslik", lambda d: GERCEK.get(d))(f)
        return mock.patch.object(bh, "url_canli", lambda u: "titck.gov.tr" in u)(f)


    @sahte_servis
    def test_kaynak_kapisi_uydurmayi_cikarir(self):
        html = _kaynakli([
            "Diffey BL. (2001). When should sunscreen be reapplied? JAAD. PMID: 11712033.",
            "Petersen B. (2014). Application of sunscreen – theory and reality. doi:10.1111/phpp.12099",
            "Uydurma A. (2020). A study that does not exist. PMID: 99999999.",
            "Yanlış B. (2019). Totally different title here. PMID: 11712033.",
            'TİTCK kılavuzu. <a href="https://titck.gov.tr/x.pdf">titck.gov.tr</a>',
        ])
        s = bh.kaynak_kapisi(html, uyku=0)
        assert s["dogrulanan"] == 3
        assert len(s["cikarilan"]) == 2
        assert "99999999" not in s["html"] and "Totally different" not in s["html"]


    @sahte_servis
    def test_kaynak_kapisi_dort_alti_sayilir(self):
        s = bh.kaynak_kapisi(_kaynakli(["Diffey. When should sunscreen be reapplied? PMID: 11712033"]), uyku=0)
        assert s["dogrulanan"] < bh.EN_AZ_KAYNAK


    def test_baslik_uyar_turkce_ceviri_eklentisine_dayanikli(self):
        assert bh.baslik_uyar("When should sunscreen be reapplied?",
                              "Diffey BL. (2001). When should sunscreen be reapplied? (Güneş kremi ne zaman...) JAAD")
        assert not bh.baslik_uyar("When should sunscreen be reapplied?", "Başka bir makale, farklı konu")


    # ------------------------------------------------------------------- Ricos
    def test_html_to_ricos_yapi_ve_ozdenetim(self):
        html = ('<p>Giriş <strong>kalın</strong> ve <a href="https://www.lcarlie.shop/post/x">bağlantı</a>.</p>'
                '<h2>Başlık</h2><ul><li>bir</li><li><strong>iki</strong> üç</li></ul>'
                '<table><thead><tr><th>A</th><th>B</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr>'
                '<tr><td>3</td></tr></tbody></table><h3>Alt</h3><ol><li>adım</li></ol>')
        doc = bh.html_to_ricos(html, [{"id": "abc~mv2.jpg", "width": 1200, "height": 800, "alt": "x", "sonra_h2": 1}])
        assert bh.ricos_denetle(doc) == []
        tipler = [n["type"] for n in doc["nodes"]]
        assert "TABLE" in tipler and "BULLETED_LIST" in tipler and "ORDERED_LIST" in tipler and "IMAGE" in tipler
        assert tipler.index("IMAGE") < [i for i, n in enumerate(doc["nodes"]) if n["type"] == "HEADING"][0]
        tablo = next(n for n in doc["nodes"] if n["type"] == "TABLE")
        assert all(len(r["nodes"]) == 2 for r in tablo["nodes"]), "eksik hücre doldurulmalı"
        link = [t for n in doc["nodes"] if n["type"] == "PARAGRAPH" for t in n["nodes"]
                if any(d["type"] == "LINK" for d in t["textData"]["decorations"])]
        assert link and link[0]["textData"]["text"] == "bağlantı"


    def test_link_ceviri_ve_kaldirma(self):
        html = '<p><a href="https://www.lcarlie.shop/post/olu">ölü</a> metin kalır.</p>'
        doc = bh.html_to_ricos(html, link_cevir=lambda u: None)
        metin = "".join(t["textData"]["text"] for t in doc["nodes"][0]["nodes"])
        assert "ölü metin kalır" in metin
        assert not any(d["type"] == "LINK" for t in doc["nodes"][0]["nodes"] for d in t["textData"]["decorations"])


    # ------------------------------------------------------------- yardımcılar
    def test_slugla_turkce(self):
        assert bh.slugla("Güneş Kremi Kaç Saat Korur?") == "gunes-kremi-kac-saat-korur"
        assert bh.slugla("İç Ölçü — ŞĞÜ") == "ic-olcu-sgu"


    def test_lit_dolar_etiketi_metinle_carpismaz(self):
        s = bh.Kuyruk._lit("içinde $b12345678$ ve ' tırnak")
        etiket = s[:s.index("$", 1) + 1]
        assert s.startswith(etiket) and s.endswith(etiket)
        assert s.count(etiket) == 2


    def test_hazir_dosya_oku_gercek_dosya(self):
        kok = Path("/opt/lcarlie/blog-hatti/kaynak/tr")
        dosyalar = sorted(kok.glob("E01-*.html")) if kok.is_dir() else []
        if not dosyalar:
            self.skipTest("kaynak dosya yok")
        d = bh.hazir_dosya_oku(dosyalar[0])
        assert d["slug"] == "gunes-kremi-kac-saat-korur" and d["tur"] == "NEW"
        assert d["faq_jsonld"]["@type"] == "FAQPage" and len(d["faq_jsonld"]["mainEntity"]) >= 4
        assert "<h1" not in d["html"] and "sunacnea" in d["kesitler"]
        json.dumps(d, ensure_ascii=False)



class TabloOranTamSayi(unittest.TestCase):
    def test_uc_sutun_orani_tam_sayi(self):
        html = "<table><tr><th>a</th><th>b</th><th>c</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>"
        rc = bh.html_to_ricos(html, [])
        tablo = [n for n in rc["nodes"] if n["type"] == "TABLE"][0]
        oran = tablo["tableData"]["dimensions"]["colsWidthRatio"]
        self.assertTrue(all(isinstance(x, int) for x in oran), oran)
        self.assertEqual(sum(oran), 100)


if __name__ == "__main__":
    unittest.main()
