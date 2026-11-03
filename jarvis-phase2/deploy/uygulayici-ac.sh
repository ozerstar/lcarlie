#!/usr/bin/env bash
# =============================================================================
# AKSIYON UYGULAYICIYI CANLIYA AL (sahip calistirir, 03.11.2026)
#
# Ne yapar:
#   1. scripts/aksiyon-uygulayici.py ve testini canli dizine kopyalar
#   2. migration 071'i uygular: META_CAMPAIGN_CHANGE + PRICE_CHANGE
#      execution_enabled=true, gunluk tavan 10 / 5
#   3. lcarlie-aksiyon-uygulayici.timer'i (2 dk) kurar ve baslatir
#
# Ne YAPMAZ: hicbir oneriyi onaylamaz. Her is yine panelde SIZIN onayinizi
# bekler; uygulayici yalniz onaylanmis isi yazar ve platformdan geri okur.
#
# Acil durdurma:
#   docker exec lcarlie-postgres psql -U n8n -d n8n -c \
#     "UPDATE core.ai_orchestrator_config SET config_value='false' WHERE config_key='uygulayici_acik';"
# Tamamen geri alma:
#   systemctl disable --now lcarlie-aksiyon-uygulayici.timer
#   docker exec -i lcarlie-postgres psql -U n8n -d n8n < migrations/rollback/071_meta_fiyat_uygulama_ROLLBACK.sql
# =============================================================================
set -euo pipefail
R=/opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2
L=/opt/lcarlie/jarvis-phase2

install -m 755 "$R/scripts/aksiyon-uygulayici.py" "$L/scripts/aksiyon-uygulayici.py"
install -m 644 "$R/tests/test_aksiyon_uygulayici.py" "$L/tests/test_aksiyon_uygulayici.py"
cp "$R/migrations/071_meta_fiyat_uygulama.sql" "$L/migrations/"
(cd "$L" && "$L/venv/bin/python" -m unittest -q tests.test_aksiyon_uygulayici 2>&1 | tail -1) || true

docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -tA \
  < "$R/migrations/071_meta_fiyat_uygulama.sql"

install -m 644 "$R/systemd/lcarlie-aksiyon-uygulayici.service" /etc/systemd/system/
install -m 644 "$R/systemd/lcarlie-aksiyon-uygulayici.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now lcarlie-aksiyon-uygulayici.timer
systemctl start lcarlie-aksiyon-uygulayici.service
journalctl -u lcarlie-aksiyon-uygulayici -n 3 --no-pager -o cat | grep -vE "Starting|Deactivated|Consumed" || true
"$L/venv/bin/python" "$L/scripts/aksiyon-uygulayici.py" --durum
