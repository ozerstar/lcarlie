# -*- coding: utf-8 -*-
"""WhatsApp Cloud API ile DIŞARIYA mesaj gönderir.

🔴 BU, PROJEDE MÜŞTERİYE DOĞRUDAN ULAŞAN İLK MODÜL.
`satis_dialog` cevabı üretir ama dışarı yolu yoktur; `gelen_kutusu` devir
durumunu yazar ama mesaj göndermez. Gönderme tek bir yerde toplandı ki
kapılar tek yerde denetlenebilsin.

BEŞ KAPI, HEPSİ GEÇİLMEDEN MESAJ ÇIKMAZ
  1. ONAY KAYNAĞI  -- kim istedi? Boş geçilemez. "sahip-panel" insan
                      eylemidir; "jarvis-otomatik" ancak 4. kapı açıkken
                      kabul edilir.
  2. METİN         -- boş değil, 4096 baytı aşmıyor (WhatsApp sınırı).
  3. MEVZUAT       -- `compliance.review` BLOCKED verirse mesaj ÇIKMAZ.
                      Bu kapı insan onayıyla da aşılmaz: sahip yanlışlıkla
                      onaylarsa bile iddia içeren metin gitmemeli.
  4. GÖNDERME ANAHTARI -- `JARVIS_WHATSAPP_GONDER=1` yoksa kapalı.
                      VARSAYILAN KAPALI; açmak bilinçli bir karardır.
  5. KİMLİK        -- anahtar ve telefon kimliği yoksa gönderilmez.

🔴 HER DENEME DEFTERE YAZILIR -- gönderilen de, reddedilen de. Reddedilen
denemeyi kaydetmemek, "hiç denenmedi" ile "engellendi"yi aynı gösterirdi;
bu projede o ayrımın kaybolması daha önce iki gün süren bir arızayı gizledi.

Kuru koşu (`kuru=True`) 1-3. kapıları işletir ama ağa çıkmaz: panelde
"ne gidecekti" sorusunun cevabı buradan alınır.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import compliance

ENV_DOSYASI = os.environ.get("META_ENV_FILE", "/opt/lcarlie/n8n/.env")
DEFTER = Path(os.environ.get("JARVIS_STATE_DIR",
                             "/opt/lcarlie/jarvis-phase2/state")) / "whatsapp-gonderim.jsonl"
API = "https://graph.facebook.com/v21.0"
METIN_SINIRI = 4096
ZAMAN_ASIMI = 25.0

ONAY_INSAN = "sahip-panel"
ONAY_OTOMATIK = "jarvis-otomatik"
GECERLI_ONAYLAR = frozenset({ONAY_INSAN, ONAY_OTOMATIK})


class GondermeReddedildi(RuntimeError):
    """Bir kapı geçilemedi. Mesaj GÖNDERİLMEDİ."""


def _env(anahtar: str) -> str:
    dogrudan = os.environ.get(anahtar)
    if dogrudan:
        return dogrudan
    try:
        for satir in Path(ENV_DOSYASI).read_text(encoding="utf-8").splitlines():
            if satir.startswith(anahtar + "="):
                return satir.split("=", 1)[1].strip()
    except OSError:
        return ""
    return ""


def gonderme_acik() -> bool:
    """4. kapı. Varsayılan KAPALI."""
    return os.environ.get("JARVIS_WHATSAPP_GONDER", "0") == "1"


def _defter_yaz(kayit: dict[str, Any]) -> None:
    """Defter bozulsa bile çağrıyı durdurmaz; ama sessiz de kalmaz."""
    try:
        DEFTER.parent.mkdir(parents=True, exist_ok=True)
        with DEFTER.open("a", encoding="utf-8") as dosya:
            dosya.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError as hata:  # noqa: BLE001 - defter cagriyi durduramaz
        import sys
        sys.stderr.write("[whatsapp] defter yazilamadi: %s\n" % hata)


def _telefon_sadele(numara: str) -> str:
    """Yalnız rakam. WhatsApp ülke kodlu, artısız bekler."""
    return "".join(ch for ch in str(numara or "") if ch.isdigit())


def denetle(metin: str) -> list[dict[str, str]]:
    """3. kapı: mevzuat bulguları. Boş liste = temiz."""
    inceleme = compliance.review(metin or "")
    return [f.to_dict() for f in inceleme.blocked]


def gonder(telefon: str, metin: str, *, onay_kaynagi: str,
           konusma_id: int | None = None, kuru: bool = False) -> dict[str, Any]:
    """Tek mesaj gönderir. Her kapı ayrı ayrı denetlenir ve kaydedilir."""
    baslangic = time.time()
    kayit: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "telefon_son4": _telefon_sadele(telefon)[-4:],
        "konusma_id": konusma_id,
        "onay_kaynagi": onay_kaynagi,
        "uzunluk": len(metin or ""),
        "kuru": bool(kuru),
    }

    def reddet(sebep: str, ayrinti: Any = None) -> None:
        kayit.update({"sonuc": "REDDEDILDI", "sebep": sebep})
        if ayrinti is not None:
            kayit["ayrinti"] = ayrinti
        _defter_yaz(kayit)
        raise GondermeReddedildi(sebep)

    # 1. ONAY KAYNAGI
    if onay_kaynagi not in GECERLI_ONAYLAR:
        reddet("onay kaynagi gecersiz: %r" % (onay_kaynagi,))

    # 2. METIN
    temiz = (metin or "").strip()
    if not temiz:
        reddet("metin bos")
    if len(temiz.encode("utf-8")) > METIN_SINIRI:
        reddet("metin %d bayt sinirini asiyor" % METIN_SINIRI)

    # 3. MEVZUAT -- insan onayiyla da asilmaz
    bulgular = denetle(temiz)
    if bulgular:
        reddet("mevzuat kapisi: %d bulgu" % len(bulgular),
               [b.get("matched") for b in bulgular])

    numara = _telefon_sadele(telefon)
    if len(numara) < 10:
        reddet("telefon numarasi gecersiz")

    if kuru:
        kayit.update({"sonuc": "KURU", "sebep": "kuru kosu, aga cikilmadi"})
        _defter_yaz(kayit)
        return {"gonderildi": False, "kuru": True, "metin": temiz,
                "telefon": numara, "bulgular": []}

    # 4. GONDERME ANAHTARI
    if not gonderme_acik():
        reddet("gonderme KAPALI (JARVIS_WHATSAPP_GONDER=1 degil)")

    # 5. KIMLIK
    jeton = _env("META_WHATSAPP_TOKEN")
    telefon_id = _env("META_WHATSAPP_PHONE_NUMBER_ID")
    if not jeton or not telefon_id:
        reddet("anahtar veya telefon kimligi yok")

    govde = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numara,
        "type": "text",
        "text": {"preview_url": False, "body": temiz},
    }).encode("utf-8")
    istek = urllib.request.Request(
        f"{API}/{telefon_id}/messages", data=govde, method="POST",
        headers={"Authorization": "Bearer " + jeton,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
            veri = json.loads(yanit.read().decode("utf-8"))
    except urllib.error.HTTPError as hata:
        # 🔴 Hata govdesi anahtar ICEREBILIR; yalniz kod ve kisa metin alinir.
        try:
            detay = json.loads(hata.read().decode("utf-8")).get("error", {})
            ozet = str(detay.get("message", ""))[:160]
        except Exception:  # noqa: BLE001 - hata govdesi okunamazsa kod yeter
            ozet = ""
        reddet("Meta HTTP %d" % hata.code, ozet)
    except (OSError, TimeoutError) as hata:
        reddet("ag hatasi: %s" % type(hata).__name__)

    wamid = ""
    mesajlar = veri.get("messages") or []
    if mesajlar:
        wamid = str(mesajlar[0].get("id") or "")
    kayit.update({"sonuc": "GONDERILDI", "wamid": wamid,
                  "gecikme_ms": round((time.time() - baslangic) * 1000, 1)})
    _defter_yaz(kayit)
    return {"gonderildi": True, "wamid": wamid, "telefon": numara,
            "metin": temiz, "bulgular": []}
