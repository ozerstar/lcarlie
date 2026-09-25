#!/usr/bin/env bash
# ONAY SONRASI ÜRETİM — sahip brief'i onayladıktan SONRA koşar.
#
#   kreatif-uret.sh hydravie-20260921-1232
#
# 🔴 BU BETİK KENDİ BAŞINA KOŞMAZ, ZAMANLAYICISI YOKTUR. Sahip kararı:
#    "üretim benim onayım olmadan yapılmasın." Zamanlayıcıya bağlansaydı
#    onay kapısı dekor olurdu.
#
# Zincir: görsel üretimi -> ekip incelemesi -> İKİNCİ öneri (yayın onayı).
set -euo pipefail

KOK="/opt/lcarlie/jarvis-phase2"
PY="$KOK/venv/bin/python"
export JARVIS_MEMORY_TRANSPORT="${JARVIS_MEMORY_TRANSPORT:-local-docker}"
PARTI="${1:?kullanim: kreatif-uret.sh <parti>}"

cd "$KOK"
BRIEF="state/kreatif-brief/${PARTI}.json"
[ -f "$BRIEF" ] || { echo "brief yok: $BRIEF" >&2; exit 2; }

# Ürün adını brief'ten al; çekimi ada göre bul.
URUN="$("$PY" -c "
import json,sys
b=json.load(open('$BRIEF',encoding='utf-8'))
print(str((b.get('urun') or {}).get('urun_adi') or '').split('|')[0].strip())
")"
anahtar="$(printf '%s' "$URUN" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
CEKIM="$(find varliklar/urun -maxdepth 1 -type f \
         \( -iname "*${anahtar}*.png" -o -iname "*${anahtar}*.jpg" \) \
         ! -name '*.etiket.txt' | sort | head -n1 || true)"
if [ -z "$CEKIM" ]; then
  echo "HATA: '$URUN' icin gercek urun cekimi yok." >&2
  echo "  Brief ve promptlar hazir ama gorsel uretilemez." >&2
  echo "  Cekimi su klasore koyun: $KOK/varliklar/urun/" >&2
  exit 3
fi
echo "urun: $URUN · cekim: $CEKIM"

echo "== GORSEL =============================================="
"$PY" scripts/gorsel-uret.py "$BRIEF" --urun-gorsel "$CEKIM"

echo
echo "== EKIP INCELEMESI ====================================="
"$PY" scripts/kreatif-inceleme.py "state/kreatif-brief/${PARTI}-gorseller" \
      --urun-gorsel "$CEKIM"

echo
echo "== YAYIN ONAYI KUYRUGU ================================="
"$KOK/bin/jarvis-operator" create-task KREATIF_INCELEME "$PARTI"
echo "gorseller uretildi ve incelendi; yayin onayi kuyruga dustu."
