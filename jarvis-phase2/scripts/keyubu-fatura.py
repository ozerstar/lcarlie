#!/usr/bin/env python3
"""SUNUCU FATURASI NOBETI -- Keyubu faturasi odenmeden sunucu kapanmasin.

NEDEN VAR
13.11.2026 00:11'de VDS (185.169.180.68) askiya alindi: 05.11'de kesilen
#390603 faturasi (son odeme 12.11) odenmemisti. 22.10'da da ayni sey oldu.
Fatura her ay Gmail'e geliyor ve Harcamalarim'da gorunuyordu ama "odendi mi"
diye soran yoktu. Faturada "Zamaninda odeme yapilmaz ise hizmetim silinsin"
secili: gecikme yalniz kesinti degil, sunucunun SILINMESI demek.

NASIL
Gmail'de Keyubu'nun "Musteri Faturasi" postalarindan fatura no / tutar /
son odeme tarihi okunur; "Fatura Odeme Onayi" postasinda gecen fatura no
odenmis sayilir. Odenmemis her fatura icin sahibe push + e-posta gider:
fatura geldigi gun bir kez, son 3 gun her gun, gecikince 7 gun boyunca her gun.
Ayni gun ayni fatura icin ikinci haber gitmez.

Kullanim:
  keyubu-fatura.py --kuru    (oku, ne gonderecegini yaz, gonderme)
  keyubu-fatura.py           (oku, gerekirse haber ver)
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "webconsole"))

DURUM = KOK / "state" / "keyubu-fatura.json"
BOLGE = ZoneInfo("Europe/Istanbul")
IPTAL_GUN = 7
AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7,
         "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}


def tarih_oku(metin: str) -> date | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})", metin)
    if not m:
        return None
    ay = AYLAR.get(m.group(2).replace("I", "ı").lower())
    return date(int(m.group(3)), ay, int(m.group(1))) if ay else None


def fatura_oku(govde: str) -> dict | None:
    """'Musteri Faturasi' postasi: fatura no, tutar, son odeme tarihi."""
    no = re.search(r"Fatura\s*#\s*(\d+)", govde)
    if not no:
        return None
    tutar = re.search(r"Ödenecek Tutar:\s*([\d.,]+)", govde)
    son = re.search(r"Son Ödeme Tarihi:\s*([^\n/]+)", govde)
    return {"no": no.group(1), "tutar": float(tutar.group(1).replace(",", "")) if tutar else None,
            "son_odeme": (tarih_oku(son.group(1)) if son else None)}


def odeme_oku(govde: str) -> str | None:
    """'Fatura Odeme Onayi' postasi: '... 390603 Faturası için bir ödeme bildirimidir'."""
    m = re.search(r"(\d+)\s+Faturası için bir ödeme", govde)
    return m.group(1) if m else None


def haber_gerekli(fatura: dict, bugun: date, gonderilen: list[str]) -> str | None:
    """Bugun bu fatura icin haber gitmeli mi? Gidecekse nedeni."""
    if bugun.isoformat() in gonderilen:
        return None
    son = fatura.get("son_odeme")
    if son is None:
        return "yeni" if not gonderilen else None
    kalan = (son - bugun).days
    if kalan < -IPTAL_GUN:
        # Odenmeyen fatura Keyubu'da iptal olur (21.09'daki 5 siparis, 24.10 disk
        # denemesi); sunucu hala calisiyorsa eski acik fatura alarm degildir.
        return None
    if kalan < 0:
        return "gecikti"
    if kalan <= 3:
        return "son-gunler"
    return "yeni" if not gonderilen else None


def _govde(parca: dict) -> str:
    """Gmail 'full' iletisinden duz metin; HTML ise etiketler atilir."""
    duz, html_ = [], []
    yigin = [parca]
    while yigin:
        p = yigin.pop()
        yigin.extend(p.get("parts") or [])
        veri = (p.get("body") or {}).get("data")
        if not veri:
            continue
        metin = base64.urlsafe_b64decode(veri + "===").decode("utf-8", "replace")
        (duz if p.get("mimeType") == "text/plain" else html_).append(metin)
    if duz:
        return "\n".join(duz)
    metin = re.sub(r"<(br|/p|/div|/tr)[^>]*>", "\n", "\n".join(html_), flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", metin))


def gmail_oku(gun: int = 60) -> tuple[dict, set]:
    import expense_vault
    import google_workspace

    jeton = google_workspace.gmail_read_access_token("operator")
    faturalar, odenen = {}, set()
    sorgu = urllib.parse.urlencode({"q": "from:keyubu newer_than:%dd" % gun, "maxResults": 100})
    for kayit in expense_vault._gmail_json("messages?" + sorgu, jeton).get("messages") or []:
        ileti = expense_vault._gmail_json("messages/%s?format=full" % kayit["id"], jeton)
        konu = next((h["value"] for h in ileti["payload"].get("headers", []) if h["name"].lower() == "subject"), "")
        govde = _govde(ileti["payload"])
        if "Ödeme Onayı" in konu:
            no = odeme_oku(govde)
            if no:
                odenen.add(no)
        elif "Faturası" in konu or "Fatura #" in govde:
            f = fatura_oku(govde)
            if f:
                faturalar[f["no"]] = f
    return faturalar, odenen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true")
    arg = ap.parse_args()
    bugun = datetime.now(BOLGE).date()
    for deneme in range(3):
        try:
            faturalar, odenen = gmail_oku()
            break
        except Exception:                               # noqa: BLE001
            # 13.11: Gmail ayni dakikada bir kez 403, sonra 200 dondu
            if deneme == 2:
                raise
            time.sleep(30)
    durum = json.loads(DURUM.read_text(encoding="utf-8")) if DURUM.exists() else {}
    acik = [f for no, f in sorted(faturalar.items()) if no not in odenen]
    print("fatura %d, odenen %d, acik %s" % (len(faturalar), len(odenen), [f["no"] for f in acik]))
    from jarvis import haberci
    for f in acik:
        neden = haber_gerekli(f, bugun, durum.get(f["no"], []))
        if not neden:
            continue
        son = f["son_odeme"]
        kalan = (son - bugun).days if son else None
        tutar = ("%.2f TL" % f["tutar"]).replace(".", ",") if f["tutar"] is not None else "tutar okunamadı"
        if kalan is None:
            zaman = "son ödeme tarihi okunamadı"
        elif kalan < 0:
            zaman = "son ödeme %s idi, %d gün GECİKTİ" % (son.strftime("%d.%m"), -kalan)
        elif kalan == 0:
            zaman = "son ödeme BUGÜN"
        else:
            zaman = "son ödeme %s (%d gün kaldı)" % (son.strftime("%d.%m"), kalan)
        baslik = "Sunucu faturası ödenmedi: Keyubu #%s" % f["no"]
        metin = ("Keyubu sunucu faturası #%s: %s, %s. Ödenmezse sunucu askıya alınır; faturadaki "
                 "ayara göre SİLİNEBİLİR (Jarvis, siteler, görseller kapanır). Ödeme: keyubu.com "
                 "müşteri paneli." % (f["no"], tutar, zaman))
        print(neden, "->", metin)
        if arg.kuru:
            continue
        giden = []
        for yol, islev, args in (("push", haberci.push_gonder, (baslik, metin, "keyubu-" + f["no"])),
                                 ("eposta", haberci.eposta_gonder, (baslik, metin))):
            try:
                islev(*args)
                giden.append(yol)
            except Exception as h:                      # noqa: BLE001
                print("%s gonderilemedi: %s" % (yol, str(h)[:120]), file=sys.stderr)
        if giden:
            durum.setdefault(f["no"], []).append(bugun.isoformat())
    if not arg.kuru:
        DURUM.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
