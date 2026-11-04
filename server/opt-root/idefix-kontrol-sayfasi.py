#!/usr/bin/env python3
"""Idefix yukleme kontrol sayfasi — 36 urun tek ekranda.

Amac: sahibin gozle denetlemesi. Hangi gorseller yuklendi, hangi kategoriye
kondu, mevzuat taramasi ne dedi, fiyat/stok ne. Karar vermesi gereken iki
sey (kategori onayi + baslik yazimi) bu sayfadan gorulebilsin diye.

Veri kaynagi: idefix-hazirlik/urunler.csv (uretilmis, elle yazilmamis).
Cikti: /opt/lcarlie/urun-gorsel/kontrol.html  (Caddy ayni dizinden servis eder)
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CIKTI = Path("/opt/lcarlie/urun-gorsel/kontrol.html")

BAS = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Idefix yükleme kontrolü · L'CARLIÉ</title>
<style>
  :root { --mu:#0f2e2b; --ac:#1b6a60; --ze:#f6f5f2; --ci:#5b6b68; --uy:#9a4a1a; }
  * { box-sizing:border-box }
  body { margin:0; background:var(--ze); color:var(--mu);
    font:15px/1.5 "Segoe UI",system-ui,sans-serif; }
  header { background:#fff; border-bottom:1px solid #e3e1dc; padding:18px 20px;
    position:sticky; top:0; z-index:5 }
  h1 { margin:0 0 4px; font-size:19px; letter-spacing:.02em }
  .ozet { color:var(--ci); font-size:13px }
  .ozet b { color:var(--mu) }
  main { padding:18px 20px 60px; max-width:1400px; margin:0 auto }
  .urun { background:#fff; border:1px solid #e3e1dc; border-radius:10px;
    padding:14px; margin-bottom:14px }
  .ust { display:flex; flex-wrap:wrap; gap:10px 16px; align-items:baseline }
  .ad { font-weight:600; font-size:16px }
  .barkod { font-family:ui-monospace,Consolas,monospace; font-size:12px; color:var(--ci) }
  .kat { color:var(--ac); font-size:13px }
  .kat code { background:var(--ze); padding:1px 5px; border-radius:4px; font-size:12px }
  .satir { color:var(--ci); font-size:13px; margin-top:4px }
  .etiket { display:inline-block; font-size:11px; padding:2px 7px; border-radius:99px;
    background:#eef3f1; color:var(--ac); margin-right:5px }
  .etiket.uyari { background:#fdf0e6; color:var(--uy) }
  .gorseller { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap }
  .gorseller a { display:block; width:110px; border:1px solid #e3e1dc; border-radius:6px;
    overflow:hidden; background:var(--ze) }
  .gorseller img { display:block; width:100%; height:165px; object-fit:cover }
  .bos { color:var(--uy); font-size:13px }
  @media (max-width:520px){ .gorseller a{ width:88px } .gorseller img{ height:132px } }
</style></head><body>
"""


def main() -> int:
    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    satirlar.sort(key=lambda r: r["urun_adi_wix"])

    bloklu = sum(1 for s in satirlar if "BLOCKED" in s["mevzuat"])
    basliksiz = sum(1 for s in satirlar if not s.get("idefix_baslik"))
    kategoriler = {s["kategori_id"] for s in satirlar}

    parcalar = [BAS, "<header>",
                "<h1>Idefix yükleme kontrolü</h1>",
                f"<div class='ozet'><b>{len(satirlar)}</b> ürün · "
                f"<b>{len(kategoriler)}</b> farklı kategori (= o kadar ayrı Excel) · "
                f"mevzuat taramasında bulgu taşıyan <b>{bloklu}</b> ürün · "
                f"başlığı henüz yazılmamış <b>{basliksiz}</b> ürün · "
                "marka <b>onay bekliyor</b> (BRAND_NOT_EXIST)</div>",
                "</header><main>"]

    for s in satirlar:
        gorseller = [s.get(f"gorsel_{i}", "") for i in range(1, 6)]
        gorseller = [g for g in gorseller if g]
        etiket = ("<span class='etiket uyari'>" + html.escape(s["mevzuat"]) + "</span>"
                  if "BLOCKED" in s["mevzuat"]
                  else "<span class='etiket'>kademe 1 temiz</span>")
        baslik = s.get("idefix_baslik") or ""
        baslik_html = (f"<span class='etiket'>başlık: {html.escape(baslik)}</span>"
                       if baslik else "<span class='etiket uyari'>başlık yazılmadı</span>")
        kat_yol = html.escape(s["kategori_secimi"])
        parcalar.append(f"""<section class="urun">
  <div class="ust">
    <span class="ad">{html.escape(s['urun_adi_wix'])}</span>
    <span class="barkod">{html.escape(s['barkod'])}</span>
    <span class="kat">{kat_yol} <code>{html.escape(s['kategori_id'])}</code></span>
  </div>
  <div class="satir">{html.escape(s['fiyat'])} TL · stok {html.escape(s['stok'])}
    · KDV %{html.escape(s['kdv'])} · açıklama {html.escape(s['aciklama_karakter'])} karakter</div>
  <div class="satir">{etiket}{baslik_html}</div>
  <div class="gorseller">""")
        if gorseller:
            for g in gorseller:
                u = html.escape(g)
                parcalar.append(f'<a href="{u}" target="_blank" rel="noopener">'
                                f'<img src="{u}" alt="" loading="lazy"></a>')
        else:
            parcalar.append("<span class='bos'>görsel yok</span>")
        parcalar.append("</div></section>")

    parcalar.append("</main></body></html>")
    CIKTI.write_text("".join(parcalar), encoding="utf-8")
    print(f"yazildi: {CIKTI} ({CIKTI.stat().st_size} bayt, {len(satirlar)} urun)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
