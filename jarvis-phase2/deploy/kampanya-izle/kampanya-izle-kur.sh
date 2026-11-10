#!/usr/bin/env bash
# Kampanya izlemeyi canliya alir. Kullanim: sudo bash kampanya-izle-kur.sh 1111
# Kapatmak: systemctl disable --now lcarlie-kampanya-izle@1111.timer lcarlie-kampanya-ozet@1111.timer
set -euo pipefail
K="${1:?kampanya adi}"
R=/opt/lcarlie/source/lcarlie-jarvis-v1/jarvis-phase2
L=/opt/lcarlie/jarvis-phase2
install -m 0644 "$R/scripts/kampanya-izle.py" "$L/scripts/kampanya-izle.py"
install -d -m 0700 "$L/state/kampanya-izle"
[ -f "$L/state/kampanya-izle/$K.json" ] || install -m 0600 "$R/deploy/kampanya-izle/$K.json" "$L/state/kampanya-izle/$K.json"
for u in lcarlie-kampanya-izle@.service lcarlie-kampanya-ozet@.service lcarlie-kampanya-izle@.timer lcarlie-kampanya-ozet@.timer; do
  install -m 0644 "$R/deploy/kampanya-izle/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now "lcarlie-kampanya-izle@$K.timer" "lcarlie-kampanya-ozet@$K.timer"
systemctl start "lcarlie-kampanya-izle@$K.service"
systemctl is-active "lcarlie-kampanya-izle@$K.timer" "lcarlie-kampanya-ozet@$K.timer"
tail -c 600 "$L/state/kampanya-izle/$K.durum.json"
