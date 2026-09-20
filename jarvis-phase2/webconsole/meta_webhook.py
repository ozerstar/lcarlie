"""Meta (Messenger/Instagram) webhook: doğrula, ayrıştır, KUYRUĞA yaz.

NEDEN VAR
Mesajlar bugün 4 saatte bir toplu çekiliyor (`meta-aktar.sh`). İki sorunu
var: (1) 24 saatlik cevap penceresinde 4 saat gecikmek doğal bir sohbeti
öldürür, (2) toplu çekim **reklam referansını getirmiyor** -- oysa müşteri
ürün adını hiç yazmıyor (ölçüldü: 540 mesajın 0'ında) ve hangi ürünü
kastettiği YALNIZCA geldiği reklamdan (`referral.ad_id`) bilinir.

🔴 NEDEN DOĞRUDAN VERİTABANINA YAZMIYOR
İki sebep, ikisi de bu projede yaşanmış:
1. Meta, yanıt gecikirse aynı olayı TEKRAR gönderir. Webhook hızlı 200
   dönmeli; DB yazmasını isteğin içine koymak hem yavaşlatır hem bir DB
   takılmasında mesajı kaybettirir.
2. `jarvis-web` veritabanına YALNIZ OKUMA kimliğiyle (`ai_reader`) bakar.
   Yazma yetkisi buraya taşınırsa mimarinin sınırı delinir.
Bu yüzden olay bir JSONL kuyruğuna yazılır; yükleyici betik onu `lcarlie`
şemasına aktarır. Kuyruk dosyası, yükleyici çökse bile olayı korur.

🔴 İMZASIZ İSTEK KABUL EDİLMEZ
`X-Hub-Signature-256` Meta'nın uygulama gizi ile hesaplanır. Giz yoksa
doğrulama YAPILAMAZ ve o zaman bu uç, isteyen herkesin sahte müşteri
mesajı enjekte edebileceği bir kapıya dönüşür. Giz yokken uç 503 döner ve
sebebini söyler -- sessizce güvensiz çalışmaz.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Any

# Meta'nın çağırdığı yol. Caddy jarvis.lcarlie.shop'u bu servise veriyor.
WEBHOOK_PATH = "/webhook/meta"

_ENV_DOSYASI = os.environ.get("META_ENV_FILE", "/opt/lcarlie/n8n/.env")


def _env_oku(anahtar: str) -> str:
    """Değeri .env'den okur. Süreç ortamı önce gelir (test ve geçici override)."""
    dogrudan = os.environ.get(anahtar)
    if dogrudan:
        return dogrudan.strip()
    try:
        metin = Path(_ENV_DOSYASI).read_text(encoding="utf-8")
    except OSError:
        return ""
    # 🔴 `cut -d= -f2` KULLANMA: bu projede 721 karakterlik bir anahtar
    # içinde '=' geçtiği için bir kez bozulmuştu.
    eslesme = re.search(rf"^{re.escape(anahtar)}=(.*)$", metin, re.MULTILINE)
    return eslesme.group(1).strip().strip('"').strip("'") if eslesme else ""


def uygulama_gizi() -> str:
    return _env_oku("META_APP_SECRET")


def dogrulama_anahtari() -> str:
    return _env_oku("META_VERIFY_TOKEN")


def imza_gecerli(govde: bytes, imza_basligi: str, giz: str) -> bool:
    """X-Hub-Signature-256 doğrulaması.

    `compare_digest` kullanılıyor: normal `==` karşılaştırması ilk farklı
    baytta döner ve zamanlama üzerinden imza tahmin edilebilir.
    """
    if not giz or not imza_basligi:
        return False
    if not imza_basligi.startswith("sha256="):
        return False
    beklenen = hmac.new(giz.encode("utf-8"), govde, hashlib.sha256).hexdigest()
    return hmac.compare_digest(beklenen, imza_basligi[len("sha256="):])


def dogrulama_yaniti(sorgu: dict[str, list[str]], anahtar: str) -> tuple[int, str]:
    """Meta'nın ilk GET el sıkışması.

    Anahtar eşleşirse `hub.challenge` AYNEN geri döner; Meta bunu bekler.
    Eşleşmezse 403 -- yanlış anahtarla kurulan bir uç sessizce çalışır
    görünüp hiç olay almazdı.
    """
    mod = (sorgu.get("hub.mode") or [""])[0]
    gelen = (sorgu.get("hub.verify_token") or [""])[0]
    challenge = (sorgu.get("hub.challenge") or [""])[0]
    if mod != "subscribe":
        return 400, "beklenen hub.mode=subscribe"
    if not anahtar:
        return 503, "META_VERIFY_TOKEN tanımlı değil"
    if not hmac.compare_digest(gelen, anahtar):
        return 403, "doğrulama anahtarı eşleşmedi"
    return 200, challenge


def dogrulama_yanit_ver(sorgu: dict[str, list[str]]) -> tuple[int, str]:
    """Anahtarı kendisi okuyan sarmalayıcı; çağıranın env bilmesine gerek yok."""
    return dogrulama_yaniti(sorgu, dogrulama_anahtari())


def olaylari_ayristir(yuk: dict[str, Any]) -> list[dict[str, Any]]:
    """Meta yükünü düz olay listesine çevirir.

    Yalnızca GERÇEKTEN gelen alanlar taşınır. Eksik alan uydurulmaz:
    reklam referansı yoksa `ad_id` None kalır ve ürün TAHMİN EDİLMEZ.
    """
    olaylar: list[dict[str, Any]] = []
    for giris in (yuk.get("entry") or []):
        sayfa_id = str(giris.get("id") or "")
        for olay in (giris.get("messaging") or []):
            mesaj = olay.get("message") or {}
            # Kendi gönderdiğimiz mesajın yankısı: kaydedilir ama müşteri
            # mesajı SAYILMAZ, yoksa kendi cevabımıza cevap üretiriz.
            yanki = bool(mesaj.get("is_echo"))
            referral = (olay.get("referral")
                        or (olay.get("postback") or {}).get("referral")
                        or {})
            olaylar.append({
                "sayfa_id": sayfa_id,
                "gonderen_id": str((olay.get("sender") or {}).get("id") or ""),
                "alici_id": str((olay.get("recipient") or {}).get("id") or ""),
                "mesaj_id": str(mesaj.get("mid") or ""),
                "metin": mesaj.get("text") or "",
                "yanki": yanki,
                "zaman_ms": olay.get("timestamp"),
                # Ürünün TEK güvenilir kaynağı.
                "ad_id": referral.get("ad_id"),
                "referral_ref": referral.get("ref"),
                "referral_kaynak": referral.get("source"),
                "ek": {"attachments": mesaj.get("attachments")} if mesaj.get("attachments") else {},
            })
    return olaylar


def kuyruga_yaz(olaylar: list[dict[str, Any]], kuyruk: Path) -> int:
    """Olayları JSONL kuyruğuna ekler. Yazılan satır sayısını döner.

    Ekleme modunda ve satır satır: yarıda kalan bir yazma yalnız son satırı
    bozar, dosyanın tamamını değil.
    """
    if not olaylar:
        return 0
    kuyruk.parent.mkdir(parents=True, exist_ok=True)
    with kuyruk.open("a", encoding="utf-8") as dosya:
        for olay in olaylar:
            dosya.write(json.dumps({**olay, "alindi_at": time.time()},
                                   ensure_ascii=False) + "\n")
    try:
        os.chmod(kuyruk, 0o640)
    except OSError:
        pass
    return len(olaylar)
