"""Uretilen dosyalara panelden erisim.

NEDEN VAR. Sahip 25.09.2026'da soyle dedi: *"yapilan dosyalarin panelden
erisimi icin guzel bir arayuz yap, ben aradigimi bulamiyorum."* Olculdu:

    state/kreatif-brief   293 dosya   64 MB   (brief, senaryo, gorsel)
    varliklar/urun        850 dosya  318 MB   (urun cekimleri)
    knowledge              49 dosya          (sirket bilgi dosyalari)
    varliklar/kutu-gercegi 40 dosya          (kutu metni dogrulamasi)
    evidence               20 dosya          (kanit dokumanlari)

Hicbirine panelden ulasilamiyordu; hepsi yalnizca SSH ile goruluyordu.

🔴 SALT OKUNUR. Bu modul dosya YAZMAZ, SILMEZ, TASIMAZ. Panelden yapilan
bir silme islemi geri alinamaz ve uretim hattinin girdisini yok edebilir;
gorunurluk ile yetki ayri seylerdir.

🔴 YOL KACISI (path traversal) TEK GERCEK RISK. Alan adlari sabit bir
sozlukten gelir ve dosya adi ASLA yol olarak yorumlanmaz: adin icinde
'/' ya da '..' varsa istek reddedilir, ayrica cozulen mutlak yol kayitli
kokun ALTINDA mi diye yeniden dogrulanir. Iki kontrol de gerekli --
birincisi niyeti, ikincisi sonucu denetler (sembolik bag birinciyi atlar).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

KOK = Path(os.environ.get("JARVIS_KOK", "/opt/lcarlie/jarvis-phase2"))

# Alan adi -> (goreli yol, baslik, aciklama)
# Yeni alan eklemek serbest; koku KOK ALTINDA olmayan bir alan eklenemez
# (asagida dogrulanir).
ALANLAR: dict[str, tuple[str, str, str]] = {
    "kreatif": ("state/kreatif-brief", "Kreatif brief",
                "Urun basina uretilen brief, senaryo ve gorsel"),
    "bilgi": ("knowledge", "Sirket bilgisi",
              "Modelin okudugu bilgi dosyalari"),
    "kutu": ("varliklar/kutu-gercegi", "Kutu gercegi",
             "Ambalaj metninin dogrulanmis hali"),
    "kanit": ("evidence", "Kanit",
              "Olcum ve dogrulama dokumanlari"),
    "urun": ("varliklar/urun", "Urun gorselleri",
             "Cekim, kesim ve katalog gorselleri"),
    "tasarim": ("state/tasarim", "Tasarim kararlari",
                "Tasarim gorevlerinin karar dosyalari"),
}

# Panelde ICERIGI gosterilebilen turler. Digerleri yalnizca listelenir.
METIN_UZANTI = {".md", ".txt", ".json", ".csv", ".log", ".sql", ".yaml", ".yml"}
GORSEL_UZANTI = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}

# 🔴 Metin onizlemesi KIRPILIR. 64 MB'lik bir klasorde tek bir dosya
# paneli kilitleyebilir; kirpildigi ACIKCA soylenir, sessizce degil.
AZAMI_METIN = 200_000
AZAMI_IKILI = 8_000_000


class AlanYok(ValueError):
    """Bilinmeyen alan adi."""


class GuvensizAd(ValueError):
    """Dosya adi yol icermez; iceriyorsa istek reddedilir."""


def _kok(alan: str) -> Path:
    if alan not in ALANLAR:
        raise AlanYok(f"bilinmeyen alan: {alan}")
    yol = (KOK / ALANLAR[alan][0]).resolve()
    # Kayitli kokun kendisi de KOK altinda olmali; sozluge yanlis bir yol
    # yazilmasi tum korumayi bosa cikarirdi.
    if not str(yol).startswith(str(KOK.resolve())):
        raise AlanYok(f"alan koku KOK disinda: {alan}")
    return yol


def _tur(ad: str) -> str:
    u = Path(ad).suffix.lower()
    if u in GORSEL_UZANTI:
        return "gorsel"
    if u in METIN_UZANTI:
        return "metin"
    return "diger"


def alanlar() -> list[dict[str, Any]]:
    """Alanlar ve her birinin dosya sayisi.

    Klasor yoksa `durum` VERI_YOK olur; okunamiyorsa OKUNAMADI. Ikisi ayni
    sey degildir ve panelde ayri gosterilir.
    """
    cikti = []
    for ad, (goreli, baslik, aciklama) in ALANLAR.items():
        kayit: dict[str, Any] = {"alan": ad, "baslik": baslik,
                                 "aciklama": aciklama, "yol": goreli}
        try:
            kok = _kok(ad)
        except AlanYok:
            kayit.update(durum="YAPILANDIRMA_HATASI", adet=0, bayt=0)
            cikti.append(kayit)
            continue
        if not kok.is_dir():
            kayit.update(durum="VERI_YOK", adet=0, bayt=0)
            cikti.append(kayit)
            continue
        try:
            adet = bayt = 0
            for p in kok.rglob("*"):
                if p.is_file():
                    adet += 1
                    bayt += p.stat().st_size
            kayit.update(durum="OK", adet=adet, bayt=bayt)
        except OSError as hata:
            kayit.update(durum="OKUNAMADI", adet=0, bayt=0,
                         sebep=type(hata).__name__)
        cikti.append(kayit)
    return cikti


def listele(alan: str, ara: str = "", tur: str = "", limit: int = 200,
            atla: int = 0) -> dict[str, Any]:
    """Bir alandaki dosyalar -- en yeniden eskiye.

    `ara` dosya adinda gecer (kucuk/buyuk harf duyarsiz). `tur` metin /
    gorsel / diger.
    """
    kok = _kok(alan)
    if not kok.is_dir():
        return {"durum": "VERI_YOK", "alan": alan, "toplam": 0, "dosyalar": []}

    ara_k = (ara or "").strip().casefold()
    kayitlar: list[dict[str, Any]] = []
    try:
        for p in kok.rglob("*"):
            if not p.is_file():
                continue
            ad = p.name
            if ara_k and ara_k not in ad.casefold():
                continue
            t = _tur(ad)
            if tur and t != tur:
                continue
            st = p.stat()
            kayitlar.append({
                "ad": ad,
                # Goreli yol gosterilir ama ISTEKTE kullanilmaz; istek
                # yalniz `ad` tasir ve alt klasor taranarak bulunur.
                "klasor": str(p.parent.relative_to(kok)) if p.parent != kok else "",
                "tur": t,
                "bayt": st.st_size,
                "zaman": time.strftime("%Y-%m-%d %H:%M",
                                       time.localtime(st.st_mtime)),
                "_sira": st.st_mtime,
            })
    except OSError as hata:
        return {"durum": "OKUNAMADI", "alan": alan, "toplam": 0,
                "dosyalar": [], "sebep": type(hata).__name__}

    kayitlar.sort(key=lambda k: k["_sira"], reverse=True)
    toplam = len(kayitlar)
    dilim = kayitlar[atla:atla + max(1, min(limit, 500))]
    for k in dilim:
        k.pop("_sira", None)
    return {"durum": "OK", "alan": alan, "toplam": toplam,
            "atla": atla, "dosyalar": dilim}


def _bul(alan: str, ad: str) -> Path:
    """Alan icinde dosyayi ADIYLA bulur. Ad yol iceremez."""
    if not ad or "/" in ad or "\\" in ad or ad.startswith("."):
        raise GuvensizAd("dosya adi yol icermez")
    kok = _kok(alan)
    for p in kok.rglob(ad):
        if p.is_file():
            # 🔴 SONUCU da dogrula: sembolik bag ad kontrolunu atlatabilir.
            cozulmus = p.resolve()
            if not str(cozulmus).startswith(str(kok)):
                raise GuvensizAd("dosya alan kokunun disinda")
            return cozulmus
    raise FileNotFoundError(ad)


def icerik(alan: str, ad: str) -> dict[str, Any]:
    """Metin dosyasinin icerigi. Kirpildiysa ACIKCA soylenir."""
    p = _bul(alan, ad)
    if _tur(ad) != "metin":
        return {"durum": "METIN_DEGIL", "ad": ad, "tur": _tur(ad)}
    try:
        ham = p.read_bytes()
    except OSError as hata:
        return {"durum": "OKUNAMADI", "ad": ad, "sebep": type(hata).__name__}
    kirpildi = len(ham) > AZAMI_METIN
    metin = ham[:AZAMI_METIN].decode("utf-8", "replace")
    cikti: dict[str, Any] = {"durum": "OK", "ad": ad, "tur": "metin",
                             "bayt": len(ham), "kirpildi": kirpildi,
                             "metin": metin}
    if p.suffix.lower() == ".json" and not kirpildi:
        try:
            cikti["json"] = json.loads(metin)
        except json.JSONDecodeError as hata:
            # Bozuk JSON gizlenmez: dosyanin kendisi bozuksa bu bir bulgudur.
            cikti["json_hatasi"] = str(hata)[:200]
    return cikti


def ikili(alan: str, ad: str) -> tuple[bytes, str]:
    """Gorsel baytlari ve icerik tipi. Buyuk dosya reddedilir."""
    p = _bul(alan, ad)
    u = p.suffix.lower()
    if u not in GORSEL_UZANTI:
        raise GuvensizAd("yalnizca gorsel dosyalar dogrudan sunulur")
    st = p.stat()
    if st.st_size > AZAMI_IKILI:
        raise GuvensizAd(f"dosya {st.st_size} bayt -- tavan {AZAMI_IKILI}")
    tipler = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}
    return p.read_bytes(), tipler.get(u, "application/octet-stream")
