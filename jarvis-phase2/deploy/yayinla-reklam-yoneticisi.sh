#!/bin/bash
# REKLAM YONETICISI canliya alma (15.11.2026, sahip: "Meta Business'taki gibi
# kreatifler ... yaninda Jarvis ve reklam ekiplerinin onerileri").
#   - webconsole: reklam_yoneticisi.py (yeni) + app.py/app.js/app.css/index.html/interior.js
#   - jarvis/reklam_uzman.py + config/reklam-uzman/ (uzman ikilisi sistem istemleri)
#   - scripts/reklam-oneri.py + lcarlie-reklam-oneri.timer (saatte bir :25)
#   - goc 077_reklam_yoneticisi.sql (15.11'de uygulandi; IF NOT EXISTS / OR REPLACE ile tekrar guvenli)
# Canli dosya yayin oncesi depodaki ESKI surumle ayni degilse DURUR (baskasinin
# canli yamasi ezilmez). Hicbir reklam ayari degismez; betik Meta'ya yazmaz.
# Geri alma: yedek dizinindeki dosyalari geri kopyala + systemctl restart jarvis-web;
#            systemctl disable --now lcarlie-reklam-oneri.timer
set -euo pipefail
K=${1:?kullanim: yayinla-reklam-yoneticisi.sh <commit>}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/reklam-yoneticisi-$(date +%Y%m%d-%H%M%S)
DEGISEN="webconsole/app.py webconsole/static/app.js webconsole/static/app.css webconsole/static/index.html webconsole/static/interior.js webconsole/tests/test_web_ui_contract.py"
YENI="webconsole/reklam_yoneticisi.py webconsole/tests/test_reklam_yoneticisi.py jarvis/reklam_uzman.py scripts/reklam-oneri.py config/reklam-uzman/uzman-1-meta-google.md config/reklam-uzman/uzman-2-pazaryeri-trendyol.md config/reklam-uzman/L-CARLIE-ozel-durum.md"
cd $L
for f in $DEGISEN; do
  if ! git -C $DEPO show $K~1:jarvis-phase2/$f | cmp -s - "$f"; then
    echo "DURDU: canli $f depodaki onceki surumle ayni degil; hicbir sey kopyalanmadi"; exit 3
  fi
done
mkdir -p "$YEDEK"
for f in $DEGISEN $YENI; do
  mkdir -p "$YEDEK/$(dirname $f)" "$(dirname $f)"
  [ -f "$f" ] && cp -p "$f" "$YEDEK/$f"
  git -C $DEPO show $K:jarvis-phase2/$f > "$f.yeni"
  chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
chmod 755 scripts/reklam-oneri.py
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q < <(git -C $DEPO show $K:jarvis-phase2/migrations/077_reklam_yoneticisi.sql)
# testler canli agacta (venv) -- kirmiziysa geri al
if ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_reklam*" >/tmp/reklam-yoneticisi-test.txt 2>&1 \
   || ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_web_ui*" >>/tmp/reklam-yoneticisi-test.txt 2>&1; then
  echo "TEST KIRMIZI -- geri aliniyor"; tail -20 /tmp/reklam-yoneticisi-test.txt
  for f in $DEGISEN; do cp -p "$YEDEK/$f" "$f"; done
  exit 4
fi
install -m 644 <(git -C $DEPO show $K:jarvis-phase2/deploy/reklam-yoneticisi/lcarlie-reklam-oneri.service) /etc/systemd/system/lcarlie-reklam-oneri.service
install -m 644 <(git -C $DEPO show $K:jarvis-phase2/deploy/reklam-yoneticisi/lcarlie-reklam-oneri.timer) /etc/systemd/system/lcarlie-reklam-oneri.timer
systemctl daemon-reload
systemctl restart jarvis-web
for i in $(seq 1 25); do k=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ || true); [ "$k" = 200 ] && break; sleep 1; done
echo "panel: HTTP $k"
# kreatif onbellegi + ilk uzman degerlendirmesi (onay gerekenler kuyruga/WhatsApp'a duser)
systemctl enable --now lcarlie-reklam-oneri.timer
( set -a; . /etc/lcarlie/jarvis-web.env; set +a; cd $L; JARVIS_STATE_DIR=$L/state $L/venv/bin/python scripts/reklam-oneri.py --elle ) || echo "UYARI: ilk oneri kosusu hata verdi (timer yine kurulu)"
chown -R root:root state/reklam-medya 2>/dev/null || true
chmod 755 state/reklam-medya 2>/dev/null || true
runuser -u jarvis-web -- test -r state/reklam-medya/index.json && echo "panel kullanicisi medyayi okuyabiliyor" || echo "UYARI: jarvis-web state/reklam-medya okuyamiyor"
journalctl -u jarvis-web --since "-2 min" --no-pager | grep -E " (500|503) " | tail -5 || true
systemctl list-timers --no-pager | grep reklam-oneri
echo "yedek: $YEDEK"
