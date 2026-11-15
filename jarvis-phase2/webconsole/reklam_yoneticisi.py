# -*- coding: utf-8 -*-
"""REKLAM YÖNETİCİSİ — KAMPANYA sekmesinin Meta Reklam Yöneticisi görünümü.

Sahip 15.11.2026: *"Jarvis'teki reklam sayfasındaki datalardan bir şey
anlamıyorum, çok genel, her şeyi bir gösteriyor. Meta Business'taki gibi
kreatifler, hangi videolar hangi kreatifler ne getirmiş, kaç lira harcamış;
yanında Jarvis ve reklam ekiplerinin önerileri, ne yapılması gerekiyor."*

Bu modül iki parçadır:
  veri_oku(bas, bit)   veritabanından OKUR (panelin jarvis_web rolüyle;
                       yalnız GRANT'li görünümler, kişisel veri yok)
  rapor_kur(veri, …)   SAF işlev: aynı girdiye aynı rapor. Testler bunu
                       veritabanı olmadan çağırır.

🔴 META'NIN İDDİASI İLE DEFTER AYRI SÜTUNDUR. `meta_*` alanları Meta'nın
   kendi saydığıdır (piksel/atıf penceresi); `defter_*` alanları bizim
   siparişlerimizdir (core.alici_siparis = ödenen tutar; Wix
   mart.siparis_kalem). Hiçbir yerde toplanmaz, birbirinin yerine geçmez.
🔴 VERI_YOK ≠ 0. Trendyol'a giden reklamda Meta satın almayı GÖREMEZ
   (pikselsiz hedef): sütun 0 değil "ölçülemez" olur. Maliyeti bilinmeyen
   üründe katkı hesaplanmaz (None), sıfır yazılmaz.
🔴 DEFTER ÜRÜN DÜZEYİNDEDİR. Trendyol siparişinin hangi reklamdan geldiği
   bilinmez; satır, reklamın ürününün aynı kanaldaki aynı dönem satışını
   "ürün geneli" diye gösterir ve kaç reklamın paylaştığını söyler. Bu atıf
   değil, artış tahminine yarayan bağlamdır (uzman-1 §3).
🔴 HESAP: uzman-1 §4.2 — K = P/1,20 − komisyon×P − maliyet − kargo(92,66,
   KDV hariç); başabaş ROAS = P/K. Sipariş katkısı aynı formülle, P yerine
   müşterinin ÖDEDİĞİ tutarla hesaplanır.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime, timedelta, timezone

TR = timezone(timedelta(hours=3))
KAP = "lcarlie-postgres"

KDV = 1.20
# uzman-1 §4.2: Sürat 1 desi şehirlerarası, BasitKargo tarifesi, KDV hariç.
KARGO_KDV_HARIC = 92.66
# uzman-2 §4.1: Trendyol'da ürünün komisyon kaydı yoksa %19 varsayılır ("*").
VARSAYILAN_TY_KOMISYON = 19.0
VARSAYILAN_IDEFIX_KOMISYON = 10.0

# Rozet eşikleri (uzman-1 §4.4)
CTR_ALT = 0.8            # ≥2000 gösterimde bağlantı CTR'si bunun altındaysa
CTR_MIN_GOSTERIM = 2000
TBM_UST = 6.0
FREKANS_UST = 2.5
AN_PAY_UST = 10.0        # trafik hedefinde Audience Network payı (%)
YASAM_TIK = 1000         # ~1.000 tıklamada ≥1 Trendyol siparişi (yaşam belirtisi)

ARALIKLAR = ("bugun", "dun", "7", "30", "ozel")

KANAL_AD = {"trendyol": "Trendyol", "wix": "Site (Wix)", "idefix": "İdefix",
            "n11": "n11", "hepsiburada": "Hepsiburada"}
HEDEF_AD = {"trendyol": "Trendyol", "site": "Site", "mesaj": "Mesaj",
            "profil": "Instagram profili", "diger": "Diğer"}

DURUM_AD = {"ACTIVE": "Yayında", "PAUSED": "Durduruldu", "DISAPPROVED": "Reddedildi",
            "WITH_ISSUES": "Sorunlu", "PENDING_REVIEW": "İncelemede", "IN_PROCESS": "İşleniyor",
            "ADSET_PAUSED": "Set durdu", "CAMPAIGN_PAUSED": "Kampanya durdu",
            "ARCHIVED": "Arşivde", "DELETED": "Silindi", "PREAPPROVED": "Ön onaylı"}
KONUM_AD = {"feed": "Akış", "instagram_reels": "Reels", "facebook_reels": "Reels",
            "instagram_stories": "Hikâye", "facebook_stories": "Hikâye", "story": "Hikâye",
            "an_classic": "Uygulama içi (klasik)", "rewarded_video": "Ödüllü video",
            "instream_video": "Video içi", "status": "Durum", "threads_feed": "Akış",
            "instagram_search": "Arama", "search": "Arama", "instagram_explore": "Keşfet",
            "instagram_explore_grid_home": "Keşfet", "instagram_profile_feed": "Profil akışı",
            "marketplace": "Marketplace", "video_feeds": "Video akışı", "right_hand_column": "Sağ sütun",
            "facebook_reels_overlay": "Reels katmanı", "messenger_inbox": "Gelen kutusu",
            "notification": "Bildirim", "profile_feed": "Profil akışı"}
YAYINCI_AD = {"facebook": "Facebook", "instagram": "Instagram",
              "audience_network": "Audience Network", "messenger": "Messenger",
              "threads": "Threads", "whatsapp": "WhatsApp"}


class VeriHatasi(RuntimeError):
    pass


# ------------------------------------------------------------------ yardımcı
def _f(x, varsayilan=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return varsayilan


def _yuvarla(x, n=2):
    return None if x is None else round(float(x), n)


def _bol(a, b, carp=1.0):
    a, b = _f(a, None), _f(b, None)
    if a is None or not b:
        return None
    return a * carp / b


def tl(x) -> str:
    """1234.5 -> '1.234,50 TL' (öneri/özet metinleri için)."""
    if x is None:
        return "—"
    s = "{:,.2f}".format(float(x)).replace(",", "X").replace(".", ",").replace("X", ".")
    return s + " TL"


def sayi(x, n=2) -> str:
    """0.493 -> '0,49' (metinde Türkçe ondalık)."""
    if x is None:
        return "—"
    return ("{:,.%df}" % n).format(float(x)).replace(",", "X").replace(".", ",").replace("X", ".")


def tl0(x) -> str:
    if x is None:
        return "—"
    return "{:,.0f}".format(float(x)).replace(",", ".") + " TL"


def _katla(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").replace("İ", "i").replace("I", "ı").lower()
                  .replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u")
                  .replace("ö", "o").replace("ç", "c"))


def aralik_coz(secim: str | None, bas: str | None = None, bit: str | None = None,
               bugun: date | None = None) -> tuple[date, date, str]:
    """('bugun'|'dun'|'7'|'30'|'ozel') -> (bas, bit, etiket). Geçersiz -> 7 gün."""
    bugun = bugun or datetime.now(TR).date()
    secim = (secim or "7").strip().lower()
    if secim == "bugun":
        return bugun, bugun, "Bugün"
    if secim == "dun":
        d = bugun - timedelta(days=1)
        return d, d, "Dün"
    if secim == "30":
        return bugun - timedelta(days=29), bugun, "Son 30 gün"
    if secim == "ozel":
        try:
            b = date.fromisoformat(str(bas))
            s = date.fromisoformat(str(bit))
        except (TypeError, ValueError):
            return bugun - timedelta(days=6), bugun, "Son 7 gün"
        if s < b:
            b, s = s, b
        s = min(s, bugun)
        b = max(b, s - timedelta(days=365))
        return b, s, "%s – %s" % (b.strftime("%d.%m"), s.strftime("%d.%m.%Y"))
    return bugun - timedelta(days=6), bugun, "Son 7 gün"


def hedef_kanal(url: str | None, cta: str | None = None, mesaj: float = 0) -> str:
    u = (url or "").lower()
    if "trendyol.com" in u:
        return "trendyol"
    if "lcarlie.shop" in u or "lcarlie.com" in u or "wixsite" in u:
        return "site"
    if "wa.me" in u or "whatsapp" in u or (cta or "").upper() in ("WHATSAPP_MESSAGE", "MESSAGE_PAGE", "SEND_MESSAGE") or mesaj:
        return "mesaj"
    if "instagram.com" in u:
        return "profil"
    return "diger"


def kanal_of(hedef: str) -> str | None:
    """Reklam hedefinin satış kanalı (defterde aranacak yer)."""
    return {"trendyol": "trendyol", "site": "wix"}.get(hedef)


# ------------------------------------------------------------------ ekonomi
def urun_ekonomi(e: dict) -> dict:
    """Ürünün iki kanaldaki katkısı ve başabaş ROAS'ı (uzman-1 §4.2)."""
    maliyet = None if (e.get("maliyet_durum") or "").upper() == "VERI_YOK" else _f(e.get("maliyet"), None)
    sonuc = {"urun_kod": e.get("urun_kod"), "maliyet": maliyet,
             "maliyet_kdv_dahil": _yuvarla(maliyet * KDV) if maliyet is not None else None,
             "kanallar": {}}
    ty_kom = _f(e.get("ty_komisyon"), None)
    tahmini = ty_kom is None
    pos = _f(e.get("pos_yuzde"), None)
    for kanal, fiyat, kom, not_ in (
        ("trendyol", _f(e.get("ty_fiyat"), None), ty_kom if ty_kom is not None else VARSAYILAN_TY_KOMISYON,
         "komisyon kaydı yok, %19 varsayıldı" if tahmini else ""),
        ("wix", _f(e.get("wix_fiyat"), None), pos if pos is not None else 5.0,
         "" if pos is not None else "POS %5 varsayıldı"),
        ("idefix", _f(e.get("wix_fiyat"), None), _f(e.get("idefix_komisyon"), VARSAYILAN_IDEFIX_KOMISYON), ""),
    ):
        if not fiyat or maliyet is None:
            sonuc["kanallar"][kanal] = {"fiyat": fiyat, "komisyon": kom, "katki": None,
                                        "basabas_roas": None,
                                        "eksik": "maliyet yok" if maliyet is None else "fiyat yok"}
            continue
        k = katki(fiyat, kom, maliyet, 1)
        sonuc["kanallar"][kanal] = {
            "fiyat": fiyat, "komisyon": kom, "katki": _yuvarla(k),
            "basabas_roas": _yuvarla(fiyat / k) if k and k > 0 else None,
            "eksik": "" if k and k > 0 else "katkı sıfırın altında",
            "not": not_}
    return sonuc


def katki(tutar: float, komisyon_yuzde: float, maliyet: float, adet: float,
          siparis: float = 1) -> float:
    """K = P/1,20 − komisyon×P − maliyet×adet − kargo×sipariş (KDV hariç)."""
    return (tutar / KDV - komisyon_yuzde / 100.0 * tutar
            - maliyet * adet - KARGO_KDV_HARIC * siparis)


# ------------------------------------------------------------------ veri okuma
def _calistir(sql: str) -> list[dict]:
    from jarvis.db_transport import run as db_run
    try:
        p = db_run(["docker", "exec", "-i", KAP, "psql", "-X", "-q", "-At",
                    "-v", "ON_ERROR_STOP=1", "-U", "n8n", "-d", "n8n", "-f", "-"],
                   input=sql, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError) as hata:
        raise VeriHatasi("veritabani calistirilamadi: %s" % hata) from None
    if p.returncode:
        raise VeriHatasi((p.stderr or p.stdout)[:300])
    return [json.loads(s) for s in p.stdout.split("\n") if s.strip()]


def _js(sql: str) -> str:
    return "SELECT row_to_json(x) FROM (%s) x;" % sql


def satis_sorgulari(bas: str, bit: str) -> dict[str, str]:
    """GERÇEK SATIŞ (defter) okumasının TEK yeri. Rapor yalnız bu üç parçanın
    BİÇİMİNE bağlıdır, kaynağına değil:
      defter          gun, kanal, barkod, kod, siparis, adet, ciro   (gün×kanal×ürün)
      defter_gunluk   gun, kanal, siparis, ciro                     (gün×kanal, sipariş bir kez)
      defter_tazelik  son_olcum                                      (satış kaydının son güncellenmesi)
    15.11.2026: pazaryeri + elle satış kanal bilgisiyle mart.siparis_kalem /
    siparis_ekonomi zincirine ekleniyor (başka ajan). Hazır olunca yalnız bu
    işlevin SQL'i o görünümlere çevrilir (aynı sütun adlarıyla); ciro =
    müşterinin ÖDEDİĞİ tutar kalmalı (Trendyol liste fiyatı değil), iptal/iade
    hariç. Görünüm yetkisi: jarvis_web SELECT (lcarlie-panel-db-rolu)."""
    return {
        "defter": _js(
            "SELECT gun, kanal, barkod, kod, siparis, adet, ciro FROM mart.reklam_defter_satis "
            "WHERE gun BETWEEN '%s' AND '%s'" % (bas, bit)),
        "defter_gunluk": _js(
            "SELECT gun, kanal, siparis, ciro FROM mart.reklam_defter_gunluk "
            "WHERE gun BETWEEN '%s' AND '%s'" % (bas, bit)),
        "defter_tazelik": _js("SELECT son_olcum FROM mart.reklam_defter_tazelik"),
    }


def veri_oku(bas: date, bit: date, trend_gun: int = 30) -> dict:
    """Panelin okuduğu her şey, tek tur. Bir parça okunamazsa o parça
    `okunamadi` listesine girer, sıfır yazılmaz."""
    trend_bas = min(bas, bit - timedelta(days=trend_gun - 1))
    b, s, tb = bas.isoformat(), bit.isoformat(), trend_bas.isoformat()
    parcalar = {
        "reklam": _js(
            "SELECT gun, hesap_id, kampanya_id, kampanya_adi, kampanya_amaci, adset_id, adset_adi, "
            "optimizasyon, ad_id, ad_adi, durum, adset_durum, kampanya_durum, gunluk_butce, harcama, "
            "gosterim, erisim, frekans, tiklama, link_tiklama, sepete_ekle, odeme_baslat, satin_alma, "
            "satin_alma_degeri, mesaj_baslat, sayfa_goruntule, an_harcama, olcum_at "
            "FROM mart.meta_kreatif_gunluk WHERE gun BETWEEN '%s' AND '%s'" % (tb, s)),
        "son_durum": _js(
            "SELECT DISTINCT ON (ad_id) ad_id, gun, durum, adset_durum, kampanya_durum, gunluk_butce, "
            "kampanya_amaci, optimizasyon FROM raw.meta_izleme_reklam ORDER BY ad_id, gun DESC"),
        "kreatif": _js("SELECT * FROM mart.reklam_kreatif"),
        # AN kararı aralık toplamına değil SON 2 GÜNE bakar (15.11: sahip AN'yi
        # 13.11'de kapatmıştı, 7 günlük toplam bayat "kapat" önerisi üretti).
        "an_gunluk": _js(
            "SELECT gun, adset_id, sum(harcama) harcama FROM raw.meta_izleme_yerlesim "
            "WHERE yayinci = 'audience_network' AND gun BETWEEN '%s' AND '%s' "
            "GROUP BY 1, 2" % (tb, s)),
        "yerlesim": _js(
            "SELECT ad_id, yayinci, konum, sum(harcama) harcama, sum(gosterim) gosterim, "
            "sum(tiklama) tiklama, sum(link_tiklama) link_tiklama, sum(sepete_ekle) sepete_ekle, "
            "sum(satin_alma) satin_alma FROM raw.meta_izleme_yerlesim "
            "WHERE gun BETWEEN '%s' AND '%s' GROUP BY 1,2,3" % (b, s)),
        **satis_sorgulari(tb, s),
        "ekonomi": _js("SELECT * FROM mart.reklam_urun_ekonomi"),
        "uyari": _js(
            "SELECT anahtar, kural, seviye, metin, oneri, veri, ilk_at, son_at "
            "FROM raw.meta_izleme_uyari WHERE son_at > now() - interval '3 days' "
            "ORDER BY CASE seviye WHEN 'KRITIK' THEN 0 WHEN 'UYARI' THEN 1 ELSE 2 END, son_at DESC LIMIT 40"),
        "kosu": _js("SELECT id, bas_at, bit_at, durum, hata FROM raw.meta_izleme_kosu ORDER BY id DESC LIMIT 1"),
        "oneri_kosu": _js(
            "SELECT id, bas_at, bit_at, tetik, durum, donem_bas, donem_bit, model, ozet, hata "
            "FROM core.reklam_oneri_kosu WHERE durum IN ('TAMAM','KISMI') ORDER BY id DESC LIMIT 1"),
        "oneri": _js(
            "SELECT o.* FROM core.reklam_oneri o WHERE o.kosu_id = (SELECT max(id) FROM "
            "core.reklam_oneri_kosu WHERE durum IN ('TAMAM','KISMI')) ORDER BY oncelik, id"),
    }
    veri: dict = {"okunamadi": []}
    for ad, sql in parcalar.items():
        try:
            veri[ad] = _calistir(sql)
        except VeriHatasi as h:
            veri[ad] = None
            veri["okunamadi"].append({"parca": ad, "sebep": str(h)[:160]})
    return veri


# ------------------------------------------------------------------ rapor
_METRIK = ("harcama", "gosterim", "erisim", "tiklama", "link_tiklama", "sepete_ekle",
           "odeme_baslat", "satin_alma", "satin_alma_degeri", "mesaj_baslat", "sayfa_goruntule",
           "an_harcama")


def _bos_metrik() -> dict:
    return {k: 0.0 for k in _METRIK}


def _turet(m: dict, gun_sayisi: int) -> dict:
    """Toplamdan oranlar. Erişim günlük erişim toplamıdır (tekil kişi değil)."""
    m["ctr"] = _yuvarla(_bol(m["link_tiklama"], m["gosterim"], 100), 2)
    m["tbm"] = _yuvarla(_bol(m["harcama"], m["link_tiklama"]), 2)
    m["cpm"] = _yuvarla(_bol(m["harcama"], m["gosterim"], 1000), 2)
    m["frekans"] = _yuvarla(_bol(m["gosterim"], m["erisim"]), 2)
    m["an_pay"] = _yuvarla(_bol(m["an_harcama"], m["harcama"], 100), 1)
    m["erisim_tekil"] = gun_sayisi == 1
    for k in ("harcama", "satin_alma_degeri", "an_harcama"):
        m[k] = round(m[k], 2)
    for k in ("gosterim", "erisim", "tiklama", "link_tiklama", "sepete_ekle", "odeme_baslat",
              "satin_alma", "mesaj_baslat", "sayfa_goruntule"):
        m[k] = int(m[k])
    return m


def _urun_bul(kreatif: dict, ad_adi: str, kodlar: list[str], barkod_kod: dict) -> str | None:
    bk = kreatif.get("trendyol_barkod")
    if bk and bk in barkod_kod:
        return barkod_kod[bk]
    metin = _katla((kreatif.get("hedef_url") or "") + " " + (ad_adi or "") + " "
                   + (kreatif.get("baslik") or ""))
    en_iyi = None
    for kod in kodlar:
        k = _katla(kod)
        if len(k) >= 4 and k in metin and (en_iyi is None or len(k) > len(_katla(en_iyi))):
            en_iyi = kod
    return en_iyi


def rapor_kur(v: dict, bas: date, bit: date, simdi: datetime | None = None,
              etiket: str = "") -> dict:
    simdi = simdi or datetime.now(TR)
    gun_sayisi = (bit - bas).days + 1
    okunamadi = list(v.get("okunamadi") or [])
    oku = {p["parca"] for p in okunamadi}

    # --- ekonomi ---
    ekon: dict[str, dict] = {}
    barkod_kod: dict[str, str] = {}
    for e in v.get("ekonomi") or []:
        kod = e.get("urun_kod")
        if not kod:
            continue
        ekon[kod] = urun_ekonomi(e)
        ekon[kod]["ham"] = e
        for bk in (e.get("barkod"), e.get("pazaryeri_barkod")):
            if bk:
                barkod_kod[str(bk)] = kod
    kodlar = sorted(ekon)

    kreatif = {str(k["ad_id"]): k for k in (v.get("kreatif") or [])}
    son = {str(r["ad_id"]): r for r in (v.get("son_durum") or [])}

    # --- reklam satırları ---
    reklamlar: dict[str, dict] = {}
    trend_harcama: dict[str, float] = {}
    for r in v.get("reklam") or []:
        gun = str(r["gun"])[:10]
        trend_harcama[gun] = trend_harcama.get(gun, 0.0) + _f(r.get("harcama"))
        if not (bas.isoformat() <= gun <= bit.isoformat()):
            continue
        aid = str(r["ad_id"])
        x = reklamlar.get(aid)
        if x is None:
            x = reklamlar[aid] = {"ad_id": aid, "m": _bos_metrik(), "ilk": r, "gunler": 0}
        x["gunler"] += 1
        if _f(r.get("harcama")) > 0 and (x.get("ilk_harc") is None or gun < x["ilk_harc"]):
            x["ilk_harc"] = gun
        for k in _METRIK:
            x["m"][k] += _f(r.get(k))
        if gun >= str(x["ilk"]["gun"])[:10]:
            x["ilk"] = r

    satirlar = []
    for aid, x in reklamlar.items():
        r, kr, sd = x["ilk"], kreatif.get(aid, {}), son.get(aid, {})
        m = _turet(x["m"], gun_sayisi)
        hedef = hedef_kanal(kr.get("hedef_url"), kr.get("cta"), m["mesaj_baslat"])
        urun = _urun_bul(kr, r.get("ad_adi"), kodlar, barkod_kod)
        satirlar.append({
            "ad_id": aid, "ad": r.get("ad_adi") or aid,
            "kampanya_id": r.get("kampanya_id"), "kampanya": r.get("kampanya_adi"),
            "adset_id": r.get("adset_id"), "set": r.get("adset_adi"),
            "amac": sd.get("kampanya_amaci") or r.get("kampanya_amaci"),
            "optimizasyon": sd.get("optimizasyon") or r.get("optimizasyon"),
            "durum": sd.get("durum") or r.get("durum"),
            "durum_ad": DURUM_AD.get(sd.get("durum") or r.get("durum") or "", sd.get("durum") or "—"),
            "set_durum": sd.get("adset_durum"), "kampanya_durum": sd.get("kampanya_durum"),
            "gunluk_butce": _f(sd.get("gunluk_butce"), None),
            "hedef": hedef, "hedef_ad": HEDEF_AD.get(hedef, hedef), "urun": urun,
            "kreatif": {
                "tip": "VIDEO" if (kr.get("video_id") or (kr.get("nesne_tipi") or "") == "VIDEO") else "GORSEL",
                "baslik": kr.get("baslik") or "", "govde": kr.get("govde") or "",
                "aciklama": kr.get("aciklama") or "", "cta": kr.get("cta") or "",
                "hedef_url": kr.get("hedef_url") or "", "kreatif_adi": kr.get("kreatif_adi") or "",
            },
            "m": m, "ilk_harcama_gunu": x.get("ilk_harc"),
        })

    # --- Audience Network: son 2 gün ve son harcama günü (set bazında) ---
    son2_bas = (bit - timedelta(days=1)).isoformat()
    an_son2: dict[str, float] = {}
    an_son_gun_set: dict[str, str] = {}
    an_son_gun_tum = None
    for a in v.get("an_gunluk") or []:
        gun = str(a["gun"])[:10]
        h = _f(a.get("harcama"))
        if h <= 0 or gun > bit.isoformat():
            continue
        sid = str(a.get("adset_id") or "")
        if gun >= son2_bas:
            an_son2[sid] = an_son2.get(sid, 0.0) + h
        if gun > an_son_gun_set.get(sid, ""):
            an_son_gun_set[sid] = gun
        if an_son_gun_tum is None or gun > an_son_gun_tum:
            an_son_gun_tum = gun

    # --- ürün grupları: aynı ürün + aynı kanal hedefleyen reklamlar ---
    grup: dict[tuple, dict] = {}
    for s in satirlar:
        kanal = kanal_of(s["hedef"])
        if not kanal or not s["urun"]:
            continue
        g = grup.setdefault((kanal, s["urun"]), {"harcama": 0.0, "reklam": [], "link_tiklama": 0,
                                                  "ilk_gun": None})
        if s["ilk_harcama_gunu"] and (g["ilk_gun"] is None or s["ilk_harcama_gunu"] < g["ilk_gun"]):
            g["ilk_gun"] = s["ilk_harcama_gunu"]
        g["harcama"] += s["m"]["harcama"]
        g["link_tiklama"] += s["m"]["link_tiklama"]
        g["reklam"].append(s["ad_id"])

    # --- defter (gün×kanal×ürün) ---
    # 🔴 Ürünün satışı, o ürünün reklamının bu aralıkta İLK harcama yaptığı
    #    günden itibaren sayılır. 10.11'deki DERMANOVA siparişi 11.11'de
    #    başlayan reklama yazılıyordu (ölçüldü, 15.11).
    defter_okundu = "defter" not in oku and v.get("defter") is not None
    def_urun: dict[tuple, dict] = {}       # (kanal, kod) -> aralık toplamı
    def_trend: dict[str, dict] = {}        # gün -> {kanal: ciro}
    for d in v.get("defter") or []:
        kod = barkod_kod.get(str(d.get("barkod") or "")) or (d.get("kod") or "").upper() or "?"
        gun = str(d["gun"])[:10]
        ilk = (grup.get((d["kanal"], kod)) or {}).get("ilk_gun") or bas.isoformat()
        if max(ilk, bas.isoformat()) <= gun <= bit.isoformat():
            x = def_urun.setdefault((d["kanal"], kod), {"siparis": 0, "adet": 0.0, "ciro": 0.0,
                                                        "katki": 0.0, "katki_tam": True})
            x["siparis"] += int(_f(d.get("siparis")))
            x["adet"] += _f(d.get("adet"))
            x["ciro"] += _f(d.get("ciro"))
            e = ekon.get(kod)
            kom = None
            if e:
                kom = (e["kanallar"].get(d["kanal"]) or {}).get("komisyon")
            if e and e["maliyet"] is not None and kom is not None:
                x["katki"] += katki(_f(d.get("ciro")), kom, e["maliyet"], _f(d.get("adet")),
                                    _f(d.get("siparis")))
            else:
                x["katki_tam"] = False
    for d in v.get("defter_gunluk") or []:
        gun = str(d["gun"])[:10]
        def_trend.setdefault(gun, {})[d["kanal"]] = {
            "siparis": int(_f(d.get("siparis"))), "ciro": _f(d.get("ciro"))}

    def _defter_ozet(kanal, kod, harcama):
        """Ürün geneli defter + rozet."""
        if not defter_okundu:
            return {"durum": "OKUNAMADI"}
        d = def_urun.get((kanal, kod), {"siparis": 0, "adet": 0.0, "ciro": 0.0,
                                         "katki": 0.0, "katki_tam": True})
        e = ekon.get(kod) or {}
        ke = (e.get("kanallar") or {}).get(kanal) or {}
        katki_v = d["katki"] if (d["katki_tam"] and e.get("maliyet") is not None) else None
        roas = _bol(d["ciro"], harcama)
        return {"durum": "OK", "siparis": d["siparis"], "adet": d["adet"],
                "ciro": round(d["ciro"], 2), "katki": _yuvarla(katki_v),
                "sonuc": _yuvarla(katki_v - harcama) if katki_v is not None else None,
                "roas": _yuvarla(roas), "basabas_roas": ke.get("basabas_roas"),
                "birim_katki": ke.get("katki"), "eksik": ke.get("eksik") or ""}

    for s in satirlar:
        kanal = kanal_of(s["hedef"])
        s["meta_olculur"] = s["hedef"] == "site"
        s["defter"] = None
        s["grup"] = None
        if kanal and s["urun"]:
            g = grup[(kanal, s["urun"])]
            s["defter"] = _defter_ozet(kanal, s["urun"], g["harcama"])
            s["grup"] = {"kanal": kanal, "reklam_sayisi": len(g["reklam"]), "ilk_gun": g["ilk_gun"],
                         "harcama": round(g["harcama"], 2), "link_tiklama": g["link_tiklama"]}
        s["rozet"], s["rozet_neden"] = rozet(s, gun_sayisi)
        s["an_son2"] = round(an_son2.get(s["adset_id"], 0.0), 2)
        s["an_son_gun"] = an_son_gun_set.get(s["adset_id"])
        s["an_not"] = None
        if (bit >= simdi.date() - timedelta(days=0) and s["m"]["an_harcama"] > 0
                and s["an_son2"] == 0 and s["an_son_gun"]):
            g = s["an_son_gun"]
            s["an_not"] = "AN şimdi kapalı · son AN harcaması %s.%s" % (g[8:10], g[5:7])
        s["isaretler"] = isaretler(s)

    satirlar.sort(key=lambda s: -s["m"]["harcama"])

    # --- kampanya ve set düzeyi ---
    def _topla(anahtar_id, anahtar_ad):
        out: dict[str, dict] = {}
        for s in satirlar:
            k = s.get(anahtar_id) or "?"
            o = out.get(k)
            if o is None:
                o = out[k] = {"id": k, "ad": s.get(anahtar_ad) or k, "m": _bos_metrik(),
                              "reklam": [], "urunler": set(), "hedefler": set(),
                              "kampanya": s.get("kampanya"), "kampanya_id": s.get("kampanya_id"),
                              "amac": s.get("amac"), "optimizasyon": s.get("optimizasyon"),
                              "durum": None, "butce": None}
            for mk in _METRIK:
                o["m"][mk] += s["m"][mk] if mk in s["m"] else 0
            o["reklam"].append(s["ad_id"])
            if s["urun"] and kanal_of(s["hedef"]):
                o["urunler"].add((kanal_of(s["hedef"]), s["urun"]))
            o["hedefler"].add(s["hedef_ad"])
            durum = s["kampanya_durum"] if anahtar_id == "kampanya_id" else s["set_durum"]
            if durum == "ACTIVE" or o["durum"] is None:
                o["durum"] = durum
            if anahtar_id == "adset_id" and s.get("gunluk_butce"):
                o["butce"] = s["gunluk_butce"]
        liste = []
        for o in out.values():
            m = _turet(o["m"], gun_sayisi)
            ciro = siparis = 0.0
            katki_v: float | None = 0.0
            ortak = []
            for kanal, kod in sorted(o["urunler"]):
                d = def_urun.get((kanal, kod), {"siparis": 0, "ciro": 0.0, "katki": 0.0, "katki_tam": True})
                ciro += d["ciro"]
                siparis += d["siparis"]
                if not d["katki_tam"] or (ekon.get(kod) or {}).get("maliyet") is None:
                    katki_v = None
                elif katki_v is not None:
                    katki_v += d["katki"]
                diger = [a for a in grup[(kanal, kod)]["reklam"] if a not in o["reklam"]]
                if diger:
                    ortak.append(kod)
            urun_harcama = sum(grup[u]["harcama"] for u in o["urunler"])
            o2 = {k: o[k] for k in ("id", "ad", "kampanya", "kampanya_id", "amac", "optimizasyon",
                                     "durum", "butce")}
            o2.update({
                "durum_ad": DURUM_AD.get(o["durum"] or "", o["durum"] or "—"),
                "reklam_sayisi": len(o["reklam"]), "m": m,
                "urunler": sorted({u[1] for u in o["urunler"]}),
                "hedefler": sorted(o["hedefler"]),
                "defter": ({"durum": "OKUNAMADI"} if not defter_okundu else
                           {"durum": "OK" if o["urunler"] else "HEDEF_SATIS_DEGIL",
                            "siparis": int(siparis), "ciro": round(ciro, 2),
                            "katki": _yuvarla(katki_v) if o["urunler"] else None,
                            "sonuc": (_yuvarla(katki_v - urun_harcama)
                                      if (katki_v is not None and o["urunler"]) else None),
                            "roas": _yuvarla(_bol(ciro, urun_harcama)) if o["urunler"] else None,
                            "urun_harcama": round(urun_harcama, 2),
                            "ortak_urun": ortak}),
            })
            liste.append(o2)
        liste.sort(key=lambda x: -x["m"]["harcama"])
        return liste

    kampanyalar = _topla("kampanya_id", "kampanya")
    setler = _topla("adset_id", "set")

    # --- yerleşim ---
    yer: dict[tuple, dict] = {}
    for y in v.get("yerlesim") or []:
        k = (y.get("yayinci") or "?", y.get("konum") or "?")
        o = yer.setdefault(k, {"harcama": 0.0, "gosterim": 0, "tiklama": 0, "link_tiklama": 0,
                               "sepete_ekle": 0, "satin_alma": 0})
        for mk in o:
            o[mk] += _f(y.get(mk))
    yer_toplam = sum(o["harcama"] for o in yer.values())
    yerlesim = []
    for (yay, konum), o in sorted(yer.items(), key=lambda kv: -kv[1]["harcama"]):
        yerlesim.append({
            "yayinci": yay, "yayinci_ad": YAYINCI_AD.get(yay, yay), "konum": konum,
            "konum_ad": KONUM_AD.get(konum, konum.replace("_", " ")),
            "an": yay == "audience_network",
            "harcama": round(o["harcama"], 2), "pay": _yuvarla(_bol(o["harcama"], yer_toplam, 100), 1),
            "gosterim": int(o["gosterim"]), "link_tiklama": int(o["link_tiklama"]),
            "ctr": _yuvarla(_bol(o["link_tiklama"], o["gosterim"], 100)),
            "tbm": _yuvarla(_bol(o["harcama"], o["link_tiklama"])),
            "sepete_ekle": int(o["sepete_ekle"]), "satin_alma": int(o["satin_alma"])})
    an_harcama = sum(o["harcama"] for o in yerlesim if o["an"])
    yayinci_ozet: dict[str, float] = {}
    for o in yerlesim:
        yayinci_ozet[o["yayinci_ad"]] = yayinci_ozet.get(o["yayinci_ad"], 0.0) + o["harcama"]

    # --- trend ---
    reklamli_urunler = set(grup)   # (kanal, kod)
    trend = []
    gun = min(bas, bit - timedelta(days=29))
    while gun <= bit:
        g = gun.isoformat()
        kanallar = def_trend.get(g, {})
        reklam_urun_ciro = 0.0
        for d in v.get("defter") or []:
            if str(d["gun"])[:10] != g:
                continue
            kod = barkod_kod.get(str(d.get("barkod") or "")) or (d.get("kod") or "").upper()
            if (d["kanal"], kod) in reklamli_urunler:
                reklam_urun_ciro += _f(d.get("ciro"))
        trend.append({
            "gun": g, "harcama": round(trend_harcama.get(g, 0.0), 2),
            "ciro": round(sum(k["ciro"] for k in kanallar.values()), 2) if defter_okundu else None,
            "siparis": sum(k["siparis"] for k in kanallar.values()) if defter_okundu else None,
            "reklamli_urun_ciro": round(reklam_urun_ciro, 2) if defter_okundu else None,
            "secili": bas <= gun <= bit})
        gun += timedelta(days=1)

    # --- toplamlar ---
    top = _turet({k: sum(s["m"][k] for s in satirlar) for k in _METRIK}, gun_sayisi)
    secili_trend = [t for t in trend if t["secili"]]
    tum_ciro = sum(t["ciro"] or 0 for t in secili_trend) if defter_okundu else None
    tum_siparis = sum(t["siparis"] or 0 for t in secili_trend) if defter_okundu else None
    hedef_ciro = hedef_siparis = 0.0
    hedef_katki: float | None = 0.0
    for (kanal, kod) in reklamli_urunler:
        d = def_urun.get((kanal, kod))
        if not d:
            continue
        hedef_ciro += d["ciro"]
        hedef_siparis += d["siparis"]
        if not d["katki_tam"] or (ekon.get(kod) or {}).get("maliyet") is None:
            hedef_katki = None
        elif hedef_katki is not None:
            hedef_katki += d["katki"]
    reklamli_harcama = sum(g["harcama"] for g in grup.values())
    meta_gorebilen = [s for s in satirlar if s["meta_olculur"]]
    ozet = {
        "harcama": top["harcama"], "gosterim": top["gosterim"], "link_tiklama": top["link_tiklama"],
        "ctr": top["ctr"], "tbm": top["tbm"], "cpm": top["cpm"],
        "sepete_ekle": top["sepete_ekle"],
        "meta_satin_alma": sum(s["m"]["satin_alma"] for s in meta_gorebilen) if meta_gorebilen else None,
        "meta_satin_alma_degeri": (round(sum(s["m"]["satin_alma_degeri"] for s in meta_gorebilen), 2)
                                   if meta_gorebilen else None),
        "meta_olculemeyen_harcama": round(sum(s["m"]["harcama"] for s in satirlar
                                              if not s["meta_olculur"]), 2),
        "defter_durum": "OK" if defter_okundu else "OKUNAMADI",
        "hedef_siparis": int(hedef_siparis) if defter_okundu else None,
        "hedef_ciro": round(hedef_ciro, 2) if defter_okundu else None,
        "hedef_katki": _yuvarla(hedef_katki) if defter_okundu else None,
        "hedef_sonuc": (_yuvarla(hedef_katki - reklamli_harcama)
                        if (defter_okundu and hedef_katki is not None) else None),
        "reklamli_harcama": round(reklamli_harcama, 2),
        "tum_siparis": tum_siparis, "tum_ciro": _yuvarla(tum_ciro),
        "mer": _yuvarla(_bol(tum_ciro, top["harcama"])) if tum_ciro is not None else None,
        "an_harcama": round(an_harcama, 2),
        "an_pay": _yuvarla(_bol(an_harcama, yer_toplam, 100), 1),
        "an_son2_harcama": (round(sum(an_son2.values()), 2) if v.get("an_gunluk") is not None else None),
        "an_son_gun": an_son_gun_tum,
        "aktif_reklam": sum(1 for s in satirlar if s["durum"] == "ACTIVE"),
        "reklam_sayisi": len(satirlar),
    }

    # --- tazelik ---
    kosu = (v.get("kosu") or [{}])[0] if v.get("kosu") else {}
    tazelik = (v.get("defter_tazelik") or [{}])[0] if v.get("defter_tazelik") else {}

    def _yas(iso):
        if not iso:
            return None
        try:
            t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            return None
        return int((simdi - t).total_seconds() // 60)

    # --- öneriler ---
    oneri_kosu = (v.get("oneri_kosu") or [None])[0] if v.get("oneri_kosu") else None
    oneriler = [dict(o) for o in (v.get("oneri") or [])]
    kural = kural_onerileri({"satirlar": satirlar, "setler": setler, "kampanyalar": kampanyalar,
                             "yerlesim": yerlesim, "ozet": ozet, "ekonomi": ekon,
                             "def_urun": def_urun, "grup": grup, "gun_sayisi": gun_sayisi,
                             "defter_okundu": defter_okundu})
    ne_yap = []
    kaynak = "YOK"
    if oneri_kosu and oneri_kosu.get("ozet"):
        ne_yap = list(oneri_kosu["ozet"])[:3]
        kaynak = "UZMAN"
    if not ne_yap:
        ne_yap = [o["ozet"] for o in kural[:3]]
        kaynak = "KURAL" if ne_yap else "YOK"
    if not oneriler:
        oneriler = kural

    rapor = {
        "durum": "OK",
        "aralik": {"bas": bas.isoformat(), "bit": bit.isoformat(), "gun": gun_sayisi, "etiket": etiket},
        "olcum": {"meta": kosu.get("bit_at") or kosu.get("bas_at"), "meta_durum": kosu.get("durum"),
                  "meta_yas_dk": _yas(kosu.get("bit_at") or kosu.get("bas_at")),
                  "defter": tazelik.get("son_olcum"), "defter_yas_dk": _yas(tazelik.get("son_olcum"))},
        "ozet": ozet,
        "ne_yapmaliyim": {"maddeler": ne_yap, "kaynak": kaynak,
                          "uretim": (oneri_kosu or {}).get("bit_at")},
        "reklamlar": satirlar, "setler": setler, "kampanyalar": kampanyalar,
        "yerlesim": yerlesim, "yayinci_ozet": [{"ad": k, "harcama": round(v2, 2)}
                                              for k, v2 in sorted(yayinci_ozet.items(), key=lambda kv: -kv[1])],
        "trend": trend,
        "uyarilar": [{"seviye": u.get("seviye"), "kural": u.get("kural"), "metin": u.get("metin"),
                      "oneri": u.get("oneri"), "zaman": u.get("son_at")} for u in (v.get("uyari") or [])],
        "oneriler": oneriler,
        "oneri_kosu": ({k: oneri_kosu.get(k) for k in ("id", "bit_at", "tetik", "model", "durum")}
                       if oneri_kosu else None),
        "urun_ekonomi": [{"urun": k, "maliyet_kdv_dahil": e["maliyet_kdv_dahil"],
                          "trendyol": {kk: e["kanallar"]["trendyol"].get(kk) for kk in ("fiyat", "katki", "basabas_roas")},
                          "wix": {kk: e["kanallar"]["wix"].get(kk) for kk in ("fiyat", "katki", "basabas_roas")}}
                         for k, e in sorted(ekon.items()) if any(k == s["urun"] for s in satirlar)],
        "okunamadi": okunamadi,
    }
    return rapor


# ------------------------------------------------------------------ rozet
def rozet(s: dict, gun_sayisi: int) -> tuple[str, str]:
    """IYI / IZLE / KES / BILINMIYOR — ürünün kanaldaki defter ROAS'ı ile
    başabaş ROAS kıyası (uzman-1 §4.4). Gerekçe her zaman yazılır."""
    m = s["m"]
    if s["durum"] in ("DISAPPROVED", "WITH_ISSUES"):
        return "KES", "Reklam %s; yayın sorunu çözülmeden harcama verimsiz." % DURUM_AD.get(s["durum"], s["durum"]).lower()
    d = s.get("defter")
    if not kanal_of(s["hedef"]):
        return "BILINMIYOR", "Hedef satış sayfası değil (%s); satış ölçülemez." % s["hedef_ad"]
    if not s.get("urun"):
        return "BILINMIYOR", "Reklamın ürünü bağlantıdan çözülemedi."
    if not d or d.get("durum") != "OK":
        return "BILINMIYOR", "Satış defteri okunamadı; sıfır sayılmadı."
    be, roas, birim = d.get("basabas_roas"), d.get("roas"), d.get("birim_katki")
    g = s["grup"] or {}
    harcama = g.get("harcama") or m["harcama"]
    if be is None or not birim:
        return "BILINMIYOR", "Başabaş hesaplanamadı (%s)." % (d.get("eksik") or "fiyat/maliyet eksik")
    if harcama <= 0:
        return "IZLE", "Bu aralıkta harcama yok."
    if roas is not None and roas >= be:
        if d["siparis"] < 2 and harcama < birim * 0.25:
            return "IZLE", "Ürün ROAS %s ama veri az: %s harcama, %d sipariş." % (
                sayi(roas), tl0(harcama), d["siparis"])
        return "IYI", "Ürün ROAS %s ≥ başabaş %s (%d sipariş)." % (sayi(roas), sayi(be), d["siparis"])
    if d["siparis"] == 0 and (harcama >= birim or g.get("link_tiklama", 0) >= YASAM_TIK):
        neden = ("Ürüne %s harcandı (1 siparişin katkısı %s), sipariş yok." % (tl0(harcama), tl0(birim))
                 if harcama >= birim else
                 "%d tıklamada sipariş yok (yaşam eşiği ~%d)." % (g.get("link_tiklama", 0), YASAM_TIK))
        return "KES", neden
    if roas is not None and roas < be * 0.6 and harcama >= birim:
        return "KES", "Ürün ROAS %s, başabaşın (%s) çok altında." % (sayi(roas), sayi(be))
    if d["siparis"] == 0:
        return "IZLE", "Ürüne %s harcandı; karar için 1 siparişin katkısı (%s) kadar harcama gerekir." % (
            tl0(harcama), tl0(birim))
    return "IZLE", "Ürün ROAS %s < başabaş %s; yaklaşıyor." % (sayi(roas or 0), sayi(be))


def isaretler(s: dict) -> list[str]:
    """Kreatif/teslim uyarıları (uzman-1 §4.4); kesin karar değil, ipucu."""
    m, out = s["m"], []
    if m["gosterim"] >= CTR_MIN_GOSTERIM and m["ctr"] is not None and m["ctr"] < CTR_ALT:
        out.append("CTR düşük (%%%s)" % sayi(m["ctr"]))
    if m["tbm"] is not None and m["tbm"] > TBM_UST:
        out.append("TBM yüksek (%s)" % tl(m["tbm"]))
    if m["frekans"] is not None and m["frekans"] > FREKANS_UST and s["m"].get("erisim_tekil"):
        out.append("Frekans %s" % sayi(m["frekans"], 1))
    if m["an_pay"] and m["an_pay"] > AN_PAY_UST and s.get("an_not"):
        out.append("Audience Network %%%s (aralık toplamı)" % sayi(m["an_pay"], 0))
    elif m["an_pay"] and m["an_pay"] > AN_PAY_UST:
        out.append("Audience Network %%%s" % sayi(m["an_pay"], 0))
    if (s.get("amac") == "OUTCOME_SALES" and s.get("optimizasyon") == "LANDING_PAGE_VIEWS"
            and s["hedef"] == "trendyol"):
        out.append("Satış kampanyası sayfa görüntülemeye optimize")
    return out


# ------------------------------------------------------------------ kural önerileri
def _oneri(dept, kapsam, hedef_id, hedef_ad, oncelik, ne, neden, etki, risk, geri, olcum,
           onay, kural, ozet):
    return {"departman": dept, "kapsam": kapsam, "hedef_id": hedef_id, "hedef_ad": hedef_ad,
            "oncelik": oncelik, "ne": ne, "neden": neden, "beklenen_etki": etki, "risk": risk,
            "geri_alma": geri, "olcum": olcum, "onay_gerekir": onay, "kaynak": "KURAL",
            "anahtar": kural + ":" + str(hedef_id), "ozet": ozet, "action_id": None}


def kural_onerileri(r: dict) -> list[dict]:
    """Deterministik öneriler (uzman-1 §4.4/§6, uzman-2 §4). Model yokken de
    çalışır; model bunları gözden geçirir, yerine geçmez. En önemli önce."""
    out: list[dict] = []
    ozet, satirlar = r["ozet"], r["satirlar"]

    # 1) Audience Network — SON 2 GÜN (bit ve bir önceki gün). Aralık toplamı
    #    kapatılmış AN'yi "kapat" diye önerir (15.11 #179 bayattı: AN 13.11'de
    #    kapatılmıştı).
    an_set: dict[str, dict] = {}
    for s in satirlar:
        if s.get("an_son2", 0) > 0 and s["adset_id"] not in an_set:
            an_set[s["adset_id"]] = {"ad": s["set"], "an": s["an_son2"]}
    if an_set:
        en = sorted(an_set.items(), key=lambda kv: -kv[1]["an"])
        adlar = ", ".join(v["ad"] for _, v in en)
        toplam = sum(v["an"] for v in an_set.values())
        out.append(_oneri(
            "META_MEDIA", "YERLESIM", ",".join(k for k, _ in en), adlar, 1,
            "%d reklam setinde Audience Network yerleşimini kapat." % len(an_set),
            "Son 2 günde Audience Network'e %s harcandı (%s). AN tıklamaları satışa "
            "dönmüyor (11.11'de pay %%98,9 ölçüldü); uzman eşiği %%%d." % (
                tl0(toplam), adlar, AN_PAY_UST),
            "AN harcaması Instagram akış/hikâyeye kayar; tıklama sayısı düşer, nitelik artar.",
            "Teslim kısa süre yavaşlayabilir; set düzenlemesi öğrenmeyi etkiler.",
            "Yerleşimde Audience Network'ü yeniden işaretle.",
            "48 saat sonra yerleşim tablosunda AN harcaması 0.", True, "an",
            "Audience Network'ü kapat: son 2 günde oraya %s gitti." % tl0(toplam)))

    # 2) Reddedilen / sorunlu reklam
    for s in satirlar:
        if s["durum"] in ("DISAPPROVED", "WITH_ISSUES") and s["m"]["harcama"] > 0:
            out.append(_oneri(
                "META_MEDIA", "REKLAM", s["ad_id"], s["ad"], 1,
                "'%s' reklamını düzelt ya da arşivle (durum: %s)." % (s["ad"], s["durum_ad"]),
                "Reklam %s; dönemde %s harcamıştı. Ret nedeni Ads Manager'da okunmalı (mevzuat/metin)." % (
                    s["durum_ad"].lower(), tl0(s["m"]["harcama"])),
                "Setin bütçesi onaylı reklamlara kalır.",
                "Aynı metinle yeniden yüklemek hesabı riske atar; metin nesne denetiminden geçmeli.",
                "Arşivden geri alınabilir.", "Ads Manager'da reklam durumu.", True, "ret",
                "'%s' reddedildi: düzelt ya da arşivle." % s["ad"]))

    # 3) Ürün düzeyi: kes / büyüt (uzman: tek seferde en fazla 3 öneri ->
    #    ikiden fazla "kes" tek öneride birleşir)
    kesler, buyut = [], []
    for (kanal, kod), g in sorted(r["grup"].items(), key=lambda kv: -kv[1]["harcama"]):
        ornek = next((s for s in satirlar if s["ad_id"] in g["reklam"]
                      and s["durum"] not in ("DISAPPROVED", "WITH_ISSUES")), None)
        if not ornek or not ornek.get("defter") or ornek["defter"].get("durum") != "OK":
            continue
        if ornek["rozet"] == "KES":
            kesler.append((kanal, kod, g, ornek))
        elif ornek["rozet"] == "IYI" and ornek["defter"]["siparis"] >= 2:
            buyut.append((kanal, kod, g, ornek))

    def _kes_satir(kanal, kod, g, ornek):
        d = ornek["defter"]
        return "%s: %s harcama, %d sipariş (%s), başabaş ROAS %s" % (
            kod, tl0(g["harcama"]), d["siparis"], tl0(d["ciro"]), sayi(d.get("basabas_roas")))

    if len(kesler) > 2:
        toplam = sum(g["harcama"] for _, _, g, _ in kesler)
        sip = sum(o["defter"]["siparis"] for _, _, _, o in kesler)
        kodlar_k = [kod for _, kod, _, _ in kesler]
        out.append(_oneri(
            "META_MEDIA", "URUN", ",".join(sorted(kodlar_k)), ", ".join(kodlar_k), 1,
            "%d ürünün Trendyol reklamlarını durdur ya da bütçesini yarıya indir: %s." % (
                len(kesler), ", ".join(kodlar_k)),
            "Bu ürünlere %s harcandı, reklam başladıktan sonra toplam %d sipariş. "
            % (tl0(toplam), sip) + " · ".join(_kes_satir(*k) for k in kesler) + ".",
            "Günlük harcama düşer; sipariş tabanı değişmezse kayıp durur.",
            "Reklamın gecikmeli etkisi (birkaç gün sonra gelen sipariş) kaybolabilir.",
            "Reklamı yeniden aç; 7 günden kısa duraklatma öğrenmeyi sıfırlamaz.",
            "3 gün sonra aynı ürünlerin siparişi reklam öncesi tabanla kıyaslanır.",
            True, "kes-toplu",
            "%d ürünün reklamını durdur/yarıya indir: %s harcandı, %d sipariş (%s)." % (
                len(kesler), tl0(toplam), sip, ", ".join(kodlar_k))))
    else:
        for kanal, kod, g, ornek in kesler:
            d = ornek["defter"]
            kanal_ad = KANAL_AD.get(kanal, kanal)
            out.append(_oneri(
                "META_MEDIA", "URUN", kod, kod, 1 if g["harcama"] >= 1000 else 2,
                "%s → %s reklamlarının (%d reklam) bütçesini durdur ya da yarıya indir." % (
                    kod, kanal_ad, len(g["reklam"])),
                _kes_satir(kanal, kod, g, ornek) + ". " + ornek["rozet_neden"],
                "Günlük harcama düşer; sipariş tabanı değişmezse kayıp durur.",
                "Reklamın gecikmeli etkisi (birkaç gün sonra gelen sipariş) kaybolabilir.",
                "Reklamı yeniden aç; 7 günden kısa duraklatma öğrenmeyi sıfırlamaz.",
                "3 gün sonra aynı ürünün %s siparişi reklam öncesi tabanla kıyaslanır." % kanal_ad,
                True, "kes:" + kanal,
                "%s reklamını durdur/yarıya indir: %s harcandı, %d sipariş." % (
                    kod, tl0(g["harcama"]), d["siparis"])))
    for kanal, kod, _g, ornek in buyut[:2]:
        d = ornek["defter"]
        kanal_ad = KANAL_AD.get(kanal, kanal)
        out.append(_oneri(
            "META_MEDIA", "URUN", kod, kod, 2,
            "%s → %s reklamlarının günlük bütçesini %%20 artır." % (kod, kanal_ad),
            "Ürün ROAS %s ≥ başabaş %s; %d sipariş, %s ciro, reklam sonrası %s." % (
                sayi(d["roas"]), sayi(d["basabas_roas"]), d["siparis"], tl0(d["ciro"]),
                tl0(d.get("sonuc"))),
            "Aynı verimle günlük katkı ~%20 artar; verim düşerse geri alınır.",
            "Bütçe artışı öğrenmeyi kısa süre bozabilir (±%20 sınırı).",
            "Bütçeyi eski değerine indir.", "3 gün sonra ürün ROAS'ı başabaşın üstünde mi.",
            True, "buyut:" + kanal,
            "%s bütçesini %%20 artır: ROAS %s, başabaş %s." % (
                kod, sayi(d["roas"]), sayi(d["basabas_roas"]))))

    # 4) Yanlış optimizasyon (satış adlı kampanya LPV'ye, Trendyol linkine)
    gorulen = set()
    for s in satirlar:
        if ("Satış kampanyası sayfa görüntülemeye optimize" in s["isaretler"]
                and s["adset_id"] not in gorulen and s["m"]["harcama"] > 0):
            gorulen.add(s["adset_id"])
    if gorulen:
        adlar = ", ".join(sorted({s["set"] for s in satirlar if s["adset_id"] in gorulen}))[:200]
        out.append(_oneri(
            "META_MEDIA", "SET", ",".join(sorted(gorulen)), adlar, 2,
            "Trendyol'a giden %d sette optimizasyonu 'Bağlantı Tıklaması'na çevir." % len(gorulen),
            "Kampanya hedefi Satış ama setler sayfa görüntülemeye (LPV) optimize; Trendyol linkinde "
            "piksel yok, LPV ölçülemiyor (uzman-1 §6.2).",
            "Meta tıklama getiren kitleye teslim eder; TBM düşer.",
            "Optimizasyon değişikliği öğrenmeyi sıfırlar.",
            "Optimizasyonu geri al (yeni öğrenme başlar).",
            "3 gün sonra TBM ve Trendyol siparişi.", True, "optim",
            "%d sette optimizasyonu bağlantı tıklamasına çevir (Trendyol linkinde LPV ölçülemiyor)." % len(gorulen)))

    # 5) Kreatif yorgunluğu / zayıf CTR (yalnız AN'siz reklam)
    for s in satirlar:
        if s["m"]["an_pay"] and s["m"]["an_pay"] > AN_PAY_UST:
            continue
        if any(i.startswith("CTR düşük") for i in s["isaretler"]) and s["m"]["harcama"] >= 100:
            out.append(_oneri(
                "META_MEDIA", "REKLAM", s["ad_id"], s["ad"], 3,
                "'%s' kreatifini yeni kancalı bir sürümle değiştir." % s["ad"],
                "%d gösterimde bağlantı CTR %%%s (eşik %%%s), TBM %s." % (
                    s["m"]["gosterim"], sayi(s["m"]["ctr"]), sayi(CTR_ALT, 1), tl(s["m"]["tbm"])),
                "CTR %1'in üstüne çıkarsa aynı bütçeyle daha çok tıklama.",
                "Yeni kreatif incelemeye girer; birkaç saat teslim düşebilir.",
                "Eski reklam açık tutulabilir.", "3 gün sonra CTR/TBM kıyası.", True, "ctr",
                "'%s' kreatifini değiştir: CTR %%%s." % (s["ad"], sayi(s["m"]["ctr"]))))

    # 6) Hesap geneli MER (uzman-1 §3: karar metriği MER)
    # Günlük örtüşme yanıltır (uzman-1 §3): MER kararı en az 3 günlük pencerede.
    if (r["defter_okundu"] and ozet.get("mer") is not None and ozet["harcama"] >= 500
            and r["gun_sayisi"] >= 3):
        if ozet["mer"] < 1.0:
            out.append(_oneri(
                "META_MEDIA", "HESAP", "hesap", "Tüm hesap", 1,
                "Toplam günlük reklam bütçesini düşür; yalnız başabaşa yaklaşan ürünler kalsın.",
                "Seçili dönemde %s harcandı, tüm kanallarda %d sipariş / %s ciro: MER %s "
                "(1 TL reklama %s TL ciro; kâr değil, ciro)." % (
                    tl0(ozet["harcama"]), ozet["tum_siparis"] or 0, tl0(ozet["tum_ciro"]),
                    sayi(ozet["mer"]), sayi(ozet["mer"])),
                "Harcama düşer; sipariş tabanı reklamsız dönemle (günde ~0,13 sipariş) kıyaslanır.",
                "Reklam etkisi gecikmeli olabilir; ani kesinti marka görünürlüğünü azaltır.",
                "Bütçeyi geri yükselt.", "7 gün sonra MER ve sipariş sayısı.", True, "mer",
                "Toplam bütçeyi düşür: %s harcandı, %d sipariş (MER %s)." % (
                    tl0(ozet["harcama"]), ozet["tum_siparis"] or 0, sayi(ozet["mer"]))))

    # 7) Pazaryeri: ölçüm (onay gerekmez)
    ty = [(k, g) for (kanal, k), g in r["grup"].items() if kanal == "trendyol"]
    if ty:
        harc = sum(g["harcama"] for _, g in ty)
        sip = sum((r["def_urun"].get(("trendyol", k)) or {}).get("siparis", 0) for k, _ in ty)
        ciro = sum((r["def_urun"].get(("trendyol", k)) or {}).get("ciro", 0.0) for k, _ in ty)
        out.append(_oneri(
            "MARKETPLACE", "HESAP", "trendyol", "Trendyol", 3,
            "Trendyol'a giden reklamları reklam öncesi aynı uzunluktaki dönemle kıyasla (artış tahmini).",
            "%d üründe %s harcandı; bu ürünlerin Trendyol satışı %d sipariş / %s. Meta Trendyol "
            "satışını göremez, atıf değil artış tahmini yapılır (uzman-1 §3)." % (
                len(ty), tl0(harc), sip, tl0(ciro)),
            "Hangi ürünün reklamla gerçekten arttığı görülür.", "Yok (analiz).", "—",
            "Haftalık: reklam öncesi 7 gün vs reklamlı 7 gün, ürün ürün.", False, "ty-olcum",
            "Trendyol satışını reklam öncesiyle kıyasla: %s harcama, %d sipariş." % (tl0(harc), sip)))

    out.sort(key=lambda o: o["oncelik"])
    return out


# ------------------------------------------------------------------ kanıt özeti
def kanit_ozeti(r: dict, sinir: int = 1500) -> str:
    """Müdüre soru (_ekip_sor) için tek yoğun kanıt parçası."""
    o = r["ozet"]
    bas = ("REKLAM YÖNETİCİSİ (%s, %s–%s): harcama %s, %d bağlantı tıklaması, TBM %s; "
           "reklamlı ürünlerin hedef kanaldaki satışı %s sipariş / %s, reklam sonrası %s; "
           "tüm kanallar %s sipariş / %s, MER %s; Audience Network payı %%%s. "
           "Meta Trendyol satışını göremez (ölçülemez). " % (
               r["aralik"]["etiket"], r["aralik"]["bas"], r["aralik"]["bit"], tl0(o["harcama"]),
               o["link_tiklama"], tl(o["tbm"]), o["hedef_siparis"], tl0(o["hedef_ciro"]),
               tl0(o["hedef_sonuc"]), o["tum_siparis"], tl0(o["tum_ciro"]), sayi(o["mer"]),
               sayi(o["an_pay"], 0)))
    satir = []
    for s in r["reklamlar"][:10]:
        d = s.get("defter") or {}
        satir.append("%s [%s→%s, %s] %s harcama, %d tık, CTR %%%s, TBM %s, ürün %s sipariş, rozet %s" % (
            s["ad"][:40], s["urun"] or "?", s["hedef_ad"], s["durum_ad"], tl0(s["m"]["harcama"]),
            s["m"]["link_tiklama"], sayi(s["m"]["ctr"]), tl(s["m"]["tbm"]),
            d.get("siparis", "?"), s["rozet"]))
    ne = " | ".join(r["ne_yapmaliyim"]["maddeler"])
    return (bas + "Reklamlar: " + "; ".join(satir) + ". Ne yapmalı: " + ne)[:sinir]


# ------------------------------------------------------------------ üst düzey
def rapor(secim: str | None = None, bas: str | None = None, bit: str | None = None) -> dict:
    b, s, etiket = aralik_coz(secim, bas, bit)
    return rapor_kur(veri_oku(b, s), b, s, etiket=etiket)
