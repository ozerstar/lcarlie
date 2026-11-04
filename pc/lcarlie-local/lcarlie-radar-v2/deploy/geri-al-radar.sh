#!/bin/bash
# Radar'ı durdurur ve Jarvis panelini kurulum öncesine döndürür. Radar verisi (/opt/lcarlie/radar) SİLİNMEZ.
# Kullanım (root): bash geri-al-radar.sh /opt/lcarlie/backup-radar-<zaman>
set -euo pipefail
Y="${1:?yedek klasörü verin: /opt/lcarlie/backup-radar-...}"
J=/opt/lcarlie/jarvis-phase2
for t in /etc/systemd/system/lcarlie-radar-*.timer; do
  [ -e "$t" ] && systemctl disable --now "$(basename "$t")" || true
done
rm -f /etc/systemd/system/lcarlie-radar-*.timer /etc/systemd/system/lcarlie-radar@.service
systemctl daemon-reload
if [ -f "$Y/ekip_isleri.py" ]; then
  install -m 0644 "$Y/ekip_isleri.py" "$J/webconsole/ekip_isleri.py"
  systemctl restart jarvis-web.service
fi
echo "Radar zamanlayıcıları kapatıldı; panel geri alındı. Veri: /opt/lcarlie/radar (elle silinmedikçe durur)."
