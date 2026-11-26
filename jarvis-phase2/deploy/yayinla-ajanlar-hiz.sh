#!/bin/bash
# AJANLAR sayfasi hiz duzeltmesi canliya alma (26.11.2026).
# Olcum: /api/panel/ajanlar 11-16 sn. Sebep: ekip gorusleri (47 sorgu) ayni
# istekte IKI KEZ ve SIRAYLA okunuyordu; mart.soru_konu her mesaj x kalip icin
# normalize islemini yeniden yapiyordu (~1,4 sn, iki kez okunuyor).
#   - webconsole/app.py: gorusler bir kez, sorgular paralel (onbellek YOK)
#   - goc 081: mart.soru_konu ayni sonuc, normalize mesaj basina bir kez
#   - webconsole/tests/test_ajanlar_hiz.py
# Canli dosya depodaki ONCEKI surumle ayni degilse DURUR. deploy.sh KULLANMAZ.
# Geri alma: yedek dizinindeki app.py'yi geri kopyala +
#   docker exec -i lcarlie-postgres psql -U n8n -d n8n < $YEDEK/soru_konu_eski.sql
#   + systemctl restart jarvis-web
set -euo pipefail
K=${1:?kullanim: yayinla-ajanlar-hiz.sh <commit>}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/ajanlar-hiz-$(date +%Y%m%d-%H%M%S)
DEGISEN="webconsole/app.py"
YENI="webconsole/tests/test_ajanlar_hiz.py migrations/081_soru_konu_hiz.sql deploy/geri-donus/081_soru_konu_eski.sql"
PSQL="docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -q"
cd $L
for f in $DEGISEN; do
  if ! git -C $DEPO show $K~1:jarvis-phase2/$f | cmp -s - "$f"; then
    echo "DURDU: canli $f depodaki onceki surumle ayni degil; hicbir sey kopyalanmadi"; exit 3
  fi
done
mkdir -p "$YEDEK"
# Gorunumun SU ANKI tanimi (geri donus icin, depodakinden bagimsiz)
{ echo "BEGIN;"; echo "CREATE OR REPLACE VIEW mart.soru_konu AS";
  docker exec lcarlie-postgres psql -U n8n -d n8n -Atc "select pg_get_viewdef('mart.soru_konu'::regclass, true)";
  echo "COMMIT;"; } > "$YEDEK/soru_konu_eski.sql"
docker exec lcarlie-postgres psql -U n8n -d n8n -Atc "select row_to_json(x) from (select * from mart.soru_konu order by konu) x" > "$YEDEK/soru_konu_once.json"
for f in $DEGISEN $YENI; do
  mkdir -p "$YEDEK/$(dirname $f)" "$(dirname $f)"
  [ -f "$f" ] && cp -p "$f" "$YEDEK/$f"
  git -C $DEPO show $K:jarvis-phase2/$f > "$f.yeni"
  chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
geri_al() {
  for f in $DEGISEN; do cp -p "$YEDEK/$f" "$f"; done
  for f in $YENI; do [ -f "$YEDEK/$f" ] && cp -p "$YEDEK/$f" "$f" || rm -f "$f"; done
  $PSQL < "$YEDEK/soru_konu_eski.sql"
}
$PSQL < migrations/081_soru_konu_hiz.sql
docker exec lcarlie-postgres psql -U n8n -d n8n -Atc "select row_to_json(x) from (select * from mart.soru_konu order by konu) x" > "$YEDEK/soru_konu_sonra.json"
if ! cmp -s "$YEDEK/soru_konu_once.json" "$YEDEK/soru_konu_sonra.json"; then
  echo "GORUNUM SONUCU DEGISTI -- geri aliniyor"; geri_al; exit 5
fi
if ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_ajanlar_hiz*" >/tmp/ajanlar-hiz-test.txt 2>&1 \
   || ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_web_ui*" >>/tmp/ajanlar-hiz-test.txt 2>&1; then
  echo "TEST KIRMIZI -- geri aliniyor"; tail -20 /tmp/ajanlar-hiz-test.txt
  geri_al; exit 4
fi
systemctl restart jarvis-web
for i in $(seq 1 25); do k=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ || true); [ "$k" = 200 ] && break; sleep 1; done
echo "panel: HTTP $k"
journalctl -u jarvis-web --since "-2 min" --no-pager | grep -E " (500|503) " | tail -5 || true
echo "yedek: $YEDEK"
