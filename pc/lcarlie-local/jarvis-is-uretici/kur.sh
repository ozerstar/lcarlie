#!/bin/bash
# Sunucuda root olarak calistirilir: bash kur.sh  (paket /tmp/jarvis-is-uretici altinda)
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
J=/opt/lcarlie/jarvis-phase2
TS=$(date +%Y%m%d-%H%M%S)
YEDEK=/opt/lcarlie/backup-is-uretici-$TS
echo "== on kontrol"
test -d "$J/jarvis" && test -x "$J/venv/bin/python" || { echo "Jarvis dizini/venv yok"; exit 1; }
for f in "$J/jarvis/is_uretici.py" "$J/scripts/is-uretici.py" /etc/systemd/system/lcarlie-is-uretici@.service; do
  if [ -e "$f" ] && ! cmp -s "$f" "$SRC/${f##*/jarvis-phase2/}" 2>/dev/null; then
    echo "UYARI: $f zaten var ve farkli -- baska bir oturum (Codex?) eklemis olabilir. Durduruldu."; exit 2; fi
done
echo "== yedek: $YEDEK"
mkdir -p "$YEDEK"
cp -a "$J/state/improvement" "$YEDEK/improvement" 2>/dev/null || true
[ -d "$J/state/is-uretici" ] && cp -a "$J/state/is-uretici" "$YEDEK/" || true
echo "== dosyalar"
install -m 0644 "$SRC/jarvis/is_uretici.py" "$J/jarvis/is_uretici.py"
install -m 0755 "$SRC/scripts/is-uretici.py" "$J/scripts/is-uretici.py"
install -d "$J/tests" && install -m 0644 "$SRC/tests/test_is_uretici.py" "$J/tests/test_is_uretici.py"
install -m 0644 "$SRC"/deploy/lcarlie-is-uretici@.service "$SRC"/deploy/lcarlie-is-uretici-*.timer /etc/systemd/system/
[ -f /etc/lcarlie/is-uretici.env ] || install -m 0600 "$SRC/deploy/is-uretici.env.example" /etc/lcarlie/is-uretici.env
echo "== testler (sahte model, sifir dis cagri)"
cd "$J" && venv/bin/python -m unittest tests.test_is_uretici -q
echo "== kuru deneme (2 departman, deftere yazmaz; 2 model cagrisi)"
JARVIS_STATE_DIR=$J/state JARVIS_MEMORY_TRANSPORT=local-docker venv/bin/python scripts/is-uretici.py --mod gunluk --sinir 2 --kuru
echo "== zamanlayicilar"
systemctl daemon-reload
systemctl enable --now lcarlie-is-uretici-gunluk.timer lcarlie-is-uretici-yurut.timer lcarlie-is-uretici-haftalik.timer lcarlie-is-uretici-aylik.timer
echo "== ilk tur: aylik hedef agaci -> gunluk gorevler -> haftalik rapor -> yurutme"
for m in aylik gunluk haftalik yurut; do systemctl start lcarlie-is-uretici@$m.service || echo "UYARI: $m basarisiz (journalctl -u lcarlie-is-uretici@$m)"; done
systemctl list-timers --no-pager | grep is-uretici || true
ls -la "$J/state/is-uretici" && cat "$J/state/is-uretici"/ozet-*.md | tail -40
echo "TAMAM. Yedek: $YEDEK"
