#!/bin/bash
# REKLAM YONETICISI · reklam bazli gorunum canliya alma (17.11.2026).
# Sahip: "hangi reklam hangisi kapali, basarili olanlar olmayanlar, ozellikler,
# aciklamalar ... reklam bazli; o reklamlari da gormek istiyorum, yorumlari da."
#   - webconsole: reklam_yoneticisi.py, app.py (varlik/yorum uclari, Range video),
#     app.js/app.css/index.html (platform sekmeleri, durum cipleri, reklam penceresi)
#   - jarvis/meta_reklam_detay.py (envanter + yorum; yalniz GET)
#   - scripts/meta-reklam-izle.py (:12, envanter+yorum adimi), scripts/reklam-oneri.py
#     (:25, video/gorsel varlik onbellegi; kapali reklam modele gitmez)
#   - goc 079 (raw.meta_reklam_envanter, raw.meta_reklam_yorum; jarvis_web GRANT)
# Canli dosya depodaki ONCEKI surumle ayni degilse DURUR. Meta'ya yazmaz,
# oneri/WhatsApp tetiklemez (yalniz --medya). Geri alma: yedek dizinindeki
# dosyalari geri kopyala + systemctl restart jarvis-web.
set -euo pipefail
K=${1:?kullanim: yayinla-reklam-detay.sh <commit>}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/reklam-detay-$(date +%Y%m%d-%H%M%S)
DEGISEN="webconsole/app.py webconsole/reklam_yoneticisi.py webconsole/static/app.js webconsole/static/app.css webconsole/static/index.html webconsole/tests/test_web_ui_contract.py scripts/meta-reklam-izle.py scripts/reklam-oneri.py"
YENI="jarvis/meta_reklam_detay.py webconsole/tests/test_reklam_detay.py"
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
chmod 755 scripts/meta-reklam-izle.py scripts/reklam-oneri.py
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q < <(git -C $DEPO show $K:jarvis-phase2/migrations/079_meta_reklam_detay.sql)
if ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_reklam*" >/tmp/reklam-detay-test.txt 2>&1 \
   || ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_web_ui*" >>/tmp/reklam-detay-test.txt 2>&1; then
  echo "TEST KIRMIZI -- geri aliniyor"; tail -20 /tmp/reklam-detay-test.txt
  for f in $DEGISEN; do cp -p "$YEDEK/$f" "$f"; done
  for f in $YENI; do rm -f "$f"; done
  exit 4
fi
systemctl restart jarvis-web
for i in $(seq 1 25); do k=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ || true); [ "$k" = 200 ] && break; sleep 1; done
echo "panel: HTTP $k"
# Varlik onbellegi (video/gorsel). Oneri uretmez, kuyruga/WhatsApp'a yazmaz.
( set -a; . /etc/lcarlie/jarvis-web.env; set +a; cd $L; umask 022; JARVIS_STATE_DIR=$L/state $L/venv/bin/python scripts/reklam-oneri.py --medya ) || echo "UYARI: varlik onbellegi hata verdi"
runuser -u jarvis-web -- test -r state/reklam-medya/varlik.json && echo "panel kullanicisi varlik dizinini okuyabiliyor" || echo "UYARI: jarvis-web state/reklam-medya/varlik.json okuyamiyor"
journalctl -u jarvis-web --since "-2 min" --no-pager | grep -E " (500|503) " | tail -5 || true
echo "yedek: $YEDEK"
