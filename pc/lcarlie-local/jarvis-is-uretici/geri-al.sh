#!/bin/bash
# Is ureticiyi tamamen kaldirir. Defterdeki 'isuretici:' isleri ve state/is-uretici raporlari arsiv icin birakilir.
set -euo pipefail
systemctl disable --now lcarlie-is-uretici-gunluk.timer lcarlie-is-uretici-yurut.timer lcarlie-is-uretici-haftalik.timer lcarlie-is-uretici-aylik.timer 2>/dev/null || true
rm -f /etc/systemd/system/lcarlie-is-uretici@.service /etc/systemd/system/lcarlie-is-uretici-*.timer
systemctl daemon-reload
rm -f /opt/lcarlie/jarvis-phase2/jarvis/is_uretici.py /opt/lcarlie/jarvis-phase2/scripts/is-uretici.py /opt/lcarlie/jarvis-phase2/tests/test_is_uretici.py
echo "Kaldirildi. Sadece durdurmak icin: /etc/lcarlie/is-uretici.env icinde IS_URETICI_ENABLED=false"
