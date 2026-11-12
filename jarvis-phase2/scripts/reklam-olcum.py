#!/usr/bin/env python3
"""Tüm kanalların satışı × tüm reklamlar: tek ölçüm, KAMPANYA sekmesinin kaynağı.

Sahip 12.11.2026: *"İdefix'ten n11'e Wix'e kadar tüm satışlara, tüm
platformlardaki tüm reklamlar... genel değerlendirme yanı sıra kampanya
kampanya bölüm bölüm görebilmeliyim. Satın alanların datasını ve analizini
bünyende barındır."*

Çıktılar:
  state/reklam-olcum/ozet.json   panelin okuduğu tek dosya
  core.alici_siparis             alıcı verisi (kendi DB'mizde; dışarı çıkmaz)

Kurallar:
  · Ciro = müşterinin ÖDEDİĞİ tutar. Trendyol'da amount/grossAmount üstü çizili
    liste fiyatıdır; price/totalPrice kullanılır.
  · Okunamayan kaynak SIFIR yazılmaz, `okunamadi` listesine girer.
  · Trendyol'da piksel yok: kampanya → satış eşleşmesi kampanya penceresinde
    kampanya ürünlerinin (barkod) satışıdır, kesin atıf DEĞİL; panelde böyle yazar.
  · Trendyol'un kendi reklamları ve Trendyol panelinden açılan Meta reklamı
    API'de yok; panelde "panelden okunur" diye ayrı satır durur.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from jarvis import pazaryeri  # noqa: E402

TR = timezone(timedelta(hours=3))
GUN = 90
DIZIN = KOK / "state" / "reklam-olcum"
KAMPANYA_DIZIN = KOK / "state" / "kampanya-izle"
G = "https://graph.facebook.com/v21.0"
META_HESAP = "1301171572214198"
IPTAL = ("cancel", "unsupplied", "return", "iptal", "iade", "refund")


def _iptal_mi(durum) -> bool:
    d = str(durum or "").lower()
    return any(k in d for k in IPTAL)


def _kod(ad: str) -> str:
    return (str(ad or "").split() or ["-"])[0].upper().strip("(),")


# ------------------------------------------------------------------ satışlar
def trendyol(bas: datetime, son: datetime) -> list[dict]:
    e = pazaryeri.env_oku("/etc/lcarlie/trendyol.env")
    sid = e["TRENDYOL_SELLER_ID"]
    yetki = base64.b64encode(("%s:%s" % (e["TRENDYOL_API_KEY"],
                                         e["TRENDYOL_API_SECRET"])).encode()).decode()
    bas_ms = basliklar = None
    basliklar = {"Authorization": "Basic " + yetki,
                 "User-Agent": "%s - SelfIntegration" % sid}
    gorulen, cikti = set(), []
    bitis = int(son.timestamp() * 1000)
    bas_ms = int(bas.timestamp() * 1000)
    # API en fazla 14 günlük aralık kabul eder.
    while bitis > bas_ms:
        baslangic = max(bas_ms, bitis - 14 * 86400000)
        sayfa = 0
        while True:
            url = ("https://apigw.trendyol.com/integration/order/sellers/%s/orders"
                   "?startDate=%d&endDate=%d&size=200&page=%d" % (sid, baslangic, bitis, sayfa))
            veri = json.loads(pazaryeri._istek(url, basliklar))
            for p in veri.get("content") or []:
                no = str(p.get("orderNumber"))
                if no in gorulen:
                    continue
                gorulen.add(no)
                sa = p.get("shipmentAddress") or {}
                # orderDate TR saatini UTC gibi yazar (-3 sa).
                zaman = datetime.fromtimestamp((int(p.get("orderDate") or 0) - 3 * 3600000) / 1000, TR)
                cikti.append(dict(
                    kanal="trendyol", no=no, zaman=zaman.isoformat(),
                    durum=str(p.get("shipmentPackageStatus") or p.get("status")),
                    tutar=float(p.get("totalPrice") or 0),
                    liste_tutar=float(p.get("grossAmount") or 0),
                    musteri=("%s %s" % (p.get("customerFirstName") or "",
                                        p.get("customerLastName") or "")).strip(),
                    musteri_id=str(p.get("customerId") or ""),
                    sehir=str(sa.get("city") or ""), ilce=str(sa.get("district") or ""),
                    kalemler=[dict(kod=_kod(s.get("productName")), barkod=str(s.get("barcode")),
                                   adet=int(s.get("quantity") or 0),
                                   tutar=float(s.get("price") or 0) * int(s.get("quantity") or 0))
                              for s in p.get("lines") or []]))
            sayfa += 1
            if sayfa >= int(veri.get("totalPages") or 0):
                break
        bitis = baslangic
    return cikti


def idefix(bas: datetime, son: datetime) -> list[dict]:
    e = pazaryeri.env_oku("/etc/lcarlie/idefix.env")
    jeton = base64.b64encode((e["IDEFIX_API_KEY"].strip() + ":" +
                              e["IDEFIX_API_SECRET"].strip()).encode()).decode()
    vendor = urllib.parse.quote(e["IDEFIX_SELLER_ID"].strip(), safe="")
    cikti, sayfa, sayfa_sayisi = [], 1, 1
    while sayfa <= sayfa_sayisi:
        veri = json.loads(pazaryeri._istek(
            "https://merchantapi.idefix.com/oms/%s/list?page=%d&limit=100" % (vendor, sayfa),
            {"X-API-KEY": jeton, "Accept": "application/json"}))
        sayfa_sayisi = max(1, int(veri.get("pageCount") or 1))
        for p in veri.get("items") or []:
            zaman = pazaryeri._iso_zaman(p.get("orderDate") or p.get("createdAt"))
            if not zaman or not (bas <= zaman <= son):
                continue
            sa = p.get("shippingAddress") or {}
            tutar = p.get("discountedTotalPrice")
            cikti.append(dict(
                kanal="idefix", no=str(p.get("orderNumber")), zaman=zaman.astimezone(TR).isoformat(),
                durum=str(p.get("status")),
                tutar=float(tutar if tutar is not None else p.get("totalPrice") or 0),
                liste_tutar=float(p.get("totalPrice") or 0),
                musteri=str(p.get("customerContactName") or sa.get("fullName") or ""),
                musteri_id=str(p.get("customerId") or ""),
                sehir=str(sa.get("city") or ""), ilce=str(sa.get("county") or sa.get("district") or ""),
                kalemler=[dict(kod=_kod(i.get("productName")), barkod=str(i.get("barcode") or ""),
                               adet=1, tutar=float(i.get("discountedTotalPrice") or i.get("price") or 0))
                          for i in p.get("items") or []]))
        sayfa += 1
        time.sleep(0.5)
    return cikti


def _adaptor(ad: str, islev, bas: datetime, son: datetime) -> list[dict]:
    cikti = []
    for s in islev():
        if not s.zaman or not (bas <= s.zaman <= son):
            continue
        if ad == "wix" and s.durum != "PAID":
            continue
        cikti.append(dict(
            kanal=ad, no=s.siparis_no, zaman=s.zaman.astimezone(TR).isoformat(), durum=s.durum,
            tutar=float(s.tutar or 0), liste_tutar=float(s.tutar or 0),
            musteri=s.musteri_ad, musteri_id="", sehir=s.sehir, ilce="",
            kalemler=[dict(kod=_kod(k.get("ad")), barkod=str(k.get("barkod") or ""),
                           adet=int(k.get("adet") or 1), tutar=0.0) for k in s.kalemler]))
    return cikti


SATIS_KANALLARI = {
    "trendyol": trendyol,
    "idefix": idefix,
    "wix": lambda b, s: _adaptor("wix", lambda: pazaryeri.wix(100), b, s),
    "n11": lambda b, s: _adaptor("n11", pazaryeri.n11, b, s),
    "hepsiburada": lambda b, s: _adaptor("hepsiburada", pazaryeri.hepsiburada, b, s),
}


# ------------------------------------------------------------------ reklamlar
def _meta(yol: str, sorgu: dict) -> dict:
    jeton = pazaryeri._n8n_env("META_ADS_TOKEN")
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    return json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))


def meta_kampanyalar(bas: datetime, son: datetime) -> list[dict]:
    aralik = json.dumps({"since": bas.strftime("%Y-%m-%d"), "until": son.strftime("%Y-%m-%d")})
    ins = _meta("act_%s/insights" % META_HESAP, {
        "level": "campaign", "time_range": aralik, "limit": 200,
        "fields": "campaign_id,campaign_name,objective,spend,impressions,reach,"
                  "inline_link_clicks,ctr,cpc,frequency,actions,action_values,date_start,date_stop"})
    durum = {}
    for c in _meta("act_%s/campaigns" % META_HESAP, {
            "fields": "id,effective_status,start_time,stop_time", "limit": 200}).get("data") or []:
        durum[c["id"]] = c
    cikti = []
    for r in ins.get("data") or []:
        eylem = {a["action_type"]: float(a["value"]) for a in r.get("actions") or []}
        deger = {a["action_type"]: float(a["value"]) for a in r.get("action_values") or []}
        c = durum.get(r["campaign_id"], {})
        cikti.append(dict(
            platform="Meta", id=r["campaign_id"], ad=r["campaign_name"],
            hedef=r.get("objective"), durum=c.get("effective_status", "?"),
            baslangic=c.get("start_time"), bitis=c.get("stop_time"),
            harcama=float(r.get("spend") or 0), gosterim=int(r.get("impressions") or 0),
            erisim=int(r.get("reach") or 0), tiklama=int(float(r.get("inline_link_clicks") or 0)),
            ctr=float(r.get("ctr") or 0), tbm=float(r.get("cpc") or 0),
            frekans=float(r.get("frequency") or 0),
            meta_satin_alma=eylem.get("offsite_conversion.fb_pixel_purchase") or eylem.get("purchase"),
            meta_satin_alma_deger=deger.get("offsite_conversion.fb_pixel_purchase") or deger.get("purchase"),
            mesaj=eylem.get("onsite_conversion.messaging_conversation_started_7d"),
            etkilesim=eylem.get("post_engagement")))
    cikti.sort(key=lambda k: -k["harcama"])
    return cikti


def meta_gunluk(bas: datetime, son: datetime) -> list[dict]:
    aralik = json.dumps({"since": bas.strftime("%Y-%m-%d"), "until": son.strftime("%Y-%m-%d")})
    ins = _meta("act_%s/insights" % META_HESAP, {
        "time_range": aralik, "time_increment": 1, "fields": "spend,inline_link_clicks", "limit": 200})
    return [dict(gun=r["date_start"], harcama=float(r.get("spend") or 0),
                 tiklama=int(float(r.get("inline_link_clicks") or 0))) for r in ins.get("data") or []]


# ------------------------------------------------------------------ eşleştirme
def kampanya_urunleri() -> dict[str, dict]:
    """kampanya-izle ayarlarından: Meta kampanya id → Trendyol barkodları."""
    sonuc = {}
    for f in KAMPANYA_DIZIN.glob("*.json"):
        if f.name.endswith(".durum.json"):
            continue
        try:
            k = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if k.get("kampanya_id"):
            sonuc[str(k["kampanya_id"])] = k
    return sonuc


def eslestir(kampanyalar: list[dict], siparisler: list[dict]) -> None:
    ayar = kampanya_urunleri()
    for k in kampanyalar:
        a = ayar.get(k["id"])
        if a:
            barkod = set(a.get("urunler", {}).values())
            b = datetime.fromisoformat(a["baslangic"])
            s = datetime.fromisoformat(a["bitis"])
            hedef = "trendyol"
        elif "trendyol" in k["ad"].lower() and k.get("baslangic"):
            # Ayarı olmayan Trendyol kampanyası: penceredeki TÜM Trendyol satışı.
            # Aynı anda süren başka Trendyol kampanyasıyla örtüşür; panel söyler.
            barkod = "*"
            b = datetime.fromisoformat(k["baslangic"].replace("+0300", "+03:00"))
            s = datetime.fromisoformat(k["bitis"].replace("+0300", "+03:00")) if k.get("bitis")                 else datetime.now(TR)
            hedef = "trendyol"
        else:
            # Site (Wix) kampanyaları: Wix'te Meta pikseli VAR, Meta'nın kendi
            # ölçtüğü satın alma kullanılır. Pencere eşleştirmesi kampanyalar
            # örtüştüğü için aynı siparişi birkaç kampanyaya yazıyordu (ROAS 25).
            if k.get("meta_satin_alma"):
                deger = k.get("meta_satin_alma_deger") or 0
                k["satis"] = dict(kanal="wix", siparis=int(k["meta_satin_alma"]),
                                  ciro=round(deger, 2),
                                  roas=round(deger / k["harcama"], 2) if k["harcama"] else None,
                                  yontem="Meta pikseli (site satın alma)")
            else:
                k["satis"] = None
            continue
        adet, ciro, nolar = 0, 0.0, []
        for o in siparisler:
            if o["kanal"] != hedef or _iptal_mi(o["durum"]):
                continue
            z = datetime.fromisoformat(o["zaman"])
            if not (b <= z <= s):
                continue
            if barkod == "*":
                adet += 1
                ciro += o["tutar"]
                nolar.append(o["no"])
                continue
            tut = [x for x in o["kalemler"] if x["barkod"] in barkod]
            if tut:
                adet += 1
                ciro += sum(x["tutar"] for x in tut)
                nolar.append(o["no"])
        k["satis"] = dict(kanal=hedef, siparis=adet, ciro=round(ciro, 2),
                          roas=round(ciro / k["harcama"], 2) if k["harcama"] else None,
                          yontem="kampanya ürünleri, kampanya penceresi" if barkod != "*"
                          else "kampanya süresince TÜM Trendyol satışı (diğer kampanyayla örtüşebilir)")


# ------------------------------------------------------------------ alıcılar
ILCE_IL = {i: "Ankara" for i in (
    "çankaya", "keçiören", "yenimahalle", "mamak", "etimesgut", "sincan", "gölbaşı",
    "altındağ", "pursaklar", "polatlı", "çubuk", "kahramankazan", "elmadağ", "beypazarı")}
ILCE_IL.update({i: "İstanbul" for i in (
    "sancaktepe", "kadıköy", "üsküdar", "beşiktaş", "ataşehir", "ümraniye", "pendik", "kartal",
    "maltepe", "esenyurt", "bağcılar", "beylikdüzü", "şişli", "fatih", "bakırköy", "başakşehir",
    "beyoğlu", "sarıyer", "küçükçekmece", "avcılar", "bahçelievler", "esenler", "sultanbeyli",
    "tuzla", "çekmeköy", "zeytinburnu", "gaziosmanpaşa", "sultangazi", "eyüpsultan", "kağıthane")})


def _kucuk(x: str) -> str:
    return x.replace("I", "ı").replace("İ", "i").lower().strip()


def il(sehir: str) -> str:
    """Wix 'city' alanına çoğu müşteri İLÇE yazıyor (GÖLBAŞI, Mamak)."""
    k = _kucuk(sehir or "")
    if not k:
        return "?"
    if k in ILCE_IL:
        return ILCE_IL[k]
    return k[:1].upper().replace("i", "İ") + k[1:] if k[:1] != "i" else "İ" + k[1:]


def alici_analizi(siparisler: list[dict]) -> dict:
    gecerli = [o for o in siparisler if not _iptal_mi(o["durum"])]
    kisi = defaultdict(list)
    for o in gecerli:
        anahtar = (o["musteri_id"] and o["kanal"] + ":" + o["musteri_id"]) or \
                  (o["musteri"].lower() + "|" + o["sehir"].lower())
        kisi[anahtar].append(o)
    tekrar = [v for v in kisi.values() if len(v) > 1]
    urun = Counter()
    for o in gecerli:
        for x in o["kalemler"]:
            urun[x["kod"]] += x["adet"]
    sehir = Counter(il(o["sehir"]) for o in gecerli)
    saat = Counter(datetime.fromisoformat(o["zaman"]).hour for o in gecerli)
    ciro = sum(o["tutar"] for o in gecerli)
    liste = sum(o["liste_tutar"] for o in gecerli if o["liste_tutar"])
    return dict(
        siparis=len(gecerli), alici=len(kisi), tekrar_eden=len(tekrar),
        ort_sepet=round(ciro / len(gecerli), 2) if gecerli else 0,
        indirim_orani=round(100 * (1 - ciro / liste), 1) if liste else None,
        sehir=sehir.most_common(12), urun=urun.most_common(12),
        saat=sorted(saat.items()),
        kanal=Counter(o["kanal"] for o in gecerli).most_common())


def db_yaz(siparisler: list[dict]) -> None:
    satirlar = []
    for o in siparisler:
        satirlar.append(json.dumps(o, ensure_ascii=False))
    sql = """
CREATE TABLE IF NOT EXISTS core.alici_siparis (
  kanal text NOT NULL, siparis_no text NOT NULL, zaman timestamptz, durum text,
  tutar numeric(12,2), liste_tutar numeric(12,2), musteri text, musteri_id text,
  sehir text, ilce text, kalemler jsonb, guncellendi timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (kanal, siparis_no));
COMMENT ON TABLE core.alici_siparis IS 'Alici verisi (PII). Yalniz panel/analiz; disari ve CompanyMemory''ye cikmaz. scripts/reklam-olcum.py yazar.';
CREATE TEMP TABLE g (j jsonb);
COPY g FROM STDIN;
"""
    govde = sql + "\n".join(s.replace("\\", "\\\\") for s in satirlar) + "\n\\.\n" + """
INSERT INTO core.alici_siparis (kanal,siparis_no,zaman,durum,tutar,liste_tutar,musteri,musteri_id,sehir,ilce,kalemler)
SELECT j->>'kanal', j->>'no', (j->>'zaman')::timestamptz, j->>'durum', (j->>'tutar')::numeric,
       (j->>'liste_tutar')::numeric, j->>'musteri', j->>'musteri_id', j->>'sehir', j->>'ilce', j->'kalemler'
FROM g
ON CONFLICT (kanal, siparis_no) DO UPDATE SET durum=EXCLUDED.durum, tutar=EXCLUDED.tutar,
  liste_tutar=EXCLUDED.liste_tutar, kalemler=EXCLUDED.kalemler, guncellendi=now();
"""
    s = subprocess.run(["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
                        "-v", "ON_ERROR_STOP=1", "-tAq"], input=govde, capture_output=True, text=True)
    if s.returncode != 0:
        raise RuntimeError("psql: " + s.stderr.strip()[:300])


# ------------------------------------------------------------------ değerlendirme
def _tl(x: float) -> str:
    return ("{:,.0f}".format(x)).replace(",", ".") + " TL"


def degerlendirme(o: dict) -> list[str]:
    c = []
    t = o["toplam"]
    c.append("Son %d günde tüm kanallarda %d sipariş, %s ciro; reklama %s harcandı."
             % (GUN, t["siparis"], _tl(t["ciro"]), _tl(t["reklam"])))
    if t["reklam"]:
        c.append("Her 1 TL reklama karşılık %.2f TL satış var (tüm satış / tüm reklam). "
                 "Komisyon ve ürün maliyeti düşülmeden önceki oran; 3'ün altı genelde zarar demek."
                 % (t["ciro"] / t["reklam"]))
    son7 = o["son7"]
    c.append("Son 7 gün: %d sipariş, %s ciro, %s reklam." % (son7["siparis"], _tl(son7["ciro"]),
                                                            _tl(son7["reklam"])))
    for k in o["kampanyalar"]:
        if k["durum"] == "ACTIVE":
            s = k.get("satis")
            if s:
                c.append("Süren kampanya \"%s\": %s harcandı, %d tıklama, eşleşen %d sipariş / %s (ROAS %s)."
                         % (k["ad"], _tl(k["harcama"]), k["tiklama"], s["siparis"], _tl(s["ciro"]),
                            s["roas"]))
            else:
                c.append("Süren kampanya \"%s\": %s harcandı, %d tıklama."
                         % (k["ad"], _tl(k["harcama"]), k["tiklama"]))
    a = o["alicilar"]
    if a["indirim_orani"]:
        c.append("Pazaryerlerinde müşteri liste fiyatının ortalama %%%s altında ödedi (satıcı indirimi)."
                 % a["indirim_orani"])
    if a["tekrar_eden"]:
        c.append("%d alıcı birden fazla sipariş verdi." % a["tekrar_eden"])
    if o["okunamadi"]:
        c.append("⚠️ Okunamayan kaynak: %s — bu kanalların rakamı yukarıda YOK, sıfır değil."
                 % ", ".join(o["okunamadi"]))
    return c


def main() -> int:
    simdi = datetime.now(TR)
    bas = simdi - timedelta(days=GUN)
    siparisler, okunamadi, kanal_durum = [], [], {}
    for ad, islev in SATIS_KANALLARI.items():
        try:
            r = islev(bas, simdi)
            siparisler.extend(r)
            kanal_durum[ad] = "OK"
        except pazaryeri.KanalKapali:
            kanal_durum[ad] = "API_YOK"
        except Exception as hata:  # noqa: BLE001
            kanal_durum[ad] = "OKUNAMADI"
            okunamadi.append("%s (%s)" % (ad, type(hata).__name__))
    try:
        kampanyalar = meta_kampanyalar(bas, simdi)
        gunluk = meta_gunluk(bas, simdi)
    except Exception as hata:  # noqa: BLE001
        kampanyalar, gunluk = [], []
        okunamadi.append("Meta (%s)" % type(hata).__name__)
    eslestir(kampanyalar, siparisler)

    gecerli = [o for o in siparisler if not _iptal_mi(o["durum"])]
    kanallar = []
    for ad in SATIS_KANALLARI:
        oo = [o for o in gecerli if o["kanal"] == ad]
        kanallar.append(dict(kanal=ad, durum=kanal_durum.get(ad), siparis=len(oo),
                             ciro=round(sum(o["tutar"] for o in oo), 2),
                             son=max((o["zaman"] for o in oo), default=None)))
    reklam = sum(k["harcama"] for k in kampanyalar)
    yedi = (simdi - timedelta(days=7)).isoformat()
    son7_sip = [o for o in gecerli if o["zaman"] >= yedi]
    son7_rek = sum(g["harcama"] for g in gunluk if g["gun"] >= (simdi - timedelta(days=7)).strftime("%Y-%m-%d"))
    gunler = defaultdict(lambda: dict(siparis=0, ciro=0.0, reklam=0.0, tiklama=0))
    for o in gecerli:
        g = gunler[o["zaman"][:10]]
        g["siparis"] += 1
        g["ciro"] += o["tutar"]
    for r in gunluk:
        gunler[r["gun"]]["reklam"] += r["harcama"]
        gunler[r["gun"]]["tiklama"] += r["tiklama"]

    ozet = dict(
        olculdu=simdi.isoformat(), gun=GUN,
        toplam=dict(siparis=len(gecerli), ciro=round(sum(o["tutar"] for o in gecerli), 2),
                    reklam=round(reklam, 2)),
        son7=dict(siparis=len(son7_sip), ciro=round(sum(o["tutar"] for o in son7_sip), 2),
                  reklam=round(son7_rek, 2)),
        kanallar=kanallar,
        platformlar=[
            dict(platform="Meta (Facebook/Instagram)", durum="OK" if kampanyalar or not okunamadi else "OKUNAMADI",
                 harcama=round(reklam, 2), kampanya=len(kampanyalar),
                 tiklama=sum(k["tiklama"] for k in kampanyalar)),
            dict(platform="Trendyol mağaza reklamları", durum="PANELDEN",
                 not_="Trendyol'un reklam API'si yok; Satıcı Paneli > Reklam'dan okunur."),
            dict(platform="Trendyol panelinden Meta reklamı", durum="PANELDEN",
                 not_="Trendyol hesabından açılır; sonucu yalnız panelde."),
            dict(platform="Google Ads", durum="KAMPANYA_YOK",
                 not_="Henüz kampanya açılmadı (reklam görsellerinden sonra)."),
        ],
        kampanyalar=kampanyalar,
        gunluk=[dict(gun=k, **v) for k, v in sorted(gunler.items())][-30:],
        alicilar=alici_analizi(siparisler),
        okunamadi=okunamadi,
    )
    ozet["degerlendirme"] = degerlendirme(ozet)
    try:
        db_yaz(siparisler)
    except Exception as hata:  # noqa: BLE001
        ozet["okunamadi"].append("alıcı tablosu yazılamadı (%s)" % hata)
    DIZIN.mkdir(parents=True, exist_ok=True)
    gecici = DIZIN / "ozet.json.tmp"
    gecici.write_text(json.dumps(ozet, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(DIZIN / "ozet.json")
    for c in ozet["degerlendirme"]:
        print(c)
    return 1 if okunamadi else 0


if __name__ == "__main__":
    sys.exit(main())
