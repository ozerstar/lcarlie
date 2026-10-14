"""Sablonlari ve uretilen tasarimlari klasorlerine tasir.

Varliklar (gorseller) yerlesti; tasarimlar hala kokte duruyor. Sablon ile
ciktiyi ayirmak onemli: sablon UZERINDE CALISILAN, cikti URETILEN seydir.
Ayni listede durduklarinda biri digerinin uzerine yazilabilir.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis import canva  # noqa: E402

KOK = Path("/opt/lcarlie/jarvis-phase2/varliklar/urun")
klasorler = json.loads((KOK / "canva-klasor.json").read_text(encoding="utf-8"))

# Kütükten HAZIR şablonların Canva kimlikleri
import subprocess  # noqa: E402
r = subprocess.run(
    ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
     "-U", "n8n", "-d", "n8n", "-c",
     "SELECT DISTINCT canva_id FROM core.tasarim_sablon "
     "WHERE canva_id IS NOT NULL;"],
    capture_output=True, text=True, timeout=30, check=False)
sablonlar = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]

# Üretilen / test tasarımları
r2 = subprocess.run(
    ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-X", "-A", "-t",
     "-U", "n8n", "-d", "n8n", "-c",
     "SELECT DISTINCT canva_tasarim FROM core.tasarim_isi "
     "WHERE canva_tasarim IS NOT NULL;"],
    capture_output=True, text=True, timeout=30, check=False)
ciktilar = [x.strip() for x in (r2.stdout or "").splitlines() if x.strip()]

# Bu oturumda elle üretilen test tasarımları da toplansın
ELLE = ["DAHV3W--Lr4", "DAHV3fnTpCE", "DAHV3Vv3GDs", "DAHV3VPPg3E"]
ciktilar = sorted(set(ciktilar) | set(ELLE) - set(sablonlar))

GERI = (2, 4, 8)


def tasi(oge, kid):
    for i, bekle in enumerate((0,) + GERI):
        if bekle:
            time.sleep(bekle)
        try:
            canva._cagir("/folders/move", metot="POST",
                         govde={"to_folder_id": kid, "item_id": oge})
            return True
        except canva.CanvaHatasi as h:
            m = str(h)
            if ("429" in m or "too_many_requests" in m) and i < len(GERI):
                continue
            print(f"   ⛔ {oge}: {m[:70]}")
            return False
    return False


for ad, liste in (("03 SABLONLAR", sablonlar),
                  ("04 URETILEN TASARIMLAR", ciktilar)):
    kid = klasorler.get(ad)
    if not kid:
        print(f"⛔ klasör yok: {ad}"); continue
    ok = 0
    for o in liste:
        time.sleep(0.4)
        if tasi(o, kid):
            ok += 1
    print(f"  {ad:<26} {ok}/{len(liste)} taşındı")
