"""Knowledge pack yukleyicisi + kaynak kokeni (provenance).

NEDEN KOKEN SART:
    Bir LLM'in kendi urettigi tasarim gorusu "kanitlanmis tasarim
    kurali" DEGILDIR. Bu modul her bilgi ogesini bir kaynaga ve bir
    guven duzeyine baglar; baglanamayan oge kutuge GIREMEZ.

KAYNAK TURLERI -- kademe sirasiyla (yuksekten dusuge):
    STANDARD                   ISO, CIE, ICC gibi normatif belge
    OFFICIAL_DOCUMENTATION     ureticinin/kurumun resmi belgesi
    ACADEMIC                   hakemli yayin
    PROFESSIONAL_REFERENCE     meslek kitabi/yayini
    INTERNAL_BRAND_RULE        sahibin karari -- tartisilmaz ama kanit degil
    MEASURED_INTERNAL_EVIDENCE bizim olcumumuz -- en guclu ic kanit

GUVEN:
    YUKSEK  -- normatif ya da tekrarlanabilir olcum
    ORTA    -- meslek pratigi, tek vaka, baglam farki var
    DUSUK   -- tek blog, dogrulanmamis, yalnizca baslangic noktasi
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass

KAYNAK_TURLERI = (
    "STANDARD",
    "OFFICIAL_DOCUMENTATION",
    "ACADEMIC",
    "PROFESSIONAL_REFERENCE",
    "INTERNAL_BRAND_RULE",
    "MEASURED_INTERNAL_EVIDENCE",
)

GUVEN = ("YUKSEK", "ORTA", "DUSUK")

ZORUNLU_DOSYALAR = (
    "README.md",
    "principles.md",
    "decision-framework.md",
    "failure-modes.md",
    "acceptance-rejection.md",
    "sources.md",
)


@dataclass(frozen=True)
class BilgiOgesi:
    knowledge_id: str
    statement: str
    discipline: str
    source: str
    source_type: str
    confidence: str
    applicability: str
    last_verified: str

    def sozluk(self) -> dict:
        return asdict(self)

    def dogrula(self) -> list[str]:
        sorunlar = []
        if self.source_type not in KAYNAK_TURLERI:
            sorunlar.append("%s: gecersiz source_type %r" % (self.knowledge_id, self.source_type))
        if self.confidence not in GUVEN:
            sorunlar.append("%s: gecersiz confidence %r" % (self.knowledge_id, self.confidence))
        if not self.source.strip():
            sorunlar.append("%s: kaynaksiz oge kutuge giremez" % self.knowledge_id)
        if not self.applicability.strip():
            sorunlar.append("%s: applicability bos -- baglam farki yazilmali" % self.knowledge_id)
        # Blog/dogrulanmamis kaynak YUKSEK guven tasiyamaz
        if self.confidence == "YUKSEK" and self.source_type in (
                "PROFESSIONAL_REFERENCE",) and "blog" in self.source.lower():
            sorunlar.append("%s: blog kaynagi YUKSEK guven tasiyamaz" % self.knowledge_id)
        return sorunlar


def oge_oku(veri: dict) -> BilgiOgesi:
    return BilgiOgesi(
        knowledge_id=veri["knowledge_id"],
        statement=veri["statement"],
        discipline=veri["discipline"],
        source=veri.get("source", ""),
        source_type=veri.get("source_type", ""),
        confidence=veri.get("confidence", ""),
        applicability=veri.get("applicability", ""),
        last_verified=veri.get("last_verified", ""),
    )


def yukle(kok: str | pathlib.Path) -> list[BilgiOgesi]:
    """knowledge/catalog altindaki tum items.json dosyalarini okur."""
    p = pathlib.Path(kok)
    ogeler: list[BilgiOgesi] = []
    for dosya in sorted(p.rglob("items.json")):
        try:
            veri = json.loads(dosya.read_text(encoding="utf-8"))
        except Exception:                            # noqa: BLE001
            continue
        for ham in veri:
            try:
                ogeler.append(oge_oku(ham))
            except KeyError:
                continue
    return ogeler


def yapi_dogrula(kok: str | pathlib.Path) -> dict:
    """Her klasorde zorunlu dosyalar var mi; bos/kopya var mi."""
    p = pathlib.Path(kok)
    if not p.is_dir():
        return {"durum": "YOK", "kok": str(p)}

    klasorler = sorted(d for d in p.iterdir() if d.is_dir())
    eksikler: dict[str, list[str]] = {}
    bos: list[str] = []
    imzalar: dict[str, list[str]] = {}

    for d in klasorler:
        yok = [f for f in ZORUNLU_DOSYALAR if not (d / f).is_file()]
        if yok:
            eksikler[d.name] = yok
        for f in ZORUNLU_DOSYALAR:
            yol = d / f
            if not yol.is_file():
                continue
            govde = yol.read_text(encoding="utf-8").strip()
            if len(govde) < 120:
                bos.append("%s/%s" % (d.name, f))
            # Ayni metnin farkli klasorlere kopyalanmasini yakala
            imzalar.setdefault(govde[:400], []).append("%s/%s" % (d.name, f))

    kopyalar = {k[:60]: v for k, v in imzalar.items() if len(v) > 1}
    return {
        "durum": "OK",
        "klasor_sayisi": len(klasorler),
        "eksik_dosyalar": eksikler,
        "cok_kisa_dosyalar": bos,
        "kopya_icerik": kopyalar,
    }


def ozet(kok: str | pathlib.Path) -> dict:
    ogeler = yukle(kok)
    sorunlar: list[str] = []
    for o in ogeler:
        sorunlar.extend(o.dogrula())

    tur_sayimi: dict[str, int] = {}
    guven_sayimi: dict[str, int] = {}
    disiplin: dict[str, int] = {}
    for o in ogeler:
        tur_sayimi[o.source_type] = tur_sayimi.get(o.source_type, 0) + 1
        guven_sayimi[o.confidence] = guven_sayimi.get(o.confidence, 0) + 1
        disiplin[o.discipline] = disiplin.get(o.discipline, 0) + 1

    return {
        "oge_sayisi": len(ogeler),
        "kaynak_turu_dagilimi": dict(sorted(tur_sayimi.items())),
        "guven_dagilimi": dict(sorted(guven_sayimi.items())),
        "disiplin_dagilimi": dict(sorted(disiplin.items())),
        "koken_sorunlari": sorunlar,
        "yapi": yapi_dogrula(kok),
    }
