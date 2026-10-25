#!/usr/bin/env python3
"""Resumable pixel-level review of every image in an image job.

This produces observations for the WEB and TASARIM teams. A small vision model
cannot approve product claims, so every result remains a review item.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image, ImageStat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.image_jobs import ImageJobs, SLOTS

SYSTEM = ("Sen L'CARLIÉ ürün görsellerini inceleyen WEB ve TASARIM ekibinin görsel gözlemcisisin. "
          "Sadece verilen tek görselde açıkça gördüklerini yaz. Okuyamadığın yazıyı tahmin etme. "
          "Ürün iddiası veya SPF gibi sayılar görünüyorsa aynen yaz. "
          "Şu JSON alanlarını doldur: visible_product (string), visible_text (string), "
          "visual_description (string), web_issues (string array), design_issues (string array), "
          "needs_human_check (string array). Sorun görmüyorsan boş dizi ver. "
          "Kısa ve somut Türkçe yaz. Görselin ticari/doğruluk onayını verme.")


def analyze(data: bytes, product: str, slot: str, provider: str) -> dict:
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        original = {"width": im.width, "height": im.height, "mode": im.mode}
        rgb = im.convert("RGB")
        stat = ImageStat.Stat(rgb.resize((128, 128)))
        original["mean_rgb"] = [round(v, 1) for v in stat.mean]
        original["stddev_rgb"] = [round(v, 1) for v in stat.stddev]
        rgb.thumbnail((1400, 1400))
        out = io.BytesIO()
        rgb.save(out, "JPEG", quality=82, optimize=True)
    image_b64 = base64.b64encode(out.getvalue()).decode("ascii")
    question = f"Ürün klasörü: {product}; görsel sırası: {slot}. Bu tek görseli incele."
    if provider == "gemini":
        model = os.environ.get("JARVIS_IMAGE_VISION_MODEL", "gemini-3.5-flash-lite")
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise ValueError("GEMINI_API_KEY ayarlı değil")
        payload = {"system_instruction": {"parts": [{"text": SYSTEM}]},
                   "contents": [{"role": "user", "parts": [
                       {"text": question},
                       {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}]}],
                   "generationConfig": {"responseMimeType": "application/json",
                                        "temperature": 0, "maxOutputTokens": 600}}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json", "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = json.load(response)
        content = raw["candidates"][0]["content"]["parts"][0]["text"]
        duration = None
    else:
        model = os.environ.get("JARVIS_LOCAL_VISION_MODEL", "qwen3-vl:2b")
        payload = {"model": model, "stream": False, "format": "json", "keep_alive": "30m",
                   "options": {"num_predict": 380, "num_ctx": 4096, "temperature": 0},
                   "messages": [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": question, "images": [image_b64]}]}
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                                     json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=240) as response:
            raw = json.load(response)
        content = raw["message"]["content"]
        duration = raw.get("total_duration")
    vision = json.loads(content)
    if isinstance(vision, list) and len(vision) == 1 and isinstance(vision[0], dict):
        vision = vision[0]
    if not isinstance(vision, dict):
        raise ValueError("Model JSON nesnesi döndürmedi")
    for key in ("visible_product", "visible_text", "visual_description"):
        if not isinstance(vision.get(key), str):
            raise ValueError(f"Eksik model alanı: {key}")
    for key in ("web_issues", "design_issues", "needs_human_check"):
        if not isinstance(vision.get(key), list):
            raise ValueError(f"Eksik model alanı: {key}")
        vision[key] = [str(x)[:300] for x in vision[key] if isinstance(x, str)][:10]
    return {"technical": original, "vision": vision, "model": model,
            "image_input_size": len(out.getvalue()), "model_duration_ns": duration}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--state-dir", default=os.environ.get("JARVIS_STATE_DIR", "state"))
    ap.add_argument("--provider", choices=("gemini", "ollama"), default="gemini")
    args = ap.parse_args()
    jobs = ImageJobs(Path(args.state_dir))
    job = jobs.get(args.job_id)
    if not job or job["status"] not in ("REVIEW_PENDING", "CHANGES_REQUIRED", "READY_FOR_OWNER"):
        raise SystemExit("Geçerli inceleme işi bulunamadı.")
    if not job["report"].get("structural_pass"):
        raise SystemExit("Yapısal kontrol başarısız.")
    db = jobs.root / "visual-reviews.sqlite3"
    cx = sqlite3.connect(db)
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("""CREATE TABLE IF NOT EXISTS observations (
        job_id TEXT NOT NULL, product TEXT NOT NULL, slot TEXT NOT NULL,
        status TEXT NOT NULL, result TEXT NOT NULL, error TEXT NOT NULL,
        updated REAL NOT NULL, PRIMARY KEY(job_id,product,slot))""")
    cx.commit()
    zip_path = jobs.root / (args.job_id + ".zip")
    with zipfile.ZipFile(zip_path) as z:
        for product in sorted(job["report"]["products"]):
            for slot in SLOTS:
                row = cx.execute("SELECT status FROM observations WHERE job_id=? AND product=? AND slot=?",
                                 (args.job_id, product, slot)).fetchone()
                if row and row[0] == "DONE":
                    continue
                name = f"E-TICARET/{product}/{slot}"
                try:
                    result = analyze(z.read(name), product, slot, args.provider)
                    status, error = "DONE", ""
                except Exception as exc:  # noqa: BLE001 - tek is coktugunde kuyruk durmaz; hata kayda gecer
                    result, status, error = {}, "FAILED", f"{type(exc).__name__}: {exc}"[:500]
                cx.execute("""INSERT INTO observations VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(job_id,product,slot) DO UPDATE SET
                    status=excluded.status,result=excluded.result,error=excluded.error,updated=excluded.updated""",
                    (args.job_id, product, slot, status,
                     json.dumps(result, ensure_ascii=False), error, time.time()))
                cx.commit()
                counts = dict(cx.execute("SELECT status,count(*) FROM observations WHERE job_id=? GROUP BY status",
                                         (args.job_id,)).fetchall())
                print(f"{product}/{slot}: {status}; {counts}", flush=True)
    cx.close()
    if jobs.visual_review_summary(args.job_id)["complete"]:
        report = jobs.root / (args.job_id + "-visual-review.md")
        notes = {x["department"]: x["status"] for x in jobs.get(args.job_id)["team_notes"]}
        if not report.exists() or notes.get("WEB") != "DONE" or notes.get("TASARIM") != "DONE":
            subprocess.run([sys.executable,
                            str(Path(__file__).with_name("image-job-finalize-visual-review.py")),
                            args.job_id, "--state-dir", str(args.state_dir)], check=True, timeout=240)


if __name__ == "__main__":
    main()
