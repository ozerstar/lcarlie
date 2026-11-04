#!/bin/bash
# v5 (ofis olaylari + sure sinirli yurutme) kurulumu ve 10 dakikalik mesai.
# v4 kurulumu/programlar bitene kadar bekler (gorev agaci ayni anda iki surecten yazilmasin).
# Sunucuda: nohup bash /tmp/jarvis-is-uretici-v5/mesai-v5.sh >/dev/null 2>&1 &   (log: /tmp/mesai-v5.log)
exec >> /tmp/mesai-v5.log 2>&1
while pgrep -f guncelle-v4.sh >/dev/null || systemctl list-units --no-legend --state=activating,active "lcarlie-is-uretici@*" | grep -q .; do sleep 15; done
S="$(cd "$(dirname "$0")" && pwd)"; J=/opt/lcarlie/jarvis-phase2
Y=/opt/lcarlie/backup-is-uretici-v5-$(date +%Y%m%d-%H%M%S); mkdir -p $Y
cp -a $J/jarvis/is_uretici.py $J/jarvis/programlar.py $J/scripts/is-uretici.py $J/scripts/yerel_model.py $J/state/is-uretici/agac.json $Y/
install -m 0644 $S/jarvis/is_uretici.py $S/jarvis/programlar.py $J/jarvis/
install -m 0755 $S/scripts/is-uretici.py $J/scripts/is-uretici.py
install -m 0644 $S/scripts/yerel_model.py $J/scripts/yerel_model.py
install -m 0644 $S/tests/test_is_uretici.py $S/tests/test_programlar.py $J/tests/
cd $J && venv/bin/python -m unittest tests.test_is_uretici tests.test_programlar -q || { echo "TEST HATASI, mesai baslamadi; yedek $Y"; exit 1; }
echo "$(date +%T) v5 kuruldu (yedek $Y); 10 dk mesai basliyor"
bitis=$(( $(date +%s) + 600 ))
( while [ $(date +%s) -lt $bitis ]; do systemctl start lcarlie-team-cycle.service; sleep 5; done ) &
systemd-run --unit=lcarlie-is-uretici-mesai --wait --collect -p EnvironmentFile=/etc/lcarlie/is-uretici.env \
  -p WorkingDirectory=$J -E JARVIS_MEMORY_TRANSPORT=local-docker -E JARVIS_STATE_DIR=$J/state -E EXTERNAL_ACTIONS=false \
  $J/venv/bin/python $J/scripts/is-uretici.py --mod yurut --sinir 200 --sure 600
wait
echo "$(date +%T) mesai bitti"
for m in b2b kreatif; do systemctl reset-failed lcarlie-is-uretici@$m.service 2>/dev/null; systemctl start lcarlie-is-uretici@$m.service || echo "UYARI $m"; journalctl -u lcarlie-is-uretici@$m.service -n 40 --no-pager -o cat | grep "^{" | tail -1 | cut -c1-500 || true; done
echo "$(date +%T) TAMAM"
