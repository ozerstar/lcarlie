"""PAZARYERİ PAKETLERİ — kargoya verilecekler ve etiketleri.

Sahip 13.11.2026: *"kargo bölümünde bu satışların kargo etiketleri görünsün
ve seçilen etiketler şablona otomatik döşensin… uygun boyutlandırma
yapılsın."*

Trendyol ve İdefix paketi kendi anlaşmalı kargosuyla gider; kargo kodunu
pazaryeri üretir, BasitKargo'dan barkod ALINMAZ (para harcanmaz). Bu modül o
paketleri panele ve HB-1006 etiket sayfasına taşır.

İKİ SÜREÇ, İKİ YETKİ
    scripts/kargo-bekleyen.py   root zamanlayıcısı. Pazaryeri API anahtarları
                                yalnız root'a açık; paketleri okur ve
                                `state/kargo-bekleyen.json` dosyasına yazar.
    panel (jarvis-web)          yalnız o dosyayı okur. Anahtarlara dokunmaz.

🔴 ADRES VE TELEFON PANELE GİTMEZ. Dosyada durur, çünkü etiketin üstüne
basılacak; `panel_ozet()` ise yalnız ad, il/ilçe, ürün ve kodu döndürür.

🔴 "PAKET YOK" İLE "OKUYAMADIM" AYRI. Dosya yoksa ya da bayatsa panel bunu
ayrıca yazar; okunamayan kanal da adıyla görünür.
"""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KOK = Path(__file__).resolve().parent.parent
DOSYA = Path(os.environ.get("KARGO_BEKLEYEN_DOSYA",
                            str(KOK / "state" / "kargo-bekleyen.json")))

# Zamanlayıcı 5 dakikada bir yazar; üç tur kaçtıysa veri bayat sayılır.
BAYAT_DAKIKA = 20

ON_EK = "PZ:"
_KANAL_KOD = {"Trendyol": "trendyol", "İdefix": "idefix", "Wix": "wix", "n11": "n11"}
_GUVENLI = re.compile(r"[^A-Za-z0-9_-]")

# Etiket: HB-1006 hücresi 99.06 × 93.13 mm. 300 dpi'de 98 × 92 mm.
ETIKET_PX = (1158, 1087)
_YAZI = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_YAZI_KALIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class EtiketHatasi(Exception):
    """Etiket çizilemedi; sebebi Türkçe."""


def anahtar(kanal: str, no: str) -> str:
    """Panelin ve etiket betiğinin paketi andığı ad: `PZ:trendyol:118…`."""
    return ON_EK + _KANAL_KOD.get(kanal, _GUVENLI.sub("", kanal.lower())) \
        + ":" + _GUVENLI.sub("", str(no))


def etiketlenebilir(p: dict) -> bool:
    """Kargo kodu olan pazaryeri paketi. Wix BasitKargo'dan etiket alır."""
    return (p.get("kanal") in ("Trendyol", "İdefix")
            and bool(re.fullmatch(r"[A-Za-z0-9-]{6,40}", str(p.get("kod") or ""))))


# ------------------------------------------------------------------ yazma
def yaz(satirlar: list[dict], okunamayan: list[str]) -> Path:
    """Zamanlayıcı çağırır. Yarım dosya panelde görünmesin diye taşıyarak yazar."""
    for s in satirlar:
        s["anahtar"] = anahtar(str(s.get("kanal") or ""), str(s.get("no") or ""))
    govde = {"guncellendi": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "okunamayan": list(okunamayan), "paketler": satirlar}
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    gecici = DOSYA.with_suffix(".json.yeni")
    gecici.write_text(json.dumps(govde, ensure_ascii=False, indent=1), encoding="utf-8")
    # 🔴 0640 şart: dizinin varsayılan ACL'i panel kullanıcısına okuma verir
    # ama maske dosyanın grup bitlerinden türer; 0600 kalırsa panel okuyamaz.
    os.chmod(gecici, 0o640)
    os.replace(gecici, DOSYA)
    return DOSYA


# ------------------------------------------------------------------ okuma
def _oku() -> dict:
    return json.loads(DOSYA.read_text(encoding="utf-8"))


def panel_ozet() -> dict:
    """Panelin KARGO sekmesine giden özet. Adres ve telefon İÇERMEZ."""
    try:
        veri = _oku()
    except FileNotFoundError:
        return {"hata": "Pazaryeri paketleri henüz okunmadı (zamanlayıcı ilk turunu "
                        "atmadı).", "paketler": []}
    except Exception as hata:  # noqa: BLE001
        return {"hata": f"Pazaryeri paket listesi okunamadı: {str(hata)[:120]}",
                "paketler": []}
    cikti: dict[str, Any] = {"guncellendi": veri.get("guncellendi"),
                             "okunamayan": veri.get("okunamayan") or [],
                             "paketler": []}
    try:
        yas = (datetime.now(timezone.utc)
               - datetime.fromisoformat(veri["guncellendi"])).total_seconds() / 60
        cikti["yas_dakika"] = round(yas)
        cikti["bayat"] = yas > BAYAT_DAKIKA
    except Exception:  # noqa: BLE001
        cikti["bayat"] = True
    for p in veri.get("paketler") or []:
        cikti["paketler"].append({
            "anahtar": p.get("anahtar"), "kanal": p.get("kanal"), "no": p.get("no"),
            "kargo": p.get("kargo"), "kod": p.get("kod"),
            "alici": p.get("alici") or p.get("musteri"),
            "nere": " / ".join(x for x in (p.get("il"), p.get("ilce")) if x),
            "urunler": p.get("urunler"), "durum": p.get("durum"),
            "etiket": etiketlenebilir(p)})
    return cikti


def paket_bul(ad: str) -> dict:
    for p in _oku().get("paketler") or []:
        if p.get("anahtar") == ad:
            return p
    raise EtiketHatasi(f"{ad}: paket listede yok (kargoya verilmiş olabilir)")


# ------------------------------------------------------------------ barkod
def code128_cubuklar(kod: str) -> list[int]:
    """Code 128 çubuk/boşluk genişlikleri (modül), çubukla başlar.

    Kodlamayı reportlab yapar (C kümesi, sağlama, dur işareti); biz yalnız
    genişlikleri alıp çizeriz. `BaAbCb…`: büyük harf çubuk, küçük harf boşluk,
    A=1 … D=4 modül.
    """
    from reportlab.graphics.barcode.code128 import Code128
    b = Code128(kod, quiet=0)
    b.validate()
    if not b.valid:
        raise EtiketHatasi(f"kargo kodu barkoda çevrilemiyor: {kod!r}")
    b.encode()
    b.decompose()
    return [ord(c.upper()) - 64 for c in b.decomposed]


def _barkod_ciz(ciz, kod: str, sol: int, ust: int, en: int, boy: int) -> int:
    """Barkodu alana ORTALAR; modül tam piksel olur (yarım piksel okunmaz)."""
    genislikler = code128_cubuklar(kod)
    modul = sum(genislikler)
    px = en // (modul + 20)          # iki yanda 10'ar modül sessiz bölge
    if px < 3:
        raise EtiketHatasi(f"kargo kodu etikete sığmıyor: {kod!r}")
    px = min(px, 7)
    x = sol + (en - modul * px) // 2
    for i, g in enumerate(genislikler):
        if i % 2 == 0:
            ciz.rectangle([x, ust, x + g * px - 1, ust + boy], fill="black")
        x += g * px
    return px


# ------------------------------------------------------------------ etiket
def _sar(ciz, metin: str, yazi, en: int, satir_tavan: int) -> list[str]:
    satirlar, su = [], ""
    for kelime in metin.split():
        aday = (su + " " + kelime).strip()
        if ciz.textlength(aday, font=yazi) <= en:
            su = aday
            continue
        if su:
            satirlar.append(su)
        su = kelime
    if su:
        satirlar.append(su)
    if len(satirlar) > satir_tavan:
        satirlar = satirlar[:satir_tavan]
        satirlar[-1] = satirlar[-1][:-1].rstrip() + "…"
    return satirlar


def etiket_png(p: dict) -> bytes:
    """Bir paketin kargo etiketi: taşıyıcı, barkod, alıcı, sipariş."""
    from PIL import Image, ImageDraw, ImageFont
    if not etiketlenebilir(p):
        raise EtiketHatasi(f"{p.get('kanal')} {p.get('no')}: kargo kodu yok")
    en, boy = ETIKET_PX
    pay = 44
    im = Image.new("RGB", (en, boy), "white")
    ciz = ImageDraw.Draw(im)

    def yazi(boyut: int, kalin: bool = False):
        return ImageFont.truetype(_YAZI_KALIN if kalin else _YAZI, boyut)

    ciz.rectangle([6, 6, en - 7, boy - 7], outline="black", width=4)
    # Üst şerit: taşıyıcı solda, kanal sağda.
    ciz.rectangle([6, 6, en - 7, 128], fill="black")
    ciz.text((pay, 34), str(p.get("kargo") or "").upper(), font=yazi(62, True), fill="white")
    kanal = str(p.get("kanal") or "").upper()
    ciz.text((en - pay - ciz.textlength(kanal, font=yazi(44, True)), 46), kanal,
             font=yazi(44, True), fill="white")

    # Barkod ve altında okunur hali.
    kod = str(p["kod"])
    _barkod_ciz(ciz, kod, pay, 168, en - 2 * pay, 250)
    kod_yazi = yazi(46, True)
    ciz.text(((en - ciz.textlength(kod, font=kod_yazi)) // 2, 432), kod,
             font=kod_yazi, fill="black")
    ciz.line([pay, 506, en - pay, 506], fill="black", width=3)

    # Alıcı.
    y = 524
    ciz.text((pay, y), "ALICI", font=yazi(26, True), fill="black")
    y += 36
    ad = str(p.get("alici") or p.get("musteri") or "").strip()
    for s in _sar(ciz, ad, yazi(54, True), en - 2 * pay, 1):
        ciz.text((pay, y), s, font=yazi(54, True), fill="black")
        y += 68
    for s in _sar(ciz, str(p.get("adres") or ""), yazi(36), en - 2 * pay, 4):
        ciz.text((pay, y), s, font=yazi(36), fill="black")
        y += 46
    yer = " / ".join(x for x in (str(p.get("ilce") or ""), str(p.get("il") or "").upper()) if x)
    y += 4
    ciz.text((pay, y), yer, font=yazi(48, True), fill="black")
    if p.get("telefon"):
        tel = "Tel: " + str(p["telefon"])
        ciz.text((en - pay - ciz.textlength(tel, font=yazi(34)), y + 10), tel,
                 font=yazi(34), fill="black")

    # Alt bilgi: sipariş, içerik, gönderici.
    alt = boy - 150
    ciz.line([pay, alt, en - pay, alt], fill="black", width=3)
    ciz.text((pay, alt + 14), "Sipariş: %s" % p.get("no"), font=yazi(32, True), fill="black")
    for i, s in enumerate(_sar(ciz, "İçerik: " + str(p.get("urunler") or "-"),
                               yazi(30), en - 2 * pay, 1)):
        ciz.text((pay, alt + 56 + i * 38), s, font=yazi(30), fill="black")
    ciz.text((pay, alt + 98), "Gönderici: LEMOS Medikal Sağlık · L'CARLIÉ",
             font=yazi(28), fill="black")

    tampon = io.BytesIO()
    im.save(tampon, format="PNG", dpi=(300, 300))
    return tampon.getvalue()
