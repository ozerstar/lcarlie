"""Ajans teslimatını saklar ve onaya gidecek şartnameyi yazar.

İKİ ÖLÇÜLEN KUSURU KAPATIR

1) TESLİMAT KAYBOLUYORDU
   Konseptler, test planı ve mevzuat bulguları hesaplanıp HTTP yanıtından
   sonra çöpe gidiyordu. Aynı kampanya yarın tekrar sorulsa sıfırdan
   üretiliyordu ve dünkü metnin ne olduğu hiçbir yerde yoktu.

2) ONAY KUYRUĞUNA BOŞ ÖNERİ DÜŞÜYORDU
   loop.py, kodlama dışındaki her niyet için şu yükü yazıyor:
       {"subject_ref": key,
        "reason": f"Automated proposal from operator-originated task {key}"}
   Yani onaylayacak insan reklamın NE DEDİĞİNİ göremiyor. İçi boş bir
   öneriyi onaylamak, onay değildir.

   Kodlama görevleri bunu disk üzerinde bir ŞARTNAME dosyasıyla çözmüş
   (CODING_TASK_PENDING_DIR). loop.py'nin kendi yorumu bunu "her niyetin
   zaten kullandığı sözleşmenin, slug yerine DOSYA ile genişletilmiş hâli"
   diye tarif ediyor. Aynı deseni ajans için tekrarlıyoruz; yeni bir yol
   icat etmiyoruz.

YETKİ SINIRI DEĞİŞMİYOR
Bu modül veritabanına YAZMAZ ve görev AÇMAZ. Yalnız dosya yazar. Görevi
insan açar (`jarvis-operator create-task`), öneriyi döngü yazar, onayı
insan verir. Zincirin hiçbir halkası atlanmaz.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
AGENCY_DIR = STATE_DIR / "agency"
PENDING_DIR = AGENCY_DIR / "pending"     # onaya gidecek sartnameler
INDEX_PATH = AGENCY_DIR / "index.jsonl"

# Sartnamede saklanan, musteriye ULASAN alanlar. Ic alanlar (name, product,
# regulatory_risk) saklanir ama yuke girmez.
PUBLISHED_FIELDS = ("hook", "headline", "primary_text", "cta",
                    "landing_page_message", "visual_brief", "video_15s_brief",
                    "audience_context")


def _slugify(text: str) -> str:
    """Dosya adı ve idempotency anahtarı için güvenli kısa ad."""
    folded = (text or "").casefold().replace("ı", "i").replace("ş", "s")
    folded = folded.replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    safe = "".join(ch if ch.isalnum() else "-" for ch in folded)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:48] or "konsept"


def deliverable_id(deliverable: dict[str, Any]) -> str:
    """Aynı görev + aynı ürün + aynı konseptler = aynı kimlik.

    Icerik hashi kullanilir ki ayni istek iki kez kaydedilmesin; degisen
    bir sey varsa yeni kayit olusur ve eskisi durur.
    """
    parcalar = [str(deliverable.get("task") or ""),
                str(deliverable.get("product") or ""),
                json.dumps(deliverable.get("creative_concepts") or [],
                           ensure_ascii=False, sort_keys=True, default=str)]
    return hashlib.sha256("\x1f".join(parcalar).encode("utf-8")).hexdigest()[:16]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    tmp.replace(path)  # atomik: yarim yazilmis sartname okunmaz
    os.chmod(path, 0o640)


def save(deliverable: dict[str, Any]) -> dict[str, Any]:
    """Teslimatı diske yazar ve önerilebilir konseptler için şartname üretir.

    Doner: {"id", "path", "specs": [{slug, concept, command, spec_path}]}
    `command` insanin calistiracagi komuttur -- bu modul onu CALISTIRMAZ.
    """
    kimlik = deliverable_id(deliverable)
    AGENCY_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(AGENCY_DIR, 0o750)

    kayit_yolu = AGENCY_DIR / f"{kimlik}.json"
    _write_json(kayit_yolu, {"id": kimlik, "saved_at": time.time(),
                             "deliverable": deliverable})

    specs: list[dict[str, Any]] = []
    onerilebilir = _proposable(deliverable)
    for index, (concept, screened) in enumerate(onerilebilir, 1):
        ad = str(concept.get("name") or f"konsept-{index}")
        slug = f"{kimlik}-{index}-{_slugify(ad)}"
        intent = _intent(deliverable)
        spec = {
            "slug": slug,
            "deliverable_id": kimlik,
            "concept_index": index,
            "concept_name": ad,
            "product": deliverable.get("product"),
            "objective": deliverable.get("objective"),
            "internal_intent": intent,
            # Yuke girecek metin: musteriye ULASAN alanlar. Mevzuat kapisi
            # bunlarin hepsini tarar (compliance.TEXT_FIELDS genisletildi).
            "payload": {
                "subject_ref": f"agency:{kimlik}:{index}",
                **{alan: concept[alan] for alan in PUBLISHED_FIELDS
                   if isinstance(concept.get(alan), str) and concept[alan].strip()},
            },
            "screening": {k: screened.get(k) for k in ("status", "verify", "error")
                          if k in screened},
            "created_at": time.time(),
        }
        spec_yolu = PENDING_DIR / f"{slug}.json"
        _write_json(spec_yolu, spec)
        specs.append({
            "slug": slug, "concept": ad, "spec_path": str(spec_yolu),
            # Insanin calistiracagi komut. Gorev acmak INSANIN isidir.
            "command": f"jarvis-operator create-task {intent} {slug}",
        })

    with INDEX_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(
            {"id": kimlik, "at": time.time(), "task": deliverable.get("task"),
             "product": deliverable.get("product"),
             "concepts": len(deliverable.get("creative_concepts") or []),
             "specs": [s["slug"] for s in specs]},
            ensure_ascii=False, default=str) + "\n")

    return {"id": kimlik, "path": str(kayit_yolu), "specs": specs,
            "note": ("Şartnameler yazıldı. Görevi İNSAN açar; bu modül "
                     "veritabanına yazmaz ve görev açmaz.")}


def _intent(deliverable: dict[str, Any]) -> str:
    return ("META_CAMPAIGN_CHANGE"
            if str(deliverable.get("objective")) == "CAMPAIGN_PROPOSAL"
            else "DRAFT_CUSTOMER_REPLY")


def _proposable(deliverable: dict[str, Any]) -> list[tuple[dict, dict]]:
    """Firewall taramasını geçmiş konseptler. Geçmeyen şartname ÜRETMEZ.

    Bloklu bir konsept icin sartname yazmak, onaya gidebilecegi izlenimi
    verirdi; firewall zaten reddederdi ama dosya ortada kalirdi.
    """
    concepts = list(deliverable.get("creative_concepts") or [])
    screened = list((deliverable.get("proposals") or {}).get("concepts") or [])
    out: list[tuple[dict, dict]] = []
    for index, concept in enumerate(concepts):
        durum = screened[index] if index < len(screened) else {}
        if durum and durum.get("status") != "PROPOSABLE":
            continue
        out.append((concept, durum))
    return out


def load_spec(slug: str) -> dict[str, Any] | None:
    """Döngünün okuyacağı şartname. Yoksa None -- uydurulmaz."""
    path = PENDING_DIR / f"{slug}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def recent(limit: int = 20) -> list[dict[str, Any]]:
    """Son teslimatlar, yeniden eskiye."""
    try:
        satirlar = INDEX_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for satir in reversed(satirlar):
        if not satir.strip():
            continue
        try:
            out.append(json.loads(satir))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def get(deliverable_id_: str) -> dict[str, Any] | None:
    try:
        return json.loads((AGENCY_DIR / f"{deliverable_id_}.json")
                          .read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
