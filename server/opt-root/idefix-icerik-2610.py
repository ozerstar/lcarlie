#!/usr/bin/env python3
"""26.10.2026 — Idefix icerik yenileme Excel'leri (25.10 e-ticaret aciklamalari).

Kaynak: eticaret-2510.csv (Downloads/...V2.../ETICARET-ACIKLAMALARI/TOPLU-YUKLEME.csv,
39 urun, 39/39 denetimden gecmis). 22.10 talepleri 4 gun sonra yayinda degildi
(canli sayfalar olculdu) ve o metinler 25.10 duzeltmelerinden (bebek salisilik,
bitkisel sayilar) ONCEYDI.

Disarida: yanlis eslesen SUNACNEA/BUGUARD; YAYINA CIKMAZ satirlari.
Sablon: 22.10'da panelden alinip kabul edilmis toplu-aciklama/baslik.xlsx.
"""
import csv, sys
sys.path.insert(0, "/opt/lcarlie")
from importlib.machinery import SourceFileLoader
t = SourceFileLoader("t", "/opt/lcarlie/idefix-toplu-excel.py").load_module()
from pathlib import Path
D = Path("/opt/lcarlie/idefix-hazirlik")
YANLIS = {"8684869609097", "8684869609301"}
rows = list(csv.DictReader(open(D/"eticaret-2510.csv", encoding="utf-8-sig"), delimiter=";"))
acik, bas = [], []
for r in rows:
    b = r["Barkod"].strip()
    if r["Durum"] != "HAZIR" or b in YANLIS or not b.isdigit():
        continue
    h = r["Açıklama (HTML)"].strip()
    assert len(h) > 1500, (b, len(h))
    assert len(r["Başlık"]) <= 150, (b, len(r["Başlık"]))
    acik.append((b, h)); bas.append((b, r["Başlık"].strip()))
t.xlsx_yaz(D/"toplu-aciklama.xlsx", D/"aciklama-2610.xlsx", ("Barkod", "Ürün Açıklaması"), acik)
t.xlsx_yaz(D/"toplu-baslik.xlsx", D/"baslik-2610.xlsx", ("Barkod", "Ürün Adı"), bas)
print(len(acik), "aciklama,", len(bas), "baslik; en uzun baslik", max(len(x[1]) for x in bas))

# ---- GORSEL: yalniz gorseli ambalajla TUTARLI olan katalog urunleri ----------
# Bitkisel sayisi/icerigi ambalajla degisen 6 urunun V2 gorselleri ESKI bilgi
# tasiyor (or. BABYSHOWER "6 bitkisel" + "Lavanta Sulari"; yeni ambalajda 5, lavanta
# yok). Gorseller duzeltilene kadar YUKLENMEZ.
import re, zipfile, urllib.request
from xml.sax.saxutils import escape
ESKI_GORSEL = set()  # 26.10 03:01: 5 urunun gorselleri ambalaja gore duzeltilip yeniden yayinlandi (yedek: urun-gorsel/_yedek-20261026); DERMASTRA zaten tutarliydi
KENDI = {"8684869609080", "8684869609172", "8684869609578",
         "8684869609585", "8684869609400", "8684869609608"}  # zaten bizim 5 gorsel
g = []
for b, _ in acik:
    if b in ESKI_GORSEL or b in KENDI:
        continue
    urls = [f"https://n8n.lcarlie.shop/urun-gorsel/{b}-0{i}.jpg" for i in range(1, 6)]
    for u in urls:
        with urllib.request.urlopen(urllib.request.Request(u, method="HEAD"), timeout=20) as r:
            assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg", u
    g.append([b] + urls)
z = zipfile.ZipFile(D/"toplu-gorsel.xlsx"); p = {n: z.read(n) for n in z.namelist()}; z.close()
sh = p["xl/worksheets/sheet1.xml"].decode()
kol = "ABCDEFGHI"
bas_s = ["Barkod"] + [f"Görsel {i}" for i in range(1, 9)]
def satir(i, vals):
    return f'<row r="{i}">' + "".join(
        f'<c r="{kol[j]}{i}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>'
        for j, v in enumerate(vals)) + "</row>"
data = "<sheetData>" + satir(1, bas_s) + "".join(satir(i + 2, r) for i, r in enumerate(g)) + "</sheetData>"
sh = re.sub(r"<sheetData>.*?</sheetData>|<sheetData\s*/>", data, sh, flags=re.S)
sh = re.sub(r'<dimension ref="[^"]*"/>', f'<dimension ref="A1:I{len(g)+1}"/>', sh)
p["xl/worksheets/sheet1.xml"] = sh.encode()
with zipfile.ZipFile(D/"gorsel-2610.xlsx", "w", zipfile.ZIP_DEFLATED) as z:
    for n, v in p.items(): z.writestr(n, v)
print(len(g), "urun gorsel (", 5*len(g), "adres, hepsi HTTP 200 image/jpeg )")
