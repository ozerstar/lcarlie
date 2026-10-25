"""Import a local pack into the same durable queue as the web upload."""
import argparse
import json
import os
from pathlib import Path

from jarvis.image_jobs import ImageJobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path", type=Path)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    jobs = ImageJobs(Path(os.environ.get("JARVIS_STATE_DIR", "/opt/lcarlie/jarvis-phase2/state")))
    with args.zip_path.open("rb") as source:
        job = jobs.create_from_stream(source, args.zip_path.stat().st_size,
                                      args.zip_path.name, args.owner)
    jobs.run_next()
    processed = jobs.get(job["id"])
    print(json.dumps({"id": job["id"], "status": processed["status"],
                      "product_count": processed["report"].get("product_count"),
                      "image_count": processed["report"].get("image_count"),
                      "problems": processed["report"].get("problems", []),
                      "error": processed["error"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
