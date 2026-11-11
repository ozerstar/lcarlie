#!/usr/bin/env bash
# KREATİF ÜRETİM + OTONOM EKİP ONAYI
# GPT Work görseli ve metni üretir; departman incelemesi gerekirse en çok üç
# kısa revizyon turu yapar. GECER olunca Jarvis içerik onayını kaydeder.
# Bu hat Instagram'da yayın yapmaz.
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

OUT="state/kreatif-brief/$PARTI-gorseller"
RAPOR="$OUT/inceleme.json"

# İlk inceleme düzeltme istiyorsa Jarvis kısa ekip notlarını GPT Work'e aktarır,
# önceki kareyi referans verir ve en fazla beş kez üretip yeniden inceler.
DUZELTME_GEREKLI="$($PY -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); print(int(any(str(x.get("direktor_karari","")).upper() in ("DUZELT","RED") for x in d.get("gorseller",[]))))' "$RAPOR")"
if [ "$DUZELTME_GEREKLI" = "1" ]; then
  echo
  echo "== OTONOM REVİZYON DÖNGÜSÜ ============================="
  REV_LOG="state/kreatif-brief/$PARTI-otonom-revizyon.log"
  REV_KOD=0
  "$PY" scripts/kreatif-revizyon.py "$BRIEF" "$RAPOR" \
    --urun-gorsel "$CEKIM" --azami-tur 5 2>&1 | tee "$REV_LOG" || REV_KOD=$?
  SON_PARTI="$(sed -n 's/^FINAL_PARTI=//p' "$REV_LOG" | tail -n1)"
  SON_DURUM="$(sed -n 's/^FINAL_DURUM=//p' "$REV_LOG" | tail -n1)"
  [ -n "$SON_PARTI" ] || SON_PARTI="$PARTI"
  if [ "$REV_KOD" -ne 0 ] || [ "$SON_DURUM" != "GECER" ]; then
    echo "Jarvis beş revizyon turundan sonra da departman onayı alamadı; kullanıcı incelemesine bırakılıyor."
    "$KOK/bin/jarvis-operator" create-task KREATIF_INCELEME "$SON_PARTI"
    exit 3
  fi
  PARTI="$SON_PARTI"
else
  echo "ilk ekip incelemesi geçti; revizyon gerekmedi."
fi

echo "Jarvis departman onayı: GECER · çıktı: state/kreatif-brief/$PARTI-gorseller"
echo "Görsel üretim ve ekip onayı tamamlandı; dış yayın ayrıca başlatılmadı."

