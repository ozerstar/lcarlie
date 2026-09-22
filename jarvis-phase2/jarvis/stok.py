"""STOK ARKA PLAN — ticari lisanslı fotoğraf getirir ve KÜNYESİNİ TUTAR.

Sahip 22.09.2026: *"stok görsel sitelerinden arka plan alsan."*

🔴 LİSANS KÜNYESİ ZORUNLU, SÜS DEĞİL.
Bu görseller bir kozmetik markasının reklamında kullanılacak, yani TİCARİ
kullanım. Fotoğrafın nereden geldiği, kimin çektiği ve hangi lisansla
alındığı kaydedilmezse, bir gün "bu görseli nereden aldınız" sorusunun
cevabı olmaz. Her indirilen dosyanın yanına künyesi yazılır.

🔴 İNSAN VE MARKA İÇEREN KARE KULLANILMAZ.
Stok lisansı telif hakkını çözer, KİŞİLİK HAKKINI ve marka hakkını
çözmez: tanınabilir bir insanın fotoğrafını reklamda kullanmak ayrı bir
izin (model release) ister. Bu yüzden sorgular nesne/doku odaklıdır ve
gelen kareler insan/yazı açısından ELEKTEN geçer.

🔴 BOŞLUK ÖLÇÜLÜR.
Reklam karesinde ürün ve iki satır yazı duracak. Fotoğrafın en sakin
bölgesi ölçülerek seçilir; "güzel görünüyor" diye alınan kalabalık bir
kare, üstüne yazı konunca okunmaz olur.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
from PIL import Image

KOK = Path(os.environ.get("JARVIS_STATE_DIR",
                          "/opt/lcarlie/jarvis-phase2/state")) / "stok-arkaplan"
KUNYE = KOK / "kunye.jsonl"

PEXELS_UC = "https://api.pexels.com/v1/search"
# 🔴 Pexels varsayilan Python User-Agent'ini 403 ile reddediyor
# (olculdu: ayni anahtarla curl 200, urllib 403). Kendimizi tanitiriz.
AJAN = "lcarlie-kreatif/1.0 (+https://lcarlie.shop)"

# 🔴 Sorgular NESNE ve DOKU odaklı. "woman skincare" gibi bir sorgu
# tanınabilir insan getirir ve o kare reklamda kullanılamaz.
SORGULAR = (
    "marble surface texture",
    "empty bathroom counter",
    "beige linen fabric texture",
    "minimal stone shelf",
    "soft neutral gradient wall",
    "white ceramic tiles wall",
    "travertine stone background",
    "concrete wall soft light",
)

# Sıcak tonlu kare ELENİR: ölçüldü, sıcak ışık beyaz şişeyi krem yapıyor.
AZAMI_SICAKLIK = 18.0     # R - B ortalaması (YÖN: sıcak mı soğuk mu)
# 🔴 ŞİDDET ayrı ölçülür. Pembe-turkuaz bir duvar soğuk (sıcaklık −16) ve
# dümdüz (boşluk 1.0) olabilir; iki kapıdan da geçer ama marka nötr.
# 0-255 ölçeğinde ortalama doygunluk; nötr gri/beyaz zemin 10'un altında.
AZAMI_DOYGUNLUK = 26.0


@dataclass
class Kare:
    kaynak: str
    foto_id: str
    fotografci: str
    sayfa: str
    indirme: str
    lisans: str
    sorgu: str
    en: int
    boy: int
    dosya: str = ""
    sicaklik: float | None = None
    bosluk_puani: float | None = None
    doygunluk: float | None = None


def _anahtar() -> str:
    a = os.environ.get("PEXELS_API_KEY")
    if not a:
        try:
            from jarvis import providers
            a = providers.load_env().get("PEXELS_API_KEY")
        except Exception:  # noqa: BLE001
            a = None
    if not a:
        raise RuntimeError(
            "PEXELS_API_KEY yok. Ücretsiz anahtar: pexels.com/api — "
            "sonra /etc/lcarlie/jarvis-web.env içine PEXELS_API_KEY=... satırı.")
    return a


def ara(sorgu: str, adet: int = 15, yon: str = "portrait") -> list[Kare]:
    """Pexels'te arar. İNDİRMEZ, yalnız künyeleri döndürür."""
    p = urllib.parse.urlencode({"query": sorgu, "per_page": min(adet, 80),
                                "orientation": yon, "size": "large"})
    istek = urllib.request.Request(
        f"{PEXELS_UC}?{p}",
        headers={"Authorization": _anahtar(), "User-Agent": AJAN})
    with urllib.request.urlopen(istek, timeout=30) as c:
        d = json.loads(c.read().decode("utf-8"))
    out = []
    for f in d.get("photos") or []:
        out.append(Kare(
            kaynak="pexels",
            foto_id=str(f.get("id")),
            fotografci=str(f.get("photographer") or ""),
            sayfa=str(f.get("url") or ""),
            indirme=str((f.get("src") or {}).get("original") or ""),
            # Pexels lisansı: ticari kullanım serbest, atıf zorunlu değil.
            lisans="Pexels License (ticari kullanım serbest, atıf zorunlu değil)",
            sorgu=sorgu,
            en=int(f.get("width") or 0), boy=int(f.get("height") or 0),
        ))
    return out


def _olc(im: Image.Image) -> tuple[float, float, float]:
    """(sıcaklık, boşluk puanı, doygunluk). Üçü de ÖLÇÜM, göz kararı değil."""
    k = im.convert("RGB").resize((160, 200), Image.BILINEAR)
    a = np.asarray(k).astype(float)
    sicaklik = float(a[:, :, 0].mean() - a[:, :, 2].mean())

    # Boşluk: yerel değişimin düşük olduğu alan oranı. Yazı ve ürün
    # sakin bölgeye oturur; kalabalık kare üstüne yazı kaldırmaz.
    gri = a.mean(axis=2)
    dx = np.abs(np.diff(gri, axis=1))[:-1, :]
    dy = np.abs(np.diff(gri, axis=0))[:, :-1]
    kenar = dx + dy
    bosluk = float((kenar < 6).mean())

    # Doygunluk: HSV'nin S kanalı. Nötr zemin düşük, renkli zemin yüksek.
    doygunluk = float(np.asarray(
        k.convert("HSV")).astype(float)[:, :, 1].mean())
    return round(sicaklik, 1), round(bosluk, 3), round(doygunluk, 1)


def indir(kare: Kare, hedef_dizin: Path | None = None) -> Kare | None:
    """Kareyi indirir, ölçer ve künyesiyle kaydeder. Elenirse None."""
    hedef_dizin = hedef_dizin or KOK
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    ad = f"{kare.kaynak}-{kare.foto_id}.jpg"
    yol = hedef_dizin / ad
    if not yol.exists():
        istek = urllib.request.Request(kare.indirme,
                                       headers={"User-Agent": AJAN})
        with urllib.request.urlopen(istek, timeout=90) as c:
            yol.write_bytes(c.read())

    im = Image.open(yol)
    sic, bos, doy = _olc(im)
    kare.dosya, kare.sicaklik, kare.bosluk_puani = ad, sic, bos
    kare.doygunluk = doy

    # 🔴 ELEME ÖLÇÜME GÖRE. Sıcak kare beyaz ambalajı bozar; kalabalık
    # kare yazıyı okunmaz yapar.
    if sic > AZAMI_SICAKLIK:
        yol.unlink(missing_ok=True)
        return None
    if bos < 0.25:
        yol.unlink(missing_ok=True)
        return None
    if doy > AZAMI_DOYGUNLUK:
        # Renkli zemin marka kimliğine aykırı — ekranda görüldü.
        yol.unlink(missing_ok=True)
        return None

    with KUNYE.open("a", encoding="utf-8") as h:
        h.write(json.dumps(asdict(kare), ensure_ascii=False) + "\n")
    return kare


def kutuphane() -> list[dict]:
    """İndirilmiş karelerin künyesi."""
    if not KUNYE.is_file():
        return []
    out = []
    for satir in KUNYE.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir:
            try:
                out.append(json.loads(satir))
            except json.JSONDecodeError:
                continue
    return out
