#!/usr/bin/env python3
"""Hepsiburada urun icerigi -- baslik + fiyat + SUSLU aciklama.

KAYNAK (uydurma yok, AYIKLAMA var)
  /opt/lcarlie/idefix-hazirlik/urunler.csv
    idefix_baslik   : mevzuattan gecmis baslik (marka basta)
    idefix_aciklama : Wix'teki onayli metinden ayiklanmis, denetlenmis HTML
    fiyat           : Wix fiyati

HEPSIBURADA KURALLARI
  - Fiyat = Wix x 1,15, yarim yukari yuvarlanir (sahip karari 24.10.2026).
  - Stok = 250 (sahip karari 24.10.2026).
  - Aciklamada <style>/<script> calismaz; yalniz satir ici stil + tablo
    duzeni. Gorsel Hepsiburada'nin kendi sunucusundan ({{G1}} {{G2}}
    yer tutuculari gonderim aninda urunun galerisinden doldurulur).
  - Marka sahibi / telefon / e-posta / adres YOK (platform disina
    yonlendirme sayilir).

Her baslik + aciklama yeniden `compliance.review`den gecirilir; idefix
betigindeki iki istisna aynen uygulanir. Bulgu varsa urun YAZILMAZ.
"""
from __future__ import annotations

import csv
import html as h
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import compliance  # noqa: E402

CSV = Path("/opt/lcarlie/idefix-hazirlik/urunler.csv")
CIKTI = Path("/opt/lcarlie/hb-hazirlik")
CARPAN = Decimal("1.15")
STOK = 250

# idefix-aciklama-yaz.py ile ayni kume
GUNES = {"8684869609097", "8684869609530"}

KOYU, PETROL, SU, KREM = "#303b40", "#176578", "#c9dddc", "#faf8f3"
FONT = "font-family:Arial,Helvetica,sans-serif"


def kucult(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def fiyat(wix: str) -> int:
    return int((Decimal(wix) * CARPAN).quantize(Decimal("1"), ROUND_HALF_UP))


def bolumle(aciklama: str) -> tuple[list[str], list[tuple[str, str]]]:
    """idefix HTML'ini (giris paragraflari, [(baslik, govde_html)]) yapar."""
    parcalar = re.split(r"<h3>(.*?)</h3>", aciklama)
    giris = re.findall(r"<p>(.*?)</p>", parcalar[0])
    bolumler = [(h.unescape(parcalar[i]), parcalar[i + 1])
                for i in range(1, len(parcalar) - 1, 2)]
    return giris, bolumler


def etiketle(p: str) -> tuple[str, str]:
    """'Bambu komuru Bambu kokenli...' -> ('Bambu komuru', 'Bambu kokenli...').

    Kaynakta icerik kartinin basligi govdeye yapismis. Ikinci buyuk harfle
    baslayan kelimede bolunur; 6 kelimeden uzunsa etiket yok sayilir."""
    k = p.split(" ")
    for i in range(1, min(len(k), 7)):
        if k[i][:1].isupper() and not k[i - 1].endswith((",", ";")):
            return " ".join(k[:i]), " ".join(k[i:])
    return "", p


def bolum_basligi(metin: str) -> str:
    return (f'<h3 style="{FONT};color:{PETROL};font-size:17px;margin:26px 0 10px;'
            f'padding-left:10px;border-left:4px solid {PETROL};">{metin}</h3>')


def kart(icerik: str, zemin: str = KREM, kenar: str = SU) -> str:
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:'
            f'collapse;margin:0 0 10px;"><tr><td style="{FONT};background:{zemin};'
            f'border:1px solid {kenar};border-radius:10px;padding:14px 16px;color:{KOYU};'
            f'font-size:14px;line-height:1.6;">{icerik}</td></tr></table>')


def gorsel(yer: str) -> str:
    return (f'<p style="text-align:center;margin:18px 0;"><img src="{yer}" alt="" '
            f'style="max-width:100%;width:600px;border-radius:12px;"></p>')


def madde_satirlari(ul: str) -> str:
    satir = ""
    for m in re.findall(r"<li>(.*?)</li>", ul):
        satir += (f'<tr><td width="28" valign="top" style="{FONT};color:{PETROL};'
                  f'font-size:16px;padding:6px 0;">&#10022;</td><td style="{FONT};'
                  f'color:{KOYU};font-size:14px;line-height:1.6;padding:6px 0;">{m}</td></tr>')
    return (f'<table width="100%" cellpadding="0" cellspacing="0" style="background:{KREM};'
            f'border-radius:10px;padding:8px 14px;">{satir}</table>')


def susle(baslik: str, aciklama: str) -> str:
    giris, bolumler = bolumle(aciklama)
    kanca = re.sub(r"</?strong>", "", giris[0]) if giris else ""
    govde_giris = giris[1:]
    o = []
    # --- Ust bant: marka + urun adi + kanca --------------------------------
    o.append(
        f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;'
        f'margin:0 0 6px;"><tr><td style="{FONT};background:{KOYU};border-radius:14px;'
        f'padding:26px 22px;text-align:center;">'
        f'<div style="color:{SU};font-size:13px;letter-spacing:6px;">L&#39;CARLI&Eacute;</div>'
        f'<div style="color:#ffffff;font-size:22px;font-weight:bold;margin:10px 0 8px;'
        f'line-height:1.3;">{h.escape(baslik.replace("L'CARLIE ", ""))}</div>'
        f'<div style="color:{SU};font-size:15px;font-style:italic;">{kanca}</div>'
        f'</td></tr></table>')
    o.append(gorsel("{{G1}}"))
    if govde_giris:
        o.append(kart("".join(f'<p style="margin:0 0 8px;">{p}</p>' for p in govde_giris)))

    for ad, govde in bolumler:
        k = kucult(ad)
        ul = "".join(re.findall(r"<ul>.*?</ul>", govde))
        pler = re.findall(r"<p>(.*?)</p>", govde)
        o.append(bolum_basligi(h.escape(ad)))
        if "rolü" in k:
            for p in pler:
                etiket, metin = etiketle(p)
                ic = (f'<div style="color:{PETROL};font-weight:bold;font-size:14px;'
                      f'margin-bottom:4px;">{etiket}</div>' if etiket else "") + metin
                o.append(kart(ic, "#ffffff"))
            o.append(gorsel("{{G2}}"))
        elif "uyarı" in k:
            ic = "".join(f'<p style="margin:0 0 6px;">{p}</p>' for p in pler)
            if ul:
                ic += "".join(f'<p style="margin:0 0 6px;">&#8226; {m}</p>'
                              for m in re.findall(r"<li>(.*?)</li>", ul))
            o.append(kart(ic, "#fdf6ec", "#e6cf9f"))
        elif "içindekiler" in k or "inci" in k:
            ic = "".join(f'<p style="margin:0;font-size:12px;color:#5b6a70;">{p}</p>'
                         for p in pler)
            o.append(kart(ic, "#f4f6f6", "#dfe5e6"))
        else:
            if ul:
                o.append(madde_satirlari(ul))
            for p in pler:
                o.append(f'<p style="{FONT};color:{KOYU};font-size:14px;line-height:1.7;'
                         f'margin:0 0 8px;">{p}</p>')
    # --- Alt bant ---------------------------------------------------------
    o.append(
        f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:26px 0 0;">'
        f'<tr><td style="{FONT};background:{PETROL};border-radius:12px;padding:16px;'
        f'text-align:center;color:#ffffff;font-size:13px;letter-spacing:2px;">'
        f'L&#39;CARLI&Eacute; &middot; T&Uuml;RK&#304;YE&#39;DE &Uuml;RET&#304;LM&#304;&#350;T&#304;R'
        f'</td></tr></table>')
    return f'<div style="{FONT};max-width:760px;margin:0 auto;">' + "".join(o) + "</div>"


def duz(html_metin: str) -> str:
    return re.sub(r"\s+", " ", h.unescape(re.sub(r"<[^>]+>", " ", html_metin))).strip()


def denetle(barkod: str, metin: str) -> list[str]:
    bulgu = []
    for f in compliance.review(metin).findings:
        cumle = f.sentence or ""
        if re.search(r"(ma(z|yın|malı)|mez|meyin|durunuz|önerilir|kaçın)", kucult(cumle)):
            continue
        if "zorunlu ibare" in f.rule and barkod not in GUNES:
            continue
        bulgu.append(f"{f.rule} -> '{f.matched}'")
    return bulgu


def main() -> int:
    CIKTI.mkdir(exist_ok=True)
    satirlar = list(csv.DictReader(CSV.open(encoding="utf-8-sig"), delimiter=";"))
    hepsi, hata = {}, 0
    for s in satirlar:
        b = s["barkod"]
        baslik = s["idefix_baslik"]
        aciklama = susle(baslik, s["idefix_aciklama"])
        bulgu = denetle(b, baslik + ". " + duz(aciklama))
        if bulgu:
            hata += 1
            print(f"BULGU {b} {baslik}: {bulgu}")
            continue
        hepsi[b] = {"baslik": baslik, "marka": "L'CARLIE", "fiyat": fiyat(s["fiyat"]),
                    "wix_fiyat": s["fiyat"], "stok": STOK, "aciklama": aciklama}
    (CIKTI / "hb-icerik.json").write_text(json.dumps(hepsi, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print(f"yazildi {len(hepsi)} urun, bulgulu {hata}")
    return 1 if hata else 0


if __name__ == "__main__":
    sys.exit(main())
