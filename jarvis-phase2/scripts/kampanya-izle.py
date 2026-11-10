#!/usr/bin/env python3
"""KAMPANYA IZLEME — kendi Meta hesabindan Trendyol'a giden kampanyayi denetler.

Neden: Meta ETL'i (ticari-kontrol.sh) gunde bir kez 08:30'da calisir. Bir
kampanyanin ilk saatlerinde reklam reddi, teslim olmamasi veya pahali tiklama
sabaha kadar gorunmez. Bu betik birkac saatte bir:
  1. Meta'dan reklam durumunu (inceleme/red) ve kampanya basindan beri
     reklam bazinda performansi canli okur,
  2. Trendyol API'sinden kampanya urunlerinin siparislerini sayar
     (Trendyol'da pikselimiz yok; satis yalniz buradan olculur),
  3. Esiklere gore uyari uretir, YENI uyariyi push + e-posta ile bildirir,
  4. --ozet ile tam raporu e-postayla gonderir.

🔴 Esikler kampanya dosyasindadir (state/kampanya-izle/<ad>.json), kodda degil.
🔴 Ayni uyari iki kez bildirilmez: anahtarlar durum dosyasinda tutulur.
🔴 Okunamayan kaynak "veri yok" sayilmaz; raporda OKUNAMADI diye yazilir.

Kullanim:
  kampanya-izle.py 1111            (denetle, yeni uyariyi bildir)
  kampanya-izle.py 1111 --ozet     (denetle + tam raporu e-postayla gonder)
  kampanya-izle.py 1111 --kuru     (yalniz ekrana yaz, bildirme, kaydetme)
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from jarvis import haberci, pazaryeri  # noqa: E402

TR = timezone(timedelta(hours=3))
G = "https://graph.facebook.com/v21.0"
DIZIN = KOK / "state" / "kampanya-izle"


def _tl(deger) -> str:
    return ("%.2f" % float(deger or 0)).replace(".", ",") + " TL"


def meta(yol: str, sorgu: dict) -> dict:
    jeton = pazaryeri._n8n_env("META_ADS_TOKEN")
    url = "%s/%s?%s" % (G, yol, urllib.parse.urlencode(sorgu))
    return json.loads(pazaryeri._istek(url, {"Authorization": "Bearer " + jeton}))


def meta_oku(k: dict, bas: datetime) -> dict:
    reklamlar = meta("%s/ads" % k["kampanya_id"], {
        "fields": "name,effective_status,ad_review_feedback,"
                  "adset{name,daily_budget,start_time,end_time}",
        "limit": 100})["data"]
    bugun = datetime.now(TR).date().isoformat()
    if bugun < bas.date().isoformat():
        # Baslamadan once yalniz inceleme durumu anlamlidir; Meta gelecek
        # tarihli araligi reddeder.
        return dict(reklamlar=reklamlar, toplam={}, bugun={})
    aralik = json.dumps({"since": bas.date().isoformat(), "until": bugun})
    alan = ("ad_id,ad_name,adset_name,spend,impressions,reach,frequency,"
            "inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click,cpm")
    toplam = meta("%s/insights" % k["kampanya_id"], {
        "level": "ad", "fields": alan, "time_range": aralik, "limit": 100})["data"]
    gunluk = meta("%s/insights" % k["kampanya_id"], {
        "level": "ad", "fields": "ad_id,spend,inline_link_clicks",
        "time_range": json.dumps({"since": bugun, "until": bugun}), "limit": 100})["data"]
    return dict(reklamlar=reklamlar, toplam={r["ad_id"]: r for r in toplam},
                bugun={r["ad_id"]: r for r in gunluk})


def trendyol_oku(barkodlar: set[str], bas: datetime, son: datetime) -> list[dict]:
    e = pazaryeri.env_oku("/etc/lcarlie/trendyol.env")
    sid = e["TRENDYOL_SELLER_ID"]
    yetki = base64.b64encode(("%s:%s" % (e["TRENDYOL_API_KEY"],
                                         e["TRENDYOL_API_SECRET"])).encode()).decode()
    basliklar = {"Authorization": "Basic " + yetki,
                 "User-Agent": "%s - SelfIntegration" % sid}
    cikti, sayfa = [], 0
    # Trendyol tarih filtresi en fazla iki haftalik araligi kabul eder.
    while True:
        url = ("https://apigw.trendyol.com/integration/order/sellers/%s/orders"
               "?startDate=%d&endDate=%d&size=200&page=%d"
               % (sid, bas.timestamp() * 1000, son.timestamp() * 1000, sayfa))
        veri = json.loads(pazaryeri._istek(url, basliklar))
        for p in veri.get("content") or []:
            if str(p.get("status") or "").lower().startswith(("cancel", "unsupplied")):
                continue
            for s in p.get("lines") or []:
                if str(s.get("barcode")) in barkodlar:
                    cikti.append(dict(siparis=str(p.get("orderNumber")),
                                      barkod=str(s.get("barcode")),
                                      adet=int(s.get("quantity") or 0),
                                      tutar=float(s.get("amount") or s.get("price") or 0)))
        sayfa += 1
        if sayfa >= int(veri.get("totalPages") or 0):
            return cikti


def degerlendir(k: dict, m: dict | None, satis: list[dict] | None,
                simdi: datetime) -> tuple[list[dict], list[str]]:
    """Uyarilar (anahtar, seviye, metin) ve rapor satirlari."""
    e = k["esikler"]
    bas = datetime.fromisoformat(k["baslangic"])
    uyari, satir = [], []
    if m is None:
        uyari.append(dict(anahtar="meta-okunamadi-%s" % simdi.date(), seviye="KRITIK",
                          metin="Meta reklam verisi okunamadı; kampanya durumu bilinmiyor."))
    else:
        saat = (simdi - bas).total_seconds() / 3600
        setler: dict[str, dict] = {}
        for r in m["reklamlar"]:
            t = m["toplam"].get(r["id"], {})
            g = m["bugun"].get(r["id"], {})
            durum = r["effective_status"]
            ad = r["name"]
            s = setler.setdefault(r["adset"]["name"], dict(
                butce=int(r["adset"].get("daily_budget") or 0) / 100, harcama=0.0, bugun=0.0))
            s["harcama"] += float(t.get("spend") or 0)
            s["bugun"] += float(g.get("spend") or 0)
            if durum in ("DISAPPROVED", "WITH_ISSUES"):
                uyari.append(dict(anahtar="red-%s" % r["id"], seviye="KRITIK",
                                  metin="%s REDDEDİLDİ/sorunlu (%s). Ads Manager'da gerekçeye bak, metni düzeltip yeniden gönder."
                                  % (ad, json.dumps(r.get("ad_review_feedback") or {}, ensure_ascii=False)[:200])))
            elif durum == "PENDING_REVIEW" and saat > e["inceleme_saat"]:
                uyari.append(dict(anahtar="inceleme-%s" % r["id"], seviye="UYARI",
                                  metin="%s başlangıçtan %d saat sonra hâlâ incelemede." % (ad, saat)))
            gos = int(t.get("impressions") or 0)
            tik = int(t.get("inline_link_clicks") or 0)
            ctr = float(t.get("inline_link_click_ctr") or 0)
            cpc = float(t.get("cost_per_inline_link_click") or 0)
            frek = float(t.get("frequency") or 0)
            satir.append("%-44s %-15s %7s gös %5d tık  CTR %%%.2f  TBM %s  frek %.1f  bugün %s"
                         % (ad[:44], durum[:15], gos, tik, ctr, _tl(cpc), frek, _tl(g.get("spend"))))
            if gos >= e["en_az_gosterim"]:
                if ctr < e["ctr_alt"]:
                    uyari.append(dict(anahtar="ctr-%s" % r["id"], seviye="UYARI",
                                      metin="%s zayıf: %d gösterimde bağlantı CTR %%%.2f (eşik %%%.2f). Görseli/ilk satırı değiştirmeyi ya da bütçeyi diğer reklama kaydırmayı düşün."
                                      % (ad, gos, ctr, e["ctr_alt"])))
                if cpc > e["tbm_ust"]:
                    uyari.append(dict(anahtar="tbm-%s" % r["id"], seviye="UYARI",
                                      metin="%s pahalı: tıklama başı %s (eşik %s)." % (ad, _tl(cpc), _tl(e["tbm_ust"]))))
            if frek > e["frekans_ust"]:
                uyari.append(dict(anahtar="frekans-%s" % r["id"], seviye="UYARI",
                                  metin="%s aynı kişiye ortalama %.1f kez gösterildi; reklam yorgunluğu başlıyor." % (ad, frek)))
        for ad, s in setler.items():
            if saat > e["teslim_saat"] and s["harcama"] == 0:
                uyari.append(dict(anahtar="teslim-%s" % ad, seviye="KRITIK",
                                  metin="%s başlangıçtan %d saat sonra HİÇ harcamadı; teslim yok." % (ad, saat)))
        toplam_harcama = sum(s["harcama"] for s in setler.values())
        toplam_tik = sum(int(t.get("inline_link_clicks") or 0) for t in m["toplam"].values())
        satir.insert(0, "Harcama (başlangıçtan beri): %s · bağlantı tıklaması: %d"
                     % (_tl(toplam_harcama), toplam_tik))
        for ad, s in setler.items():
            satir.insert(1, "  %-28s bugün %s / günlük bütçe %s · toplam %s"
                         % (ad[:28], _tl(s["bugun"]), _tl(s["butce"]), _tl(s["harcama"])))
        if satis is not None and toplam_tik >= e["satissiz_tik"] and not satis:
            uyari.append(dict(anahtar="satissiz-%d" % (toplam_tik // e["satissiz_tik"]), seviye="UYARI",
                              metin="%d bağlantı tıklaması geldi ama kampanya ürünlerinden Trendyol siparişi yok. Trendyol sayfasını (fiyat, %%30, stok, yorum) kontrol et."
                              % toplam_tik))
        if satis:
            ciro = sum(x["tutar"] for x in satis)
            satir.append("ROAS (Trendyol cirosu / Meta harcaması): %s"
                         % ("%.2f" % (ciro / toplam_harcama) if toplam_harcama else "-"))
    if satis is None:
        uyari.append(dict(anahtar="trendyol-okunamadi-%s" % simdi.date(), seviye="UYARI",
                          metin="Trendyol siparişleri okunamadı; satış bilinmiyor (sıfır değil)."))
        satir.append("Trendyol satış: OKUNAMADI")
    else:
        adlar = {b: a for a, b in k["urunler"].items()}
        adet: dict[str, int] = {}
        for x in satis:
            adet[adlar[x["barkod"]]] = adet.get(adlar[x["barkod"]], 0) + x["adet"]
        satir.append("Trendyol satış (kampanya ürünleri, başlangıçtan beri): %d sipariş, %d adet, %s · %s"
                     % (len({x["siparis"] for x in satis}), sum(adet.values()),
                        _tl(sum(x["tutar"] for x in satis)),
                        ", ".join("%s %d" % kv for kv in sorted(adet.items())) or "-"))
        satir.append("Karşılaştırma: kampanya öncesi 14 günde bu ürünlerden %s Trendyol siparişi vardı."
                     % k.get("onceki_14_gun_siparis", "?"))
    return uyari, satir


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("kampanya")
    a.add_argument("--ozet", action="store_true")
    a.add_argument("--kuru", action="store_true")
    arg = a.parse_args()
    dosya = DIZIN / ("%s.json" % arg.kampanya)
    k = json.loads(dosya.read_text(encoding="utf-8"))
    durum_yolu = DIZIN / ("%s.durum.json" % arg.kampanya)
    durum = json.loads(durum_yolu.read_text(encoding="utf-8")) if durum_yolu.exists() else {"bildirilen": []}

    simdi = datetime.now(TR)
    bas = datetime.fromisoformat(k["baslangic"])
    son = min(simdi, datetime.fromisoformat(k["bitis"]))
    if simdi > son + timedelta(days=2) and not arg.kuru:
        # Zamanlayici kapatilmasa da biten kampanya icin bildirim uretmez.
        print("Kampanya %s tarihinde bitti; izleme durdu." % son)
        return 0
    if simdi < bas:
        print("Kampanya henüz başlamadı (%s)." % bas)
    try:
        m = meta_oku(k, bas)
    except Exception as h:                              # noqa: BLE001
        print("META HATA:", str(h)[:200], file=sys.stderr)
        m = None
    try:
        satis = trendyol_oku(set(k["urunler"].values()), bas, son) if simdi >= bas else []
    except Exception as h:                              # noqa: BLE001
        print("TRENDYOL HATA:", str(h)[:200], file=sys.stderr)
        satis = None

    uyari, satir = degerlendir(k, m, satis, simdi)
    yeni = [u for u in uyari if u["anahtar"] not in durum["bildirilen"]]
    baslik = "%s · %s" % (k["ad"], simdi.strftime("%d.%m %H:%M"))
    rapor = "\n".join([baslik, ""] + satir + ["", "UYARILAR:" if uyari else "Uyarı yok."]
                      + ["• [%s] %s" % (u["seviye"], u["metin"]) for u in uyari]
                      + ["", "Trendyol panelindeki Meta reklamının sonuçları API'de yok; panelde Reklam > Meta Reklamları'ndan bakılır."])
    print(rapor)
    if arg.kuru:
        return 0

    gonderildi = []
    if yeni:
        metin = "\n".join("• " + u["metin"] for u in yeni)
        for yol, islev in (("push", lambda: haberci.push_gonder("Reklam uyarısı: " + k["ad"], metin, "kampanya-" + arg.kampanya)),
                           ("eposta", lambda: haberci.eposta_gonder("Reklam uyarısı · " + baslik, metin + "\n\n" + rapor))):
            try:
                islev()
                gonderildi.append(yol)
            except Exception as h:                      # noqa: BLE001
                print("%s gönderilemedi: %s" % (yol, str(h)[:120]), file=sys.stderr)
        # En az bir yol ulastiysa bildirildi sayilir; hicbiri ulasmadiysa
        # bir sonraki calismada yeniden denenir.
        if gonderildi:
            durum["bildirilen"] += [u["anahtar"] for u in yeni]
    if arg.ozet:
        try:
            haberci.eposta_gonder("Reklam özeti · " + baslik, rapor)
            gonderildi.append("ozet")
        except Exception as h:                          # noqa: BLE001
            print("özet gönderilemedi: %s" % str(h)[:120], file=sys.stderr)

    durum["son"] = dict(zaman=simdi.isoformat(), uyari=len(uyari), yeni=len(yeni),
                        gonderildi=gonderildi, rapor=rapor)
    durum_yolu.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")
    with (DIZIN / ("%s.gecmis.jsonl" % arg.kampanya)).open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(zaman=simdi.isoformat(), satir=satir,
                                uyari=[u["anahtar"] for u in uyari]), ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
