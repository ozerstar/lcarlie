#!/usr/bin/env bash
# KREATİF SIRASI — zamanlayıcının çağırdığı giriş.
#
# Hat bir ÜRÜN adı ister; zamanlayıcının o adı bir yerden seçmesi gerekir.
# Seçim kuralı: gerçek çekimi olan ürünler arasında SIRAYLA.
#
# 🔴 Neden çekimi olanlar arasından: ambalaj AI'ya çizdirilmediği için
#    çekimi olmayan ürün için görsel zaten üretilemez. Listeyi ürün
#    kataloğundan almak, her koşuda 30 küsur "çekim yok" hatası üretirdi.
#
# 🔴 Neden sırayla ve tek ürün: her koşu bir brief + N görsel + N×4 inceleme
#    çağrısı demek. Hepsini aynı anda koşmak hem faturayı hem onay kuyruğunu
#    şişirir. Sahip dört kareye bakıp karar verir; kırk kareye bakmaz.
set -euo pipefail

KOK="/opt/lcarlie/jarvis-phase2"
DURUM="$KOK/state/kreatif-sira.txt"
cd "$KOK"

mapfile -t URUNLER < <(find varliklar/urun -maxdepth 1 -type f \
    \( -iname '*.png' -o -iname '*.jpg' \) ! -name '*.etiket.txt' -printf '%f\n' \
    | sed 's/\.[^.]*$//' | tr '[:lower:]' '[:upper:]' | sort -u)

if [ "${#URUNLER[@]}" -eq 0 ]; then
  echo "varliklar/urun/ bos -- gercek cekim olmadan kreatif uretilemez" >&2
  exit 2
fi

SON="$(cat "$DURUM" 2>/dev/null || echo '')"
SIRADAKI="${URUNLER[0]}"
for i in "${!URUNLER[@]}"; do
  if [ "${URUNLER[$i]}" = "$SON" ]; then
    SIRADAKI="${URUNLER[$(( (i + 1) % ${#URUNLER[@]} ))]}"
    break
  fi
done

echo "kreatif sirasi: $SIRADAKI (onceki: ${SON:-yok}, havuz: ${#URUNLER[@]})"
printf '%s' "$SIRADAKI" > "$DURUM"

exec bash "$KOK/scripts/kreatif-hat.sh" "$SIRADAKI" --gorsel 4

