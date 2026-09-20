"""Kod tabanındaki TÜM Türkçe sabit-dizgi eşleşmelerini tarar.

NEDEN
20.09.2026'da bu tuzağa YEDİ kez düşüldü ve her seferinde tek tek
düzeltildi. Tek tek düzeltmek yanlış yöntem: her biri üretimde sessizce
yanlış cevap üretirken haftalarca durabilir.

TUZAK NE
Türkçe sondan eklemeli. Sabit bir dizgi aramak, o kelimenin çekimli
hâlini GÖRMEZ ve hata FIRLATMAZ -- sadece eşleşme olmaz:

  "satış"          aranır, "sattık" içinde YOK        -> soru veri yoluna gitmez
  "kampanya hazır" aranır, "kampanyası hazırla" içinde YOK -> ajans çalışmaz
  "nasıl gidiyor"  aranır, iş sorusunun İÇİNDE VAR    -> sohbet sanılır
  "sınır"          aranır, deaccent "sinir"e çarpar   -> yanlış eşleşme

BU BETİK NE YAPAR
`x in text` / `any(... in text ...)` kalıbıyla kullanılan Türkçe sabit
listelerini bulur ve her terim için riski sınıflar:
  YUKSEK  : ek almadan neredeyse hiç kullanılmayan kök (fiil kökü, "satış")
  ORTA    : çok kelimeli kalıp (araya ek girerse bölünür)
  DUSUK   : eksiz de kullanılan isim, marka, kısaltma

Karar vermez, KANIT sunar. Her bulgu insanın bakacağı bir satırdır.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

KOK = Path(sys.argv[1] if len(sys.argv) > 1 else "/opt/lcarlie/jarvis-phase2")

# Turkce harf tasiyan ya da Turkce kelime gibi duran dizgiler
_TR = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_STRING = re.compile(r'"([^"\\\n]{3,40})"|\'([^\'\\\n]{3,40})\'')

# `in text` / `in lowered` / `in body` gibi uyelik testleri ve tuple listeleri
_MEMBERSHIP = re.compile(r"\bin\s+(text|lowered|body|message|raw|folded|flat|content|answer|sentence|query|host|name)\b")
_HAS_CALL = re.compile(r"_has\(|any\(\s*\w+\s+in\s|startswith\(|endswith\(")

# Eksiz de sikca kullanilan sozcukler: dusuk risk
EKSIZ_KULLANILAN = {
    "meta", "wix", "crm", "roas", "ctr", "cpc", "cpa", "cpm", "seo", "spf",
    "titck", "kdv", "sms", "url", "api", "pdf", "inci", "instagram",
    "whatsapp", "facebook", "google", "tiktok", "hello", "hey", "hi ",
    "research", "competitor", "cro", "landing page", "copy yaz",
}

# Fiil koku ya da ek almadan neredeyse hic gecmeyen govde: yuksek risk
YUKSEK_RISK_SON_EKLER = ("mak", "mek", "ış", "iş", "uş", "üş", "ma", "me")


def risk(term: str) -> tuple[str, str]:
    t = term.strip().casefold()
    if not t or t in EKSIZ_KULLANILAN:
        return "DUSUK", "eksiz de kullanılır"
    if len(t.split()) > 1:
        return "ORTA", "çok kelimeli kalıp: araya ek/kelime girerse bölünür"
    if t.endswith(YUKSEK_RISK_SON_EKLER):
        return "YUKSEK", "çekimli biçimleri bu dizgiyi içermez"
    if len(t) <= 4:
        return "ORTA", "kısa kök: başka kelimenin içinde geçebilir"
    if _TR.search(term):
        return "ORTA", "Türkçe kelime: çekimli hâli kaçabilir"
    return "DUSUK", ""


bulgular: list[tuple[str, int, str, str, str]] = []
for path in sorted(KOK.rglob("*.py")):
    if any(k in path.parts for k in ("venv", ".git", "__pycache__", "tests",
                                     "site-packages", ".backup")):
        continue
    try:
        satirlar = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        continue
    # bir liste birden cok satira yayilabilir: 4 satirlik pencere
    for i, satir in enumerate(satirlar):
        pencere = "\n".join(satirlar[i:i + 4])
        if not (_MEMBERSHIP.search(pencere) or _HAS_CALL.search(satir)):
            continue
        for eslesme in _STRING.finditer(satir):
            terim = eslesme.group(1) or eslesme.group(2) or ""
            if not terim or not (_TR.search(terim) or terim.casefold() in EKSIZ_KULLANILAN
                                 or re.fullmatch(r"[a-z ]{3,}", terim)):
                continue
            seviye, sebep = risk(terim)
            if seviye == "DUSUK":
                continue
            bulgular.append((str(path.relative_to(KOK)), i + 1, terim, seviye, sebep))

print(f"taranan kök: {KOK}")
print(f"bulgu: {len(bulgular)}\n")

for seviye in ("YUKSEK", "ORTA"):
    kume = [b for b in bulgular if b[3] == seviye]
    if not kume:
        continue
    print(f"=== {seviye} RİSK ({len(kume)})")
    dosyalar: dict[str, list] = {}
    for dosya, satir, terim, _s, sebep in kume:
        dosyalar.setdefault(dosya, []).append((satir, terim, sebep))
    for dosya, kayitlar in sorted(dosyalar.items()):
        print(f"  {dosya}")
        for satir, terim, sebep in kayitlar[:12]:
            print(f"     {satir:>5}: {terim!r:<28} {sebep}")
        if len(kayitlar) > 12:
            print(f"           ... {len(kayitlar) - 12} tane daha")
    print()
