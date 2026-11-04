#!/bin/bash
# v3: rakip / kreatif / b2b / retro programlari. Sunucuda root: bash /tmp/jarvis-is-uretici-v3/guncelle-v3.sh
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"; J=/opt/lcarlie/jarvis-phase2
Y=/opt/lcarlie/backup-is-uretici-v3-$(date +%Y%m%d-%H%M%S); mkdir -p $Y
cp -a $J/jarvis/is_uretici.py $J/scripts/is-uretici.py $J/state/is-uretici/agac.json /etc/lcarlie/is-uretici.env $Y/
for f in jarvis/programlar.py scripts/program_baglantilari.py; do
  if [ -e $J/$f ] && ! cmp -s $J/$f $S/$f; then echo "UYARI: $J/$f var ve farkli; durduruldu"; exit 2; fi
done
install -m 0644 $S/jarvis/is_uretici.py $S/jarvis/programlar.py $J/jarvis/
install -m 0755 $S/scripts/is-uretici.py $J/scripts/is-uretici.py
install -m 0644 $S/scripts/program_baglantilari.py $J/scripts/
install -m 0644 $S/tests/test_is_uretici.py $S/tests/test_programlar.py $J/tests/
install -m 0644 $S/deploy/lcarlie-is-uretici-*.timer /etc/systemd/system/
sed -i "s/^IS_URETICI_GUNLUK_TAVAN=.*/IS_URETICI_GUNLUK_TAVAN=240/" /etc/lcarlie/is-uretici.env
if [ -f /tmp/eczaneler.csv ]; then install -d -m 0700 $J/state/b2b; install -m 0600 /tmp/eczaneler.csv $J/state/b2b/eczaneler.csv; shred -u /tmp/eczaneler.csv; fi
cd $J && venv/bin/python -m unittest tests.test_is_uretici tests.test_programlar -q
systemctl daemon-reload
systemctl enable --now lcarlie-is-uretici-rakip.timer lcarlie-is-uretici-kreatif.timer lcarlie-is-uretici-b2b.timer lcarlie-is-uretici-retro.timer
echo "== ilk tur"
for m in rakip kreatif b2b retro; do systemctl start lcarlie-is-uretici@$m.service || echo "UYARI: $m (journalctl -u lcarlie-is-uretici@$m)"; journalctl -u lcarlie-is-uretici@$m.service -n 30 --no-pager -o cat | grep '^{' | tail -1 | cut -c1-600; done
ls $J/state/programlar/*/ 2>/dev/null | head -30
echo "TAMAM. Yedek: $Y"
