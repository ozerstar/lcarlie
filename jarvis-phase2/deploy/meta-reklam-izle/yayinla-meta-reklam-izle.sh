#!/bin/bash
# Meta reklam izleyicisini canliya alir (15.11.2026).
#   - scripts/meta-reklam-izle.py  -> /opt/lcarlie/jarvis-phase2/scripts/
#   - systemd service + timer (saatte bir, :12)
# Goc (076_meta_izleme.sql) 15.11 16:09'da uygulandi; betik yine de
# IF NOT EXISTS ile guvenle tekrar uygular.
# Geri alma: systemctl disable --now lcarlie-meta-reklam-izle.timer
set -euo pipefail
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2
CANLI=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/meta-izle/yayin-$(date +%Y%m%d-%H%M%S)
mkdir -p "$YEDEK"
[ -f "$CANLI/scripts/meta-reklam-izle.py" ] && cp -p "$CANLI/scripts/meta-reklam-izle.py" "$YEDEK/"
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q < "$DEPO/migrations/076_meta_izleme.sql"
install -m 755 "$DEPO/scripts/meta-reklam-izle.py" "$CANLI/scripts/meta-reklam-izle.py"
install -m 644 "$DEPO/deploy/meta-reklam-izle/lcarlie-meta-reklam-izle.service" /etc/systemd/system/
install -m 644 "$DEPO/deploy/meta-reklam-izle/lcarlie-meta-reklam-izle.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now lcarlie-meta-reklam-izle.timer
systemctl start lcarlie-meta-reklam-izle.service || true
systemctl --no-pager status lcarlie-meta-reklam-izle.service | tail -5
docker exec lcarlie-postgres psql -U n8n -d n8n -c "SELECT id, durum, reklam_satir, yerlesim_satir, uyari_sayisi, yeni_uyari, bildirim, hata FROM raw.meta_izleme_kosu ORDER BY id DESC LIMIT 1;"
systemctl list-timers --no-pager | grep meta-reklam-izle
echo "yedek: $YEDEK"
