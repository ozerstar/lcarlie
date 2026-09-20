"""Tokensiz araştırma → kalıcı bilgi birikimi.

NE YAPAR
Yapılandırılmış konular için mevcut Research Controller'ı çalıştırır ve
bulguları kaynağıyla birlikte kalıcı bir dosyaya yazar. Her kayıt nereden
geldiğini, ne zaman görüldüğünü ve içerik parmak izini taşır.

SIFIR MODEL ÇAĞRISI
Arama, çekme, çıkarma, alaka ve tekilleştirme -- hepsi deterministik.
Bu modül bilerek hiçbir modele bağlanmaz: token maliyeti sıfırdır ve
sağlayıcı kotası dolsa bile çalışmaya devam eder.

ÖĞRENMENİN SUBSTRATI
Aynı konu tekrar araştırıldığında yeni olan ayrılır. "Değişen ne?" sorusu,
öğrenmenin ölçülebilir ilk hâlidir: sistem neyi zaten bildiğini
hatırlamadan neyin yeni olduğunu söyleyemez.

NE YAPMAZ
Hiçbir şey önermez, hiçbir şey yayımlamaz, kendi kodunu değiştirmez.
Bulgular kaydedilir; onlardan aksiyon üretmek Action Firewall'un işidir.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
KNOWLEDGE_LOG = STATE_DIR / "knowledge.jsonl"
TOPICS_FILE = STATE_DIR / "research_topics.json"

# Konu başına saklanacak en fazla kayıt; dosya sınırsız büyümesin.
MAX_PER_TOPIC = 40
# Bir kaynağın kaç karakteri saklanır. Snippet zaten kısadır; bu, tam sayfa
# metninin diske yığılmasını engeller.
MAX_CONTENT_CHARS = 2000

DEFAULT_TOPICS = (
    "dermokozmetik pazar raporu son gelişmeler",
    "dermokozmetik rakip markalar yeni ürün lansmanı",
    "kozmetik mevzuat yönetmelik değişikliği",
)


@dataclass(frozen=True)
class KnowledgeItem:
    topic: str
    url: str
    publisher: str
    source_type: str
    title: str
    snippet: str
    content_hash: str
    observed_at: str
    first_seen: str
    relevance: float = 0.0
    injection_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRun:
    topic: str
    new_items: tuple[KnowledgeItem, ...] = ()
    known_items: int = 0
    stop_reason: str = ""
    confidence: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    model_calls: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "new": len(self.new_items),
            "known": self.known_items,
            "stop_reason": self.stop_reason,
            "confidence": self.confidence,
            "duration_ms": self.duration_ms,
            "model_calls": self.model_calls,
            "error": self.error,
            "items": [item.to_dict() for item in self.new_items],
        }


def load_topics() -> tuple[str, ...]:
    """Konular dosyadan okunur; yoksa varsayılan set kullanılır."""
    if TOPICS_FILE.is_file():
        try:
            data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
            topics = tuple(str(t).strip() for t in data.get("topics", []) if str(t).strip())
            if topics:
                return topics
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_TOPICS


def _known_hashes() -> dict[str, set[str]]:
    """Konu başına daha önce görülmüş içerik parmak izleri."""
    seen: dict[str, set[str]] = {}
    if not KNOWLEDGE_LOG.is_file():
        return seen
    for line in KNOWLEDGE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        topic = str(row.get("topic") or "")
        digest = str(row.get("content_hash") or "")
        if topic and digest:
            seen.setdefault(topic, set()).add(digest)
    return seen


def _append(items: list[KnowledgeItem]) -> None:
    if not items:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with KNOWLEDGE_LOG.open("a", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")


def research_topic(controller: Any, topic: str, known: set[str],
                   now: str | None = None) -> ResearchRun:
    """Tek konuyu araştırır ve YENİ olanları döndürür."""
    now = now or datetime.now(timezone.utc).isoformat()
    started = perf_counter()
    try:
        result = controller.run(topic)
    except Exception as exc:  # noqa: BLE001
        return ResearchRun(topic=topic, error=str(exc)[:300],
                           duration_ms=round((perf_counter() - started) * 1000, 3))

    fresh: list[KnowledgeItem] = []
    already = 0
    for source in result.get("sources", []):
        digest = str(source.get("content_hash") or "")
        if not digest:
            continue
        if digest in known:
            already += 1
            continue
        known.add(digest)
        snippets = source.get("evidence_snippets") or ()
        snippet = " ".join(str(s) for s in snippets)[:MAX_CONTENT_CHARS]
        if not snippet:
            snippet = str(source.get("content") or "")[:MAX_CONTENT_CHARS]
        fresh.append(KnowledgeItem(
            topic=topic,
            url=str(source.get("canonical_url") or source.get("url") or ""),
            publisher=str(source.get("publisher") or ""),
            source_type=str(source.get("source_type") or "UNKNOWN"),
            title=str(source.get("title") or "")[:300],
            snippet=snippet,
            content_hash=digest,
            observed_at=str(source.get("observed_at") or ""),
            first_seen=now,
            relevance=float(source.get("relevance") or 0.0),
            injection_detected=bool(source.get("injection_detected")),
        ))

    return ResearchRun(
        topic=topic, new_items=tuple(fresh[:MAX_PER_TOPIC]), known_items=already,
        stop_reason=str(result.get("stop_reason") or ""),
        confidence=dict(result.get("confidence_breakdown") or {}),
        duration_ms=round((perf_counter() - started) * 1000, 3),
        model_calls=int(result.get("model_calls") or 0))


def run(controller: Any, topics: tuple[str, ...] | None = None,
        now: str | None = None) -> dict[str, Any]:
    """Tüm konuları araştırır, yenileri kaydeder ve özet döndürür."""
    topics = topics if topics is not None else load_topics()
    known = _known_hashes()
    runs: list[ResearchRun] = []
    for topic in topics:
        result = research_topic(controller, topic, known.setdefault(topic, set()), now=now)
        _append(list(result.new_items))
        runs.append(result)

    total_new = sum(len(r.new_items) for r in runs)
    failed = [r.topic for r in runs if r.error]
    injections = [item.url for r in runs for item in r.new_items if item.injection_detected]
    return {
        "topics": len(topics),
        "new_items": total_new,
        "known_items": sum(r.known_items for r in runs),
        "failed_topics": failed,
        "model_calls": sum(r.model_calls for r in runs),
        "external_actions": 0,
        "injection_flagged": injections,
        "runs": [r.to_dict() for r in runs],
        "store": str(KNOWLEDGE_LOG),
        "note": ("Bulgular kaydedildi. Hiçbiri öneriye dönüşmedi; aksiyon "
                 "üretmek Action Firewall'un işidir."),
    }


def summary(limit: int = 10) -> dict[str, Any]:
    """Birikmiş bilginin özeti -- panel ve rapor için."""
    if not KNOWLEDGE_LOG.is_file():
        return {"total": 0, "topics": [], "publishers": []}
    rows = []
    for line in KNOWLEDGE_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    by_topic: dict[str, int] = {}
    by_publisher: dict[str, int] = {}
    for row in rows:
        by_topic[row.get("topic", "?")] = by_topic.get(row.get("topic", "?"), 0) + 1
        by_publisher[row.get("publisher", "?")] = by_publisher.get(row.get("publisher", "?"), 0) + 1
    return {
        "total": len(rows),
        "topics": sorted(({"topic": k, "count": v} for k, v in by_topic.items()),
                         key=lambda e: -e["count"])[:limit],
        "publishers": sorted(({"publisher": k, "count": v} for k, v in by_publisher.items()),
                             key=lambda e: -e["count"])[:limit],
        "last_seen": max((r.get("first_seen", "") for r in rows), default=""),
    }


def _fingerprint(row: dict[str, Any]) -> str:
    """İçerik parmak izi: aynı sayfa ikinci kez 'yeni' sayılmasın.

    URL degil ICERIK esas alinir -- ayni yazi farkli adresten yeniden
    yayimlanabilir ve o zaman "yeni bulgu" degildir.
    """
    import hashlib
    govde = (str(row.get("title") or "") + "\x1f"
             + str(row.get("content") or row.get("url") or ""))[:4000]
    return hashlib.sha256(govde.encode("utf-8", "replace")).hexdigest()[:20]


def remember(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Araştırma bulgularını deftere yazar ve YENİ olanları sayar.

    Doner: {"stored": kac kayit islendi, "new": kaci ilk kez gorundu}

    Defter yazilamazsa sayaclar sifir doner ve arastirma DURMAZ: bulgu
    kaydedilemedi diye kullaniciya cevap verilmemesi sacma olurdu.
    """
    if not rows:
        return {"stored": 0, "new": 0}
    bilinen: set[str] = set()
    try:
        with KNOWLEDGE_LOG.open(encoding="utf-8") as handle:
            for satir in handle:
                if not satir.strip():
                    continue
                try:
                    bilinen.add(json.loads(satir).get("fingerprint") or "")
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass

    simdi = datetime.now(timezone.utc).isoformat()
    yeni: list[dict[str, Any]] = []
    for row in rows:
        izi = _fingerprint(row)
        if izi in bilinen:
            continue
        bilinen.add(izi)
        yeni.append({
            "at": simdi, "question": question[:300], "fingerprint": izi,
            "url": row.get("url"), "title": str(row.get("title") or "")[:300],
            "source_type": row.get("source_type"),
            "published": row.get("observed_at"),
            "publisher": row.get("publisher"),
            "found_by": row.get("found_by"),
            # Metnin TAMAMI saklanmaz: defter bir indeks, arsiv degil.
            "excerpt": str(row.get("content") or "")[:MAX_CONTENT_CHARS],
        })

    if not yeni:
        return {"stored": len(rows), "new": 0}
    try:
        KNOWLEDGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with KNOWLEDGE_LOG.open("a", encoding="utf-8") as handle:
            for kayit in yeni:
                handle.write(json.dumps(kayit, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        return {"stored": len(rows), "new": 0, "error": str(exc)[:160]}
    return {"stored": len(rows), "new": len(yeni)}


def recall(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Daha önce öğrenilenler. Sorgu verilirse başlık/soru içinde aranır.

    Tam metin aramasi DEGIL: defter bir indekstir ve amaci "bunu daha once
    gormus muyduk" sorusuna cevap vermektir. Gercek arama gerekiyorsa
    arastirma yeniden calistirilir.
    """
    try:
        satirlar = KNOWLEDGE_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    aranan = (query or "").casefold()
    out: list[dict[str, Any]] = []
    for satir in reversed(satirlar):
        if not satir.strip():
            continue
        try:
            kayit = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if aranan:
            govde = (str(kayit.get("title") or "") + " "
                     + str(kayit.get("question") or "")).casefold()
            if aranan not in govde:
                continue
        out.append(kayit)
        if len(out) >= limit:
            break
    return out
