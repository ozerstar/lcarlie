"""Read-only, evidence-based management desk for the team panel."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _stamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


AGENCY_ITEMS = {
    "creative_concepts": "reklam fikri",
    "performance_baseline": "performans başlangıç ölçümü",
    "test_plan": "deneme planı",
    "experiment_matrix": "deneme seçeneği",
    "cro_recommendations": "sayfa iyileştirme önerisi",
    "problems": "sorun",
    "opportunities": "fırsat",
    "social_plan": "sosyal medya içerik günü",
}


def _number_tr(value: str, digits: int = 2) -> str:
    return format(Decimal(value), f",.{digits}f").replace(",", "_").replace(".", ",").replace("_", ".")


def explain_result(key: str, result: str) -> str:
    patterns = {
        "ecommerce_sales": (
            r"Sales bounded context: (\d+) orders and (\d+) line items; (\d+) measured orders represent a ([\d.]+) net-revenue subtotal\.",
            lambda parts: f"{parts[0]} sipariş ve {parts[1]} sipariş kalemi incelendi. Ölçüme dahil {parts[2]} siparişin kayıtlı net ciro toplamı {_number_tr(parts[3])}; bu tüm satışların toplamı değildir."),
        "product_portfolio": (
            r"E-commerce bounded context: (\d+) product profitability rows, (\d+) price rows and (\d+) funnel transitions; net revenue is ([\d.]+), with (\d+) product rows below full cost coverage\.",
            lambda parts: f"{parts[0]} ürün kârlılık, {parts[1]} fiyat ve {parts[2]} satış yolu kaydı incelendi. Kayıtlı net ciro {_number_tr(parts[3])}; {parts[4]} ürünün maliyet verisi tam değil."),
        "meta_performance": (
            r"Advertising bounded context: (\d+) 30-day ad rows with a ([\d.]+) spend subtotal; (\d+) rows lack commercial confirmation\.",
            lambda parts: f"Son 30 güne ait {parts[0]} reklam kaydı incelendi. Kayıtlı harcama toplamı {_number_tr(parts[1])}; {parts[2]} reklamın satış sonucu doğrulanmamış."),
        "crm_customer": (
            r"CRM bounded context: (\d+) customer records and (\d+) unanswered conversations; longest wait is ([\d.]+) hours\.",
            lambda parts: f"{parts[0]} müşteri kaydı ve {parts[1]} yanıtsız görüşme var. En uzun bekleme {_number_tr(parts[2], 1)} saat."),
        "operations": (
            r"Operations bounded context: (\d+) shipment records, (\d+) shipment alarms and (\d+) open-work records\.",
            lambda parts: f"{parts[0]} gönderi kaydı, {parts[1]} gönderi uyarısı ve {parts[2]} açık iş kaydı incelendi."),
    }
    if key in patterns:
        pattern, describe = patterns[key]
        match = re.fullmatch(pattern, result)
        if match:
            return describe(match.groups())
    fixed = {
        "red_team": {"Red Team result: OBJECTION": "Denetim ekibi bir itiraz buldu. Gerekçe bu kısa kayıtta yer almıyor; karar vermeden önce ayrıntıyı inceleyin."},
        "strategy": {"Strategy options: clear the evidenced unanswered-conversation backlog; reconcile commercial confirmation before budget changes; close revenue, cost, and margin measurement gaps; maintain shipment monitoring and obtain real inventory data.": "Önerilen sıra: yanıtsız müşteri görüşmelerini ele alın; reklam bütçesini değiştirmeden önce satış sonucunu doğrulayın; ciro, maliyet ve kâr ölçümündeki eksikleri kapatın; gönderileri izleyip gerçek stok verisini alın."},
        "managing_director": {"PROPOSED: first clear the CRM response backlog; then validate advertising sales, revenue, cost, margin, and inventory evidence before approving growth actions.": "Genel müdür önerisi: önce yanıtsız müşteri görüşmelerini ele alın. Büyüme kararlarından önce reklam satışlarını, ciroyu, maliyeti, kârı ve stok verisini doğrulayın. Henüz uygulanmadı."},
    }
    if result in fixed.get(key, {}):
        return fixed[key][result]
    if " — " in result and result.endswith("Taslak üretildi; yayımlanmadı."):
        task, details = result.split(" — ", 1)
        items = []
        for field, count in re.findall(r"([a-z_]+): (\d+)", details):
            if field in AGENCY_ITEMS:
                items.append(f"{count} {AGENCY_ITEMS[field]}")
        if items:
            return f"{task}: {', '.join(items)} hazırlandı. Taslak yayımlanmadı."
    if key in ("market_intelligence", "competitor_intelligence", "research", "COMPETITOR_CREATIVE"):
        match = re.match(r"Son 14 günde (\d+) kaynak kaydı incelendi\.", result)
        if match:
            return f"Son 14 günde {match.group(1)} dış kaynak incelendi. Bulgular şirket verisi olarak doğrulanmadı; kaynak bağlantılarını inceleyin."
    return result


def build_brief(departments: list[dict], report: dict, works: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    generated = _stamp(report.get("generated_at"))
    fresh = bool(generated and timedelta(0) <= now - generated <= timedelta(hours=24))
    activity = report.get("activity", {}) if fresh and isinstance(report.get("activity"), dict) else {}
    states = {"WORKED": "ÇALIŞTI", "WAITING": "GÖREV BEKLİYOR", "ERROR": "HATA"}
    members = []
    for department in departments:
        for member in department.get("uyeler", []):
            key = member.get("key", "")
            record = activity.get(key, {})
            state = states.get(record.get("status"), "İZLENMİYOR")
            refs = record.get("evidence_refs", [])
            if state == "ÇALIŞTI" and not refs:
                state = "GÖREV BEKLİYOR"
            result = record.get("result", "")
            plain_result = explain_result(key, str(result))
            members.append({
                "key": key,
                "ad": member.get("ad", ""), "birim": department.get("ad", ""),
                "durum": state,
                "veri_durumu": member.get("durum", "BİLİNMİYOR"),
                "gorev": str(record.get("task") or "")[:180],
                "gorev_turu": str(record.get("kind") or "")[:60],
                "rol_tanimi": str(member.get("gorev") or "")[:180],
                "son_is": str(result)[:240] if state == "ÇALIŞTI" else "",
                "sonuc": str(result)[:240],
                "son_is_acik": plain_result[:500] if state == "ÇALIŞTI" else "",
                "sonuc_acik": plain_result[:500],
                "kanitlar": [str(ref)[:220] for ref in refs[:4]],
                "baslangic": str(record.get("started_at") or ""),
                "zaman": str(record.get("finished_at") or ""),
                "sure_ms": record.get("duration_ms"),
            })
    priorities = []
    for work in works:
        if work.get("approval_state") in ("REJECTED", "EXPIRED"):
            continue
        due = _stamp(work.get("due"))
        if not due:
            continue
        overdue = due < now and not work.get("has_measurement")
        if overdue or not work.get("has_application"):
            priorities.append({
                "id": work.get("id"), "hedef": str(work.get("objective", ""))[:180],
                "sorumlu": str(work.get("owner", ""))[:80], "son_tarih": due.isoformat(),
                "durum": "GECİKMİŞ" if overdue else "UYGULAMA KANITI BEKLER",
            })
    priorities.sort(key=lambda item: (item["durum"] != "GECİKMİŞ", item["son_tarih"]))
    return {
        "uretim_zamani": generated.isoformat() if generated else "",
        "guncel": fresh, "uyeler": members,
        "kanitli_cikti": sum(member["durum"] == "ÇALIŞTI" for member in members),
        "durum_sayilari": {state: sum(member["durum"] == state for member in members)
                          for state in ("ÇALIŞTI", "GÖREV BEKLİYOR", "HATA", "İZLENMİYOR")},
        "rutin_kontrol": sum(member["durum"] == "ÇALIŞTI" and
                             member["gorev_turu"] == "VERİ KONTROLÜ" for member in members),
        "oncelikler": priorities[:8],
        "not": "ÇALIŞTI, son döngüde kayıtlı bir aşamanın tamamlandığını gösterir; mesai, yeni keşif veya dışarıya uygulanan iş değildir. VERİ KONTROLÜ salt okunur rutin değerlendirmedir. Dış araştırma kaynağı 14 güne kadar eski olabilir. Görev ataması ve mesaj gönderimi yapılmaz.",
    }


def load_brief(departments: list[dict]) -> dict:
    state = Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state"))
    try:
        report = json.loads((state / "team-cycle" / "latest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    works = []
    ledger = state / "improvement" / "ledger.sqlite3"
    if ledger.exists():
        try:
            with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True, timeout=2) as database:
                database.row_factory = sqlite3.Row
                works = [dict(row) for row in database.execute("""
                    SELECT w.id, w.objective, w.owner, w.due, w.approval_state,
                      EXISTS(SELECT 1 FROM application a WHERE a.work_id=w.id) has_application,
                      EXISTS(SELECT 1 FROM measurement m WHERE m.work_id=w.id) has_measurement
                    FROM work w ORDER BY w.due LIMIT 150
                """)]
        except (OSError, sqlite3.Error):
            works = []
    return build_brief(departments, report, works)
