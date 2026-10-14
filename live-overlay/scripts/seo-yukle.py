#!/usr/bin/env python3
"""Wix'ten urun SEO alanlarini ceker ve core.urun_seo'ya yazar.

🔴 SEO departmani kadrosuzdu cunku okuyacagi kaynak yoktu. Veri Wix'te
duruyordu (seoData) ve hic okunmuyordu. Bu betik o bosluğu kapatir.

🔴 YORUM YAPMAZ, OLCER. "Baslik iyi/kotu" demez; uzunlugu ve varligini
yazar. Yorumu ekip yapar, cunku iyi/kotu esigi degisebilir ama olcum
degismez.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ENVF = Path("/opt/lcarlie/n8n/.env")


def env(anahtar: str) -> str:
    try:
        for satir in ENVF.read_text(encoding="utf-8").splitlines():
            if satir.startswith(f"{anahtar}="):
                return satir.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ""


def urunleri_cek(anahtar: str, site: str) -> list[dict]:
    """Sayfalayarak TUM urunleri ceker — ilk 100 ile yetinmez."""
    hepsi: list[dict] = []
    offset = 0
    while True:
        govde = json.dumps({"query": {"paging": {"limit": 100, "offset": offset}},
                            "includeVariants": False}).encode("utf-8")
        istek = urllib.request.Request(
            "https://www.wixapis.com/stores-reader/v1/products/query",
            data=govde,
            headers={"Authorization": anahtar, "wix-site-id": site,
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(istek, timeout=60) as cevap:
            d = json.loads(cevap.read().decode("utf-8"))
        parca = d.get("products") or []
        hepsi.extend(parca)
        toplam = (d.get("totalResults") or 0)
        offset += len(parca)
        if not parca or offset >= toplam:
            break
    return hepsi


def etiket_bul(seo: dict, tur: str, ad: str = "", ozellik: str = "") -> str:
    for etk in (seo.get("tags") or []):
        if etk.get("type") != tur:
            continue
        props = etk.get("props") or {}
        if ad and props.get("name") != ad:
            continue
        if ozellik and props.get("property") != ozellik:
            continue
        if tur == "title":
            return str(etk.get("children") or "")
        return str(props.get("content") or "")
    return ""


def q(x: object) -> str:
    return "'" + str(x if x is not None else "").replace("'", "''")[:900] + "'"


def main() -> int:
    anahtar, site = env("WIX_API_KEY"), env("WIX_SITE_ID")
    if not anahtar or not site:
        print("WIX_API_KEY / WIX_SITE_ID yok", file=sys.stderr)
        return 1

    urunler = urunleri_cek(anahtar, site)
    print(f"Wix'ten {len(urunler)} ürün çekildi")

    satirlar = []
    for u in urunler:
        seo = u.get("seoData") or {}
        baslik = etiket_bul(seo, "title")
        aciklama = etiket_bul(seo, "meta", ad="description")
        og = etiket_bul(seo, "meta", ozellik="og:title")
        kelimeler = [str(k.get("term") or "")
                     for k in ((seo.get("settings") or {}).get("keywords") or [])
                     if k.get("term")]
        ana = next((str(k.get("term")) for k in
                    ((seo.get("settings") or {}).get("keywords") or [])
                    if k.get("isMain")), "")
        dizi = ("ARRAY[" + ",".join(q(k) for k in kelimeler) + "]::text[]"
                if kelimeler else "NULL")
        satirlar.append(
            f"({q(u.get('id'))},{q(u.get('name'))},{q(u.get('sku'))},"
            f"{q(u.get('slug'))},{q(baslik)},{q(aciklama)},{q(og)},{dizi},"
            f"{q(ana)},{len(baslik)},{len(aciklama)},"
            f"{'true' if baslik else 'false'},"
            f"{'true' if aciklama else 'false'},"
            f"{'true' if kelimeler else 'false'},"
            f"{'true' if u.get('visible') else 'false'})")

    if not satirlar:
        print("yazılacak satır yok", file=sys.stderr)
        return 1

    sql = (
        "INSERT INTO core.urun_seo (urun_id,urun_adi,sku,slug,seo_baslik,"
        "seo_aciklama,og_baslik,anahtar_kelimeler,ana_anahtar,baslik_uzunluk,"
        "aciklama_uzunluk,baslik_var,aciklama_var,anahtar_var,yayinda) VALUES "
        + ",".join(satirlar) +
        " ON CONFLICT (urun_id) DO UPDATE SET guncelleme=clock_timestamp(),"
        "urun_adi=EXCLUDED.urun_adi,slug=EXCLUDED.slug,"
        "seo_baslik=EXCLUDED.seo_baslik,seo_aciklama=EXCLUDED.seo_aciklama,"
        "og_baslik=EXCLUDED.og_baslik,"
        "anahtar_kelimeler=EXCLUDED.anahtar_kelimeler,"
        "ana_anahtar=EXCLUDED.ana_anahtar,"
        "baslik_uzunluk=EXCLUDED.baslik_uzunluk,"
        "aciklama_uzunluk=EXCLUDED.aciklama_uzunluk,"
        "baslik_var=EXCLUDED.baslik_var,aciklama_var=EXCLUDED.aciklama_var,"
        "anahtar_var=EXCLUDED.anahtar_var,yayinda=EXCLUDED.yayinda;")

    r = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n",
         "-d", "n8n", "-v", "ON_ERROR_STOP=1"],
        input=sql.encode("utf-8"), capture_output=True, timeout=120)
    if r.returncode:
        print(f"DB yazilamadi: {r.stderr.decode()[:220]}", file=sys.stderr)
        return 1
    print(f"core.urun_seo'ya {len(satirlar)} satır yazıldı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
