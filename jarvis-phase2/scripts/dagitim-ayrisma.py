#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CANLI ile KAYNAK ayrıştı mı -- ölçer ve alarm üretir.

🔴 BU BETİĞİN VAR OLMA SEBEBİ ÖLÇÜLMÜŞ BİR OLAYDIR. 25.09.2026'da katalog
motorunun dört dosyası kaynak depoda işlendi ama `deploy.sh` koşturulmadı;
canlı ağaçta hiç görünmediler. Betikleri doğrudan kaynak yolundan
çalıştırdığım için fark etmedim ve "katalog motoru çalışıyor" diye rapor
verdim. Dışarıdan bir inceleme yakaladı.

"Depoda var" ile "şu an çalışan sistemde var" AYNI ŞEY DEĞİLDİR.

`deploy.sh` kendi içinde doğrulama yapıyor -- ama yalnız KOŞTURULURSA.
Koşturulmayan bir adımı hiçbir doğrulama yakalamaz. Bu betik o boşluğu
kapatır: kimse bir şey yapmasa bile ayrışmayı görünür kılar.

DAVRANIŞ: hiçbir şeyi düzeltmez, yalnız RAPOR EDER. Otomatik dağıtım
bilerek yapılmıyor -- dağıtım testlerden geçmeyi ve insan kararını
gerektiren bir iştir; sessizce dağıtan bir zamanlayıcı, kapıyı kaldırmak
olurdu.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

KAYNAK = Path("/opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2")
CANLI = Path("/opt/lcarlie/jarvis-phase2")
DURUM = Path(os.environ.get("JARVIS_STATE_DIR", str(CANLI / "state")))
RAPOR = DURUM / "dagitim-ayrisma.json"

# Canlıda BULUNMASI BEKLENMEYEN yollar: dağıtım bunları kopyalamıyor.
ATLA_ONEK = ("tests/", "webconsole/tests/", "migrations/", "docs/")
ATLA_SON = (".md", ".sql", ".sha256")


def izlenen_dosyalar() -> list[str]:
    p = subprocess.run(["git", "ls-files"], cwd=str(KAYNAK),
                       capture_output=True, text=True, check=False)
    if p.returncode:
        raise SystemExit("git ls-files basarisiz: " + (p.stderr or "")[:200])
    return [s for s in p.stdout.splitlines() if s.strip()]


def ozet(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(65536), b""):
            h.update(parca)
    return h.hexdigest()[:16]


def main() -> int:
    t0 = time.time()
    if not KAYNAK.is_dir() or not CANLI.is_dir():
        print("DURDU: kaynak ya da canli dizin yok")
        return 1

    eksik, farkli, bakildi = [], [], 0
    for goreli in izlenen_dosyalar():
        if goreli.startswith(ATLA_ONEK) or goreli.endswith(ATLA_SON):
            continue
        k = KAYNAK / goreli
        c = CANLI / goreli
        if not k.is_file():
            continue
        bakildi += 1
        if not c.is_file():
            eksik.append(goreli)
        elif ozet(k) != ozet(c):
            farkli.append(goreli)

    p = subprocess.run(["git", "log", "-1", "--format=%h %s"], cwd=str(KAYNAK),
                       capture_output=True, text=True, check=False)
    rapor = {
        "olcum_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "kaynak_commit": (p.stdout or "").strip(),
        "bakilan": bakildi,
        "canlida_eksik": sorted(eksik),
        "icerik_farkli": sorted(farkli),
        "ayrisma": len(eksik) + len(farkli),
        "sure_sn": round(time.time() - t0, 2),
    }
    RAPOR.parent.mkdir(parents=True, exist_ok=True)
    gecici = RAPOR.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(rapor, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    gecici.replace(RAPOR)

    print("kaynak: %s" % rapor["kaynak_commit"])
    print("bakilan dosya: %d · %.1f sn" % (bakildi, rapor["sure_sn"]))
    if not rapor["ayrisma"]:
        print("AYRISMA YOK -- canli ile kaynak esit")
        return 0

    print("🔴 AYRISMA: %d dosya" % rapor["ayrisma"])
    if eksik:
        print("  CANLIDA YOK (%d):" % len(eksik))
        for g in sorted(eksik)[:12]:
            print("    " + g)
        if len(eksik) > 12:
            print("    … %d tane daha" % (len(eksik) - 12))
    if farkli:
        print("  ICERIGI FARKLI (%d):" % len(farkli))
        for g in sorted(farkli)[:12]:
            print("    " + g)
        if len(farkli) > 12:
            print("    … %d tane daha" % (len(farkli) - 12))
    print("  Cozum: jarvis-phase2/tools/deploy.sh")
    # Cikis kodu 2: zamanlayici bunu basarisizlik olarak gosterir ve
    # journalctl'de gorunur olur. Sessiz gecmemesi bilincli.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
