"""Read-only live check of the unified action registry and approval boundary."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "webconsole"))

from jarvis.operator import OperatorSession  # noqa: E402
import personal_action_store as store  # noqa: E402


def main() -> None:
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT source,count(*) AS total FROM core.jarvis_action_registry GROUP BY source")
        counts = {row["source"]: row["total"] for row in cur.fetchall()}
        assert counts.get("company", 0) > 0 and counts.get("personal", 0) > 0
        cur.execute("SELECT count(*) AS total FROM core.jarvis_action_registry_event")
        assert cur.fetchone()["total"] >= sum(counts.values())
    os.environ["JARVIS_MEMORY_TRANSPORT"] = "direct-pg"
    pending = OperatorSession(host=None).list_pending()
    assert all(row.get("fingerprint") for row in pending)
    print(f"Unified registry OK: {counts}; {len(pending)} pending company action(s)")


if __name__ == "__main__":
    main()
