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



# ============================================================ 28.11.2026 kapıları
def _olumsuz(cumle: str, dil: str = "tr") -> list:
    return bh.olumsuz_dil_kapisi("<p>%s</p><h2>Kaynaklar</h2><ul><li>x</li></ul>" % cumle, dil)


class OlumsuzDilKapisi(unittest.TestCase):
    """Sahip 28.11: 'etkisi görülmedi / kanıtlanmadı' tarzı hiçbir şey olmayacak."""

    def test_sahibin_verdigi_ornekler_yakalanir(self):
        for c in ["300 kişide test yapıldı, etkisi görülmedi.",
                  "Bu içeriğin etkisi kanıtlanmadı.",
                  "Asidik pH'lı bir toniğin bu dönüşü hızlandırdığını gösteren güçlü bir klinik çalışma ise yoktur.",
                  "Kuru ve hassas ciltte sık kullanım önerilmez.",
                  "Klinik veriler sınırlıdır ama vardır.",
                  "Bu krem işe yaramaz.",
                  "Hayır, temel bir rutin için zorunlu değildir.",
                  "Hodan yağı içeren her ürünün aynı sonucu vereceği anlamına gelmez.",
                  "Listenin ilk sıralarındaysa sık kullanım için iyi bir aday değildir."]:
            assert _olumsuz(c), "yakalanmalıydı: " + c

    def test_ek_almis_ve_buyuk_harfli_bicimler(self):
        # Türkçe tuzak: İ/I katlaması ve çekim ekleri
        for c in ["ETKİSİ KANITLANMADI.", "Etkisi KANITLANMAMIŞTIR.", "Etkinliği henüz kanıtlanamamıştır.",
                  "İŞE YARAMAZ.", "Bu kullanım ÖNERİLMEZ.", "Bu yönde bir kanıt bulunmamaktadır.",
                  "Gruplar arasında anlamlı fark bulunmadı.", "Araştırmalar yetersizdir.",
                  "Kullanımı tavsiye edilmemektedir.", "Bu adım gereksizdir."]:
            assert _olumsuz(c), "yakalanmalıydı: " + c

    def test_birlesik_noktali_i_katlanir(self):
        assert _olumsuz("İŞE YARAMAZ.")
        assert bh.tr_kucuk("İŞE") == "işe" and bh.tr_kucuk("İŞE") == "işe" and bh.tr_kucuk("ISI") == "ısı"

    def test_urun_ozelligi_ve_talimat_olumsuz_dil_degildir(self):
        for c in ["Alkolsüz, parabensiz ve parfümsüz bir toniktir.",
                  "Göz çevresine uygulanmaz; yalnız haricen kullanılır.",
                  "Uçucu yağlar saf sürülmez, taşıyıcı yağ içinde seyreltilir.",
                  "Kuru ciltler çiçek suyu bazlı toniklerle daha rahat eder.",
                  "Sınırsız ferahlık hissi veren hafif bir dokudur.",
                  "Çalışmada transepidermal su kaybı azaldı.",
                  "Veriler tabloda özetlenmiştir; kanıt düzeyi yüksektir.",
                  "Shea yağı zararlı mı?"]:
            assert not _olumsuz(c), "yanlış pozitif: %s -> %s" % (c, _olumsuz(c))

    def test_kelime_ici_eslesme_yok(self):
        # kalıp kelimenin ortasında/çekimli başka kelimede eşleşmemeli
        for c in ["Zararlılara karşı ambalaj kapalı tutulur.", "Formül sınırlı sayıda içerikle sade tutulmuştur.",
                  "Serum tonikten sonra uygulanır.", "Efsanevi bir koku değil, hafif bir çiçek notası taşır."]:
            assert not _olumsuz(c), "yanlış pozitif: %s -> %s" % (c, _olumsuz(c))

    def test_kaynaklar_ve_zorunlu_gunes_uyarisi_haric(self):
        html = ("<p>Güneş koruyucu sabah rutininin son adımıdır.</p>" + bh.GUNES_UYARI_TR +
                "<h2>Kaynaklar</h2><ul><li>Smith J. No evidence of harm. Etkisi kanıtlanmadı. 2020.</li></ul>")
        assert bh.olumsuz_dil_kapisi(html, "tr") == []

    def test_bulgu_blok_html_tasir(self):
        html = "<p>Temiz cümle.</p><ul><li><strong>Etanol:</strong> sık kullanım önerilmez.</li></ul><h2>Kaynaklar</h2>"
        b = bh.olumsuz_dil_kapisi(html, "tr")
        assert len(b) == 1 and b[0]["blok"].startswith("<li>") and "önerilmez" in b[0]["blok"]

    def test_meta_ve_baslik_de_denetlenir(self):
        b = bh.olumsuz_dil_kapisi("<p>Temiz.</p>", "tr", ["Tonik gerekli değildir; işte nedenleri."])
        assert b and b[0]["blok"] is None

    def test_ceviri_dilleri(self):
        assert _olumsuz("There is no clinical evidence that a toner speeds this up.", "en")
        assert _olumsuz("Frequent use is not recommended for dry skin.", "en")
        assert not _olumsuz("Dry skin feels more comfortable with flower-water toners.", "en")
        assert _olumsuz("Die Wirkung ist nicht belegt.", "de")
        assert not _olumsuz("Trockene Haut fühlt sich mit Blütenwasser wohler an.", "de")
        assert _olumsuz("Эффективность не доказана.", "ru")
        assert _olumsuz("لا يوجد دليل سريري على ذلك.", "ar")


class GeoKapisi(unittest.TestCase):
    IYI = ("<p><strong>Kısa cevap:</strong> " + " ".join(["kelime"] * 40) + "</p>"
           "<h2>Tonik nedir?</h2><p>a</p><h2>Tonik nasıl kullanılır?</h2><p>b <a href=\"https://www.lcarlie.shop/post/x\">x</a> "
           "<a href=\"https://www.lcarlie.shop/product-page/calmaros\">CALMAROS</a></p><h2>Tonik ne zaman sürülür?</h2><p>c</p>"
           "<h2>Sık Sorulan Sorular</h2>" + "".join("<h3>Soru %d?</h3><p>Cevap %d.</p>" % (i, i) for i in range(4)) +
           "<h2>Kaynaklar</h2><ul><li>x</li></ul>")

    def test_iyi_yazi_gecer(self):
        r = bh.geo_kapisi(self.IYI, "Tonik Nedir? Nasıl Kullanılır", "m" * 150)
        assert r["sorun"] == [], r
        assert r["olcum"]["soru_h2"] == 3 and r["olcum"]["sss"] == 4 and r["olcum"]["urun_baglantisi"] == 1

    def test_kisa_cevap_soru_baslik_sss_ve_baglanti_ister(self):
        kotu = "<h2>Giriş</h2><p>uzun</p><h2>Kaynaklar</h2><ul><li>x</li></ul>"
        s = " | ".join(bh.geo_kapisi(kotu, "x" * 80, "kısa")["sorun"])
        for beklenen in ("kısa cevap", "soru biçimli H2", "SSS", "ilgili yazı bağlantısı", "SEO başlığı", "meta açıklama"):
            assert beklenen in s, (beklenen, s)

    def test_sss_govdeden_cikar_ve_sema_gorunen_metinle_ayni(self):
        s = bh.sss_cikar(self.IYI)
        assert [x["q"] for x in s] == ["Soru %d?" % i for i in range(4)] and s[0]["a"] == "Cevap 0"
        j = bh.faq_jsonld(s, "tr")
        assert j["@type"] == "FAQPage" and len(j["mainEntity"]) == 4
        # çeviride başlık metni farklıdır: aynı sıradaki H2 kullanılır
        en = self.IYI.replace("Sık Sorulan Sorular", "Frequently Asked Questions")
        assert bh.sss_cikar(en) == [] and len(bh.sss_cikar(en, bh.sss_sirasi(self.IYI))) == 4


class UrunKonuEslesmesi(unittest.TestCase):
    """Görseldeki ürün konu içeriğini İÇİNDEKİLER listesinde taşımak zorunda."""
    INCI = {"lipvora": "Simmondsia Chinensis Seed Oil, Butyrospermum Parkii Butter, Borago Officinalis Seed Oil",
            "calmaros": "Rosa Damascena Flower Water, Glycerin, Aqua",
            "babysoft": "Butyrospermum Parkii Butter, Borago Officinalis Seed Oil"}

    def _sec(self, ic, ambar=None):
        return bh.gorsel_urun_sec(ic, inci_dosya=self.INCI.get, inci_ambar=(ambar or {}).get, foto=lambda k: Path("/x"))

    def _ic(self, kesitler, baglantilar, anahtar="hodan yağı nedir"):
        return {"anahtar": anahtar, "slug": "hodan-yagi-nedir", "kesitler": kesitler,
                "html": "".join('<a href="https://www.lcarlie.shop/product-page/%s">x</a>' % b for b in baglantilar)}

    def test_icerigi_tasimayan_urun_gorselden_duser(self):
        r = self._sec(self._ic(["calmaros", "lipvora"], ["calmaros", "lipvora"]))
        assert r["urunler"] == ["lipvora"] and any("calmaros" in k and "yok" in k for k in r["kayit"])

    def test_govdede_baglantisi_olmayan_urun_gorsele_giremez(self):
        r = self._sec(self._ic(["lipvora", "babysoft"], ["babysoft"]))
        assert r["urunler"] == ["babysoft"] and any("lipvora" in k and "bağlantısı yok" in k for k in r["kayit"])

    def test_ambar_celisirse_urun_duser(self):
        r = self._sec(self._ic(["lipvora"], ["lipvora"]), ambar={"lipvora": "Cera Alba, Tocopherol"})
        assert r["urunler"] == [] and "çelişkili" in " ".join(r["kayit"])

    def test_hic_uygun_urun_yoksa_kapak_urunsuz(self):
        assert self._sec(self._ic(["calmaros"], ["calmaros"]))["urunler"] == []

    def test_konu_icerik_degilse_baglantili_urun_yeter(self):
        r = self._sec(self._ic(["calmaros"], ["calmaros"], anahtar="tonik nedir") | {"slug": "tonik-nedir-gerekli-mi"})
        assert r["urunler"] == ["calmaros"] and r["konu_bileseni"] is None

    def test_yazar_secmediyse_tek_urun(self):
        r = self._sec(self._ic([], ["babysoft", "lipvora"]))
        assert r["urunler"] == ["babysoft"]

    def test_slug_kesit_ve_konu_bileseni(self):
        assert bh.slug_kesit("sunacnea-30-spf") == "sunacnea" and bh.slug_kesit("femisia-for-women") == "femisia"
        assert bh.slug_kesit("baby-rescue") == "babyrescue" and bh.slug_kesit("calmjaw") == "caljaw"
        assert bh.konu_bileseni("HODAN YAĞI NEDİR") and bh.konu_bileseni("jojoba yağı ne işe yarar")
        assert bh.konu_bileseni("cilt bakım rutini sırası", "cilt-bakim-rutini-siralamasi") is None
        assert bh.konu_bileseni("süre ne kadar") is None, "'üre' kelime içinde eşleşmemeli"


class EtiketDenetimi(unittest.TestCase):
    def test_dogru_etiket_gecer(self):
        r = bh.etiket_okunuyor_mu({"L’CARLIE", "LIPVORA", "Rhett"}, "LIPVORA")
        assert r["gecti"] and r["marka"] and r["urun"]

    def test_bozuk_harf_red(self):
        assert not bh.etiket_okunuyor_mu({"L’CARLIE", "LIPVOKA"}, "LIPVORA")["gecti"]
        assert not bh.etiket_okunuyor_mu({"LCARUE", "CALMAROS"}, "CALMAROS")["gecti"]

    def test_iddia_sozcugu_tasiyan_etiket_red(self):
        r = bh.etiket_okunuyor_mu({"UCARLIE", "CALMAROS", "Redness", "Relief"}, "CALMAROS")
        assert r["marka"] and r["urun"] and not r["gecti"] and r["iddia_sozcugu"]


class GorunumHazirligi(unittest.TestCase):
    def test_tirnak_turkce_ve_dillere_gore(self):
        assert bh.tirnak_duzelt('<p>"pH dengeleme" L\'CARLIÉ\'nin pH\'ı</p>', "tr") == "<p>“pH dengeleme” L’CARLIÉ’nin pH’ı</p>"
        assert bh.tirnak_duzelt('<p>"a"</p>', "de") == "<p>„a“</p>" and bh.tirnak_duzelt('<p>"a"</p>', "ru") == "<p>«a»</p>"

    def test_tirnak_etiket_icine_dokunmaz_ve_blokta_sifirlanir(self):
        h = bh.tirnak_duzelt('<p><a href="https://x.y/a?b=\'c\'">"x</a></p><p>"y"</p>', "tr")
        assert 'href="https://x.y/a?b=\'c\'"' in h and h.endswith("<p>“y”</p>")

    def test_genis_tablo_listeye_doner_dar_tablo_kalir(self):
        genis = ("<table><thead><tr><th>Tür</th><th>İçerik</th><th>His</th><th>Kimler</th></tr></thead><tbody>"
                 "<tr><td>Çiçek suyu</td><td>Rosa</td><td>Ferah</td><td>Hassas</td></tr></tbody></table>")
        h = bh.tablo_duzenle(genis)
        assert "<table" not in h and h.startswith("<ul><li><strong>Çiçek suyu</strong>")
        assert "<em>İçerik:</em> Rosa" in h and "<em>Kimler:</em> Hassas" in h
        dar = "<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>"
        assert bh.tablo_duzenle(dar) == dar

    def test_tablo_telefona_sigar(self):
        doc = bh.html_to_ricos("<table><tr><th>A</th><th>B</th><th>C</th></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>")
        t = next(n for n in doc["nodes"] if n["type"] == "TABLE")
        assert sum(t["tableData"]["dimensions"]["colsMinWidth"]) <= 300
        assert all(isinstance(x, int) for x in t["tableData"]["dimensions"]["colsWidthRatio"])

    def test_baglanti_renkli_ve_alti_cizili(self):
        doc = bh.html_to_ricos('<p>bkz. <a href="https://www.lcarlie.shop/post/x">yazı</a></p>')
        dek = doc["nodes"][0]["nodes"][1]["textData"]["decorations"]
        tip = {d["type"] for d in dek}
        assert {"LINK", "COLOR", "UNDERLINE"} <= tip
        assert next(d for d in dek if d["type"] == "COLOR")["colorData"]["foreground"] == bh.LINK_RENK
        assert doc["nodes"][0]["nodes"][0]["textData"]["decorations"] == []

    def test_gorunum_hazirla_guncellendi_ve_urun_yonlendirmesi(self):
        import datetime as dt
        html = ('<p><strong>Kısa cevap:</strong> x.</p><h2>A?</h2><p><a href="https://www.lcarlie.shop/product-page/calmaros">'
                'CALMAROS</a> "tonik"</p><h2>Kaynaklar</h2><ul><li>k "x"</li></ul>')
        h = bh.gorunum_hazirla(html, "tr", dt.date(2026, 11, 28))
        assert h.index("Kısa cevap") < h.index("Güncellendi: 28 Kasım 2026") < h.index("<h2>A?")
        assert h.index("İlgili L’CARLIÉ ürünleri") < h.index("<h2>Kaynaklar")
        assert "“tonik”" in h and "Güncellendi" not in bh.gorunum_hazirla(html, "tr")
        assert "Updated: November 28, 2026" in bh.gorunum_hazirla(html, "en", dt.date(2026, 11, 28))

    def test_kapak_en_basta(self):
        doc = bh.html_to_ricos("<p>ilk</p><h2>a</h2><p>x</p><h2>b</h2><h2>c</h2>",
                               [{"id": "K", "width": 1500, "height": 1000, "alt": "k", "sonra_h2": 0},
                                {"id": "I", "width": 1200, "height": 800, "alt": "i", "sonra_h2": 3}])
        assert doc["nodes"][0]["type"] == "IMAGE" and doc["nodes"][0]["imageData"]["image"]["src"]["id"] == "K"
        sira = [n["imageData"]["image"]["src"]["id"] if n["type"] == "IMAGE" else
                ("H" if n["type"] == "HEADING" else "") for n in doc["nodes"]]
        sira = [x for x in sira if x]
        assert sira == ["K", "H", "H", "I", "H"], sira
        assert bh.ricos_denetle(doc) == []

class CeviriKelimeIciTuzagi(unittest.TestCase):
    """28.11 canlıda ölçüldü: Arapça 'ضار' (zararlı) kalıbı 'نضارة' (tazelik) içinde eşleşti,
    hodan yazısının Arapça çevirisi haksız yere düştü. İki yön de kilitli."""

    def test_arapca_tazelik_zararli_sayilmaz(self):
        assert not _olumsuz("وللحفاظ على نضارة الزيت مدة أطول، خزّنه في زجاجة داكنة.", "ar")
        assert not _olumsuz("يُضاف بصفته مضادًا للأكسدة للمحافظة على نضارة الزيوت.", "ar")

    def test_arapca_gercek_olumsuz_yakalanir(self):
        assert _olumsuz("هذا الزيت ضار بالبشرة.", "ar")
        assert _olumsuz("هذه مادة ضارة.", "ar")
        assert _olumsuz("هذه خرافة شائعة.", "ar")

    def test_almanca_unschaedlich_olumlu(self):
        assert not _olumsuz("Das Öl gilt als unschädlich für die Haut.", "de")
        assert _olumsuz("Das ist schädlich.", "de")

if __name__ == "__main__":
    unittest.main()
