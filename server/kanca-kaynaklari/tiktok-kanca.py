#!/usr/bin/env python3
"""TikTok organik kanca kaynagi — ms_token ile calisir.

🔴 NEDEN TOKEN GEREKIYOR. Olculdu (22.09.2026, ALTI yol denendi):

    TikTok-Api + chromium headless      -> EmptyResponseException (bot tespiti)
    TikTok-Api + webkit (deps kuruldu)  -> EmptyResponseException
    TikTok-Api + Xvfb, headless=False   -> EmptyResponseException
    yt-dlp hashtag sayfasi              -> "No working app info is available"
    yt-dlp marka hesabi                 -> "Unable to extract secondary user ID"
    grounded arama ile baglanti toplama -> 0 tiktok.com baglantisi

TikTok sunucu IP'lerinden gelen oturumsuz istekleri bosa donduruyor. Bu bir
kod sorunu degil, KIMLIK sorunu. Cozum: gercek bir tarayici oturumundan
alinan `ms_token` cerezi.

TOKEN NASIL ALINIR (2 dakika, tarayicidan):
  1. Chrome'da tiktok.com ac ve giris yap
  2. F12 -> Application -> Cookies -> https://www.tiktok.com
  3. `msToken` satirindaki Value degerini kopyala
  4. Sunucuda: /etc/lcarlie/tiktok.env icine
         TIKTOK_MS_TOKEN=<yapistir>
  Token birkac haftada bir yenilenmeli; suresi dolunca bu betik
  "token gecersiz" der ve hat SESSIZCE devam eder.

🔴 TOKEN YOKSA HATA VERMEZ, BOS DONER. Kanca havuzu bes kaynakli; biri
calismiyorsa digerleri beslemeye devam eder. Eksik kaynak brief'i
durdurmaz -- ama LOG'a yazar, cunku "kaynak yok" ile "kaynak bos dondu"
ayri durumlardir.

GIRDI  (stdin, JSON): {"etiketler": ["sacbakimi", ...], "azami": 6,
                       "asgari_izlenme": 50000}
CIKTI  (stdout, JSON): [{"metin","kanal","izlenme","video_id","etiket"}]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOKEN_DOSYASI = Path(os.environ.get("TIKTOK_ENV", "/etc/lcarlie/tiktok.env"))
KOK = Path(__file__).resolve().parent
YTDLP = KOK / "venv-kanca" / "bin" / "yt-dlp"
SANIYE = 8
AZAMI_SURE = 120
MODEL_ADI = "small"

UYDURMA = ("altyazı", "altyazi", "abone ol", "amara.org", "subtitle",
           "beni izlediğiniz", "iyi seyirler")


def token_oku() -> str:
    for kaynak in (os.environ.get("TIKTOK_MS_TOKEN"), None):
        if kaynak:
            return kaynak.strip()
    try:
        for satir in TOKEN_DOSYASI.read_text(encoding="utf-8").splitlines():
            if satir.startswith("TIKTOK_MS_TOKEN="):
                return satir.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ""


def uydurma_mi(metin: str) -> bool:
    duz = metin.casefold().strip()
    if len(duz.split()) < 3:
        return True
    return any(k in duz for k in UYDURMA)


def ses_al(url: str, hedef: Path) -> bool:
    taban = str(hedef.with_suffix(""))
    for komut in (
        [str(YTDLP), url, "-f", "bestaudio/best",
         "--download-sections", f"*0-{SANIYE}", "--force-keyframes-at-cuts",
         "-x", "--audio-format", "wav", "-o", taban, "--no-warnings", "--quiet"],
        [str(YTDLP), url, "-f", "bestaudio/best", "-x", "--audio-format", "wav",
         "-o", taban, "--no-warnings", "--quiet"],
    ):
        try:
            r = subprocess.run(komut, capture_output=True, timeout=240)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if r.returncode == 0 and hedef.exists() and hedef.stat().st_size > 1000:
            return True
    return False


async def videolari_bul(etiketler: list[str], token: str, azami: int,
                        asgari: int) -> list[dict]:
    from TikTokApi import TikTokApi

    bulunan: dict[str, dict] = {}
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[token], num_sessions=1,
                                  sleep_after=3, headless=True,
                                  browser="chromium")
        for etiket in etiketler[:3]:
            try:
                async for video in api.hashtag(name=etiket).videos(count=20):
                    d = video.as_dict
                    kimlik = str(d.get("id") or "")
                    stats = d.get("stats") or {}
                    izlenme = int(stats.get("playCount") or 0)
                    sure = int((d.get("video") or {}).get("duration") or 0)
                    if not kimlik or izlenme < asgari or sure > AZAMI_SURE:
                        continue
                    yazar = (d.get("author") or {}).get("uniqueId") or ""
                    bulunan.setdefault(kimlik, {
                        "video_id": kimlik, "izlenme": izlenme, "sure": sure,
                        "kanal": str(yazar)[:60], "etiket": etiket,
                        "url": f"https://www.tiktok.com/@{yazar}/video/{kimlik}",
                    })
            except Exception as hata:  # noqa: BLE001
                print(f"tiktok/{etiket}: {type(hata).__name__}: "
                      f"{str(hata)[:110]}", file=sys.stderr)
    return sorted(bulunan.values(), key=lambda v: v["izlenme"],
                  reverse=True)[:azami]


def main() -> int:
    try:
        istek = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[]")
        return 1
    etiketler = [re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]", "", e)
                 for e in (istek.get("etiketler") or []) if e]
    if not etiketler:
        print("[]")
        return 0

    token = token_oku()
    if not token:
        print("[]")
        print(f"tiktok: ms_token YOK ({TOKEN_DOSYASI}) — kaynak atlandı. "
              "Token almak için betiğin başındaki yönergeye bak.",
              file=sys.stderr)
        return 0

    try:
        videolar = asyncio.run(videolari_bul(
            etiketler, token, int(istek.get("azami") or 6),
            int(istek.get("asgari_izlenme") or 50000)))
    except Exception as hata:  # noqa: BLE001
        print("[]")
        print(f"tiktok: oturum kurulamadı ({type(hata).__name__}: "
              f"{str(hata)[:140]}) — token süresi dolmuş olabilir",
              file=sys.stderr)
        return 0

    if not videolar:
        print("[]")
        print("tiktok: eşiği geçen video bulunamadı", file=sys.stderr)
        return 0

    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL_ADI, device="cpu", compute_type="int8")
    cikti = []
    with tempfile.TemporaryDirectory() as gecici:
        for v in videolar:
            ses = Path(gecici) / f"{v['video_id']}.wav"
            if not ses_al(v["url"], ses):
                continue
            try:
                parcalar, _ = model.transcribe(str(ses), language="tr",
                                               beam_size=1)
                metin = " ".join(p.text.strip() for p in parcalar).strip()
            except Exception:  # noqa: BLE001
                continue
            ilk = metin.split(". ")[0].strip(" .")
            if 10 <= len(ilk) <= 200 and not uydurma_mi(ilk):
                cikti.append({"metin": ilk, "kanal": v["kanal"],
                              "izlenme": v["izlenme"],
                              "video_id": v["video_id"], "etiket": v["etiket"]})
            ses.unlink(missing_ok=True)

    print(json.dumps(cikti, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
