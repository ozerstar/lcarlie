# -*- coding: utf-8 -*-
"""Reklam uzman ikilisi — META_MEDIA ve MARKETPLACE departmanlarının sorumlusu.

Sahip 15.11.2026: "dünyanın en iyi satışçılarını/reklamlarını incelesin,
stratejileri öğrensin, bu tarafı yönetsin" + "Jarvis ve reklam ekiplerinin
önerileri, ne yapılması gerekiyor".

İki sistem istemi (Desktop\\01 LCARLIE\\REKLAM-UZMAN-IKILISI kaynaklı, depoda
config/reklam-uzman/ altında kopyası durur; düzenleme önce masaüstünde yapılır,
sonra buraya kopyalanır):
  META_MEDIA   -> uzman-1-meta-google.md       (Meta + Google)
  MARKETPLACE  -> uzman-2-pazaryeri-trendyol.md (Trendyol/HB/n11/Idefix)
  ortak        -> L-CARLIE-ozel-durum.md        (hesabın ölçülmüş geçmişi)

Kullananlar: scripts/reklam-oneri.py (öneri üretimi, tam istem) ve
webconsole/app.py::_ekip_sor (müdüre soru; istemin karar kuralları kanıt
olarak). Dosya okunamazsa None döner; uydurulmuş bir istem yazılmaz.
"""
from __future__ import annotations

import re
from pathlib import Path

DIZIN = Path(__file__).resolve().parents[1] / "config" / "reklam-uzman"

DEPARTMAN_UZMAN_ISTEMI = {
    "META_MEDIA": "uzman-1-meta-google.md",
    "MARKETPLACE": "uzman-2-pazaryeri-trendyol.md",
}
ORTAK = "L-CARLIE-ozel-durum.md"
UZMAN_ADI = {"META_MEDIA": "Uzman 1 (Meta/Google)", "MARKETPLACE": "Uzman 2 (Pazaryeri)"}

# _ekip_sor'a kanıt olarak giden karar bölümleri (başlık önekleri)
KARAR_BOLUMLERI = {
    "META_MEDIA": ("## 3.", "### 4.4", "## 5."),
    "MARKETPLACE": ("## 3.", "## 7."),
}


def _oku(ad: str, dizin: Path | None = None) -> str | None:
    try:
        return ((dizin or DIZIN) / ad).read_text(encoding="utf-8")
    except OSError:
        return None


def istem(kod: str, dizin: Path | None = None) -> str | None:
    """Departmanın tam sistem istemi + ortak ölçülmüş durum. Yoksa None."""
    ad = DEPARTMAN_UZMAN_ISTEMI.get(kod)
    if not ad:
        return None
    ana = _oku(ad, dizin)
    if not ana:
        return None
    ortak = _oku(ORTAK, dizin) or ""
    return ana.strip() + ("\n\n---\n\n" + ortak.strip() if ortak else "")


def bolumler(metin: str, onekler: tuple[str, ...]) -> str:
    """Markdown'dan önekle başlayan başlık bölümlerini sırayla çıkarır."""
    satirlar = metin.splitlines()
    out, alin, seviye = [], False, 0
    for s in satirlar:
        m = re.match(r"^(#{1,6}) ", s)
        if m:
            sv = len(m.group(1))
            if alin and sv <= seviye:
                alin = False
            if not alin and any(s.startswith(o) for o in onekler):
                alin, seviye = True, sv
        if alin:
            out.append(s)
    return "\n".join(out).strip()


def karar_kurallari(kod: str, sinir: int = 2200, dizin: Path | None = None) -> str | None:
    """_ekip_sor için kısa yöntem özeti (kanıt bütçesi 6000 karakter)."""
    ad = DEPARTMAN_UZMAN_ISTEMI.get(kod)
    metin = _oku(ad, dizin) if ad else None
    if not metin:
        return None
    parca = bolumler(metin, KARAR_BOLUMLERI.get(kod, ()))
    parca = re.sub(r"\n{3,}", "\n\n", parca)
    return parca[:sinir] if parca else None
