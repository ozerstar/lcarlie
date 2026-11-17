# -*- coding: utf-8 -*-
"""Reklam bazlı görünüm (17.11.2026) — envanter, kreatif varyasyonları,
hedef kitle, yorum okuma ve panel raporu sözleşmesi.

Kilitlenenler:
  * kapalı/reddedilen reklam listede görünür ama satış (defter) hesabına girmez
  * okunamayan yorum kaynağı "0 yorum" değil OKUNAMADI + sebep
  * yorum METNİ panel raporuna (ve öneri modeline giden kanıta) girmez
  * Trendyol hedefli satış kampanyasında sonuç "ölçülemez"
  * dinamik kreatifin tüm metin/görsel/video varyasyonları ayrı ayrı gelir
  * varlık dosya adı sabit desen (yol geçişi yok)
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
from jarvis import meta_reklam_detay as md  # noqa: E402

TR = timezone(timedelta(hours=3))

DINAMIK = {
    "id": "c9", "name": "UGC", "object_type": "VIDEO",
    "effective_object_story_id": "1_2", "effective_instagram_media_id": "179",
    "instagram_permalink_url": "https://www.instagram.com/p/X/",
    "asset_feed_spec": {
        "videos": [{"video_id": "1838447927", "thumbnail_url": "https://cdn/a.jpg"},
                   {"video_id": "1408160477", "thumbnail_url": "https://cdn/b.jpg"}],
        "images": [{"hash": "abcdef12"}, {"hash": "abcdef12"}],
        "bodies": [{"text": "Metin bir"}, {"text": "Metin iki"}],
        "titles": [{"text": "Başlık"}], "descriptions": [{"text": "Açıklama"}],
        "link_urls": [{"website_url": "https://www.trendyol.com/l-carlie/femisia-p-1105914513"}],
        "call_to_action_types": ["SHOP_NOW"]},
    "object_story_spec": {"page_id": "1", "instagram_user_id": "178"},
}
KARUSEL = {
    "id": "c8", "object_story_spec": {"page_id": "1", "link_data": {
        "message": "Gövde", "link": "https://lcarlie.shop/x",
        "child_attachments": [{"name": "Kart 1", "image_hash": "aa11bb22", "link": "https://lcarlie.shop/1"},
                              {"name": "Kart 2", "video_id": "333", "picture": "https://cdn/p.jpg"}]}}}

ADSET = {"id": "S1", "name": "Set", "effective_status": "ACTIVE", "daily_budget": "0",
         "lifetime_budget": "125000", "start_time": "2026-11-18T09:00:00+0300",
         "end_time": "2026-12-02T23:59:00+0300", "optimization_goal": "OFFSITE_CONVERSIONS",
         "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
         "targeting": {"age_min": 18, "age_max": 65, "age_range": [25, 55], "genders": [2],
                       "geo_locations": {"countries": ["TR"], "cities": [{"name": "Ankara", "radius": 25}]},
                       "flexible_spec": [{"interests": [{"name": "Cilt bakımı"}]}],
                       "publisher_platforms": ["instagram"], "instagram_positions": ["story", "reels"],
                       "targeting_automation": {"advantage_audience": 1}}}


class Kreatif(unittest.TestCase):
    def test_dinamik_tum_varyasyonlar(self):
        k = md.kreatif_ozet(DINAMIK)
        self.assertEqual(k["govde"], ["Metin bir", "Metin iki"])
        self.assertEqual(k["tip"], "VIDEO")
        self.assertTrue(k["dinamik"])
        adlar = [v["ad"] for v in k["varliklar"]]
        self.assertEqual(adlar, ["v_1838447927", "v_1408160477", "i_abcdef12"])   # tekrar eden hash bir kez
        self.assertEqual(k["cta"], ["SHOP_NOW"])

    def test_karusel_kartlari(self):
        k = md.kreatif_ozet(KARUSEL)
        self.assertEqual(k["tip"], "KARUSEL")
        self.assertEqual([c["varlik"] for c in k["kartlar"]], ["i_aa11bb22", "v_333"])
        self.assertEqual(k["govde"], ["Gövde"])

    def test_hedef_kitle(self):
        kit = md.hedef_kitle_ozet(ADSET["targeting"])
        self.assertEqual(kit["yas"], "25–55")
        self.assertEqual(kit["cinsiyet"], "Kadın")
        self.assertIn("Ankara (+25 km)", kit["konum"])
        self.assertEqual(kit["ilgi"], ["Cilt bakımı"])
        self.assertTrue(kit["advantage_kitle"])
        self.assertFalse(kit["advantage_yerlesim"])
        self.assertEqual(kit["yerlesim"][0]["konumlar"], ["Hikâye", "Reels"])

    def test_omur_butce_kurus(self):
        e = md.envanter_satiri("1", {"id": "120", "effective_status": "ACTIVE", "adset": ADSET,
                                     "campaign": {"objective": "OUTCOME_SALES"}, "creative": DINAMIK})
        self.assertIsNone(e["adset"]["gunluk_butce"])          # "0" bütçe değil, yok
        self.assertEqual(e["adset"]["omur_butce"], 1250.0)


class Yorum(unittest.TestCase):
    def test_cevaplandi_bizden_yanita_bakar(self):
        ham = {"comments": {"data": [
            {"id": "y1", "text": "Fiyat?", "username": "musteri", "timestamp": "2026-11-16T10:00:00+0000",
             "replies": {"data": [{"id": "y2", "text": "Merhaba", "username": "Lcarlie.Official"}]}},
            {"id": "y3", "text": "Güzel", "username": "baska"}]}}
        ys = md.ig_yorumlari("m1", ham, "lcarlie.official")
        ust = {y["yorum_id"]: y for y in ys if not y["ust_yorum_id"]}
        self.assertTrue(ust["y1"]["cevaplandi"])
        self.assertFalse(ust["y3"]["cevaplandi"])
        yan = [y for y in ys if y["ust_yorum_id"]]
        self.assertTrue(yan[0]["bizden"])

    def test_fb_izin_hatasi_okunamadi_sifir_degil(self):
        reklam = {"id": "120", "effective_status": "ACTIVE", "adset": ADSET, "campaign": {},
                  "creative": DINAMIK}
        cagri = []

        def get(yol, sorgu, jeton):
            cagri.append(yol)
            if yol.endswith("/comments"):
                raise RuntimeError('HTTP 400: {"error":{"message":"(#10) This endpoint requires the '
                                   '\'pages_read_user_content\' permission"}}')
            if yol == "178":
                return {"username": "lcarlie"}
            return {"comments_count": 0, "like_count": 4, "comments": {"data": []}}

        d = md.topla("1", get, lambda yol, q: [reklam, dict(reklam, id="121")])
        e = d["envanter"][0]
        self.assertEqual(e["fb_yorum_durum"], "OKUNAMADI")
        self.assertIn("pages_read_user_content", e["fb_yorum_sebep"])
        self.assertEqual(e["ig_yorum_durum"], "OK")
        self.assertEqual(d["olcum"]["fb_okundu"], 0)
        # aynı gönderi bir kez sorulur
        self.assertEqual(sum(1 for c in cagri if c.endswith("/comments")), 2)  # iki jeton denemesi

    def test_hata_sebebi_jetonsuz(self):
        s = md.hata_sebebi(RuntimeError('HTTP 400: {"error":{"code":190,"message":"Invalid OAuth abcTOKEN"}}'))
        self.assertEqual(s, "jeton geçersiz/süresi dolmuş")


def _env(ad_id, durum="PAUSED", kreatif=None, yorum=0, cevapsiz=0, ig="OK"):
    return {"ad_id": ad_id, "ad_adi": "Kapalı reklam " + ad_id, "durum": durum, "adset_id": "S9",
            "adset_adi": "Set 9", "adset_durum": "ACTIVE", "kampanya_id": "K9", "kampanya_adi": "Kamp 9",
            "kampanya_durum": "ACTIVE", "kampanya_amaci": "OUTCOME_SALES", "hesap_id": "1301",
            "onizleme": "https://fb.me/x", "red_sebep": None, "sorunlar": None,
            "kampanya": {}, "adset": {"optimizasyon": "OFFSITE_CONVERSIONS", "kitle": {}},
            "kreatif": kreatif or md.kreatif_ozet(DINAMIK), "ig_baglanti": "https://www.instagram.com/p/X/",
            "ig_yorum_durum": ig, "ig_yorum_sebep": None, "fb_yorum_durum": "OKUNAMADI",
            "fb_yorum_sebep": "izin yok", "yorum_sayisi": yorum, "cevapsiz_yorum": cevapsiz,
            "olcum_at": "2026-11-17T05:00:00+03:00"}


def _rapor(envanter, reklam=None):
    v = {"okunamadi": [], "reklam": reklam or [], "son_durum": [], "kreatif": [], "an_gunluk": [],
         "yerlesim": [], "defter": [], "defter_gunluk": [], "defter_tazelik": [], "ekonomi": [
             {"urun_kod": "FEMISIA", "barkod": "8684869609127", "maliyet": 89.88, "maliyet_durum": "GIRILDI",
              "ty_komisyon": 19, "ty_fiyat": 2760, "wix_fiyat": 2400, "pos_yuzde": 5}],
         "uyari": [], "kosu": [], "oneri_kosu": [], "oneri": [], "envanter": envanter}
    b = date(2026, 11, 11)
    s = date(2026, 11, 17)
    return ry.rapor_kur(v, b, s, simdi=datetime(2026, 11, 17, 6, tzinfo=TR), etiket="7")


class PanelRaporu(unittest.TestCase):
    def test_kapali_reklam_listede_ama_defterde_degil(self):
        r = _rapor([_env("9001"), _env("9002", durum="DISAPPROVED")])
        self.assertEqual(r["ozet"]["reklam_sayisi"], 2)
        self.assertEqual(r["ozet"]["durum_sayim"]["kapali"], 1)
        self.assertEqual(r["ozet"]["durum_sayim"]["reddedildi"], 1)
        s = [x for x in r["reklamlar"] if x["ad_id"] == "9001"][0]
        self.assertFalse(s["aralikta_veri"])
        self.assertIsNone(s["defter"])
        self.assertEqual(r["ozet"]["hedef_siparis"], 0)
        self.assertEqual(s["kapali_neden"], "Reklamın kendisi kapalı")
        self.assertEqual(s["rozet"], "BILINMIYOR")
        red = [x for x in r["reklamlar"] if x["ad_id"] == "9002"][0]
        self.assertEqual(red["rozet"], "KES")
        self.assertEqual(red["durum_sinif"], "reddedildi")

    def test_trendyol_satis_sonucu_olculemez(self):
        s = _rapor([_env("9001", durum="ACTIVE")])["reklamlar"][0]
        self.assertIsNone(s["sonuc"]["deger"])
        self.assertIn("ölçülemez", s["sonuc"]["neden"])

    def test_varyasyonlar_ve_varlik_adlari(self):
        s = _rapor([_env("9001")])["reklamlar"][0]
        self.assertEqual(s["metinler"]["govde"], ["Metin bir", "Metin iki"])
        for v in s["varliklar"]:
            self.assertRegex(v["ad"], r"^[vi]_k?[0-9a-fA-F]{4,64}$")
            self.assertNotIn("kapak_kaynak", v)          # imzalı Meta adresi panele gitmez
        self.assertTrue(s["baglanti"]["ads_manager"].startswith("https://adsmanager.facebook.com/"))

    def test_yorum_metni_rapora_girmez(self):
        r = _rapor([_env("9001", yorum=3, cevapsiz=1)])
        metin = json.dumps(r, ensure_ascii=False, default=str)
        self.assertNotIn("kullanici", metin)
        self.assertEqual(r["ozet"]["yorum"], 3)
        self.assertEqual(r["ozet"]["cevapsiz_yorum"], 1)
        self.assertNotIn('"env"', metin)

    def test_planlanan_reklam(self):
        e = _env("9003", durum="ACTIVE")
        e["adset"]["baslangic"] = "2026-11-18T09:00:00+0300"
        s = _rapor([e])["reklamlar"][0]
        self.assertEqual(s["durum_sinif"], "planlandi")
        self.assertIn("18.11.2026 09:00", s["kapali_neden"])

    def test_platformlar_bagli_olmayani_sifir_yazmaz(self):
        p = {x["kod"]: x for x in _rapor([_env("9001")])["platformlar"]}
        self.assertEqual(p["meta"]["durum"], "BAGLI")
        for k in ("trendyol", "google", "hepsiburada", "n11", "idefix"):
            self.assertIsNone(p[k]["reklam"])
            self.assertTrue(p[k]["gereken"])


class OneriKaniti(unittest.TestCase):
    def test_kapali_reklam_modele_gitmez(self):
        spec = importlib.util.spec_from_file_location("ro", KOK / "scripts" / "reklam-oneri.py")
        ro = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ro)
        r = _rapor([_env("9001", yorum=2)])
        kanit = json.loads(ro.kanit_metni(r, None, None))
        self.assertEqual(kanit["reklamlar"], [])


class VarlikUcu(unittest.TestCase):
    def test_yol_gecisi_yok(self):
        app = (KOK / "webconsole" / "app.py").read_text(encoding="utf-8")
        self.assertIn(r're.fullmatch(r"[vi]_k?[0-9a-fA-F]{4,64}\.(mp4|jpg)", ad)', app)
        self.assertIn('"Accept-Ranges", "bytes"', app)
        for kotu in ("../etc/passwd", "v_..%2f.mp4", "v_123.mp4/../x", "x_123.mp4"):
            self.assertIsNone(re.fullmatch(r"[vi]_k?[0-9a-fA-F]{4,64}\.(mp4|jpg)", kotu))


if __name__ == "__main__":
    unittest.main()
