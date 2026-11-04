#!/usr/bin/env python3
"""Reklam videosunun ilk saniyelerinden KONUŞULAN kancayı çıkarır.

NEDEN AYRI BİR BETİK
====================
🔴 Bu dosya `venv-kanca` içinde çalışır, Jarvis'in ana venv'inde DEĞİL.
`faster_whisper` ve `yt-dlp` ana venv'e kurulmaz; kreatif-brief.py buraya
alt süreç olarak seslenir. Aynı ders MCP sunucusunda da yaşandı: ağır ve
sürümü oynak bağımlılıklar ana ortama karıştırılmaz.

NEDEN GEREKLİ
=============
Yazılı reklam metni ile videoda SÖYLENEN cümle aynı şey değil. Ölçüldü
(21.09.2026, Propia Türkiye reklamı):

    yazılı  : "#reklam @propiaturkiye Saç dökülmesi başlayınca insan ister…"
    söylenen: "Şuradaki bebek saçlarımın ne kadar örtüldüğüne bakar mısınız?"

İzleyiciyi ilk 3 saniyede tutan şey ikincisi. Grounded arama bunu ASLA
göremez çünkü hiçbir web sayfasında yazmıyor -- videonun içinde konuşuluyor.
Organik/UGC kancasının tek gerçek kaynağı budur.

GİRDİ  (stdin, JSON) : [{"id": "...", "url": "...", "marka": "..."}]
ÇIKTI  (stdout, JSON): [{"id": "...", "metin": "...", "marka": "..."}]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SANIYE = 8          # kanca ilk saniyelerde; videonun tamamı indirilmez
MODEL_ADI = "small"  # tiny/base Türkçe'de kullanılamaz kalitede
AZAMI_VIDEO = 8      # bir koşuda en fazla kaç video


def ses_al(url: str, hedef: Path) -> bool:
    """Videonun ilk saniyelerinin sesini alır. Tüm dosya indirilmez."""
    komut = ["ffmpeg", "-y", "-loglevel", "error", "-t", str(SANIYE),
             "-i", url, "-vn", "-ac", "1", "-ar", "16000", str(hedef)]
    try:
        r = subprocess.run(komut, capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and hedef.exists() and hedef.stat().st_size > 1000


def main() -> int:
    try:
        girdi = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("[]")
        return 1
    if not isinstance(girdi, list) or not girdi:
        print("[]")
        return 0

    from faster_whisper import WhisperModel

    model = WhisperModel(MODEL_ADI, device="cpu", compute_type="int8")
    cikti = []
    with tempfile.TemporaryDirectory() as gecici:
        for kayit in girdi[:AZAMI_VIDEO]:
            url = str(kayit.get("url") or "")
            if not url:
                continue
            ses = Path(gecici) / "k.wav"
            if not ses_al(url, ses):
                continue
            try:
                parcalar, _ = model.transcribe(str(ses), language="tr", beam_size=1)
                metin = " ".join(p.text.strip() for p in parcalar).strip()
            except Exception:  # noqa: BLE001
                continue
            # 🔴 Kanca = İLK cümle. Transkript 8 saniyeyi kapsar ama kanca
            # onun başıdır; tamamını almak kancayı sulandırır.
            ilk = metin.split(". ")[0].strip(" .")
            if 10 <= len(ilk) <= 200:
                cikti.append({"id": kayit.get("id"), "metin": ilk,
                              "marka": kayit.get("marka", "")})
            ses.unlink(missing_ok=True)

    print(json.dumps(cikti, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
