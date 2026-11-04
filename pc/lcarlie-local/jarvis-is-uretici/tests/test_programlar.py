"""Programlar (rakip/kreatif/b2b/retro) testleri: sahte model ve kaynaklar; sıfır dış çağrı."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.is_uretici import Departman, IsUretici, Kanit, Ortam, Uye  # noqa: E402
from jarvis.programlar import Programlar  # noqa: E402

SAAT = datetime(2026, 10, 26, 6, 30, tzinfo=timezone.utc)


class Defter:
    def __init__(self):
        self.works = {}

    def work(self, **kw):
        return self.works.setdefault(kw["source_key"], len(self.works) + 1)

    def apply(self, **kw):
        pass


def deps():
    u = lambda k: Uye(k, k, "iş")  # noqa: E731
    return [Departman("COMPETITOR_INT", "Rakip", "rakip", uyeler=[u("competitor_intelligence")]),
            Departman("CREATIVE", "Kreatif", "içerik", uyeler=[u("creative_director")]),
            Departman("PHARMACY", "Eczane", "eczane", uyeler=[u("eczane_uzmani")]),
            Departman("BRAND", "Marka", "marka", uyeler=[u("marka")])]


def model(m, kw):
    u = m[-1]["content"]
    if "arama" in u and "3 soru" in u:
        return {"sorular": ["La Roche-Posay 2026 campaign hooks Germany", "q2"], "reklam_anahtar_kelimesi": "baby skincare"}
    if "Rakip ve pazar istihbaratı sentezi" in u:
        return {"rakip_kartlari": [{"marka": "Mustela", "ne_yapiyor": "bebek bariyer", "nasil_one_cikiyor": "pediatrik", "kanit": ["K1"]},
                                   {"marka": "Uydurma", "ne_yapiyor": "?", "nasil_one_cikiyor": "?", "kanit": []}],
                "bizde_eksik": [{"baslik": "Pediatrist onaylı test anlatısı", "neden_onemli": "güven", "onem": 4, "kanit": ["K2"]}],
                "firsatlar": [{"baslik": "Bebek bariyer içerik serisi taslağı", "ilgili_departman": "CREATIVE", "tip": "TASLAK",
                               "cikti": "5 içerik", "kabul_olcutu": "5 taslak", "erisim": 8, "etki": 2, "guven": 0.8, "efor_gun": 4},
                              {"baslik": "Olmayan birime iş", "ilgili_departman": "YOK", "tip": "ANALIZ", "cikti": "x", "kabul_olcutu": "y"}],
                "yeni_arastirma_sorulari": ["Mustela Türkiye eczane kampanyası 2026"], "ozet": "AB'de pediatrik vurgu."}
    if "bilimsel kaynak arayacağız" in u:
        return {"odaklar": [{"konu": "seramid", "pubmed": "ceramide infant skin barrier", "web": "seramid bebek cildi"}]}
    if "Kreatif bilgi hattı" in u:
        kart = lambda b, k: {"baslik": b, "kanca": "Bebek cildi yetişkinden %30 ince.", "bilgi": "...", "neden_sasirtici": "...",  # noqa: E731
                             "kaynak": k, "urune_baglanti": "formülümüzde seramid bulunur", "format": "carousel",
                             "gorsel_brif": {"metafor": "tuğla duvar", "istem_en": "brick wall macro", "metin_katmani": ["1", "2"]}}
        return {"kartlar": [kart("Bebek cildi neden daha ince?", ["K2"]), kart("Çantada taşınır çünkü 5 ml", ["K2"]),
                            kart("Sadece ürün bilgisine dayanan", ["K1"])]}
    if "içerik kartını puanla" in u:
        if "Çantada" in u:
            return {"bilgi_degeri": 1, "kaynakla_tutarli": True, "mevzuat_sorunu": "", "karar": "REDDET", "gerekce": "bariz"}
        return {"bilgi_degeri": 5, "kaynakla_tutarli": True, "mevzuat_sorunu": "", "karar": "GECTI", "gerekce": "öğretici"}
    if "B2B eczane programı" in u:
        assert "05551234567" not in u and "AHMET" not in u, "kişi verisi modele gitmemeli"
        return {"il_onceligi": [{"il": "ISTANBUL", "neden": "en yoğun", "ilk_hedef_eczane": 50, "yontem": "depo"}],
                "gorevler": [{"baslik": "Eczanelere toplu e-posta gönder", "tip": "TASLAK", "cikti": "kampanya", "kabul_olcutu": "x"},
                             {"baslik": "Eczacı eğitim notu taslağı hazırla", "tip": "TASLAK", "cikti": "not", "kabul_olcutu": "1 sayfa"}],
                "ozet": "İstanbul önce."}
    if "Haftalık ekip retrosu" in u:
        return {"degerlendirme": "ok", "kok_neden": "veri eksik", "odak": "kaynak bağlantısı", "sahipten_istek": "GSC erişimi",
                "yeni_konular": ["Google Search Central yapılandırılmış veri rehberi 2026"]}
    raise AssertionError(u[:200])


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cagri, self.planlar = [], []
        self.o = Ortam(
            departmanlar=deps, uye_gorusleri=lambda d: [], arastirma_notlari=lambda k, g: [],
            uret=lambda m, **kw: (self.cagri.append((m, kw)) or {"text": json.dumps(model(m, kw), ensure_ascii=False), "provider": "sahte"}),
            defter=Defter(), durum_dizini=Path(self.tmp.name), saat=lambda: SAAT,
            grounded=lambda s: ("Mustela pediatrik bariyer kampanyası...", ["Mustela https://mustela.de/x"]),
            adlib=lambda k, u: [{"metin": "Ilk 3 saniye kanca", "marka": "Mustela", "gun_sayisi": 40, "ad_id": "1"}],
            urunler=lambda: [("BABY RESCUE", "İçindekiler: Aqua, Ceramide NP ...")],
            bilgi_dosyasi=lambda ad: "kural" if "iddia" in ad else "",
            pubmed=lambda q: [Kanit("", "pubmed:1 https://pubmed.ncbi.nlm.nih.gov/1/", "Infant skin is 30% thinner")],
            b2b_ozet=lambda: {"toplam_eczane": 29488, "il_ilk25": [{"il": "ISTANBUL", "eczane": 6292}]},
            b2b_liste=lambda: "/tmp/oncelik.csv",
            plan_ekle=lambda h, k, g: self.planlar.append((h, k)) or True)
        self.iu = IsUretici(self.o, gunluk_tavan=100)

    def tearDown(self):
        self.tmp.cleanup()

    def agac(self):
        return json.loads((Path(self.tmp.name) / "is-uretici" / "agac.json").read_text(encoding="utf-8"))

    def test_rakip(self):
        s = Programlar(self.iu).rakip()
        self.assertEqual(s["kart"], 1)            # kaynaksız kart atıldı
        self.assertEqual(s["gorev"], 2)           # olmayan birimin işi rakip istihbaratı birimine düşer
        g = self.agac()["departmanlar"]["CREATIVE"]["gorevler"][0]
        self.assertIn("RICE", g["neden"])
        self.assertEqual(len(self.agac()["departmanlar"]["COMPETITOR_INT"]["gorevler"]), 1)
        self.assertEqual(self.planlar[0][0], "COMPETITOR_INT")
        kart = json.loads((Path(self.tmp.name) / "programlar" / "rakip" / "kartlar.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(any("mustela.de" in k for k in kart["kaynaklar"]))
        self.assertEqual([kw["kademe"] for _, kw in self.cagri], ["hizli", "muhakeme"])

    def test_kreatif_hakem_sig_karti_reddeder(self):
        s = Programlar(self.iu).kreatif()
        self.assertEqual(s["aday"], 2)            # yalnız ürün bilgisine dayanan kart atıldı
        self.assertEqual(s["hakemden_gecen"], 1)  # "çantada taşınır" hakemden döndü
        self.assertEqual(s["gorsel_gorevi"], 1)
        g = self.agac()["departmanlar"]["CREATIVE"]["gorevler"][0]
        self.assertEqual(g["durum"], "ONAY_BEKLIYOR")   # görsel üretim onaysız başlamaz
        md = list((Path(self.tmp.name) / "programlar" / "kreatif" / "kartlar").glob("*.md"))[0].read_text(encoding="utf-8")
        self.assertIn("pubmed.ncbi.nlm.nih.gov", md)
        self.assertIn("tuğla duvar", md)
        hakem = [kw for _, kw in self.cagri if kw.get("is_anahtari") == "kreatif-hakem"]
        self.assertTrue(all(k["kademe"] == "hizli" for k in hakem))  # üretici muhakeme (Claude), hakem farklı aile

    def test_b2b_kisi_verisi_gitmez_ve_temas_onayda(self):
        s = Programlar(self.iu).b2b()
        self.assertEqual(s["gorev"], 2)
        g = self.agac()["departmanlar"]["PHARMACY"]["gorevler"]
        self.assertEqual(g[0]["durum"], "ONAY_BEKLIYOR")
        self.assertEqual(g[1]["durum"], "ACIK")

    def test_retro_konu_yazar_ve_odak_gunluge_akar(self):
        IsUretici(self.o, gunluk_tavan=100)
        Programlar(self.iu).rakip()                  # CREATIVE'de görev olsun
        s = Programlar(IsUretici(self.o, gunluk_tavan=100)).retro()
        self.assertGreaterEqual(s["rapor"], 1)
        self.assertIn(("CREATIVE", "Google Search Central yapılandırılmış veri rehberi 2026"), self.planlar)
        self.assertEqual(self.agac()["departmanlar"]["CREATIVE"]["retro"]["odak"], "kaynak bağlantısı")
        from jarvis.is_uretici import istem_gunluk
        msg = istem_gunluk(deps()[1], [], self.agac(), "2026-10-27")
        self.assertIn("kaynak bağlantısı", msg[1]["content"])

    def test_butce_tavani_aramayi_da_durdurur(self):
        iu = IsUretici(self.o, gunluk_tavan=1)
        s = Programlar(iu).calistir("rakip")
        self.assertIn("tavan", s["durdu"])


if __name__ == "__main__":
    unittest.main()
