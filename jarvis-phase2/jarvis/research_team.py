"""Araştırma ekibi: aynı soruya farklı açılardan bakan uzmanlar.

NEDEN VAR
Araştırma tek atıştı: bir soru -> bir sorgu kümesi -> bir tarama -> bitti.
Ekip listesindeki üç araştırma üyesi (Pazar İstihbaratı, Rakip İstihbaratı,
Araştırmacı) ise hiç çalışmıyordu; panelde "dış araştırma gerekir" deyip
susuyorlardı. Yani üç isim vardı, sıfır araştırma.

Sahibin talebi (20.09.2026): "piyasa analizi, rakipler, taktikler, kreatif
düşünceler... birden fazla uzman kullanılması. Bilgi her şeydir. Araştırıp
öğrenebilmesi çok önemli."

NE YAPAR
Bir soruyu AÇILARA böler. Her açı ayrı bir arama turudur ve kendi
sorgusunu kurar: pazar büyüklüğü sorusuyla rakip lansmanı sorusu aynı
sayfaları getirmez. Sonra hepsi tek listede birleştirilir ve KAÇ AÇININ
bulduğu sayılır -- iki açının birden bulduğu kaynak, bir açının bulduğundan
daha önemlidir ve bu sıralamaya girer.

NE ÖĞRENİR
Her bulgu jarvis/knowledge.py'ye yazılır. Aynı soru yarın tekrar
sorulduğunda NEYİN YENİ olduğu ayrılabilir. "Değişen ne?" sorusu
öğrenmenin ölçülebilir ilk hâlidir; sistem neyi bildiğini hatırlamadan
neyin yeni olduğunu söyleyemez.

MALİYETİ AÇIKÇA SÖYLENİR
Her açı ayrı bir tarama demektir. Ölçüldü: bir tur 18-22 saniye. Üç açı
~60 saniye eder. Bu yüzden ekip HER soruda çalışmaz; ayrıca istenir.

SIFIR MODEL ÇAĞRISI
Açı sorguları şablondur, model üretmez. Bulgular deterministik olarak
toplanır. Yorum isteniyorsa o ayrı bir adımdır ve bu modülün işi değildir.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# Aci = (uzman anahtari, gorunur ad, sorguya eklenecek cerceve)
# Cerceve sorgunun SONUNA eklenir; konu kelimeleri kullanicidan gelir.
@dataclass(frozen=True)
class Angle:
    key: str
    name: str
    frame: str
    why: str


ANGLES: tuple[Angle, ...] = (
    Angle("market_intelligence", "Pazar İstihbaratı",
          "pazar büyüklüğü büyüme oranı sektör raporu",
          "Pazarın boyu ve yönü: ne kadar büyük, hangi yöne gidiyor."),
    Angle("competitor_intelligence", "Rakip İstihbaratı",
          "rakip marka yeni ürün lansmanı fiyat",
          "Rakipler ne yapıyor: hangi ürünü, hangi fiyata çıkardılar."),
    Angle("research", "Araştırmacı",
          "",   # kullanicinin sorusunu oldugu gibi sorar
          "Sorunun kendisi: kullanıcının sorduğu hâliyle."),
    Angle("tactics", "Taktik Analisti",
          "strateji taktik kampanya örneği nasıl yapılır",
          "Başkaları bu işi nasıl yapmış: uygulanabilir taktikler."),
    Angle("creative", "Kreatif Gözlemci",
          "reklam örneği kreatif kampanya mesajı",
          "Hangi anlatım tutmuş: kreatif örnekler ve mesaj kalıpları."),
)

DEFAULT_ANGLES = ("market_intelligence", "competitor_intelligence", "research")
BY_KEY = {a.key: a for a in ANGLES}


@dataclass(frozen=True)
class AngleResult:
    key: str
    name: str
    why: str
    query: str
    sources: int
    kept: list[dict[str, Any]] = field(default_factory=list)
    elapsed_s: float = 0.0
    status: str = "OK"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_key(row: dict[str, Any]) -> str:
    """Aynı kaynağı iki açı bulduysa tek sayılmalı."""
    return str(row.get("origin_id") or row.get("publisher")
               or row.get("url") or "").casefold()


def investigate(question: str, controller: Any,
                angles: tuple[str, ...] = DEFAULT_ANGLES,
                remember: bool = True,
                on_progress: Callable[[str], None] | None = None,
                ) -> dict[str, Any]:
    """Soruyu açılara bölüp her birini ayrı araştırır.

    `controller` bir ResearchController'dır; bu modul arama yapmaz, ona
    delege eder -- zaman asimi, devre kesici ve alaka filtresi orada.

    Bir aci basarisiz olursa DIGERLERI DEVAM EDER ve o acinin durumu
    raporlanir. Tek bir zaman asimi butun arastirmayi iptal etmemeli.
    """
    soru = " ".join((question or "").split())
    if not soru:
        raise ValueError("soru boş olamaz")

    secili = [BY_KEY[k] for k in angles if k in BY_KEY] or [BY_KEY["research"]]
    sonuclar: list[AngleResult] = []
    birlesik: dict[str, dict[str, Any]] = {}
    bulan_aci: dict[str, set[str]] = {}

    for aci in secili:
        sorgu = f"{soru} {aci.frame}".strip() if aci.frame else soru
        if on_progress:
            on_progress(f"{aci.name}: araştırılıyor")
        t0 = time.perf_counter()
        try:
            rapor = controller.run(sorgu)
        except Exception as exc:  # noqa: BLE001 - bir aci digerlerini durdurmaz
            sonuclar.append(AngleResult(
                aci.key, aci.name, aci.why, sorgu, 0, [],
                round(time.perf_counter() - t0, 1), "HATA",
                f"{type(exc).__name__}: {str(exc)[:160]}"))
            continue

        gecen = round(time.perf_counter() - t0, 1)
        kaynaklar = list(rapor.get("sources") or [])
        zaman_asimi = int((rapor.get("telemetry") or {}).get("timeouts") or 0)

        for row in kaynaklar:
            anahtar = _source_key(row)
            if not anahtar:
                continue
            birlesik.setdefault(anahtar, row)
            bulan_aci.setdefault(anahtar, set()).add(aci.name)

        # Zaman asimi "kaynak yok" DEGILDIR; ayri raporlanir.
        if not kaynaklar and zaman_asimi:
            durum, detay = "ZAMAN AŞIMI", f"{zaman_asimi} kaynak zaman aşımına uğradı"
        elif not kaynaklar:
            durum, detay = "SONUÇ YOK", str(rapor.get("stop_reason") or "")
        else:
            durum, detay = "OK", str(rapor.get("stop_reason") or "")

        sonuclar.append(AngleResult(
            aci.key, aci.name, aci.why, sorgu, len(kaynaklar),
            [{"url": r.get("url"), "title": r.get("title"),
              "type": r.get("source_type"), "date": r.get("observed_at")}
             for r in kaynaklar[:6]],
            gecen, durum, detay))

    # Kac acinin buldugu = onem sinyali. Iki acinin birden buldugu kaynak
    # tek acinin buldugundan daha merkezi bir kaynaktir.
    sirali = sorted(
        birlesik.items(),
        key=lambda kv: (-len(bulan_aci.get(kv[0], set())),
                        str(kv[1].get("source_type") or "")))

    hafiza = {"stored": 0, "new": 0}
    if remember:
        hafiza = _remember(soru, [row for _k, row in sirali])

    return {
        "question": soru,
        "angles": [a.to_dict() for a in sonuclar],
        "sources": [
            {**{k: row.get(k) for k in ("url", "title", "source_type",
                                        "observed_at", "publisher")},
             "found_by": sorted(bulan_aci.get(anahtar, set()))}
            for anahtar, row in sirali],
        "source_count": len(sirali),
        "cross_confirmed": sum(1 for k in bulan_aci if len(bulan_aci[k]) > 1),
        "memory": hafiza,
        "model_calls": 0,
        "note": ("Her açı ayrı bir aramadır; aynı kaynağı birden çok açı "
                 "bulduysa bir kez sayılır ve kaç açının bulduğu yazılır. "
                 "Yorum yapılmaz -- bulgular ham hâliyle verilir."),
    }


def _remember(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Bulguları kalıcı bilgi defterine yazar. Yazılamazsa araştırma durmaz."""
    try:
        from . import knowledge
    except Exception as exc:  # noqa: BLE001
        return {"stored": 0, "new": 0, "error": f"knowledge yüklenemedi: {exc}"}
    try:
        return knowledge.remember(question, rows)
    except AttributeError:
        # knowledge.remember yoksa modulun kendi akisini bozmadan gec.
        return {"stored": 0, "new": 0,
                "error": "knowledge.remember() tanımlı değil"}
    except Exception as exc:  # noqa: BLE001
        return {"stored": 0, "new": 0, "error": str(exc)[:160]}


def summarize(result: dict[str, Any]) -> str:
    """Ekibin bulduğunu tek paragrafta, kim ne buldu diyerek."""
    acilar = result.get("angles") or []
    calisan = [a for a in acilar if a["status"] == "OK"]
    parcalar = [
        f"{len(acilar)} açıdan arandı, {len(calisan)}'i sonuç verdi; "
        f"toplam {result.get('source_count', 0)} ayrı kaynak."
    ]
    if result.get("cross_confirmed"):
        parcalar.append(
            f"{result['cross_confirmed']} kaynağı birden çok açı buldu "
            f"-- bunlar konunun merkezinde.")
    for aci in acilar:
        if aci["status"] != "OK":
            parcalar.append(f"{aci['name']}: {aci['status']} ({aci['detail'][:60]}).")
    hafiza = result.get("memory") or {}
    if hafiza.get("new"):
        parcalar.append(f"{hafiza['new']} bulgu ilk kez görüldü ve kaydedildi.")
    elif hafiza.get("stored"):
        parcalar.append("Yeni bulgu yok; hepsi daha önce kaydedilmişti.")
    return " ".join(parcalar)
