#!/bin/bash
# AJANLAR hiz, ikinci adim (26.11.2026): panel rolunde (jarvis_web) JIT kapali.
# Kod degismez; goc 082 uygulanir. Ayar yeni baglantida gecerli, panel
# yeniden baslatilmaz. Geri alma:
#   docker exec lcarlie-postgres psql -U n8n -d n8n -c "ALTER ROLE jarvis_web RESET jit"
set -euo pipefail
K=${1:?kullanim: yayinla-ajanlar-jit.sh <commit>}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/ajanlar-jit-$(date +%Y%m%d-%H%M%S)
mkdir -p "$YEDEK/webconsole/tests"
docker exec lcarlie-postgres psql -U n8n -d n8n -Atc "select coalesce(array_to_string(rolconfig, ','), '(ayar yok)') from pg_roles where rolname='jarvis_web'" > "$YEDEK/jarvis_web_rolconfig_once.txt"
cp -p "$L/webconsole/tests/test_ajanlar_hiz.py" "$YEDEK/webconsole/tests/"
for f in migrations/082_jarvis_web_jit_kapali.sql webconsole/tests/test_ajanlar_hiz.py; do
  git -C $DEPO show $K:jarvis-phase2/$f > "$L/$f.yeni"; chmod 644 "$L/$f.yeni"; mv "$L/$f.yeni" "$L/$f"
done
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q < "$L/migrations/082_jarvis_web_jit_kapali.sql"
echo "jarvis_web ayari: $(docker exec lcarlie-postgres psql -U n8n -d n8n -Atc "select array_to_string(rolconfig, ',') from pg_roles where rolname='jarvis_web'")"
echo "yedek: $YEDEK"
