"""A bounded department briefing for a ZIP manifest, without pixel claims."""
from __future__ import annotations

import re


def ask(department: str, job: dict) -> dict:
    if department not in ("WEB", "TASARIM"):
        return {"hata": "Geçersiz departman.", "model_kullanildi": False}
    from jarvis import roster
    from jarvis.model_layer import ModelRouter

    report = job.get("report") or {}
    lead = roster.departman_sorumlusu(department)
    role = lead.job if lead else department
    count = int(report.get("product_count", 0))
    images = int(report.get("image_count", 0))
    problems = report.get("problems") or []
    evidence = [{
        "ref": f"image-job:{job['id']}",
        "summary": (f"Yüklenen ZIP dosyasında {count} ürün klasörü ve {images} JPEG görsel "
                    f"var. Yapısal sorunlar: {problems or 'yok'}. ZIP SHA-256: {job['sha256']}. "
                    "Görsellerin pikselleri, yazıları, ürün iddiaları, tasarım düzeni ve "
                    "canlı Wix ürün eşleşmeleri incelenmedi."),
    }]
    system = (f"Sen L'CARLIÉ {department} ekibinin {role} rolündesin. "
              "Sadece verilen ZIP yapısı kanıtına dayan. Görselleri görmedin; "
              "gördüğünü veya tasarımı onayladığını söyleme. Şirketin diğer ölçümlerini "
              "ve kanıtta olmayan rakamları ekleme. Kısa Türkçe yaz: doğrulanan, "
              "yayın öncesi kontrol, bilinmeyen. Karar olarak onay verme.")
    try:
        result = ModelRouter().synthesize(
            "Bu ürün görsel paketinin yayın öncesi kontrol görüşünü ver.", evidence,
            escalate=True, max_tokens=500, system=system)
    except Exception as exc:  # noqa: BLE001 - tek is coktugunde kuyruk durmaz; hata kayda gecer
        return {"hata": f"Model yanıtı alınamadı: {str(exc)[:180]}", "model_kullanildi": False}
    answer = str(getattr(result, "answer", "") or "")
    # Ignore single-digit list numbering; multi-digit values must be evidenced.
    numbers = lambda s: set(re.findall(r"(?<!\w)\d{2,}(?!\w)", s))
    unsupported = sorted(numbers(answer) - numbers(evidence[0]["summary"]))
    return {"cevap": answer, "model_kullanildi": bool(answer),
            "dogrulanmayan_sayilar": unsupported,
            "evidence_refs": [evidence[0]["ref"]]}
