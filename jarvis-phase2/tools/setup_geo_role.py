"""One-time GEO ingest role setup on the lcarlie server."""

import os
import secrets
import subprocess
from pathlib import Path


def main() -> None:
    password = secrets.token_hex(24)
    sql = f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='geo_ingest') THEN
    CREATE ROLE geo_ingest LOGIN PASSWORD '{password}';
  ELSE
    ALTER ROLE geo_ingest PASSWORD '{password}';
  END IF;
END $$;
GRANT CONNECT ON DATABASE n8n TO geo_ingest;
GRANT USAGE ON SCHEMA core, raw TO geo_ingest;
GRANT SELECT ON core.geo_query, core.geo_alias, core.geo_brand,
  core.geo_source, core.geo_citation, core.geo_mention,
  core.geo_observation, raw.geo_response TO geo_ingest;
GRANT INSERT ON core.geo_source, core.geo_citation, core.geo_mention,
  core.geo_observation, raw.geo_response TO geo_ingest;
GRANT UPDATE (son_gorulme) ON core.geo_source TO geo_ingest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA core, raw TO geo_ingest;
"""
    result = subprocess.run(
        ["docker", "exec", "-i", "lcarlie-postgres", "psql", "-U", "n8n",
         "-d", "n8n", "-v", "ON_ERROR_STOP=1", "-q"],
        input=sql, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "GEO role setup failed")
    target = Path("/opt/lcarlie/jarvis-phase2/.geo-env")
    target.write_text(
        "PGHOST=127.0.0.1\nPGPORT=5433\nPGDATABASE=n8n\n"
        f"PGUSER=geo_ingest\nPGPASSWORD={password}\n", encoding="utf-8"
    )
    os.chmod(target, 0o600)
    print("GEO role and root-readable environment created")


if __name__ == "__main__":
    main()
