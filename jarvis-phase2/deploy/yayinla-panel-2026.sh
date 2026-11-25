#!/bin/bash
# PANEL TASARIM 2026 canliya alma (25.11.2026).
# Sahip: "jarvis panelini biraz geliştir, zaten çok eski kaldı."
#   - webconsole: tasarim jetonlari + yeni katmanlar, menu, Bugun seridi, telefon
#   - app.py / reklam_yoneticisi.py: ?ozet=1 kesiti, gizli yorum cevapsiz sayilmaz
#   - jarvis/meta_reklam_detay.py + scripts/meta-reklam-izle.py: Instagram hidden (yalniz GET)
#   - goc 080 (raw.meta_reklam_yorum.gizli, jarvis_web GRANT; tekrar guvenli)
# Canli dosya depodaki ONCEKI surumle ayni degilse DURUR. Meta'ya yazmaz,
# push/WhatsApp tetiklemez (toplayici kendi saatlik zamanlayicisiyla kosar).
# Geri alma: yedek dizinindeki dosyalari geri kopyala, YENI-DOSYALAR.txt'tekileri sil,
#            systemctl restart jarvis-web (goc 080 eklemeli; geri almaya gerek yok).
set -euo pipefail
K=${1:?kullanim: yayinla-panel-2026.sh commit}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/panel-2026-$(date +%Y%m%d-%H%M%S)
DEGISEN=$(git -C $DEPO diff --name-only --diff-filter=M "$K~1" "$K" -- jarvis-phase2 | sed 's#^jarvis-phase2/##')
YENI=$(git -C $DEPO diff --name-only --diff-filter=A "$K~1" "$K" -- jarvis-phase2 | sed 's#^jarvis-phase2/##' | grep -v '^deploy/' || true)
cd $L
for f in $DEGISEN; do
  if ! git -C $DEPO show "$K~1:jarvis-phase2/$f" | cmp -s - "$f"; then
    echo "DURDU: canli $f depodaki onceki surumle ayni degil; hicbir sey kopyalanmadi"; exit 3
  fi
done
mkdir -p "$YEDEK"
for f in $DEGISEN $YENI; do
  mkdir -p "$YEDEK/$(dirname "$f")" "$(dirname "$f")"
  if [ -f "$f" ]; then cp -p "$f" "$YEDEK/$f"; fi
  git -C $DEPO show "$K:jarvis-phase2/$f" > "$f.yeni"
  chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
chmod 755 scripts/meta-reklam-izle.py
printf '%s\n' $YENI > "$YEDEK/YENI-DOSYALAR.txt"
docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q < <(git -C $DEPO show "$K:jarvis-phase2/migrations/080_meta_yorum_gizli.sql")
geri_al() { for f in $DEGISEN; do cp -p "$YEDEK/$f" "$f"; done; for f in $YENI; do rm -f "$f"; done; }
if ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_*.py" >/tmp/panel-2026-test.txt 2>&1; then
  echo "TEST KIRMIZI (webconsole) -- geri aliniyor"; tail -25 /tmp/panel-2026-test.txt; geri_al; exit 4
fi
tail -3 /tmp/panel-2026-test.txt
PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s tests -t tests -p "test_*.py" >/tmp/panel-2026-test2.txt 2>&1 || true
grep -E "^Ran |^OK|^FAILED" /tmp/panel-2026-test2.txt | tail -2
systemctl restart jarvis-web
k=000
for i in $(seq 1 25); do k=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ || true); [ "$k" = 200 ] && break; sleep 1; done
echo "panel: HTTP $k"
for u in /tasarim-2026.css /tema-2026.js /mobile/tasarim-2026.css; do echo "$u $(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8091$u")"; done
journalctl -u jarvis-web --since "-2 min" --no-pager | grep -E " (500|503) " | tail -5 || true
echo "yedek: $YEDEK"
