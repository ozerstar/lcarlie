# -*- coding: utf-8 -*-
"""Reklam Yöneticisi (KAMPANYA sekmesi) — saf rapor işlevinin sözleşmesi.

Veritabanı yok: veri_oku'nun döndürdüğü biçimde uydurma satırlar verilir.
Kilitlenenler: Meta iddiası ile defter ayrı · pikselsiz hedefte "ölçülemez"
(0 değil) · okunamayan defter OKUNAMADI (0 değil) · katkı/başabaş uzman
tablosuyla aynı · reklam başlamadan önceki satış reklama yazılmaz · rozet ·
öneri kuralları · Türkçe sayı eki üretilmez.
"""
import importlib.util
import json
import re
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOK / "webconsole"))
sys.path.insert(0, str(KOK))

import reklam_yoneticisi as ry  # noqa: E402

TR = timezone(timedelta(hours=3))
BUGUN = date(2026, 11, 15)


def _reklam(gun, ad_id, harcama, link=100, gosterim=3000, an=0.0, durum="ACTIVE",
            adset="S1", kampanya="K1", ad="Reklam", opt="LINK_CLICKS", amac="LINK_CLICKS",
            satin_alma=0, deger=0.0, erisim=1500):
    return {"gun": gun, "hesap_id": "1", "kampanya_id": kampanya, "kampanya_adi": "Kampanya " + kampanya,
            "kampanya_amaci": amac, "adset_id": adset, "adset_adi": "Set " + adset, "optimizasyon": opt,
            "ad_id": ad_id, "ad_adi": ad, "durum": durum, "adset_durum": "ACTIVE",
            "kampanya_durum": "ACTIVE", "gunluk_butce": 300, "harcama": harcama, "gosterim": gosterim,
            "erisim": erisim, "frekans": 2.0, "tiklama": link + 10, "link_tiklama": link,
            "sepete_ekle": 0, "odeme_baslat": 0, "satin_alma": satin_alma, "satin_alma_degeri": deger,
            "mesaj_baslat": 0, "sayfa_goruntule": 0, "an_harcama": an, "olcum_at": "2026-11-15T16:00:00+03:00"}


EKONOMI = [
    {"urun_kod": "FEMISIA", "barkod": "8684869609127", "pazaryeri_barkod": "8684869609127",
     "maliyet": 89.88, "maliyet_durum": "GIRILDI", "ty_komisyon": 19, "idefix_komisyon": 10,
     "ty_fiyat": 2760, "wix_fiyat": 2400, "pos_yuzde": 5},
    {"urun_kod": "LUCIDERM", "barkod": "8684869609295", "pazaryeri_barkod": "8684869609295",
     "maliyet": 80.02, "maliyet_durum": "GIRILDI", "ty_komisyon": 19, "idefix_komisyon": 10,
     "ty_fiyat": 1247, "wix_fiyat": 1200, "pos_yuzde": 5},
    {"urun_kod": "KINESIS+", "barkod": "8684869609547", "pazaryeri_barkod": "8684869609547",
     "maliyet": 87.06, "maliyet_durum": "GIRILDI", "ty_komisyon": 19, "idefix_komisyon": 10,
     "ty_fiyat": 2457, "wix_fiyat": 1950, "pos_yuzde": 5},
    {"urun_kod": "DORSIVIA", "barkod": "8684869609400", "pazaryeri_barkod": None,
     "maliyet": None, "maliyet_durum": "VERI_YOK", "ty_komisyon": None, "idefix_komisyon": None,
     "ty_fiyat": None, "wix_fiyat": 2100, "pos_yuzde": 5},
]
KREATIF = [
    {"ad_id": "A1", "kreatif_id": "c1", "nesne_tipi": "SHARE", "video_id": None, "cta": "SHOP_NOW",
     "hedef_url": "https://www.trendyol.com/l-carlie/femisia-p-1105914513", "baslik": "FEMISIA",
     "govde": "Metin", "aciklama": None, "trendyol_barkod": "8684869609127"},
    {"ad_id": "A2", "kreatif_id": "c2", "nesne_tipi": "VIDEO", "video_id": "v2", "cta": "SHOP_NOW",
     "hedef_url": "https://www.trendyol.com/l-carlie/luciderm-p-1105914595", "baslik": "LUCIDERM",
     "govde": "Metin", "aciklama": None, "trendyol_barkod": "8684869609295"},
    {"ad_id": "A3", "kreatif_id": "c3", "nesne_tipi": "VIDEO", "video_id": "v3", "cta": "SHOP_NOW",
     "hedef_url": "https://kinesis.lcarlie.shop/?utm_source=meta", "baslik": "Formülü oku",
     "govde": "Metin", "aciklama": None, "trendyol_barkod": None},
]


def _veri(**ek):
    v = {
        "okunamadi": [],
        "reklam": [
            _reklam("2026-11-13", "A1", 600.0, link=600, an=320.0, ad="FEMISIA | Tek görsel", adset="S1"),
            _reklam("2026-11-14", "A1", 900.0, link=700, an=0.0, ad="FEMISIA | Tek görsel", adset="S1"),
            _reklam("2026-11-13", "A2", 300.0, link=150, ad="L'CARLIE LUCIDERM", adset="S2", kampanya="K2",
                    opt="LANDING_PAGE_VIEWS", amac="OUTCOME_SALES"),
            _reklam("2026-11-14", "A2", 200.0, link=100, ad="L'CARLIE LUCIDERM", adset="S2", kampanya="K2",
                    opt="LANDING_PAGE_VIEWS", amac="OUTCOME_SALES"),
            _reklam("2026-11-14", "A3", 400.0, link=80, ad="K+ 01", adset="S3", kampanya="K3",
                    satin_alma=3, deger=5850.0, amac="OUTCOME_SALES", opt="OFFSITE_CONVERSIONS"),
        ],
        "son_durum": [
            {"ad_id": "A1", "gun": "2026-11-14", "durum": "ACTIVE", "adset_durum": "ACTIVE",
             "kampanya_durum": "ACTIVE", "gunluk_butce": 300, "kampanya_amaci": "LINK_CLICKS",
             "optimizasyon": "LINK_CLICKS"},
            {"ad_id": "A2", "gun": "2026-11-14", "durum": "DISAPPROVED", "adset_durum": "ACTIVE",
             "kampanya_durum": "ACTIVE", "gunluk_butce": 200, "kampanya_amaci": "OUTCOME_SALES",
             "optimizasyon": "LANDING_PAGE_VIEWS"},
        ],
        "kreatif": KREATIF,
        "yerlesim": [
            {"ad_id": "A1", "yayinci": "audience_network", "konum": "an_classic", "harcama": 320,
             "gosterim": 40000, "tiklama": 500, "link_tiklama": 480, "sepete_ekle": 0, "satin_alma": 0},
            {"ad_id": "A1", "yayinci": "instagram", "konum": "instagram_reels", "harcama": 1180,
             "gosterim": 20000, "tiklama": 830, "link_tiklama": 820, "sepete_ekle": 0, "satin_alma": 0},
        ],
        "an_gunluk": [{"gun": "2026-11-14", "adset_id": "S1", "harcama": 320.0}],
        "defter": [
            # reklam başlamadan ÖNCE (12.11) -> sayılmamalı
            {"gun": "2026-11-12", "kanal": "trendyol", "barkod": "8684869609295", "kod": "LUCIDERM",
             "siparis": 1, "adet": 1, "ciro": 585.82},
            {"gun": "2026-11-14", "kanal": "trendyol", "barkod": "8684869609295", "kod": "LUCIDERM",
             "siparis": 1, "adet": 1, "ciro": 580.82},
            {"gun": "2026-11-14", "kanal": "wix", "barkod": "8684869609547", "kod": "KINESIS+",
             "siparis": 1, "adet": 1, "ciro": 1950.0},
        ],
        "defter_gunluk": [
            {"gun": "2026-11-12", "kanal": "trendyol", "siparis": 1, "ciro": 585.82},
            {"gun": "2026-11-14", "kanal": "trendyol", "siparis": 1, "ciro": 580.82},
            {"gun": "2026-11-14", "kanal": "wix", "siparis": 1, "ciro": 1950.0},
        ],
        "defter_tazelik": [{"son_olcum": "2026-11-15T16:40:00+03:00", "siparis_kaydi": 22}],
        "ekonomi": EKONOMI,
        "uyari": [{"anahtar": "x", "kural": "AN", "seviye": "KRITIK", "metin": "AN harcaması",
                   "oneri": "kapat", "veri": {}, "ilk_at": "2026-11-15T10:00:00+03:00",
                   "son_at": "2026-11-15T16:00:00+03:00"}],
        "kosu": [{"id": 5, "bas_at": "2026-11-15T16:12:20+03:00", "bit_at": "2026-11-15T16:12:23+03:00",
                  "durum": "TAMAM", "hata": None}],
        "oneri_kosu": [], "oneri": [],
    }
    v.update(ek)
    return v


def _rapor(v=None, bas=date(2026, 11, 9), bit=BUGUN):
    return ry.rapor_kur(v or _veri(), bas, bit, simdi=datetime(2026, 11, 15, 17, 0, tzinfo=TR),
                        etiket="test")


def _satir(r, aid):
    return next(s for s in r["reklamlar"] if s["ad_id"] == aid)


class Ekonomi(unittest.TestCase):
    def test_katki_ve_basabas_uzman_tablosuyla_ayni(self):
        # L-CARLIE-ozel-durum.md §6: FEMISIA TY 2760 -> K 1593,06, başabaş 1,73;
        # Wix 2400 -> K 1697,46, başabaş 1,41
        e = ry.urun_ekonomi(EKONOMI[0])
        self.assertAlmostEqual(e["kanallar"]["trendyol"]["katki"], 1593.06, places=2)
        self.assertAlmostEqual(e["kanallar"]["trendyol"]["basabas_roas"], 1.73, places=2)
        self.assertAlmostEqual(e["kanallar"]["wix"]["katki"], 1697.46, places=2)
        self.assertAlmostEqual(e["kanallar"]["wix"]["basabas_roas"], 1.41, places=2)

    def test_maliyeti_bilinmeyen_urunde_katki_uydurulmaz(self):
        e = ry.urun_ekonomi(EKONOMI[3])
        self.assertIsNone(e["maliyet"])
        self.assertIsNone(e["kanallar"]["wix"]["katki"])
        self.assertEqual(e["kanallar"]["wix"]["eksik"], "maliyet yok")

    def test_komisyon_kaydi_yoksa_yuzde_19_ve_not(self):
        x = dict(EKONOMI[0], ty_komisyon=None)
        e = ry.urun_ekonomi(x)
        self.assertEqual(e["kanallar"]["trendyol"]["komisyon"], 19.0)
        self.assertIn("varsayıldı", e["kanallar"]["trendyol"]["not"])


class MetaVeDefterAyri(unittest.TestCase):
    def test_trendyol_hedefinde_meta_olculemez_sifir_degil(self):
        r = _rapor()
        a1 = _satir(r, "A1")
        self.assertEqual(a1["hedef"], "trendyol")
        self.assertFalse(a1["meta_olculur"])
        # site hedefli (A3) Meta'nın iddiası özet kartına girer, Trendyol'unki girmez
        self.assertEqual(r["ozet"]["meta_satin_alma"], 3)
        self.assertEqual(r["ozet"]["meta_satin_alma_degeri"], 5850.0)
        self.assertEqual(r["ozet"]["meta_olculemeyen_harcama"], 2000.0)

    def test_hic_site_reklami_yoksa_meta_satin_alma_None(self):
        v = _veri()
        v["reklam"] = [x for x in v["reklam"] if x["ad_id"] != "A3"]
        r = _rapor(v)
        self.assertIsNone(r["ozet"]["meta_satin_alma"])

    def test_meta_iddiasi_deftere_karismaz(self):
        a3 = _satir(_rapor(), "A3")
        self.assertEqual(a3["m"]["satin_alma_degeri"], 5850.0)
        self.assertEqual(a3["defter"]["ciro"], 1950.0)       # defter: Wix'teki gerçek sipariş
        self.assertEqual(a3["defter"]["siparis"], 1)

    def test_defter_okunamazsa_OKUNAMADI_sifir_degil(self):
        v = _veri(defter=None, okunamadi=[{"parca": "defter", "sebep": "x"}])
        r = _rapor(v)
        self.assertEqual(_satir(r, "A1")["defter"]["durum"], "OKUNAMADI")
        self.assertIsNone(r["ozet"]["hedef_siparis"])
        self.assertEqual(r["ozet"]["defter_durum"], "OKUNAMADI")
        self.assertEqual(_satir(r, "A1")["rozet"], "BILINMIYOR")

    def test_reklam_baslamadan_onceki_satis_sayilmaz(self):
        # LUCIDERM reklamı 13.11'de başladı; 12.11 siparişi yazılmamalı
        d = _satir(_rapor(), "A2")["defter"]
        self.assertEqual(d["siparis"], 1)
        self.assertAlmostEqual(d["ciro"], 580.82)

    def test_siparis_katkisi_odenen_tutardan(self):
        d = _satir(_rapor(), "A2")["defter"]
        beklenen = 580.82 / 1.2 - 0.19 * 580.82 - 80.02 - 92.66
        self.assertAlmostEqual(d["katki"], round(beklenen, 2), places=2)
        self.assertAlmostEqual(d["sonuc"], round(beklenen - 500.0, 2), places=2)


class Rozet(unittest.TestCase):
    def test_reddedilen_reklam_KES(self):
        a2 = _satir(_rapor(), "A2")
        self.assertEqual(a2["rozet"], "KES")
        self.assertIn("reddedildi", a2["rozet_neden"])

    def test_bir_siparis_katkisi_kadar_harcama_ve_sifir_siparis_KES(self):
        v = _veri()
        for x in v["reklam"]:
            if x["ad_id"] == "A1":
                x["harcama"] = 900.0      # toplam 1800 > 1593 (1 siparişin katkısı)
        a1 = _satir(_rapor(v), "A1")
        self.assertEqual(a1["rozet"], "KES")

    def test_az_harcamada_IZLE(self):
        v = _veri()
        v["reklam"] = [x for x in v["reklam"] if x["ad_id"] == "A1"][:1]
        v["reklam"][0]["link_tiklama"] = 100
        a1 = _satir(_rapor(v), "A1")
        self.assertEqual(a1["rozet"], "IZLE")

    def test_basabas_ustu_IYI(self):
        v = _veri()
        v["defter"].append({"gun": "2026-11-14", "kanal": "trendyol", "barkod": "8684869609127",
                            "kod": "FEMISIA", "siparis": 2, "adet": 2, "ciro": 5520.0})
        a1 = _satir(_rapor(v), "A1")
        self.assertEqual(a1["rozet"], "IYI")

    def test_hedef_satis_degilse_BILINMIYOR(self):
        v = _veri()
        v["kreatif"] = [dict(KREATIF[0], hedef_url="https://www.instagram.com/lcarlie", trendyol_barkod=None)]
        a1 = _satir(_rapor(v), "A1")
        self.assertEqual(a1["rozet"], "BILINMIYOR")


class Duzeyler(unittest.TestCase):
    def test_kampanya_set_yerlesim(self):
        r = _rapor()
        self.assertEqual({k["id"] for k in r["kampanyalar"]}, {"K1", "K2", "K3"})
        self.assertEqual({s["id"] for s in r["setler"]}, {"S1", "S2", "S3"})
        an = [y for y in r["yerlesim"] if y["an"]]
        self.assertEqual(len(an), 1)
        self.assertEqual(r["ozet"]["an_harcama"], 320.0)

    def test_trend_30_gun_ve_secili_isaret(self):
        r = _rapor(bas=date(2026, 11, 14), bit=BUGUN)
        self.assertEqual(len(r["trend"]), 30)
        self.assertEqual([t["gun"] for t in r["trend"] if t["secili"]], ["2026-11-14", "2026-11-15"])
        g = next(t for t in r["trend"] if t["gun"] == "2026-11-14")
        self.assertEqual(g["harcama"], 1500.0)
        self.assertAlmostEqual(g["ciro"], 2530.82)

    def test_cok_gunde_erisim_tekil_degil(self):
        self.assertFalse(_satir(_rapor(), "A1")["m"]["erisim_tekil"])
        r1 = _rapor(bas=date(2026, 11, 14), bit=date(2026, 11, 14))
        self.assertTrue(_satir(r1, "A1")["m"]["erisim_tekil"])


class Oneriler(unittest.TestCase):
    def test_kural_onerileri_ve_ne_yapmaliyim(self):
        r = _rapor()
        kurallar = {o["anahtar"].split(":")[0] for o in r["oneriler"]}
        self.assertIn("an", kurallar)       # AN payı %16 > %10
        self.assertIn("ret", kurallar)
        self.assertIn("optim", kurallar)    # satış kampanyası LPV'ye, Trendyol linki
        self.assertEqual(r["ne_yapmaliyim"]["kaynak"], "KURAL")
        self.assertEqual(len(r["ne_yapmaliyim"]["maddeler"]), 3)
        for o in r["oneriler"]:
            for alan in ("ne", "neden", "beklenen_etki", "risk", "geri_alma", "olcum"):
                self.assertTrue(o[alan], (o["anahtar"], alan))

    def test_AN_karari_son_iki_gune_bakar(self):
        # 15.11 #179: AN 13.11'de kapatılmıştı, 7 günlük toplam bayat öneri üretti.
        v = _veri(an_gunluk=[{"gun": "2026-11-12", "adset_id": "S1", "harcama": 320.0}])
        r = _rapor(v)
        self.assertNotIn("an", {o["anahtar"].split(":")[0] for o in r["oneriler"]})
        a1 = _satir(r, "A1")
        self.assertEqual(a1["an_not"], "AN şimdi kapalı · son AN harcaması 12.11")
        self.assertEqual(r["ozet"]["an_son2_harcama"], 0)
        self.assertEqual(r["ozet"]["an_son_gun"], "2026-11-12")
        self.assertIn("Audience Network %21 (aralık toplamı)", a1["isaretler"])
        # aralık bugünü içermiyorsa not yok
        self.assertIsNone(_satir(_rapor(v, bit=date(2026, 11, 14)), "A1")["an_not"])

    def test_toplu_kes_anahtari_siradan_bagimsiz(self):
        # 15.11 #185: ürün sırası harcamaya göre değişince aynı öneri yeniden kuyruğa düştü.
        o = ry._oneri("META_MEDIA", "URUN", ",".join(sorted(["VIREON", "FEMISIA"])), "", 1,
                      "x", "y", "", "", "", "", True, "kes-toplu", "")
        self.assertEqual(o["anahtar"], "kes-toplu:FEMISIA,VIREON")

    def test_tek_gunde_MER_kurali_calismaz(self):
        r = _rapor(bas=BUGUN - timedelta(days=1), bit=BUGUN - timedelta(days=1))
        self.assertNotIn("mer", {o["anahtar"].split(":")[0] for o in r["oneriler"]})

    def test_uzman_kosusu_varsa_onun_ozeti(self):
        v = _veri(oneri_kosu=[{"id": 1, "bit_at": "2026-11-15T09:30:00+03:00", "tetik": "ZAMANLI",
                               "durum": "TAMAM", "model": "gemini", "ozet": ["A", "B", "C"]}],
                  oneri=[{"departman": "META_MEDIA", "kapsam": "HESAP", "hedef_id": "hesap", "ne": "x",
                          "neden": "y", "oncelik": 1, "onay_gerekir": True, "kaynak": "MODEL"}])
        r = _rapor(v)
        self.assertEqual(r["ne_yapmaliyim"]["maddeler"], ["A", "B", "C"])
        self.assertEqual(r["ne_yapmaliyim"]["kaynak"], "UZMAN")
        self.assertEqual(len(r["oneriler"]), 1)

    def test_turkce_sayi_eki_uretilmez(self):
        # "%32'ı" gibi ek kodda üretilemez (panel-premium dersi); cümle ek almadan kurulur.
        # Sabit tarih yazımı ("11.11'de") elle yazılmış metindir, üretilmiş ek değil.
        metin = json.dumps(_rapor(), ensure_ascii=False).replace("11.11'de", "")
        self.assertIsNone(re.search(r"\d'(ı|i|u|ü|si|sı|su|sü|e|a|de|da)\b", metin))

    def test_ondalik_turkce(self):
        a2 = _satir(_rapor(), "A1")
        self.assertNotRegex(a2["rozet_neden"], r"\d\.\d\d\b")


class Aralik(unittest.TestCase):
    def test_araliklar(self):
        self.assertEqual(ry.aralik_coz("bugun", bugun=BUGUN)[:2], (BUGUN, BUGUN))
        self.assertEqual(ry.aralik_coz("dun", bugun=BUGUN)[0], date(2026, 11, 14))
        self.assertEqual(ry.aralik_coz("30", bugun=BUGUN)[0], date(2026, 10, 17))
        self.assertEqual(ry.aralik_coz("bozuk", bugun=BUGUN)[0], date(2026, 11, 9))
        b, s, _ = ry.aralik_coz("ozel", "2026-11-20", "2026-11-01", bugun=BUGUN)
        self.assertEqual((b, s), (date(2026, 11, 1), BUGUN))   # ters çevrilir, bugünden ileri gidilmez

    def test_hedef_kanal(self):
        self.assertEqual(ry.hedef_kanal("https://www.trendyol.com/x-p-1"), "trendyol")
        self.assertEqual(ry.hedef_kanal("https://kinesis.lcarlie.shop/?a"), "site")
        self.assertEqual(ry.hedef_kanal("https://wa.me/90"), "mesaj")
        self.assertEqual(ry.hedef_kanal("https://www.instagram.com/x"), "profil")


class OneriBetigi(unittest.TestCase):
    """scripts/reklam-oneri.py: sayı kapısı ve onay anahtarı."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("reklam_oneri", KOK / "scripts" / "reklam-oneri.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def test_sayi_kapisi(self):
        kanit = self.m._sayilar('{"harcama": 1492.32, "roas": 0.49, "siparis": 3}')
        self.assertEqual(self.m.dogrulanmayan("1.492 TL harcandı, ROAS 0,49, 3 sipariş, %20 artır", kanit), [])
        self.assertEqual(self.m.dogrulanmayan("Bütçeyi 4.000 TL yap", kanit), ["4.000"])
        self.assertEqual(self.m.dogrulanmayan("ROAS 2,75 olur", kanit), ["2,75"])

    def test_onay_anahtari_bicimi(self):
        a = self.m._anahtar({"anahtar": "kes-toplu:FEMISIA,KINESIS+,VIREON"}, "2026w46")
        self.assertRegex(a, r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,120}$")
        uzun = self.m._anahtar({"anahtar": "optim:" + ",".join(["120255736682610045"] * 8)}, "2026w46")
        self.assertRegex(uzun, r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,120}$")

    def test_onay_metni_hicbir_sey_degismez_der(self):
        o = {"departman": "META_MEDIA", "ne": "x", "neden": "y"}
        self.assertIn("DEĞİŞTİRMEZ", self.m.onay_metni(o))


class UzmanBaglantisi(unittest.TestCase):
    def test_iki_departman_istemli(self):
        from jarvis import reklam_uzman as ru
        for kod in ("META_MEDIA", "MARKETPLACE"):
            ist = ru.istem(kod)
            self.assertTrue(ist and len(ist) > 5000, kod)
            self.assertIn("Öneri formatı", ist)
            self.assertTrue(ru.karar_kurallari(kod), kod)
        self.assertIsNone(ru.istem("SEO"))

    def test_bolum_cikarma(self):
        from jarvis import reklam_uzman as ru
        md = "# A\n## 1. x\nbir\n## 3. Veri\nuc\n### 3.1 alt\nalt\n## 4. y\ndort\n"
        self.assertEqual(ru.bolumler(md, ("## 3.",)), "## 3. Veri\nuc\n### 3.1 alt\nalt")


if __name__ == "__main__":
    unittest.main()
