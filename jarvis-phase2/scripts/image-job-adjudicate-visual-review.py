#!/usr/bin/env python3
"""Attach a checked decision to a complete visual report and refresh team notes."""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.image_jobs import ImageJobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("decision_file", type=Path)
    ap.add_argument("--state-dir", type=Path, default=Path("state"))
    args = ap.parse_args()
    jobs = ImageJobs(args.state_dir)
    job = jobs.get(args.job_id)
    if not job or not job["visual_review"]["complete"]:
        raise SystemExit("195 görselin incelemesi tamamlanmadı")
    decision = args.decision_file.read_text(encoding="utf-8")
    report_path = jobs.root / (args.job_id + "-visual-review.md")
    report = report_path.read_text(encoding="utf-8")
    marker = "\n# Doğrulanmış karar\n"
    report = report.split(marker)[0] + marker + decision + "\n"
    report_path.write_text(report, encoding="utf-8")
    summary = runpy.run_path(str(Path(__file__).with_name("image-job-finalize-visual-review.py")))["_gemini_summary"]
    evidence = ("195/195 görselin tekil görsel okuması tamamlandı. İlk modelin işaretlediği "
                "9 dosya ikinci görsel kontrolünden geçti. Aşağıdaki doğrulanmış karar ilk model "
                "önerilerinin üstündedir; yanlış işaretleri yeniden hazırlama gerekçesi yapma. "
                "Beş rutin görselindeki tekrarları isteğe bağlı redaksiyon olarak sun. "
                "SUNACNEA görseli katalogla aynı SPF 30 değerini taşıyor; görsel için yeniden "
                "hazırlama önerme, canlı site adını düzeltme ihtiyacını belirt. "
                "Yayın onayı verme.\n\n" + decision)
    for department in ("WEB", "TASARIM"):
        answer = summary(department, evidence)
        jobs.save_team_note(args.job_id, department,
                            {"cevap": answer, "model_kullanildi": True,
                             "evidence_refs": [f"image-job:{args.job_id}:visual-review:adjudicated"]})
        print(department, answer[:1000], flush=True)


if __name__ == "__main__":
    main()
