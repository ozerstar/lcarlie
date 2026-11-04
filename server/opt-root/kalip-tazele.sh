#!/usr/bin/env bash
# Gercek konusmalardan soru->cevap kaliplarini yeniden cikarir.
# meta-aktar.sh yeni veri getirdikten sonra calistirilir.
set -Eeuo pipefail
docker cp /opt/lcarlie/kalip-cikar.sql lcarlie-postgres:/tmp/kc.sql >/dev/null
docker exec lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -f /tmp/kc.sql | tail -n 2
N=$(docker exec lcarlie-postgres psql -U n8n -d n8n -tAc "SELECT count(*)||' kalip / '||sum(adet)||' cift' FROM lcarlie.kalip")
echo "[$(date '+%F %T')] kalip tazelendi: $N" | tee -a /opt/lcarlie/meta-aktar.log
