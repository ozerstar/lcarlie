#!/usr/bin/env python3
"""Idefix urun yukleme HAZIRLIK tablosu. Hicbir sey yuklemez, dosya uretir.

NE URETIR
  idefix-hazirlik/urunler.csv   36 urun x Excel'in istedigi alanlar
  idefix-hazirlik/RAPOR.md      engeller, mevzuat bulgulari, eksikler

NEDEN ONCE BU
Idefix'te urun bilgisi API ile GUNCELLENEMIYOR ("API servisleri uzerinden
urune ait yalniz stok-fiyat guncellemeleri yapilabilmektedir"). Yani yanlis
baslik/aciklama yuklenirse panelden elle duzeltilir. Bu yuzden mevzuat
taramasi yuklemeden ONCE calisir.

KATEGORI
Kategori ADAYI uretir, karari vermez. 6315 yaprak icinden urun adi/aciklamasi
ile en cok ortusen 3 aday siralanir; dogru yapragi secmek sahibin isi --
kategori komisyonu ve zorunlu ozellikleri belirler.

Girdiyi KENDISI ceker: raw.wix_urun dokumu her kosuda yenilenir, Idefix
kategori agaci 24 saatten eskiyse tazelenir. (Bayat girdi 22.10'da yanlis
rapor uretti; bir daha olmasin diye.)
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import compliance  # noqa: E402

CIKTI = Path("/opt/lcarlie/idefix-hazirlik")
GORSEL_DIZIN = Path("/opt/lcarlie/urun-gorsel")
GORSEL_TABAN = "https://n8n.lcarlie.shop/urun-gorsel"
KDV = 20
# Idefix hesabi LEMOS Medikal Saglik; bu iki ust kategori disi aranmaz.
KOK = {44: "Kozmetik & Kişisel Bakım", 11: "Anne Bebek Çocuk"}


def sade(metin: str) -> str:
    """Turkce'ye duyarli katlama. Kodda tam kelime karsilastirmasi yapilmaz."""
    metin = metin.replace("İ", "i").replace("I", "ı")
    metin = metin.casefold()
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return metin.replace("ı", "i").replace("ğ", "g").replace("ş", "s")


def metne_cevir(html_metin: str) -> str:
    duz = re.sub(r"<br\s*/?>", "\n", html_metin or "")
    duz = re.sub(r"</(p|h\d|li|div)>", "\n", duz)
    duz = re.sub(r"<[^>]+>", " ", duz)
    duz = html.unescape(duz)
    return re.sub(r"[ \t]+", " ", duz).strip()


def yapraklar(agac, yol=()):
    for dugum in agac or []:
        y = yol + (dugum["name"],)
        alt = dugum.get("subs") or []
        if alt:
            yield from yapraklar(alt, y)
        else:
            yield dugum["id"], " > ".join(y)


def gorseller(ham: dict) -> list[str]:
    cikti = []
    medya = (ham.get("media") or {})
    for oge in (medya.get("items") or []):
        url = ((oge.get("image") or {}).get("url")
               or (oge.get("mediaType") == "image" and oge.get("url")) or "")
        if url:
            cikti.append(url)
    if not cikti:
        ana = (medya.get("mainMedia") or {}).get("image", {}).get("url")
        if ana:
            cikti.append(ana)
    return cikti


URUN_JSON = Path("/tmp/idefix-urun.json")
KAT_JSON = Path("/tmp/idefix-kat.json")

URUN_SQL = ("select coalesce(json_agg(json_build_object("
            "'sku',sku,'ad',ad,'fiyat',fiyat,'stok_adet',stok_adet,'ham',ham))::text,'[]') "
            "from raw.wix_urun;")


def girdileri_tazele() -> None:
    """Urun dokumunu HER KOSUDA yeniden al.

    22.10.2026'da tam bu yuzden yanlis rapor uretildi: Wix'teki SKU duzeltildi,
    ayna tazelendi, ama betik /tmp'deki BAYAT dokumu okuyup kapanmis barkod
    cakismasini hala "engel" diye yazdi. Girdiyi disaridan beklemek yerine
    kendisi cekiyor; bayat veri sessizce rapora giremez.
    """
    import subprocess
    cikti = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres",
         "psql", "-U", "n8n", "-d", "n8n", "-At", "-f", "-"],
        input=URUN_SQL, capture_output=True, text=True, check=True)
    veri = cikti.stdout.strip()
    if not veri.startswith("["):
        raise SystemExit("urun dokumu alinamadi: " + (cikti.stderr or veri)[:200])
    URUN_JSON.write_text(veri, encoding="utf-8")

    # Kategori agaci gunde bir yeter; yoksa veya 24 saatten eskiyse cekilir.
    import time
    bayat = (not KAT_JSON.exists()
             or time.time() - KAT_JSON.stat().st_mtime > 86400)
    if bayat:
        env = dict(satir.split("=", 1) for satir in
                   Path("/etc/lcarlie/idefix.env").read_text(encoding="utf-8").splitlines()
                   if satir and not satir.startswith("#") and "=" in satir)
        import base64
        import urllib.request
        jeton = base64.b64encode(
            (env["IDEFIX_API_KEY"] + ":" + env["IDEFIX_API_SECRET"]).encode()).decode()
        istek = urllib.request.Request(
            "https://merchantapi.idefix.com/pim/product-category",
            headers={"X-API-KEY": jeton, "Accept": "application/json"})
        with urllib.request.urlopen(istek, timeout=60) as yanit:
            KAT_JSON.write_bytes(yanit.read())


def main() -> int:
    girdileri_tazele()
    urunler = json.loads(URUN_JSON.read_text(encoding="utf-8"))
    agac = json.loads(KAT_JSON.read_text(encoding="utf-8"))

    havuz = [(kid, yol) for kid, yol in yapraklar(agac)
             if yol.split(" > ")[0] in KOK.values()]
    havuz_sade = [(kid, yol, set(sade(yol.split(" > ")[-1]).split())) for kid, yol in havuz]

    CIKTI.mkdir(parents=True, exist_ok=True)
    satirlar, bulgular, engeller = [], [], []
    barkod_sayaci: dict[str, list[str]] = {}

    for u in urunler:
        ad = (u.get("ad") or "").strip()
        barkod = (u.get("sku") or "").strip()
        barkod_sayaci.setdefault(barkod, []).append(ad)

        aciklama = metne_cevir((u.get("ham") or {}).get("description", ""))
        # Gorsel kaynagi: Kontrollu V2 TRENDYOL seti (1200x1800), barkod adiyla
        # /opt/lcarlie/urun-gorsel altinda duruyor ve Caddy'den HTTPS servis
        # ediliyor. Idefix "images.url" istiyor; SSL sart, barkod basina <=8.
        # Dosya DISKTE yoksa URL uretilmez -- var sayilmaz, bakilir.
        gorsel = [f"{GORSEL_TABAN}/{barkod}-{i:02d}.jpg"
                  for i in range(1, 6)
                  if (GORSEL_DIZIN / f"{barkod}-{i:02d}.jpg").exists()]
        if not gorsel:  # yedek: Wix medyasindaki eski gorseller
            gorsel = gorseller(u.get("ham") or {})

        # --- mevzuat: kademe 1 tarama ---
        # Baslik ve aciklama AYRI AYRI taranmaz: "zorunlu ibare" kurallari
        # ibarenin YOKLUGUNU bulgu sayar, baslik tek basina tarandiginda
        # SUNACNEA'nin SPF'i yuzunden dort ibare birden "eksik" gorunurdu --
        # oysa o ibareler aciklamada duruyor. Musterinin gordugu sey tek bir
        # listeleme metnidir; tarama da onun uzerinde yurur.
        listeleme = ad + "\n\n" + aciklama
        inceleme = compliance.review(listeleme)
        etiketler = []
        for bulgu in inceleme.findings:
            nerede = "BASLIK" if bulgu.matched and bulgu.matched in ad else "ACIKLAMA"
            etiketler.append(f"{nerede}:{bulgu.label}")
            bulgular.append({
                "urun": ad, "yer": nerede, "etiket": bulgu.label,
                "kural": bulgu.rule, "ifade": bulgu.matched,
                "cumle": (bulgu.sentence or "")[:140],
                "cozum": bulgu.remedy,
            })

        # --- kategori adaylari: yaprak adiyla kelime ortusmesi ---
        anahtar = set(sade(ad + " " + aciklama[:400]).split())
        puanli = sorted(
            ((len(kelimeler & anahtar), kid, yol) for kid, yol, kelimeler in havuz_sade),
            reverse=True)
        adaylar = [f"{kid} | {yol}" for puan, kid, yol in puanli[:3] if puan > 0]

        satirlar.append({
            "barkod": barkod,
            "urun_adi_wix": ad,
            "idefix_baslik": "",          # mevzuat denetiminden sonra ELLE
            "kategori_adaylari": " || ".join(adaylar) or "ADAY YOK",
            "kategori_secimi": "",        # sahip secer
            # Idefix'e 22.10.2026'da bu yazimla talep acildi; Trendyol'daki
            # onayli kayit ve Wix ham->>'brand' de birebir boyle (É yok).
            "marka": "L'CARLIE",
            "marka_id": "TALEP BEKLIYOR -- idefix-marka-kontrol.sh",
            "stok_kodu": barkod,
            "fiyat": u.get("fiyat"),
            "kdv": KDV,
            "stok": int(float(u.get("stok_adet") or 0)),
            "gorsel_adet": len(gorsel),
            "gorsel_1": gorsel[0] if len(gorsel) > 0 else "",
            "gorsel_2": gorsel[1] if len(gorsel) > 1 else "",
            "gorsel_3": gorsel[2] if len(gorsel) > 2 else "",
            "gorsel_4": gorsel[3] if len(gorsel) > 3 else "",
            "gorsel_5": gorsel[4] if len(gorsel) > 4 else "",
            "aciklama_karakter": len(aciklama),
            "mevzuat": ";".join(sorted(set(etiketler))) or "kademe1-temiz",
        })

    for barkod, adlar in barkod_sayaci.items():
        if len(adlar) > 1:
            engeller.append(f"Ayni barkod {barkod} iki urunde: {' / '.join(adlar)}. "
                            "Idefix'te barkod birincil anahtardir -- ikisi birden yuklenemez.")

    with (CIKTI / "urunler.csv").open("w", encoding="utf-8-sig", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=list(satirlar[0].keys()), delimiter=";")
        yazici.writeheader()
        yazici.writerows(satirlar)

    bloklu = sum(1 for b in bulgular if b["etiket"] == "BLOCKED")
    dogrula = sum(1 for b in bulgular if b["etiket"] == "VERIFY")
    adaysiz = [s["urun_adi_wix"] for s in satirlar if s["kategori_adaylari"] == "ADAY YOK"]
    gorselsiz = [s["urun_adi_wix"] for s in satirlar if s["gorsel_adet"] == 0]

    rapor = [
        "# Idefix yukleme hazirligi",
        "",
        f"Urun: {len(satirlar)} · Idefix yaprak kategori havuzu: {len(havuz)}",
        f"Mevzuat kademe 1: BLOCKED {bloklu} · VERIFY {dogrula} bulgu",
        f"Kategori adayi cikmayan: {len(adaysiz)} · Gorseli olmayan: {len(gorselsiz)}",
        "",
        "## Yuklemeden once kapanmasi gerekenler",
        "",
        "1. **Marka yok.** `brandId` zorunlu; Idefix marka listesinde L'CARLIÉ YOK",
        "   (`?title=LCARLIE` -> 0 kayit, dogrulandi). Once 'Excel ile Marka Ekleme'",
        "   ya da panelden 'Destek Cagrisi Olustur'.",
        "2. **Baslik/aciklama API ile duzeltilemez** -- yalniz stok-fiyat. Mevzuat",
        "   denetimi yuklemeden ONCE bitmeli; Trendyol'daki yasak ifadeli basliklar",
        "   buraya KOPYALANMAMALI.",
        "3. **Kategori karari** komisyonu ve zorunlu ozellikleri belirler; bu dosya",
        "   yalniz aday siralar.",
        "4. **Komisyon orani API'de yok** -- marj hesaplanamaz, insan beyani gerekir.",
        "",
    ]
    if engeller:
        rapor += ["## Veri engelleri", ""] + [f"- 🔴 {e}" for e in engeller] + [""]
    if adaysiz:
        rapor += ["## Kategori adayi cikmayanlar (elle secilecek)", ""] \
                 + [f"- {a}" for a in adaysiz] + [""]
    if gorselsiz:
        rapor += ["## Gorseli olmayanlar (images.url zorunlu)", ""] \
                 + [f"- {g}" for g in gorselsiz] + [""]
    if bulgular:
        rapor += ["## Mevzuat bulgulari (kademe 1)", "",
                  "| Urun | Yer | Etiket | Kural | Yakalanan ifade | Cumle |",
                  "|---|---|---|---|---|---|"]
        for b in bulgular[:80]:
            rapor.append(
                f"| {b['urun'][:26]} | {b['yer']} | {b['etiket']} | {b['kural'][:26]} "
                f"| **{b['ifade'][:34]}** | {b['cumle'][:90]} |")
        if len(bulgular) > 80:
            rapor.append(f"| ... | | | {len(bulgular) - 80} bulgu daha |")
        rapor += ["", "Tarayicinin sessiz kalmasi onay DEGILDIR (kademe 1 yalniz "
                  "mekanik tarama; gorsel yargi ve konumlandirma insana ait).", ""]

    (CIKTI / "RAPOR.md").write_text("\n".join(rapor), encoding="utf-8")
    print(f"urunler.csv  : {len(satirlar)} satir")
    print(f"RAPOR.md     : BLOCKED {bloklu}, VERIFY {dogrula}, engel {len(engeller)}")
    print(f"dizin        : {CIKTI}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
