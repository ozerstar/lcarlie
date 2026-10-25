"""Prepare or run a reviewed Wix Catalog V1 image replacement."""
import argparse
import json
import os
from pathlib import Path

from jarvis.image_jobs import ImageJobs
from jarvis.wix_image_publish import WixClient, publish


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--mapping", type=Path, help="JSON: folder -> {id,slug}")
    parser.add_argument("--media-stage", type=Path, help="Wix'e önceden yüklenmiş 195 medya ID'si")
    parser.add_argument("--execute", action="store_true", help="Actually replace Wix media")
    args = parser.parse_args()
    jobs = ImageJobs(Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")))
    job = jobs.get(args.job_id)
    if not job:
        parser.error("İş bulunamadı.")
    if not args.execute:
        print(json.dumps({folder: {"id": "", "slug": ""}
                          for folder in sorted(job["report"].get("products") or {})},
                         ensure_ascii=False, indent=2))
        return
    if not args.mapping:
        parser.error("--execute için --mapping dosyası gerekli.")
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    stage_path = args.media_stage or (jobs.root / (args.job_id + "-media-stage.json"))
    media_stage = json.loads(stage_path.read_text(encoding="utf-8")) if stage_path.exists() else None
    client = WixClient(os.environ.get("WIX_API_KEY", ""), os.environ.get("WIX_SITE_ID", ""))
    done = publish(args.job_id, mapping, jobs, client, media_stage)
    print(json.dumps({"id": done["id"], "status": done["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
