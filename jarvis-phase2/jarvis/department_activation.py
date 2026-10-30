"""Evidence-bounded, read-only duties for newly staffed departments."""

from __future__ import annotations

from typing import Callable


def _customer_service(rows: dict[str, list]) -> str:
    unanswered = rows.get("crm_unanswered", [])
    products = rows.get("urun_bilgi", [])
    longest = max((float(row.get("bekleme_saat") or 0) for row in unanswered), default=0)
    return (f"{len(unanswered)} yanıtsız görüşme ve {len(products)} ürün bilgi kaydı incelendi. "
            f"En uzun bekleme {longest:.1f} saat. Yanıt gönderilmedi; görüşmeler "
            "müşteri temsilcisi ve onay hattına bırakıldı.")


def _customer_intelligence(rows: dict[str, list]) -> str:
    themes = rows.get("customer_voice", [])
    if not themes:
        return "Konu özeti kaydı yok; müşteri dili hakkında çıkarım yapılmadı."
    leading = max(themes, key=lambda row: int(row.get("distinct_konusma") or 0))
    return (f"{len(themes)} anonimleştirilmiş konu özeti incelendi. En sık konu: "
            f"{leading.get('konu') or 'belirsiz'} "
            f"({int(leading.get('distinct_konusma') or 0)} farklı görüşme). "
            "Ham müşteri mesajları okunmadı.")


def _experimentation(rows: dict[str, list]) -> str:
    hypotheses = rows.get("creative_hypotheses", [])
    measurable = sum(bool(row.get("olcum_yontemi") and row.get("yanlislama"))
                     for row in hypotheses)
    return (f"{len(hypotheses)} hipotez incelendi; {measurable} tanesinde ölçüm "
            "ve yanlışlama yöntemi kayıtlı. Deney uygulanmadı; sonuç veya "
            "başarı iddiası üretilmedi.")


def _decision_memory(rows: dict[str, list]) -> str:
    proposals = rows.get("own_proposals", [])
    decisions = rows.get("decision_outcomes", [])
    learning = rows.get("learning_loop", [])
    return (f"{len(proposals)} öneri, {len(decisions)} insan kararı ve "
            f"{len(learning)} model öğrenme kaydı incelendi. Kayıtlar ayrı "
            "kaynaklardan geldiği için tek tek eşleştirilmeden nedensellik "
            "veya başarı sonucu çıkarılmadı.")


def _instagram(rows: dict[str, list]) -> str:
    posts = rows.get("content_performance", [])
    interactions = sum(int(row.get("etkilesim") or 0) for row in posts)
    return (f"{len(posts)} organik içerik kaydı ve kayıtlı toplam "
            f"{interactions} etkileşim incelendi. Erişim/gösterim izni "
            "olmadığından etkileşim oranı hesaplanmadı; yayın yapılmadı.")


def _ig_direktor(rows: dict[str, list]) -> str:
    paket = rows.get("ig_gunluk_paket", [])
    if not paket:
        return "Son 7 günde günlük paket yok; inceleme yapılmadı."
    gunler = sorted({str(r.get("gun")) for r in paket})
    duzelt = sum(r.get("uzman_karari") == "DUZELT" for r in paket)
    bulgulu = sum(r.get("denetim") != "TEMIZ" for r in paket)
    bekleyen = sum(r.get("durum") == "ONERI" for r in paket)
    puanlar = [int(r["kanca_puani"]) for r in paket if r.get("kanca_puani") is not None]
    ort = round(sum(puanlar) / len(puanlar)) if puanlar else None
    son = [r for r in paket if str(r.get("gun")) == gunler[-1]]
    return (f"{len(gunler)} günde {len(paket)} içerik inceledim; {duzelt} tanesini "
            f"düzelttirdim, {bulgulu} tanesi mevzuat bulgusuyla onaya kapalı. "
            f"Son paket {gunler[-1]}: {son[0].get('urun_slug')}. "
            f"Ortalama kanca puanı {ort if ort is not None else 'yok'} (eleme ölçüsü, "
            f"izlenme tahmini değil). {bekleyen} içerik sahip kararını bekliyor; "
            "yayın yapılmadı.")


def _stock_coverage(rows: dict[str, list]) -> str:
    products = rows.get("urun_bilgi", [])
    known = [row for row in products if row.get("wix_stok") not in (None, "")]
    empty = sum(float(row["wix_stok"]) <= 0 for row in known)
    return (f"{len(products)} ürünün Wix vitrin kaydı incelendi; "
            f"{len(products) - len(known)} ürünün Wix stok değeri yok, "
            f"{empty} üründe değer sıfır veya altında. Bu fiziksel depo "
            "envanteri değildir; alım ya da stok düzeltmesi yapılmadı.")


def _video_brief(rows: dict[str, list]) -> str:
    posts = rows.get("content_performance", [])
    videos = [row for row in posts if any(term in str(row.get("bicim") or "").casefold()
              for term in ("video", "reels", "reel"))]
    return (f"{len(posts)} içerikten {len(videos)} video biçimli kayıt "
            "bulundu. Bu yalnızca brief girdisidir; UGC hakları, çekim "
            "izni ve üretim bağlantısı doğrulanmadı.")


def _new_product_research(rows: dict[str, list]) -> str:
    themes = rows.get("customer_voice", [])
    products = rows.get("urun_karti", [])
    findings = rows.get("market_research", [])
    return (f"{len(themes)} müşteri konu özeti, {len(products)} ürün ve "
            f"{len(findings)} pazar bulgusu ön fikir için tarandı. "
            "Formülasyon, mevzuat ve talep doğrulaması yapılmadı; yeni ürün "
            "kararı veya dış işlem yok.")


SPEAKERS: dict[str, Callable[[dict[str, list]], str]] = {
    "musteri_hizmetleri": _customer_service,
    "musteri_istihbarati": _customer_intelligence,
    "deney_izleme": _experimentation,
    "karar_hafizasi": _decision_memory,
    "instagram_olcum": _instagram,
    "ig_icerik_direktoru": _ig_direktor,
    "stok_kapsama": _stock_coverage,
    "video_brief": _video_brief,
    "yeni_urun_on_arastirma": _new_product_research,
}
