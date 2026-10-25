#!/usr/bin/env python3
"""Finish a complete 195-image visual pass and replace manifest-only team notes."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.image_jobs import ImageJobs, SLOTS


def _expected(zip_path: Path) -> dict[str, dict]:
    with zipfile.ZipFile(zip_path) as z:
        text = z.read("URUN-ICERIK-SAYIMLARI.md").decode("utf-8-sig", errors="replace")
    expected = {}
    for line in text.splitlines():
        columns = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(columns) == 5 and re.fullmatch(r"\d+\s*ml", columns[1], re.I):
            key = re.sub(r"[^a-z0-9]", "", columns[0].casefold())
            expected[key] = {"name": columns[0], "volume": columns[1],
                             "botanical_count": columns[2], "catalog_page": columns[4]}
    return expected


def _gemini_summary(department: str, evidence: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("Gemini anahtarı ayarlı değil")
    model = os.environ.get("JARVIS_IMAGE_VISION_MODEL", "gemini-3.5-flash-lite")
    instruction = (f"Sen L'CARLIÉ {department} ekibinin incelemecisisin. Aşağıdaki bulgular 195 gerçek "
                   "görselin tek tek görsel modelle okunmasıyla üretildi. Sadece kanıttaki bulguları kullan. "
                   "Görsellerin tamamını doğrudan gördüğünü iddia etme. Sorun ve yeniden hazırlama "
                   "gerektirenleri dosya adıyla belirt. Eksik insan doğrulamasını açıkça yaz. "
                   "Yayın onayı verme. Kısa, somut Türkçe cevap ver.")
    body = {"system_instruction": {"parts": [{"text": instruction}]},
            "contents": [{"role": "user", "parts": [{"text": evidence}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1100}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        json.dumps(body, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.load(response)
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--state-dir", default=os.environ.get("JARVIS_STATE_DIR", "state"))
    args = ap.parse_args()
    jobs = ImageJobs(Path(args.state_dir))
    job = jobs.get(args.job_id)
    if not job:
        raise SystemExit("İş bulunamadı")
    observations = jobs.visual_observations(args.job_id)["observations"]
    expected_slots = {f"{p}/{s}" for p in job["report"].get("products", {}) for s in SLOTS}
    if set(observations) != expected_slots or any(x["status"] != "DONE" for x in observations.values()):
        raise SystemExit(f"İnceleme eksik: {sum(x['status']=='DONE' for x in observations.values())}/{len(expected_slots)}")
    expected = _expected(jobs.root / (args.job_id + ".zip"))
    lines = ["# L’CARLIÉ ürün görselleri: tam inceleme", "",
             f"İş: `{args.job_id}` · ZIP SHA-256: `{job['sha256']}`", "",
             f"{len(job['report']['products'])} ürün / {len(observations)} görsel tek tek açıldı, çözümlendi ve görsel modelle okundu.",
             "39 kapak küçük listeleme kartı boyutunda ayrıca önizlendi: metinler bu ölçekte okunmuyor ve ürün şişeleri karenin yaklaşık yarısında kalıyor. Listeleme için sade ürün fotoğrafıyla karşılaştırma gerekir.",
             "SUNACNEA yeni kapakta SPF 30 yazıyor; kaynak kataloğun 14. sayfasında da SPF 30 var. Canlı sitenin SPF 30+ ürün adı ayrıca düzeltilmeli veya yetkili ürün verisiyle teyit edilmeli.",
             "Bu inceleme ürün iddialarına, mevzuata veya yayına insan onayı vermez.", ""]
    problems = []
    for product in sorted(job["report"]["products"]):
        lines += [f"## {product}", ""]
        pkey = re.sub(r"[^a-z0-9]", "", product.split("-", 1)[1].casefold())
        spec = expected.get(pkey)
        if spec:
            lines.append(f"Katalog referansı: s. {spec['catalog_page']}; {spec['volume']}; "
                         f"{spec['botanical_count']} bitkisel bileşen.")
        else:
            problems.append(f"{product}: katalog sayım tablosunda eşleşme bulunamadı")
        for slot in SLOTS:
            entry = observations[f"{product}/{slot}"]["result"]
            v = entry["vision"]
            t = entry["technical"]
            lines += [f"### {slot}", "",
                      f"Teknik: {t['width']}×{t['height']} {t['mode']}; model: {entry['model']}.",
                      f"Gözlem: {v['visual_description']}",
                      f"Okunan metin: {v['visible_text'] or '(okunamadı)'}"]
            if t["width"] != 2000 or t["height"] != 2000 or t["mode"] != "RGB":
                problems.append(f"{product}/{slot}: beklenen 2000×2000 RGB değil")
            if spec:
                volume = re.search(r"\d+", spec["volume"])
                seen_volumes = re.findall(r"(?<!\d)(\d{1,3})\s*ml\b", v["visible_text"], re.I)
                if volume and seen_volumes and volume.group() not in seen_volumes:
                    problems.append(f"{product}/{slot}: model {', '.join(seen_volumes)} ml okudu; katalog {spec['volume']} (OCR doğrulaması gerekli)")
                seen_counts = re.findall(r"(?<!\d)(\d{1,2})\s*bitkisel\s+bileşen", v["visible_text"], re.I)
                if seen_counts and spec["botanical_count"] not in seen_counts:
                    problems.append(f"{product}/{slot}: model {', '.join(seen_counts)} bitkisel bileşen okudu; katalog {spec['botanical_count']} (OCR doğrulaması gerekli)")
            for key, label in (("web_issues", "WEB"), ("design_issues", "TASARIM"),
                               ("needs_human_check", "İnsan kontrolü")):
                for issue in v[key]:
                    note = f"{product}/{slot} · {label}: {issue}"
                    problems.append(note)
                    lines.append(f"- {label}: {issue}")
            lines.append("")
    lines += ["## Açık bulgular", ""]
    lines += [f"- {x}" for x in problems] if problems else ["Görsel model açık bir kusur işaretlemedi; metin ve iddialar ayrıca doğrulanmalıdır."]
    report_path = jobs.root / (args.job_id + "-visual-review.md")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence = (f"İş {args.job_id}; 39 ürün ve 195 görselin tamamı tek tek görsel modelle okundu. "
                f"Teknik ve görsel bulgu sayısı: {len(problems)}.\n"
                "İşaretlenen bulgular:\n" + "\n".join(problems)[:13000] +
                "\nSUNACNEA yeni görselinde SPF 30 yazıyor ve kaynak ürün kataloğunun 14. sayfası da SPF 30 diyor; "
                "canlı site ürün adındaki SPF 30+ düzeltilmeli veya yetkili ürün verisiyle yeniden teyit edilmeli. "
                "39 kapak küçük ürün kartı ölçüsünde önizlendi: metinler okunmuyor ve ürün şişeleri karenin yaklaşık yarısında kalıyor. "
                "EARCLIA, AUROLIS, NOMORE canlı sitede gizli ürünlerdir; eşleşme kararı gerekir. "
                "Model okuması her yazı veya iddianın doğruluğunu garanti etmez.")
    for dept in ("WEB", "TASARIM"):
        try:
            answer = _gemini_summary(dept, evidence)
            response = {"cevap": answer, "model_kullanildi": True,
                        "evidence_refs": [f"image-job:{args.job_id}:visual-review"]}
        except Exception as exc:  # noqa: BLE001 - tek is coktugunde kuyruk durmaz; hata kayda gecer
            response = {"hata": f"Ekip özeti alınamadı: {type(exc).__name__}",
                        "model_kullanildi": False}
        jobs.save_team_note(args.job_id, dept, response)
    print(json.dumps({"reviewed": len(observations), "problems": len(problems),
                      "report": str(report_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
