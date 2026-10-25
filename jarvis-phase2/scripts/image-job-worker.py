"""Run queued image checks after a web process restart.

NEDEN sys.path: birim dosyasi betigi dogrudan calistiriyor
  ExecStart=.../venv/bin/python .../scripts/image-job-worker.py
O zaman Python sys.path[0] olarak betigin KENDI dizinini (scripts/) alir,
WorkingDirectory'yi DEGIL. Yani "jarvis" paketi gorunmez ve servis
ModuleNotFoundError ile cikis 1 verir -- 23.10.2026'da olculdu, servis
o tarihte FAILED durumdaydi. Kardes betiklerdeki (basin-tara.py,
departman-arastirma.py) yerlesik KOK kalibi kullanildi.
"""
import os
import sys
from pathlib import Path

KOK = "/opt/lcarlie/jarvis-phase2"
sys.path.insert(0, KOK)

from jarvis.image_jobs import ImageJobs  # noqa: E402


if __name__ == "__main__":
    jobs = ImageJobs(Path(os.environ.get("JARVIS_STATE_DIR", KOK + "/state")))
    jobs.recover()
    while jobs.run_next() is not None:
        pass
