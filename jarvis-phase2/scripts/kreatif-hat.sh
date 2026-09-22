#!/usr/bin/env bash
# KREATİF HAT — brief, görsel, ekip incelemesi ve SAHİBİN ONAY KUYRUĞU.
#
#   kreatif-hat.sh HYDRAVIE
#   kreatif-hat.sh HYDRAVIE --gorsel 3
#
# 🔴 BU BETİK BİR İNSANIN ELİYLE ÇALIŞTIRILMAK İÇİN DEĞİL, ZAMANLAYICI İÇİN
#    yazıldı: `lcarlie-kreatif-hat.timer`. Sahip kararı (21.09.2026): görseli
#    Jarvis üretecek, Gemini/GPT'ye o gönderecek, dönen işi Jarvis'in ekibi ve
#    direktörleri inceleyecek, sahibin önüne öyle gelecek.
#
# Zincir:
#   1-6  ürün gerçeği · rakip · konumlandırma · denetim kapıları · red team
#   7    ürün fotoğrafı + logo görsel modeline gider; kesim/montaj/tasarım orada
#   8    Jarvis'in ekibi inceler (ölçüm + departman görüşü + direktör kararı)
#   9    görev açılır -> jarvis döngüsü öneriyi SAHİBİN ONAY KUYRUĞUNA yazar
#
# 🔴 9. ADIM YAPMAYAN BİR KOŞU YARIM KALMIŞ SAYILIR: görsel üretilip kimseye
#    gösterilmiyorsa hattın anlamı yok. O yüzden görev açma adımı hata verirse
#    betik sıfırdan farklı çıkar.
set -euo pipefail

KOK="/opt/lcarlie/jarvis-phase2"
PY="$KOK/venv/bin/python"
URUN="${1:?kullanim: kreatif-hat.sh <URUN> [--gorsel N]}"
shift || true

cd "$KOK"

anahtar="$(printf '%s' "$URUN" | tr '[:upper:]' '[:lower:]')"
CEKIM="$(find varliklar/urun -maxdepth 1 -type f \
         \( -iname "*${anahtar}*.png" -o -iname "*${anahtar}*.jpg" \) \
         ! -name '*.etiket.txt' | sort | head -n1 || true)"
if [ -z "$CEKIM" ]; then
  echo "HATA: $URUN icin urun cekimi yok." >&2
  echo "  Gercek cekimi su klasore koyun: $KOK/varliklar/urun/" >&2
  echo "  Ambalaj AI'ya cizdirilmedigi icin cekim olmadan gorsel uretilemez." >&2
  exit 2
fi
echo "urun cekimi: $CEKIM"

echo "== 1-6  BRIEF =========================================="
"$PY" scripts/kreatif-brief.py "$URUN" "$@"

BRIEF="$(ls -1t state/kreatif-brief/*.json | head -n1)"
PARTI="$(basename "${BRIEF%.json}")"

echo
echo "== 7    GORSEL ========================================="
"$PY" scripts/gorsel-uret.py "$BRIEF" --urun-gorsel "$CEKIM"

echo
echo "== 8    EKIP INCELEMESI ================================"
"$PY" scripts/kreatif-inceleme.py "state/kreatif-brief/${PARTI}-gorseller" \
      --urun-gorsel "$CEKIM"

echo
echo "== 9    SAHIBIN ONAY KUYRUGU ==========================="
# Gorev acilir; onerinin kendisini JARVIS DONGUSU yazar (loop.py ->
# _build_kreatif_payload -> core.ai_propose_action). Bu betik onay
# kuyruguna DOGRUDAN yazmaz -- yazsaydi firewall ve sozlesme kapilarini
# atlamis olurdu.
"$KOK/bin/jarvis-operator" create-task KREATIF_INCELEME "$PARTI"

echo
echo "TESLIM:"
echo "  parti : $PARTI"
echo "  brief : ${BRIEF%.json}.md"
echo "  gorsel: state/kreatif-brief/${PARTI}-gorseller/"
echo "  onay  : jarvis dongusu gorevi alinca panelde ONERILER'de gorunur"

