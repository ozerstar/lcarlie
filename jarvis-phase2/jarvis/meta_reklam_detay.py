# -*- coding: utf-8 -*-
"""META REKLAM DETAYI — reklam bazlı envanter + yorum (17.11.2026).

Sahip 17.11.2026: *"hangi reklam hangisi kapalı, başarılı olanlar olmayanlar,
özellikler, açıklamalar ne tür bilgi varsa reklam bazlı görmek istiyorum; o
reklamları da görmek istiyorum, yorumları da görmek istiyorum."*

scripts/meta-reklam-izle.py her saat (:12) bu modülle:
  1. hesaptaki TÜM reklamları (kapalı/reddedilen dahil) okur: durum, red
     sebebi, kampanya/set ayarları, hedef kitle, kreatif (tüm varyasyonlar)
     -> raw.meta_reklam_envanter
  2. reklam gönderisinin yorumlarını okur -> raw.meta_reklam_yorum
     Instagram: effective_instagram_media_id /comments (+ yanıtlar)
     Facebook : effective_object_story_id /comments
     Okunamayan kaynak "yorum yok" DEĞİLDİR: durum OKUNAMADI + sebep yazılır.

🔴 YALNIZ GET. Meta'da hiçbir şey değişmez; yoruma cevap yazılmaz.
🔴 Yorumda müşteri adı/metni var: bu modül onları LOG'A YAZMAZ (yalnız
   sayı basar) ve öneri modeline giden kanıta girmez (panel ayrı uçtan okur).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Callable

# ------------------------------------------------------------------ alanlar
REKLAM_ALAN = (
    "id,name,status,configured_status,effective_status,created_time,updated_time,"
    "ad_review_feedback,issues_info,preview_shareable_link,"
    "adset{id,name,effective_status,daily_budget,lifetime_budget,start_time,end_time,"
    "optimization_goal,billing_event,bid_strategy,targeting,destination_type},"
    "campaign{id,name,objective,effective_status,daily_budget,lifetime_budget,"
    "start_time,stop_time,buying_type},"
    "creative{id,name,object_type,title,body,call_to_action_type,image_url,image_hash,"
    "thumbnail_url,video_id,effective_object_story_id,effective_instagram_media_id,"
    "instagram_permalink_url,object_story_spec,asset_feed_spec,link_url}")

IG_YORUM_ALAN = ("comments_count,like_count,comments.limit(100){id,timestamp,text,like_count,"
                 "username,replies.limit(50){id,timestamp,text,username,like_count}}")
FB_YORUM_ALAN = "id,created_time,message,like_count,comment_count,from{id,name},comments.limit(50){id,created_time,message,like_count,from{id,name}}"

DURUM_SINIF = {
    "ACTIVE": "acik",
    "PAUSED": "kapali", "ADSET_PAUSED": "kapali", "CAMPAIGN_PAUSED": "kapali",
    "ARCHIVED": "kapali", "DELETED": "kapali", "CAMPAIGN_GROUP_PAUSED": "kapali",
    "DISAPPROVED": "reddedildi", "WITH_ISSUES": "reddedildi",
    "PENDING_REVIEW": "inceleniyor", "IN_PROCESS": "inceleniyor", "PREAPPROVED": "inceleniyor",
    "PENDING_BILLING_INFO": "inceleniyor",
}
KAPALI_SEVIYE = {"PAUSED": "Reklam kapalı", "ADSET_PAUSED": "Reklam seti kapalı",
                 "CAMPAIGN_PAUSED": "Kampanya kapalı", "ARCHIVED": "Arşivde", "DELETED": "Silindi"}

CINSIYET = {1: "Erkek", 2: "Kadın"}
YAYINCI = {"facebook": "Facebook", "instagram": "Instagram", "audience_network": "Audience Network",
           "messenger": "Messenger", "threads": "Threads", "whatsapp": "WhatsApp"}
KONUM = {"feed": "Akış", "stream": "Akış", "story": "Hikâye", "reels": "Reels", "explore": "Keşfet",
         "explore_home": "Keşfet ana", "profile_feed": "Profil akışı", "ig_search": "Arama",
         "profile_reels": "Profil Reels", "facebook_reels": "Reels", "facebook_reels_overlay": "Reels katmanı",
         "marketplace": "Marketplace", "video_feeds": "Video akışı", "right_hand_column": "Sağ sütun",
         "instream_video": "Video içi", "search": "Arama", "messenger_home": "Gelen kutusu",
         "sponsored_messages": "Sponsorlu mesaj", "classic": "Uygulama içi (klasik)",
         "rewarded_video": "Ödüllü video", "notification": "Bildirim"}
KONUM_TIP = {"location_types": None}


def _kurus(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v / 100.0, 2) if v > 0 else None


def _benzersiz(liste):
    out = []
    for x in liste:
        if x and x not in out:
            out.append(x)
    return out


# ------------------------------------------------------------------ kreatif
def kreatif_ozet(cr: dict | None) -> dict:
    """Kreatifin TÜM metin varyasyonları + varlıklar (görsel/video/kart).
    Varlık adları yerel önbellek dosya adıdır (v_<video_id>, i_<hash>);
    'kaynak' alanı yalnız önbelleği dolduran betik içindir (imzalı, süreli
    Meta adresi), panele gönderilmez."""
    cr = cr or {}
    afs = cr.get("asset_feed_spec") or {}
    oss = cr.get("object_story_spec") or {}
    ld = oss.get("link_data") or {}
    vd = oss.get("video_data") or {}
    govde = _benzersiz([cr.get("body"), ld.get("message"), vd.get("message")]
                       + [b.get("text") for b in afs.get("bodies") or []])
    baslik = _benzersiz([cr.get("title"), ld.get("name"), vd.get("title")]
                        + [t.get("text") for t in afs.get("titles") or []])
    aciklama = _benzersiz([ld.get("description"), vd.get("link_description")]
                          + [d.get("text") for d in afs.get("descriptions") or []])
    cta_l = _benzersiz([cr.get("call_to_action_type"), (ld.get("call_to_action") or {}).get("type"),
                        (vd.get("call_to_action") or {}).get("type")]
                       + list(afs.get("call_to_action_types") or [])
                       + [(c or {}).get("type") for c in afs.get("call_to_actions") or []])
    url = _benzersiz([ld.get("link"), cr.get("link_url"),
                      ((vd.get("call_to_action") or {}).get("value") or {}).get("link"),
                      ((ld.get("call_to_action") or {}).get("value") or {}).get("link")]
                     + [u.get("website_url") for u in afs.get("link_urls") or []])
    varlik: list[dict] = []

    def ekle(v):
        if v["ad"] not in {x["ad"] for x in varlik}:
            varlik.append(v)

    for v in afs.get("videos") or []:
        if v.get("video_id"):
            ekle({"tur": "video", "ad": "v_%s" % v["video_id"], "video_id": str(v["video_id"]),
                  "kapak_kaynak": v.get("thumbnail_url")})
    if cr.get("video_id") or vd.get("video_id"):
        vid = str(cr.get("video_id") or vd.get("video_id"))
        ekle({"tur": "video", "ad": "v_%s" % vid, "video_id": vid,
              "kapak_kaynak": vd.get("image_url") or cr.get("thumbnail_url")})
    for g in afs.get("images") or []:
        if g.get("hash"):
            ekle({"tur": "gorsel", "ad": "i_%s" % g["hash"], "hash": g["hash"]})
    kartlar = []
    for i, k in enumerate(ld.get("child_attachments") or []):
        ad = None
        if k.get("video_id"):
            ad = "v_%s" % k["video_id"]
            ekle({"tur": "video", "ad": ad, "video_id": str(k["video_id"]), "kapak_kaynak": k.get("picture")})
        elif k.get("image_hash"):
            ad = "i_%s" % k["image_hash"]
            ekle({"tur": "gorsel", "ad": ad, "hash": k["image_hash"]})
        kartlar.append({"sira": i + 1, "baslik": k.get("name") or "", "aciklama": k.get("description") or "",
                        "hedef_url": k.get("link") or "", "varlik": ad})
    if not varlik:
        h = cr.get("image_hash") or ld.get("image_hash")
        if h:
            ekle({"tur": "gorsel", "ad": "i_%s" % h, "hash": h, "kaynak": cr.get("image_url")})
        elif cr.get("id") and (cr.get("image_url") or ld.get("picture") or cr.get("thumbnail_url")):
            ekle({"tur": "gorsel", "ad": "i_k%s" % cr["id"],
                  "kaynak": cr.get("image_url") or ld.get("picture") or cr.get("thumbnail_url")})
    tip = "KARUSEL" if kartlar else ("VIDEO" if any(v["tur"] == "video" for v in varlik) else "GORSEL")
    return {"kreatif_id": cr.get("id"), "kreatif_adi": cr.get("name") or "", "tip": tip,
            "dinamik": bool(afs), "govde": govde, "baslik": baslik, "aciklama": aciklama,
            "cta": [c for c in cta_l if c], "hedef_url": url, "varliklar": varlik, "kartlar": kartlar,
            "ig_baglanti": cr.get("instagram_permalink_url") or ""}


# ------------------------------------------------------------------ kitle
def hedef_kitle_ozet(t: dict | None) -> dict:
    t = t or {}
    yas_min, yas_max = t.get("age_min"), t.get("age_max")
    ar = t.get("age_range")
    if isinstance(ar, list) and len(ar) == 2:
        yas_min, yas_max = ar
    geo = t.get("geo_locations") or {}
    konum = list(geo.get("countries") or [])
    for anahtar in ("regions", "cities", "zips", "custom_locations", "places"):
        for x in geo.get(anahtar) or []:
            ad = x.get("name") or x.get("key") or x.get("address_string")
            if ad:
                yar = (" (+%s km)" % x["radius"]) if x.get("radius") else ""
                konum.append(str(ad) + yar)
    haric = [x.get("name") for k in ("regions", "cities") for x in (t.get("excluded_geo_locations") or {}).get(k) or []]
    ilgi = []
    for fs in t.get("flexible_spec") or []:
        for k in ("interests", "behaviors", "life_events", "family_statuses", "industries",
                  "work_positions", "education_statuses", "income"):
            ilgi += [x.get("name") for x in fs.get(k) or [] if x.get("name")]
    for k in ("interests", "behaviors"):
        ilgi += [x.get("name") for x in t.get(k) or [] if x.get("name")]
    haric_ilgi = [x.get("name") for k in ("interests", "behaviors")
                  for x in (t.get("exclusions") or {}).get(k) or [] if x.get("name")]
    ozel = [x.get("name") or x.get("id") for x in t.get("custom_audiences") or []]
    ozel_haric = [x.get("name") or x.get("id") for x in t.get("excluded_custom_audiences") or []]
    ta = t.get("targeting_automation") or {}
    yay = t.get("publisher_platforms")
    yerlesim = []
    if yay:
        for y in yay:
            pos = t.get("%s_positions" % ("facebook" if y == "facebook" else y)) or []
            if y == "audience_network":
                pos = t.get("audience_network_positions") or []
            if y == "messenger":
                pos = t.get("messenger_positions") or []
            yerlesim.append({"yayinci": YAYINCI.get(y, y),
                             "konumlar": [KONUM.get(p, p.replace("_", " ")) for p in pos] or ["tümü"]})
    cinsiyet = [CINSIYET.get(g, str(g)) for g in t.get("genders") or []]
    return {
        "yas": "%s–%s%s" % (yas_min or 18, yas_max or 65, "+" if (yas_max or 65) >= 65 else ""),
        "cinsiyet": ", ".join(cinsiyet) if cinsiyet else "Tümü",
        "konum": konum or ["—"], "haric_konum": [h for h in haric if h],
        "ilgi": _benzersiz(ilgi), "haric_ilgi": _benzersiz(haric_ilgi),
        "ozel_kitle": [o for o in ozel if o], "haric_ozel_kitle": [o for o in ozel_haric if o],
        "advantage_kitle": bool(ta.get("advantage_audience")),
        "advantage_yerlesim": not yay,
        "yerlesim": yerlesim,
        "cihaz": t.get("device_platforms") or [],
    }


# ------------------------------------------------------------------ envanter
def envanter_satiri(hid: str, a: dict) -> dict:
    cr = a.get("creative") or {}
    s = a.get("adset") or {}
    k = a.get("campaign") or {}
    red = a.get("ad_review_feedback") or None
    sorun = [{"ozet": i.get("error_summary"), "mesaj": i.get("error_message"), "seviye": i.get("level"),
              "tur": i.get("error_type")} for i in (a.get("issues_info") or [])]
    return {
        "ad_id": str(a["id"]), "hesap_id": hid, "ad_adi": a.get("name"),
        "durum": a.get("effective_status"), "ayar_durum": a.get("configured_status"),
        "adset_id": s.get("id"), "adset_adi": s.get("name"), "adset_durum": s.get("effective_status"),
        "kampanya_id": k.get("id"), "kampanya_adi": k.get("name"),
        "kampanya_durum": k.get("effective_status"), "kampanya_amaci": k.get("objective"),
        "olusturma": a.get("created_time"), "guncelleme": a.get("updated_time"),
        "onizleme": a.get("preview_shareable_link"),
        "red_sebep": red, "sorunlar": sorun or None,
        "kampanya": {"gunluk_butce": _kurus(k.get("daily_budget")), "omur_butce": _kurus(k.get("lifetime_budget")),
                     "baslangic": k.get("start_time"), "bitis": k.get("stop_time"),
                     "satin_alma_tipi": k.get("buying_type")},
        "adset": {"gunluk_butce": _kurus(s.get("daily_budget")), "omur_butce": _kurus(s.get("lifetime_budget")),
                  "baslangic": s.get("start_time"), "bitis": s.get("end_time"),
                  "optimizasyon": s.get("optimization_goal"), "faturalama": s.get("billing_event"),
                  "teklif": s.get("bid_strategy"), "hedef_tipi": s.get("destination_type"),
                  "kitle": hedef_kitle_ozet(s.get("targeting"))},
        "kreatif": kreatif_ozet(cr),
        "fb_gonderi_id": cr.get("effective_object_story_id"),
        "ig_medya_id": cr.get("effective_instagram_media_id"),
        "ig_baglanti": cr.get("instagram_permalink_url"),
    }


# ------------------------------------------------------------------ yorum
def _z(s):
    return s or None


def ig_yorumlari(medya_id: str, ham: dict, biz: str | None) -> list[dict]:
    out = []
    biz = (biz or "").lower()
    for c in (ham.get("comments") or {}).get("data") or []:
        yan = (c.get("replies") or {}).get("data") or []
        bizden_yanit = any((r.get("username") or "").lower() == biz for r in yan) if biz else False
        out.append({"platform": "instagram", "yorum_id": str(c["id"]), "medya_id": medya_id,
                    "ust_yorum_id": None, "zaman": _z(c.get("timestamp")), "metin": c.get("text") or "",
                    "kullanici": c.get("username") or "", "begeni": int(c.get("like_count") or 0),
                    "yanit_sayisi": len(yan), "bizden": bool(biz) and (c.get("username") or "").lower() == biz,
                    "cevaplandi": bizden_yanit})
        for r in yan:
            out.append({"platform": "instagram", "yorum_id": str(r["id"]), "medya_id": medya_id,
                        "ust_yorum_id": str(c["id"]), "zaman": _z(r.get("timestamp")), "metin": r.get("text") or "",
                        "kullanici": r.get("username") or "", "begeni": int(r.get("like_count") or 0),
                        "yanit_sayisi": 0, "bizden": bool(biz) and (r.get("username") or "").lower() == biz,
                        "cevaplandi": None})
    return out


def fb_yorumlari(gonderi_id: str, liste: list[dict], sayfa_id: str | None) -> list[dict]:
    out = []
    for c in liste:
        yan = (c.get("comments") or {}).get("data") or []
        bizden_yanit = any(((r.get("from") or {}).get("id")) == sayfa_id for r in yan) if sayfa_id else False
        out.append({"platform": "facebook", "yorum_id": str(c["id"]), "medya_id": gonderi_id,
                    "ust_yorum_id": None, "zaman": _z(c.get("created_time")), "metin": c.get("message") or "",
                    "kullanici": (c.get("from") or {}).get("name") or "", "begeni": int(c.get("like_count") or 0),
                    "yanit_sayisi": int(c.get("comment_count") or len(yan)),
                    "bizden": bool(sayfa_id) and (c.get("from") or {}).get("id") == sayfa_id,
                    "cevaplandi": bizden_yanit})
        for r in yan:
            out.append({"platform": "facebook", "yorum_id": str(r["id"]), "medya_id": gonderi_id,
                        "ust_yorum_id": str(c["id"]), "zaman": _z(r.get("created_time")),
                        "metin": r.get("message") or "", "kullanici": (r.get("from") or {}).get("name") or "",
                        "begeni": int(r.get("like_count") or 0), "yanit_sayisi": 0,
                        "bizden": bool(sayfa_id) and (r.get("from") or {}).get("id") == sayfa_id,
                        "cevaplandi": None})
    return out


def hata_sebebi(h: Exception | str) -> str:
    """Meta hatasını panelde okunur, jetonsuz kısa Türkçe sebebe çevirir."""
    s = str(h)
    if "pages_read_engagement" in s:
        return ("video başka bir sayfaya ait ya da sayfa jetonunda 'pages_read_engagement' izni yok "
                "(Meta önizlemesinden izlenebilir)")
    if "pages_read_user_content" in s or "Page Public Content Access" in s:
        return ("Facebook gönderi yorumları okunamıyor: sayfa jetonunda 'pages_read_user_content' "
                "izni yok (Meta uygulamasına bu izin eklenmeli)")
    if '"code":190' in s or "Cannot parse access token" in s or "Invalid OAuth" in s:
        return "jeton geçersiz/süresi dolmuş"
    if '"code":10' in s or "does not have permission" in s:
        return "izin yok (Meta kod 10)"
    if "does not exist" in s:
        return "Instagram/Facebook gönderisi artık yok ya da bu jetonla görülemiyor (Meta: nesne bulunamadı)"
    if '"code":100' in s:
        return "gönderi/medya bulunamadı ya da erişilemiyor (Meta kod 100)"
    if '"code":4' in s or '"code":17' in s or "80004" in s:
        return "Meta hız sınırı"
    return "Meta hatası: " + s[:120]


# ------------------------------------------------------------------ toplama
def topla(hid: str, get: Callable[[str, dict, str], dict], get_liste: Callable[[str, dict], list],
          jeton_var: Callable[[str], bool] | None = None) -> dict:
    """Envanter + yorum. get(yol, sorgu, jeton_adi) tek nesne; get_liste
    reklam listesi (ADS jetonu, sayfalı). Dönüş: {envanter, yorumlar,
    olcum: {...sayılar...}}. Hiçbir metin/ad yazdırılmaz."""
    reklamlar = get_liste("act_%s/ads" % hid, {"fields": REKLAM_ALAN, "limit": "100"})
    env = [envanter_satiri(hid, a) for a in reklamlar]
    simdi = datetime.now().astimezone().isoformat()

    # Instagram hesap adı (cevaplandı mı?)
    biz_ig = None
    ig_kullanici_id = None
    sayfa_id = None
    for a in reklamlar:
        oss = (a.get("creative") or {}).get("object_story_spec") or {}
        ig_kullanici_id = ig_kullanici_id or oss.get("instagram_user_id") or oss.get("instagram_actor_id")
        sayfa_id = sayfa_id or oss.get("page_id")
    if ig_kullanici_id:
        try:
            biz_ig = get(str(ig_kullanici_id), {"fields": "username"}, "FB_PAGE_TOKEN").get("username")
        except Exception:  # noqa: BLE001
            biz_ig = None

    yorumlar: list[dict] = []
    okunan_ig: dict[str, dict] = {}
    for mid in sorted({e["ig_medya_id"] for e in env if e.get("ig_medya_id")}):
        son_hata = None
        for jeton in ("FB_PAGE_TOKEN", "META_ADS_TOKEN"):
            try:
                ham = get(mid, {"fields": IG_YORUM_ALAN}, jeton)
                ys = ig_yorumlari(mid, ham, biz_ig)
                okunan_ig[mid] = {"durum": "OK", "jeton": jeton, "sayac": ham.get("comments_count"),
                                  "begeni": ham.get("like_count"), "okunan": len(ys)}
                yorumlar += ys
                break
            except Exception as h:  # noqa: BLE001
                son_hata = h
        else:
            okunan_ig[mid] = {"durum": "OKUNAMADI", "sebep": hata_sebebi(son_hata)}

    okunan_fb: dict[str, dict] = {}
    fb_genel_hata = None
    for gid in sorted({e["fb_gonderi_id"] for e in env if e.get("fb_gonderi_id")}):
        if fb_genel_hata:
            okunan_fb[gid] = {"durum": "OKUNAMADI", "sebep": fb_genel_hata}
            continue
        son_hata = None
        for jeton in ("FB_PAGE_TOKEN", "META_ADS_TOKEN"):
            try:
                ham = get(gid + "/comments", {"fields": FB_YORUM_ALAN, "limit": "100", "filter": "toplevel"}, jeton)
                ys = fb_yorumlari(gid, ham.get("data") or [], sayfa_id)
                okunan_fb[gid] = {"durum": "OK", "jeton": jeton, "okunan": len(ys)}
                yorumlar += ys
                break
            except Exception as h:  # noqa: BLE001
                son_hata = h
        else:
            sebep = hata_sebebi(son_hata)
            okunan_fb[gid] = {"durum": "OKUNAMADI", "sebep": sebep}
            # İzin hatası her gönderide aynıdır: 100 kez sormak yerine hepsine yaz.
            if "pages_read_user_content" in sebep or "jeton" in sebep:
                fb_genel_hata = sebep

    for e in env:
        ig = okunan_ig.get(e.get("ig_medya_id") or "") or {}
        fb = okunan_fb.get(e.get("fb_gonderi_id") or "") or {}
        e["ig_yorum_durum"] = ig.get("durum") or ("YOK_GONDERI" if not e.get("ig_medya_id") else None)
        e["ig_yorum_sebep"] = ig.get("sebep") or (
            "Meta sayacı %s · okunan %s (yanıtlar dahil)" % (ig.get("sayac"), ig.get("okunan"))
            if ig.get("durum") == "OK" and (ig.get("sayac") or 0) != (ig.get("okunan") or 0) else None)
        e["ig_yorum_sayaci"] = ig.get("sayac")
        e["ig_begeni"] = ig.get("begeni")
        e["fb_yorum_durum"] = fb.get("durum") or ("YOK_GONDERI" if not e.get("fb_gonderi_id") else None)
        e["fb_yorum_sebep"] = fb.get("sebep")
        e["yorum_olcum_at"] = simdi
    olcum = {
        "reklam": len(env),
        "ig_medya": len(okunan_ig), "ig_okundu": sum(1 for v in okunan_ig.values() if v["durum"] == "OK"),
        "ig_yorum": sum(1 for y in yorumlar if y["platform"] == "instagram"),
        "fb_gonderi": len(okunan_fb), "fb_okundu": sum(1 for v in okunan_fb.values() if v["durum"] == "OK"),
        "fb_yorum": sum(1 for y in yorumlar if y["platform"] == "facebook"),
        "fb_sebep": fb_genel_hata,
    }
    return {"envanter": env, "yorumlar": yorumlar, "okunan_ig": okunan_ig, "okunan_fb": okunan_fb,
            "olcum": olcum}


def json_dump(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)
