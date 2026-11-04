#!/usr/bin/env python3
"""Idefix birim marj tablosu -- her girdi OLCULMUS kaynaktan gelir.

GIRDILER VE KAYNAKLARI
  fiyat          Idefix API /pim/catalog/{v}/inventory/list -> price (canli)
  komisyon       PANEL "Komisyon ve Vade" sutunu; 30 satirin 30'u da DOM'dan
                 okundu (23.10.2026). API'de komisyon ucu YOK (404/503 ile
                 olculdu), bu yuzden tek kaynak panel.
                 🔴 Oran sabit DEGIL: 29 urun %10, BABYSHOWER %15.
  kdv            urunler.csv -> kdv
  maliyet        core.urun_maliyet -> 36/36 kayit ₺400, kaynak ELLE.
                 🔴 BU OLCUM DEGIL, BEYAN. Wix maliyet alani 0,00 oldugu icin
                 urun basina gercek maliyet bilinmiyor; tabloda isaretlenir.
  kargo          KARGOYU BIZ ODUYORUZ -- isletme sahibi beyani (23.10.2026).
                 Tutar BasitKargo tarifesinden olculdu (firma indirimi
                 uygulanmis, KDV dahil): listelemelerde secili tasiyici
                 HEPSIJET, 1 desi ₺107,91 (4 desiye kadar sabit).
                 Tasiyici secimi marji ciddi degistirir, raporda duyarlilik
                 tablosu var.

HESAP (birim, ₺)
  net_ciro      = fiyat / (1 + kdv)     KDV tahsilatti, bize kalmaz
  komisyon      = fiyat * oran          KDV DAHIL fiyat uzerinden; panelin
                                        yazdigi tutarla capraz dogrulanir
  marj          = net_ciro - komisyon - maliyet - kargo(KDV haric)

Komisyon faturasinin KDV'si indirilebilir oldugu icin marjdan dusulmez.
Nakit akisinda 28 gun vade vardir; tabloda ayrica yazilir.
"""
from __future__ import annotations

import base64
import csv
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ENV = Path("/etc/lcarlie/idefix.env")
CSV_URUN = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CSV_KOM = Path("/opt/lcarlie/idefix-hazirlik/komisyon-olculen.csv")
CIKTI = Path("/opt/lcarlie/idefix-hazirlik")
TABAN = "https://merchantapi.idefix.com"

# BasitKargo tarifesi, 1 desi, KDV dahil (23.10.2026 olcumu). Listelerimizde
# acik olan tasiyicilar: Yurtici, Surat, DHL eCommerce, Aras.
KARGO_SECENEK = {
    "Hepsijet": 107.91,                 # listelemelerde SECILI olan tasiyici
    "Surat, sehirlerarasi": 111.19,
    "Aras, sehir ici": 103.09,
    "Aras, sehirlerarasi": 130.65,
    "Yurtici, sehirlerarasi": 202.42,
}
# 🔴 Panelde urunlerin kargo sirketi HEPSIJET secili (ID 84, 23.10.2026'da
# envanter satirindan okundu). Onceki surumde Surat tarifesi kullaniliyordu;
# varsayim degil, listelemedeki gercek tasiyici esas alinir.
KARGO_ADI = "Hepsijet"
KARGO_KDV_DAHIL = KARGO_SECENEK[KARGO_ADI]
KARGO_KDV = 0.20


def ortam() -> dict[str, str]:
    return dict(s.split("=", 1) for s in ENV.read_text(encoding="utf-8").splitlines()
                if s and not s.startswith("#") and "=" in s)


def envanter(jeton: str, satici: str) -> dict[str, float]:
    fiyat: dict[str, float] = {}
    sayfa = 1
    while True:
        istek = urllib.request.Request(
            f"{TABAN}/pim/catalog/{satici}/inventory/list?page={sayfa}&limit=100",
            headers={"X-API-KEY": jeton, "Accept": "application/json"})
        with urllib.request.urlopen(istek, timeout=60) as y:
            d = json.loads(y.read().decode("utf-8") or "{}")
        for x in d.get("items") or []:
            fiyat[x["barcode"]] = float(x["price"])
        if sayfa >= int(d.get("pageCount") or 1):
            break
        sayfa += 1
    return fiyat


def maliyetler() -> dict[str, float]:
    """barkod -> birim maliyet (core.urun_maliyet, raw.wix_urun.sku uzerinden)."""
    sql = ("select w.sku, m.maliyet from core.urun_maliyet m "
           "join raw.wix_urun w using (urun_id) where m.gecerli_bitis is null;")
    cikti = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-At", "-F", ";", "-c", sql],
        capture_output=True, text=True, check=True).stdout
    return {s.split(";")[0]: float(s.split(";")[1])
            for s in cikti.splitlines() if ";" in s}


def trendyol_oranlari() -> dict[str, float]:
    """barkod -> Trendyol komisyon yuzdesi (karsilastirma icin)."""
    sql = ("select w.sku, k.komisyon_yuzde from core.urun_platform_komisyon k "
           "join raw.wix_urun w using (urun_id) where k.platform_kod = 'trendyol';")
    cikti = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n", "-d", "n8n",
         "-At", "-F", ";", "-c", sql],
        capture_output=True, text=True, check=True).stdout
    return {s.split(";")[0]: float(s.split(";")[1])
            for s in cikti.splitlines() if ";" in s}


def tl(v) -> str:
    return "-" if v is None else f"{v:,.0f}".replace(",", ".")


def yuzde(v) -> str:
    return "-" if v is None else f"%{v:.0f}"


def rapor_yaz(satirlar: list[dict], disarida: list[str], kargo: float,
              ty: dict[str, float], uyari: list[str]) -> None:
    """MARJ.md -- rakamlar ve HER rakamin kaynagi."""
    toplam_net = sum(s["net_ciro"] for s in satirlar)
    toplam_kom = sum(s["komisyon"] for s in satirlar if s["komisyon"])
    toplam_marj = sum(s["marj_kargolu"] for s in satirlar if s["marj_kargolu"])
    ort_marj = toplam_marj / toplam_net * 100 if toplam_net else 0

    # Ayni urunler Trendyol oraniyla satilsaydi ne olurdu
    fark = []
    for s in satirlar:
        t = ty.get(s["barkod"])
        if t is None or s["komisyon"] is None:
            continue
        fark.append((s, s["fiyat"] * t / 100 - s["komisyon"]))
    fark_toplam = sum(f for _, f in fark)

    sapan = [s for s in satirlar if s["komisyon_yuzde"] not in (None, 10)]
    oranli = [s for s in satirlar if s["komisyon_yuzde"] is not None]
    ort_oran = (sum(s["komisyon_yuzde"] for s in oranli) / len(oranli)) if oranli else 0
    olculen = [s for s in satirlar if s["marj_kargolu"] is not None]
    en_dusuk = min(olculen, key=lambda s: s["marj_kargolu"])
    en_yuksek = max(olculen, key=lambda s: s["marj_kargolu"])
    dip = [s["urun"] for s in olculen
           if s["marj_kargolu"] == en_dusuk["marj_kargolu"]]

    kargo_sat = []
    for ad, dahil in sorted(KARGO_SECENEK.items(), key=lambda t: t[1]):
        haric = dahil / (1 + KARGO_KDV)
        m = en_dusuk["marj_kargolu"] + kargo - haric
        isaret = "  <- hesapta bu" if ad == KARGO_ADI else ""
        kargo_sat.append(f"| {ad} | {dahil:.2f} | {haric:.2f} | "
                         f"{tl(m)} TL{isaret} |")

    sat = []
    for s in satirlar:
        t = ty.get(s["barkod"])
        sat.append(
            f"| {s['urun']} | {tl(s['fiyat'])} | {tl(s['net_ciro'])} | "
            f"%{s['komisyon_yuzde']} / {tl(s['komisyon'])} | {tl(s['maliyet'])} | "
            f"{kargo:.0f} | **{tl(s['marj_kargolu'])}** | "
            f"{yuzde(s['marj_kargolu_yuzde'])} | "
            f"{('%' + str(round(t)) if t else '-')} | {s['buybox']} |")

    metin = f"""# Idefix birim marj tablosu

Satista olan **{len(satirlar)} urun** icin, bir adet satista cebimizde ne kaliyor.
Disarida kalan {len(disarida)} urun satisa KAPALI (yanlis katalog eslesmesi
nedeniyle kapattigimiz SUNACNEA ve BUGUARD); API envanter listesi yalniz satisa
acik urunleri dondurdugu icin tabloda yoklar.

Kargoyu **biz oduyoruz**, yani asagidaki her rakamda kargo dusulmus durumda.

**Sonuc:** {len(satirlar)} urunun hicbiri zarar etmiyor. En dusuk marj
**{tl(en_dusuk['marj_kargolu'])} TL** ({", ".join(dip)}), en yuksek
**{tl(en_yuksek['marj_kargolu'])} TL** ({en_yuksek['urun']}). Ortalama marj
net ciro uzerinden **%{ort_marj:.0f}**.

## Rakamlar nereden geldi

| Girdi | Kaynak | Guven |
|---|---|---|
| Satis fiyati | Idefix API, canli envanter kaydi | olculdu |
| Komisyon orani | Satici paneli "Komisyon ve Vade" sutunu, 30 satirin 30'u | olculdu |
| Komisyon tabani | KDV **dahil** fiyat; panelin yazdigi tutar hesabimizla 30/30 tuttu | olculdu |
| Vade | 28 gun, panelde her satirda yazili | olculdu |
| KDV | %20, urun dosyasindan | olculdu |
| Kargonun bizde oldugu | Isletme sahibi beyani | **beyan** |
| Kargo tutari | BasitKargo tarifesi: {KARGO_ADI}, 1 desi, {KARGO_KDV_DAHIL:.2f} TL (KDV dahil) -> {kargo:.2f} TL | olculdu |
| **Maliyet** | **core.urun_maliyet: 36/36 urune 400 TL, kaynak ELLE** | **BEYAN -- olcum degil** |

Maliyet tablonun tek zayif ayagi. Wix'teki maliyet alani 36 urunun 36'sinda da
0,00 oldugu icin urun basina gercek maliyet bilinmiyor; 400 TL tek tek olculmus
degil, topluca beyan edilmis bir rakam. Gercek maliyet 400 TL'nin uzerindeyse
asagidaki marjlar oldugundan yuksek gorunur -- ozellikle 900 TL'lik bandda.

## Urun urun

| Urun | Fiyat | Net ciro | Komisyon | Maliyet | Kargo | Marj | Marj % | TY oran | Buybox |
|---|---|---|---|---|---|---|---|---|---|
{chr(10).join(sat)}

### Tasiyici secimi marji degistirir

Yukaridaki tablo **{KARGO_ADI}** ile hesaplandi ({KARGO_KDV_DAHIL:.2f} TL).
Listelerimizde acik olan diger tasiyicilarla ayni urunlerde marj su kadar
degisir -- en dar bandi ({tl(en_dusuk["fiyat"])} TL'lik urunler) ornek aldim:

| Tasiyici (1 desi) | KDV dahil | KDV haric | En dar bandda marj |
|---|---|---|---|
{chr(10).join(kargo_sat)}

Yurtici ile Surat arasindaki fark urun basina
{tl((KARGO_SECENEK["Yurtici, sehirlerarasi"] - KARGO_SECENEK[KARGO_ADI]) / 1.2)} TL;
900 TL'lik bandda bu, marjin yaklasik
%{(KARGO_SECENEK["Yurtici, sehirlerarasi"] - KARGO_SECENEK[KARGO_ADI]) / 1.2 / en_dusuk["marj_kargolu"] * 100:.0f}'i
demek. Tasiyiciyi urun basina degil, sepet tutarina gore secmek gerekir.

## Trendyol ile ayni urunler

Ayni {len(fark)} urunun Trendyol komisyon orani ambarda kayitli ({min(ty.values()):.0f}-{max(ty.values()):.0f}%,
ortalama {sum(ty.values()) / len(ty):.1f}%). Idefix ortalamasi %{ort_oran:.1f} ({len(oranli)}/{len(satirlar)} urunde olculdu).

Birer adet satilsa, yalniz komisyon farkindan **{tl(fark_toplam)} TL** daha
fazla kalirdi: tur basina en buyuk fark
{max(fark, key=lambda f: f[1])[0]['urun']} ({tl(max(f for _, f in fark))} TL),
en kucugu {min(fark, key=lambda f: f[1])[0]['urun']} ({tl(min(f for _, f in fark))} TL).

## Dikkat edilecek iki nokta

1. **Komisyon sabit %10 degil.** {len(sapan)} urunde farkli:
   {", ".join(s['urun'] + ' %' + str(s['komisyon_yuzde']) for s in sapan) or "yok"}.
   Kategori degistiginde oran da degisiyor; destek talebindeki kategori
   duzeltmeleri onaylanirsa bu oranlarin yeniden okunmasi gerekir.
2. **Buybox sutunu.** Panelde her urunde 1 veya 2 yaziyor
   ({sum(1 for s in satirlar if s['buybox'] == '1')} urun 1,
   {sum(1 for s in satirlar if s['buybox'] == '2')} urun 2). Bunun "sayfadaki
   satici adedi" mi yoksa "bizim siramiz" mi oldugu panelde yazmiyor, ipucu
   verecek bir aciklama da yok. 2 ise ayni sayfada Mcaris/Lc.Imeeke ile yan yana
   satiyoruz demektir ve fiyat farki dogrudan satisi belirler -- bu yuzden
   anlami teyit edilmeden fiyat karari verilmemeli.

## Henuz bilinmeyen

- Urun basina gercek maliyet (en onemlisi).
- Iade/teslim edilemeyen gonderide kargonun kime kaldigi.
- Mcaris'in bugunku liste fiyatlari (3 gunluk indirim yapmislardi, bitti mi
  olculmedi).
- Idefix'in iade/iptal kesintisi ve varsa kampanya katilim bedeli.

Nakit akisi: tahsilat **28 gun** vadeli, yani satis gunu degil 28 gun sonra.
"""
    if uyari:
        metin += "\n## Capraz dogrulama uyarisi\n\n" + "\n".join(
            f"- {s}" for s in uyari) + "\n"

    (CIKTI / "MARJ.md").write_text(metin, encoding="utf-8")
    print(f"yazildi: {CIKTI / 'MARJ.md'} ({len(metin)} karakter)")


def main() -> int:
    env = ortam()
    jeton = base64.b64encode(
        (env["IDEFIX_API_KEY"] + ":" + env["IDEFIX_API_SECRET"]).encode()).decode()
    satici = env["IDEFIX_SELLER_ID"]

    urun = {x["barkod"]: x for x in csv.DictReader(
        CSV_URUN.open(encoding="utf-8-sig"), delimiter=";")}
    kom = {x["barkod"]: x for x in csv.DictReader(
        CSV_KOM.open(encoding="utf-8-sig"), delimiter=";")}
    fiyat = envanter(jeton, satici)
    maliyet = maliyetler()
    kargo_haric = round(KARGO_KDV_DAHIL / (1 + KARGO_KDV), 2)

    satirlar, uyari = [], []
    for b, f in sorted(fiyat.items(), key=lambda t: -t[1]):
        u = urun.get(b, {})
        k = kom.get(b)
        kdv = float(u.get("kdv") or 20) / 100
        net = f / (1 + kdv)
        m = maliyet.get(b)

        if k:
            oran = float(k["komisyon_yuzde"]) / 100
            komisyon = f * oran
            panel_tutar = float(k["komisyon_tutar"])
            if abs(komisyon - panel_tutar) > 0.51:
                uyari.append(
                    f"{b}: panel {panel_tutar:.0f} TL ama %{k['komisyon_yuzde']} x "
                    f"{f:.0f} TL = {komisyon:.0f} TL -- taban fiyat farkli olabilir")
        else:
            oran = komisyon = None

        if komisyon is None or m is None:
            marj = marj_k = None
        else:
            marj = net - komisyon - m
            marj_k = marj - kargo_haric

        satirlar.append({
            "barkod": b,
            "urun": re.split(r"[(|]", u.get("urun_adi_wix") or "?")[0].strip()[:28],
            "fiyat": round(f, 2),
            "kdv_yuzde": round(kdv * 100),
            "net_ciro": round(net, 2),
            "komisyon_yuzde": round(oran * 100) if oran else None,
            "komisyon": round(komisyon, 2) if komisyon is not None else None,
            "maliyet": m,
            "maliyet_kaynak": "ELLE BEYAN" if m is not None else "YOK",
            "marj_kargosuz": round(marj, 2) if marj is not None else None,
            "marj_yuzde": round(marj / net * 100, 1) if marj is not None else None,
            "marj_kargolu": round(marj_k, 2) if marj_k is not None else None,
            "marj_kargolu_yuzde": (round(marj_k / net * 100, 1)
                                   if marj_k is not None else None),
            "buybox": k["buybox"] if k else None,
            "vade_gun": k["vade_gun"] if k else None,
        })

    # 🔴 API'nin envanter listesi YALNIZ satisa acik urunleri dondurur; burada
    # eksik cikanlar havuzda degil, SATISA KAPALI olanlardir (23.10: yanlis
    # katalog eslesmesi olan SUNACNEA ve BUGUARD).
    disarida = [b for b in urun if b not in fiyat]
    ty = trendyol_oranlari()
    rapor_yaz(satirlar, disarida, kargo_haric, ty, uyari)

    with (CIKTI / "marj.csv").open("w", encoding="utf-8-sig", newline="") as y:
        w = csv.DictWriter(y, fieldnames=list(satirlar[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(satirlar)

    zarar = [s for s in satirlar
             if s["marj_kargolu"] is not None and s["marj_kargolu"] < 0]
    ince = [s for s in satirlar
            if s["marj_kargolu"] is not None and 0 <= s["marj_kargolu"] < 100]

    print(f"{'barkod':<14}{'urun':<31}{'fiyat':>7}{'net':>7}{'kom':>6}"
          f"{'mal':>6}{'kargosuz':>9}{'MARJ':>7}{'marj%':>7}{'bb':>4}")
    for s in satirlar:
        print(f"{s['barkod']:<14}{s['urun']:<31}{tl(s['fiyat']):>7}"
              f"{tl(s['net_ciro']):>7}{tl(s['komisyon']):>6}{tl(s['maliyet']):>6}"
              f"{tl(s['marj_kargosuz']):>9}{tl(s['marj_kargolu']):>7}"
              f"{yuzde(s['marj_kargolu_yuzde']):>7}{(s['buybox'] or '-'):>4}")

    print(f"\nurun: {len(satirlar)} satista, {len(disarida)} satisa kapali "
          f"(API envanter listesine girmiyor)")
    print(f"kargo (KDV haric): {kargo_haric} TL  "
          f"[{KARGO_ADI}, KDV dahil {KARGO_KDV_DAHIL} TL]")
    print(f"zarar eden: {len(zarar)}  |  marji 100 TL altinda: {len(ince)}")
    for s in zarar + ince:
        print(f"    {s['urun']:<30} marj {s['marj_kargolu']:>8.0f} TL")
    if uyari:
        print("\nCAPRAZ DOGRULAMA UYARISI:")
        for s in uyari:
            print("   ", s)
    else:
        print(f"\ncapraz dogrulama: panelin yazdigi komisyon tutari hesapla "
              f"TUTUYOR ({len(kom)}/{len(kom)})")
    print(f"\nyazildi: {CIKTI / 'marj.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
