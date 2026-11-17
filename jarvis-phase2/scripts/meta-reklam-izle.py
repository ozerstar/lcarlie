#!/usr/bin/env python3
"""META REKLAM IZLEME — hesabin tamamini saatte bir okur, DB'ye yazar, uyarir.

Sahip 15.11.2026: "Jarvis'in Meta reklam API'sine erisimi var, surekli
kontrol etsin." Mevcut iki parca bunu karsilamiyordu:
  - ticari-kontrol.sh (raw.meta_reklam) gunde BIR kez, 08:30, yerlesimsiz.
  - kampanya-izle.py TEK kampanyaya bagli (11.11) ve 17.11'de susar.

Bu betik her kosuda, hesaptaki TUM kampanya/reklam seti/reklamlar icin:
  1. bugun + onceki iki gunun reklam x gun performansini okur
     (harcama, gosterim, tik, CTR, TBM, sepete ekleme, odeme, satin alma,
     mesaj) -> raw.meta_izleme_reklam
  2. ayni araligi yerlesim kirilimiyla okur (facebook/instagram/
     audience_network x konum) -> raw.meta_izleme_yerlesim
  3. reklam/set/kampanya durumunu ve set butcesini okur
  4. kurallari isletir, YENI uyariyi sahibe push + e-posta ile bildirir
     (haberci; siparis nobetcisi ve kampanya-izle ile ayni hat)
  5. kosuyu raw.meta_izleme_kosu'ya yazar.
  6. (17.11) TUM reklamlarin envanteri (kapali/reddedilen dahil: durum, red
     sebebi, kitle, butce, kreatif varyasyonlari) + reklam gonderisi
     yorumlari -> raw.meta_reklam_envanter / raw.meta_reklam_yorum
     (jarvis/meta_reklam_detay.py). Yorum metni/kullanici adi LOG'A YAZILMAZ.

🔴 YALNIZ OKUR VE ONERIR. Meta'ya tek bir yazma istegi gitmez (yalniz GET).
   Uyarilardaki "oneri" metni sahibin karari icindir.
🔴 Okunamayan kaynak sifir sayilmaz: Meta okunamazsa reklam satiri yazilmaz,
   kosu HATA olur ve "okunamadi" uyarisi gider. Satis okunamazsa
   harcama/satis kurali hic isletilmez (sifir siparis DIYE uyari uretmez).
🔴 Ayni uyari iki kez bildirilmez (raw.meta_izleme_uyari.anahtar).
🔴 WhatsApp kullanilmaz: sahibe onayli iki sablon var (siparis haberi,
   onay dugmeli oneri). Reklam uyarisini onlara yuklemek sablonun anlamini
   bozar; yeni sablon Meta onayi ister.

Kullanim:
  meta-reklam-izle.py                (izle, yaz, yeni uyariyi bildir)
  meta-reklam-izle.py --kuru         (oku + ekrana yaz; DB'ye yazmaz, bildirmez)
  meta-reklam-izle.py --geri 30      (ilk dolum: son 30 gunu yaz; uyarilar
                                       yine yalniz dun+bugun icin isler)
  meta-reklam-izle.py --bildirme     (yaz ama bildirim gonderme)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import haberci, meta_reklam_detay, pazaryeri  # noqa: E402

TR = timezone(timedelta(hours=3))
G = "https://graph.facebook.com/v21.0"
AYAR_YOLU = KOK / "state" / "meta-izle" / "ayar.json"

# Esikler: state/meta-izle/ayar.json varsa oradaki deger kazanir.
VARSAYILAN = {
    "an_harcama_tl": 0.0,           # Audience Network harcamasi bunun USTUNDEYSE KRITIK
    "dun_harcama_min_tl": 300.0,    # dunku harcama bunun altindaysa harcama/satis kurali sessiz
    "dun_ciro_orani_alt": 1.0,      # dun kayitli ciro / harcama bunun altindaysa UYARI
    "bugun_satissiz_tl": 500.0,     # bugun bu kadar harcandi ve hic siparis yoksa UYARI
    "set_iki_gun_min_tl": 200.0,    # set 2 gunde bu kadar harcayip 0 sonuc -> UYARI
}

# Ayni olay icin Meta birden cok eylem tipi dondurur (omni_* = toplam).
# Ilk bulunan alinir; toplanmaz, yoksa ayni satis iki kez sayilir.
EYLEM = {
    "sepete_ekle": ("omni_add_to_cart", "add_to_cart",
                    "offsite_conversion.fb_pixel_add_to_cart", "onsite_web_add_to_cart"),
    "odeme_baslat": ("omni_initiated_checkout", "initiate_checkout",
                     "offsite_conversion.fb_pixel_initiate_checkout"),
    "satin_alma": ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase",
                   "onsite_web_purchase"),
    "mesaj_baslat": ("onsite_conversion.messaging_conversation_started_7d",),
    "sayfa_goruntule": ("omni_landing_page_view", "landing_page_view"),
}


# --------------------------------------------------------------------- yardimci
def _sayi(d, varsayilan=0.0) -> float:
    try:
        return float(d)
    except (TypeError, ValueError):
        return varsayilan


def _eylem(liste: list | None, tipler: tuple[str, ...]) -> float:
    harita = {e.get("action_type"): e.get("value") for e in (liste or [])}
    for t in tipler:
        if t in harita:
            return _sayi(harita[t])
    return 0.0


def _tl(x) -> str:
    return ("%.2f" % float(x or 0)).replace(".", ",") + " TL"


def ayar() -> dict:
    a = dict(VARSAYILAN)
    try:
        a.update(json.loads(AYAR_YOLU.read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    return a


def psql(sorgu: str) -> str:
    return haberci.psql(sorgu)


def _j(veri) -> str:
    """JSON'u SQL'e dolar tirnagiyla gomer; metinde $J$ gecemez."""
    s = json.dumps(veri, ensure_ascii=False)
    if "$J$" in s:
        raise ValueError("JSON icinde $J$ var")
    return "$J$" + s + "$J$"


# ------------------------------------------------------------------- meta (GET)
def meta_get(yol: str, sorgu: dict) -> list[dict]:
    """Yalniz GET; sayfalari izler. Hata yukari firlatilir (sifir sayilmaz)."""
    jeton = pazaryeri._n8n_env("META_ADS_TOKEN")
    if not jeton:
        raise RuntimeError("META_ADS_TOKEN yok")
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    cikti: list[dict] = []
    for _ in range(50):
        for deneme in range(3):
            try:
                yanit = json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))
                break
            except RuntimeError as h:
                # 17/4/80004 = hiz siniri; kisa bekle, yeniden dene.
                if deneme == 2 or not any(k in str(h) for k in ('"code":17', '"code":4', "80004", "HTTP 5")):
                    raise
                time.sleep(20 * (deneme + 1))
        cikti.extend(yanit.get("data") or [])
        url = (yanit.get("paging") or {}).get("next")
        if not url:
            return cikti
    raise RuntimeError("sayfalama 50 sayfayi asti: %s" % yol)


def meta_tek(yol: str, sorgu: dict, jeton_adi: str = "META_ADS_TOKEN") -> dict:
    """Tek nesne GET (envanter/yorum). Hata yukari firlatilir."""
    jeton = pazaryeri._n8n_env(jeton_adi)
    if not jeton:
        raise RuntimeError("%s yok" % jeton_adi)
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    for deneme in range(3):
        try:
            return json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))
        except RuntimeError as h:
            if deneme == 2 or not any(k in str(h) for k in ('"code":17', '"code":4,', "80004", "HTTP 5")):
                raise
            time.sleep(15 * (deneme + 1))
    raise RuntimeError("ulasilamadi")


ENVANTER_KOLON = (
    "ad_id text, hesap_id text, ad_adi text, durum text, ayar_durum text, adset_id text, "
    "adset_adi text, adset_durum text, kampanya_id text, kampanya_adi text, kampanya_durum text, "
    "kampanya_amaci text, olusturma timestamptz, guncelleme timestamptz, onizleme text, "
    "red_sebep jsonb, sorunlar jsonb, kampanya jsonb, adset jsonb, kreatif jsonb, "
    "fb_gonderi_id text, ig_medya_id text, ig_baglanti text, ig_yorum_sayaci int, ig_begeni int, "
    "ig_yorum_durum text, ig_yorum_sebep text, fb_yorum_durum text, fb_yorum_sebep text, "
    "yorum_olcum_at timestamptz")
YORUM_KOLON = (
    "platform text, yorum_id text, medya_id text, ust_yorum_id text, zaman timestamptz, "
    "metin text, kullanici text, begeni int, yanit_sayisi int, bizden boolean, cevaplandi boolean")


def detay_yaz(hid: str, kuru: bool = False) -> dict:
    """Envanter + yorum (jarvis/meta_reklam_detay). Donus yalniz SAYILAR."""
    d = meta_reklam_detay.topla(hid, meta_tek, meta_get)
    if kuru:
        return d["olcum"]
    _upsert("raw.meta_reklam_envanter", ENVANTER_KOLON, "ad_id", d["envanter"])
    # Okunabilen medyanin yorumlari tam yenilenir (silinen yorum kalmaz);
    # okunamayaninki DOKUNULMAZ (son bilinen hali kalir, durum OKUNAMADI).
    okunan = [m for m, v in {**d["okunan_ig"], **d["okunan_fb"]}.items() if v["durum"] == "OK"]
    if okunan:
        psql("DELETE FROM raw.meta_reklam_yorum WHERE medya_id IN (SELECT jsonb_array_elements_text(%s::jsonb));"
             % _j(okunan))
    _upsert("raw.meta_reklam_yorum", YORUM_KOLON, "platform, yorum_id", d["yorumlar"])
    return d["olcum"]


def hesaplar() -> list[str]:
    satir = psql("SELECT hesap_id FROM raw.meta_hesap WHERE durum::text = '1' ORDER BY 1;")
    return [s for s in satir.splitlines() if s.strip()]


def meta_oku(hid: str, bas: date, bit: date) -> dict:
    aralik = json.dumps({"since": bas.isoformat(), "until": bit.isoformat()})
    alan = ("account_id,campaign_id,campaign_name,objective,adset_id,adset_name,"
            "optimization_goal,ad_id,ad_name,spend,impressions,reach,frequency,clicks,"
            "inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click,cpm,"
            "actions,action_values")
    reklam = meta_get("act_%s/insights" % hid, {
        "level": "ad", "fields": alan, "time_increment": "1",
        "time_range": aralik, "limit": "500"})
    yerlesim = meta_get("act_%s/insights" % hid, {
        "level": "ad", "time_increment": "1", "time_range": aralik, "limit": "500",
        "breakdowns": "publisher_platform,platform_position",
        "fields": "account_id,campaign_id,adset_id,ad_id,spend,impressions,clicks,"
                  "inline_link_clicks,actions"})
    durum = meta_get("act_%s/ads" % hid, {
        "fields": "id,effective_status,adset{id,daily_budget,effective_status},"
                  "campaign{id,effective_status}",
        "limit": "200"})
    return dict(reklam=reklam, yerlesim=yerlesim,
                durum={d["id"]: d for d in durum})


def reklam_satirlari(hid: str, m: dict) -> list[dict]:
    satir = []
    for r in m["reklam"]:
        d = m["durum"].get(r["ad_id"], {})
        aset = d.get("adset") or {}
        butce = aset.get("daily_budget")
        satir.append(dict(
            gun=r["date_start"], ad_id=r["ad_id"], hesap_id=hid,
            kampanya_id=r.get("campaign_id"), kampanya_adi=r.get("campaign_name"),
            kampanya_amaci=r.get("objective"), adset_id=r.get("adset_id"),
            adset_adi=r.get("adset_name"), optimizasyon=r.get("optimization_goal"),
            ad_adi=r.get("ad_name"), durum=d.get("effective_status"),
            adset_durum=aset.get("effective_status"),
            kampanya_durum=(d.get("campaign") or {}).get("effective_status"),
            gunluk_butce=(_sayi(butce) / 100) if butce else None,
            harcama=_sayi(r.get("spend")), gosterim=int(_sayi(r.get("impressions"))),
            erisim=int(_sayi(r.get("reach"))) if r.get("reach") is not None else None,
            frekans=_sayi(r.get("frequency"), None) if r.get("frequency") is not None else None,
            tiklama=int(_sayi(r.get("clicks"))),
            link_tiklama=int(_sayi(r.get("inline_link_clicks"))),
            ctr=_sayi(r.get("inline_link_click_ctr"), None) if r.get("inline_link_click_ctr") is not None else None,
            tbm=_sayi(r.get("cost_per_inline_link_click"), None) if r.get("cost_per_inline_link_click") is not None else None,
            cpm=_sayi(r.get("cpm"), None) if r.get("cpm") is not None else None,
            sepete_ekle=int(_eylem(r.get("actions"), EYLEM["sepete_ekle"])),
            odeme_baslat=int(_eylem(r.get("actions"), EYLEM["odeme_baslat"])),
            satin_alma=int(_eylem(r.get("actions"), EYLEM["satin_alma"])),
            satin_alma_degeri=round(_eylem(r.get("action_values"), EYLEM["satin_alma"]), 2),
            mesaj_baslat=int(_eylem(r.get("actions"), EYLEM["mesaj_baslat"])),
            sayfa_goruntule=int(_eylem(r.get("actions"), EYLEM["sayfa_goruntule"])),
            eylemler=r.get("actions") or [], eylem_degerleri=r.get("action_values") or []))
    return satir


def yerlesim_satirlari(hid: str, m: dict) -> list[dict]:
    return [dict(
        gun=r["date_start"], ad_id=r["ad_id"], yayinci=r.get("publisher_platform") or "?",
        konum=r.get("platform_position") or "?", hesap_id=hid,
        kampanya_id=r.get("campaign_id"), adset_id=r.get("adset_id"),
        harcama=_sayi(r.get("spend")), gosterim=int(_sayi(r.get("impressions"))),
        tiklama=int(_sayi(r.get("clicks"))), link_tiklama=int(_sayi(r.get("inline_link_clicks"))),
        sepete_ekle=int(_eylem(r.get("actions"), EYLEM["sepete_ekle"])),
        satin_alma=int(_eylem(r.get("actions"), EYLEM["satin_alma"])))
        for r in m["yerlesim"]]


# ------------------------------------------------------------------- DB yazimi
REKLAM_KOLON = (
    "gun date, ad_id text, hesap_id text, kampanya_id text, kampanya_adi text, "
    "kampanya_amaci text, adset_id text, adset_adi text, optimizasyon text, ad_adi text, "
    "durum text, adset_durum text, kampanya_durum text, gunluk_butce numeric, harcama numeric, "
    "gosterim bigint, erisim bigint, frekans numeric, tiklama bigint, link_tiklama bigint, "
    "ctr numeric, tbm numeric, cpm numeric, sepete_ekle int, odeme_baslat int, satin_alma int, "
    "satin_alma_degeri numeric, mesaj_baslat int, sayfa_goruntule int, eylemler jsonb, "
    "eylem_degerleri jsonb")
YERLESIM_KOLON = (
    "gun date, ad_id text, yayinci text, konum text, hesap_id text, kampanya_id text, "
    "adset_id text, harcama numeric, gosterim bigint, tiklama bigint, link_tiklama bigint, "
    "sepete_ekle int, satin_alma int")


def _upsert(tablo: str, kolon_tanim: str, anahtar: str, satirlar: list[dict]) -> None:
    if not satirlar:
        return
    adlar = [k.split()[0] for k in kolon_tanim.split(", ")]
    guncel = ", ".join("%s = EXCLUDED.%s" % (a, a) for a in adlar
                       if a not in anahtar.split(", "))
    for i in range(0, len(satirlar), 400):
        psql("INSERT INTO %s (%s, olcum_at) SELECT %s, now() FROM jsonb_to_recordset(%s::jsonb) "
             "AS x(%s) ON CONFLICT (%s) DO UPDATE SET %s, olcum_at = now();"
             % (tablo, ", ".join(adlar), ", ".join(adlar), _j(satirlar[i:i + 400]),
                kolon_tanim, anahtar, guncel))


def yaz(reklam: list[dict], yerlesim: list[dict], bas: date, bit: date) -> None:
    _upsert("raw.meta_izleme_reklam", REKLAM_KOLON, "gun, ad_id", reklam)
    # Yerlesim: aralik icindeki eski kirilimi sil, yenisini yaz (Meta bir
    # konumu bir sonraki okumada hic dondurmeyebilir; artik satir kalmasin).
    psql("DELETE FROM raw.meta_izleme_yerlesim WHERE gun BETWEEN '%s' AND '%s' AND hesap_id IN (%s);"
         % (bas, bit, ", ".join("'%s'" % h for h in {r["hesap_id"] for r in yerlesim} or {"-"})))
    _upsert("raw.meta_izleme_yerlesim", YERLESIM_KOLON, "gun, ad_id, yayinci, konum", yerlesim)


# ------------------------------------------------------------------- satis
def satis_oku(gunler: list[date]) -> dict[str, dict] | None:
    """Gun -> {siparis, ciro}. Tum kanallar (Wix + pazaryerleri). Okunamazsa None.
    🔴 Trendyol satirinda 'tutar' liste fiyati olabilir (12.11 tuzagi);
       metinde 'kayitli tutar' denir, kesin ciro denmez."""
    # 🔴 Siparis tablosu ancak nobetci calisiyorsa tazedir. Nobetci 30 dk'dir
    #    basarili kosmadiysa "0 siparis" bilgi degil, soramamaktir.
    import subprocess
    try:
        g = subprocess.run(["systemctl", "show", "lcarlie-siparis-nobetci.service",
                            "-p", "Result", "-p", "ActiveState",
                            "-p", "InactiveEnterTimestampMonotonic",
                            "-p", "ExecMainStartTimestampMonotonic"],
                           capture_output=True, text=True, timeout=10).stdout
        alan = dict(s.split("=", 1) for s in g.splitlines() if "=" in s)
        simdi_mono = time.monotonic()
        # Nobetci o an kosuyorsa bitis damgasi henuz yok (15.11 ilk canli
        # kosuda bu yuzden yanlis BAYAT dendi): baslangic damgasina bak.
        anahtar = ("ExecMainStartTimestampMonotonic"
                   if alan.get("ActiveState") in ("activating", "active")
                   else "InactiveEnterTimestampMonotonic")
        son = int(alan.get(anahtar) or 0) / 1e6
        if alan.get("Result") != "success" or not son or simdi_mono - son > 1800:
            print("SATIS BAYAT: nobetci son basarili kosu %.0f dk once, sonuc %s"
                  % ((simdi_mono - son) / 60 if son else -1, alan.get("Result")), file=sys.stderr)
            return None
    except Exception as h:                                # noqa: BLE001
        print("SATIS TAZELIGI OLCULEMEDI:", str(h)[:120], file=sys.stderr)
        return None
    try:
        ham = psql(
            "SELECT json_agg(t) FROM (SELECT (siparis_zamani AT TIME ZONE 'Europe/Istanbul')::date AS gun, "
            "count(*) AS siparis, coalesce(sum(tutar),0) AS ciro FROM core.pazaryeri_siparis "
            "WHERE (siparis_zamani AT TIME ZONE 'Europe/Istanbul')::date BETWEEN '%s' AND '%s' "
            "AND durum !~* '(cancel|iptal|unsupplied|return|iade)' GROUP BY 1) t;"
            % (min(gunler), max(gunler)))
    except Exception as h:                                # noqa: BLE001
        print("SATIS OKUNAMADI:", str(h)[:160], file=sys.stderr)
        return None
    sonuc = {g.isoformat(): dict(siparis=0, ciro=0.0) for g in gunler}
    for s in json.loads(ham or "null") or []:
        sonuc[s["gun"]] = dict(siparis=int(s["siparis"]), ciro=float(s["ciro"]))
    return sonuc


def trendyol_hedefli_setler() -> set[str]:
    """Butun reklamlari Trendyol'a giden setler: Meta orada satis/sepet GOREMEZ
    (piksel yok). Bu setlere 'sonucsuz' denmez, 'olculemez' denir."""
    try:
        ham = psql("SELECT json_agg(adset_id) FROM (SELECT adset_id FROM raw.meta_kreatif "
                   "WHERE adset_id IS NOT NULL GROUP BY adset_id "
                   "HAVING bool_and(coalesce(hedef_url,'') ~* 'trendyol')) t;")
        return set(json.loads(ham or "null") or [])
    except Exception:                                     # noqa: BLE001
        return set()


# ------------------------------------------------------------------- kurallar
def kurallar(reklam: list[dict], yerlesim: list[dict], satis: dict | None,
             a: dict, bugun: date) -> tuple[list[dict], list[str]]:
    dun = bugun - timedelta(days=1)
    uyari: list[dict] = []
    satir: list[str] = []
    gunluk = {}
    for r in reklam:
        gunluk[r["gun"]] = gunluk.get(r["gun"], 0.0) + r["harcama"]

    # --- 1) Audience Network ---
    an: dict[tuple[str, str], float] = {}
    for y in yerlesim:
        if y["yayinci"] == "audience_network" and y["gun"] >= dun.isoformat():
            k = (y["gun"], y["kampanya_id"] or "?")
            an[k] = an.get(k, 0.0) + y["harcama"]
    kampanya_adi = {r["kampanya_id"]: r["kampanya_adi"] for r in reklam}
    for (g, kid), tl in sorted(an.items()):
        if tl > a["an_harcama_tl"]:
            uyari.append(dict(
                anahtar="AN|%s|%s" % (g, kid), kural="AN_HARCAMA", seviye="KRITIK",
                metin="%s kampanyası %s günü Audience Network'e %s harcadı."
                      % (kampanya_adi.get(kid, kid), g, _tl(tl)),
                oneri="Reklam setinde yerleşimleri elle seç, Audience Network'ü kapat "
                      "(13.11'de LEMOS harcamasının ~%91'i buraya gitmişti).",
                veri=dict(gun=g, kampanya_id=kid, harcama=round(tl, 2))))
    an_bugun = sum(tl for (g, _), tl in an.items() if g == bugun.isoformat())
    satir.append("Audience Network bugün: %s" % _tl(an_bugun))

    # --- 2) Harcama / satis orani ---
    if satis is None:
        satir.append("Satış: OKUNAMADI — harcama/satış kuralı bu koşuda işletilmedi.")
    else:
        for g, etiket in ((dun, "dün"), (bugun, "bugün")):
            h = gunluk.get(g.isoformat(), 0.0)
            s = satis.get(g.isoformat(), dict(siparis=0, ciro=0.0))
            satir.append("%s (%s): harcama %s · tüm kanallarda %d sipariş · kayıtlı tutar %s"
                         % (etiket.capitalize(), g, _tl(h), s["siparis"], _tl(s["ciro"])))
        h = gunluk.get(dun.isoformat(), 0.0)
        s = satis.get(dun.isoformat(), dict(siparis=0, ciro=0.0))
        if h >= a["dun_harcama_min_tl"]:
            if s["siparis"] == 0:
                uyari.append(dict(
                    anahtar="HS|%s|sifir" % dun, kural="HARCAMA_SATIS", seviye="KRITIK",
                    metin="Dün (%s) Meta'ya %s harcandı, hiçbir kanalda sipariş yok." % (dun, _tl(h)),
                    oneri="En çok harcayan setlere bak (aşağıdaki liste); sonuçsuz olanları "
                          "duraklatmayı ya da bütçeyi düşürmeyi değerlendir.",
                    veri=dict(gun=str(dun), harcama=round(h, 2), siparis=0)))
            elif s["ciro"] < h * a["dun_ciro_orani_alt"]:
                uyari.append(dict(
                    anahtar="HS|%s|oran" % dun, kural="HARCAMA_SATIS", seviye="UYARI",
                    metin="Dün (%s) harcama %s, kayıtlı satış tutarı %s (%d sipariş) — "
                          "satış harcamanın altında." % (dun, _tl(h), _tl(s["ciro"]), s["siparis"]),
                    oneri="Kâr değil ciro karşılaştırması; ürün maliyeti eklenince açık daha büyük.",
                    veri=dict(gun=str(dun), harcama=round(h, 2), **s)))
        hb = gunluk.get(bugun.isoformat(), 0.0)
        sb = satis.get(bugun.isoformat(), dict(siparis=0, ciro=0.0))
        if hb >= a["bugun_satissiz_tl"] and sb["siparis"] == 0:
            uyari.append(dict(
                anahtar="HS|%s|bugun" % bugun, kural="HARCAMA_SATIS", seviye="UYARI",
                metin="Bugün şu ana kadar %s harcandı, henüz hiçbir kanalda sipariş yok." % _tl(hb),
                oneri="Gün bitmeden karar gerekmez; akşam özetinde yeniden bak.",
                veri=dict(gun=str(bugun), harcama=round(hb, 2))))

    # --- 3) Reklam seti 2 gunde sonucsuz ---
    pencere = {dun.isoformat(), bugun.isoformat()}
    setler: dict[str, dict] = {}
    for r in reklam:
        if r["gun"] not in pencere:
            continue
        s = setler.setdefault(r["adset_id"], dict(ad=r["adset_adi"], kampanya=r["kampanya_adi"],
                                                  harcama=0.0, sonuc=0, tik=0,
                                                  opt=r["optimizasyon"], durum=r["adset_durum"]))
        s["harcama"] += r["harcama"]
        s["tik"] += r["link_tiklama"]
        s["sonuc"] += r["sepete_ekle"] + r["odeme_baslat"] + r["satin_alma"] + r["mesaj_baslat"]
    trendyol = trendyol_hedefli_setler()
    for sid, s in sorted(setler.items(), key=lambda kv: -kv[1]["harcama"]):
        if s["harcama"] < a["set_iki_gun_min_tl"] or s["sonuc"] > 0:
            continue
        if sid in trendyol:
            uyari.append(dict(
                anahtar="SET|%s|%s|olculemez" % (sid, dun), kural="SET_SONUCSUZ", seviye="BILGI",
                metin="%s 2 günde %s harcadı; hedef Trendyol olduğu için Meta sonucu göremez "
                      "(piksel yok) — satış yalnız Trendyol siparişinden ölçülür." % (s["ad"], _tl(s["harcama"])),
                oneri=None, veri=dict(adset_id=sid, harcama=round(s["harcama"], 2), tik=s["tik"])))
            continue
        uyari.append(dict(
            anahtar="SET|%s|%s" % (sid, dun), kural="SET_SONUCSUZ", seviye="UYARI",
            metin="%s (%s) dün+bugün %s harcadı, %d bağlantı tıklaması, 0 sonuç "
                  "(sepete ekleme/ödeme/satın alma/mesaj yok)."
                  % (s["ad"], s["kampanya"], _tl(s["harcama"]), s["tik"]),
            oneri="Seti duraklatmayı ya da kreatifi değiştirmeyi değerlendir; karar senin.",
            veri=dict(adset_id=sid, harcama=round(s["harcama"], 2), tik=s["tik"],
                      optimizasyon=s["opt"])))

    # --- rapor: en cok harcayan setler (bugun) ---
    bugun_set: dict[str, float] = {}
    for r in reklam:
        if r["gun"] == bugun.isoformat():
            bugun_set[r["adset_adi"] or "?"] = bugun_set.get(r["adset_adi"] or "?", 0.0) + r["harcama"]
    for ad, tl in sorted(bugun_set.items(), key=lambda kv: -kv[1])[:6]:
        satir.append("  set bugün %-40s %s" % (ad[:40], _tl(tl)))
    return uyari, satir


def uyarilari_kaydet(uyari: list[dict]) -> list[dict]:
    """Yeni anahtarlari ekler, yenileri dondurur. Var olanin son_at'i guncellenir."""
    if not uyari:
        return []
    ham = psql(
        "WITH g AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) AS x(anahtar text, kural text, "
        "seviye text, metin text, oneri text, veri jsonb)), "
        "e AS (INSERT INTO raw.meta_izleme_uyari (anahtar, kural, seviye, metin, oneri, veri) "
        "SELECT anahtar, kural, seviye, metin, oneri, coalesce(veri,'{}') FROM g "
        "ON CONFLICT (anahtar) DO UPDATE SET son_at = now(), metin = EXCLUDED.metin, veri = EXCLUDED.veri "
        "RETURNING anahtar, (xmax = 0) AS yeni, bildirildi_at) "
        "SELECT coalesce(json_agg(anahtar), '[]') FROM e WHERE bildirildi_at IS NULL;"
        % _j(uyari))
    bekleyen = set(json.loads(ham or "[]"))
    return [u for u in uyari if u["anahtar"] in bekleyen]


def bildir(yeni: list[dict], rapor: str) -> str:
    """KRITIK/UYARI bildirilir; BILGI yalniz raporda kalir. Donus: ulasan yollar."""
    gidecek = [u for u in yeni if u["seviye"] in ("KRITIK", "UYARI")]
    if not gidecek:
        return ""
    kisa = "\n".join("• %s" % u["metin"] for u in gidecek)
    uzun = "\n\n".join("[%s] %s\nÖneri: %s" % (u["seviye"], u["metin"], u.get("oneri") or "-")
                       for u in gidecek)
    yollar = []
    for ad, islev in (
            ("push", lambda: haberci.push_gonder(
                "Meta reklam: %d uyarı" % len(gidecek), kisa, "meta-reklam-izle")),
            ("eposta", lambda: haberci.eposta_gonder(
                "Meta reklam uyarısı · %s" % datetime.now(TR).strftime("%d.%m %H:%M"),
                uzun + "\n\n— Hiçbir reklam ayarı otomatik değiştirilmedi. —\n\n" + rapor))):
        try:
            islev()
            yollar.append(ad)
        except Exception as h:                            # noqa: BLE001
            print("%s gönderilemedi: %s" % (ad, str(h)[:120]), file=sys.stderr)
    if yollar:
        psql("UPDATE raw.meta_izleme_uyari SET bildirildi_at = now(), kanallar = '%s' "
             "WHERE anahtar IN (SELECT jsonb_array_elements_text(%s::jsonb));"
             % (",".join(yollar), _j([u["anahtar"] for u in gidecek])))
    return ",".join(yollar) or "HICBIRI"


# ------------------------------------------------------------------- ana akis
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true")
    ap.add_argument("--bildirme", action="store_true")
    ap.add_argument("--geri", type=int, default=2, help="bugunden geriye kac gun (varsayilan 2)")
    arg = ap.parse_args()

    a = ayar()
    bugun = datetime.now(TR).date()
    bas = bugun - timedelta(days=max(1, arg.geri))
    kosu_id = None
    if not arg.kuru:
        kosu_id = psql("INSERT INTO raw.meta_izleme_kosu (durum, aralik_bas, aralik_bit) "
                       "VALUES ('SURUYOR', '%s', '%s') RETURNING id;" % (bas, bugun))

    reklam: list[dict] = []
    yerlesim: list[dict] = []
    hatalar: list[str] = []
    try:
        hlar = hesaplar()
    except Exception as h:                                # noqa: BLE001
        hlar, hatalar = [], ["hesap listesi: %s" % str(h)[:160]]
    if not hlar and not hatalar:
        hatalar.append("raw.meta_hesap'te aktif hesap yok")
    for hid in hlar:
        try:
            m = meta_oku(hid, bas, bugun)
            reklam += reklam_satirlari(hid, m)
            yerlesim += yerlesim_satirlari(hid, m)
        except Exception as h:                            # noqa: BLE001
            hatalar.append("act_%s: %s" % (hid, str(h)[:200]))

    if not arg.kuru and (reklam or yerlesim):
        yaz(reklam, yerlesim, bas, bugun)

    # 6) Envanter + yorum. Ana olcumu bozmaz: hatasi ayri yazilir.
    for hid in hlar:
        try:
            o = detay_yaz(hid, kuru=arg.kuru)
            print("envanter act_%s: %d reklam · Instagram %d/%d medya okundu, %d yorum · "
                  "Facebook %d/%d gonderi okundu, %d yorum%s"
                  % (hid, o["reklam"], o["ig_okundu"], o["ig_medya"], o["ig_yorum"], o["fb_okundu"],
                     o["fb_gonderi"], o["fb_yorum"], (" (FB: %s)" % o["fb_sebep"]) if o["fb_sebep"] else ""))
        except Exception as h:                            # noqa: BLE001
            print("ENVANTER OKUNAMADI act_%s: %s" % (hid, meta_reklam_detay.hata_sebebi(h)), file=sys.stderr)

    satis = satis_oku([bugun - timedelta(days=1), bugun])
    uyari, satir = kurallar(reklam, yerlesim, satis, a, bugun) if not hatalar or reklam else ([], [])
    if hatalar:
        uyari.append(dict(anahtar="OKUNAMADI|%s" % bugun, kural="OKUNAMADI", seviye="KRITIK",
                          metin="Meta reklam verisi okunamadı (%s). Harcama BİLİNMİYOR, sıfır değil."
                                % "; ".join(hatalar)[:300],
                          oneri="Jeton/izin kontrolü: META_ADS_TOKEN.", veri=dict(hatalar=hatalar)))

    rapor = "\n".join(["Meta reklam izleme · %s" % datetime.now(TR).strftime("%d.%m.%Y %H:%M"),
                       "Aralık %s – %s · %d reklam-gün satırı · %d yerleşim satırı"
                       % (bas, bugun, len(reklam), len(yerlesim)), ""] + satir
                      + ["", "UYARILAR:" if uyari else "Uyarı yok."]
                      + ["• [%s] %s" % (u["seviye"], u["metin"]) for u in uyari])
    print(rapor)
    if arg.kuru:
        return 0

    # BILGI seviyesi bildirilmez; "yeni" yalniz sahibe gidecek olanlardir.
    yeni = [u for u in uyarilari_kaydet(uyari) if u["seviye"] in ("KRITIK", "UYARI")]
    kanal = "" if arg.bildirme else bildir(yeni, rapor)
    durum = "HATA" if hatalar and not reklam else ("KISMI" if hatalar else "TAMAM")
    psql("UPDATE raw.meta_izleme_kosu SET bit_at = now(), durum = '%s', reklam_satir = %d, "
         "yerlesim_satir = %d, uyari_sayisi = %d, yeni_uyari = %d, bildirim = %s, hata = %s "
         "WHERE id = %s;"
         % (durum, len(reklam), len(yerlesim), len(uyari), len(yeni),
            haberci._m(kanal or None) if kanal else "NULL",
            haberci._m("; ".join(hatalar)) if hatalar else "NULL", int(kosu_id)))
    return 1 if durum == "HATA" else 0


if __name__ == "__main__":
    sys.exit(main())
