#!/usr/bin/env bash
# L'CARLIE - aylik stok sifirlama
# Her ayin 1'inde tum urunlerin stogunu MIKTAR degerine ceker ve takibi acik tutar.
# Kaynak kopyasi: 07 YAZILIM\LCARLIE-n8n-kaynak\stok-sifirla.sh
set -uo pipefail

ENV_DOSYA=/opt/lcarlie/n8n/.env
LOG=/opt/lcarlie/stok-sifirla.log
HATA_LOG=/opt/lcarlie/hata.log
MIKTAR="${MIKTAR:-250}"
VARSAYILAN_VARYANT="00000000-0000-0000-0000-000000000000"
KURU=0
[ "${1:-}" = "--kuru" ] && KURU=1

zaman() { date '+%Y-%m-%d %H:%M:%S'; }
hata() { echo "$(zaman) | STOK | $*" >> "$HATA_LOG"; echo "HATA: $*" >&2; }

# 721 karakterlik anahtar: cut -d= -f2 BOZAR, sed kullan (bkz. fiyat-log.sh dersi)
API_KEY=$(sed -n 's/^WIX_API_KEY=//p' "$ENV_DOSYA" | head -1)
SITE_ID=$(sed -n 's/^WIX_SITE_ID=//p' "$ENV_DOSYA" | head -1)

if [ -z "$API_KEY" ]; then hata "WIX_API_KEY bos"; exit 1; fi
if [ -z "$SITE_ID" ]; then hata "WIX_SITE_ID bos"; exit 1; fi

cagir() { # method url body -> "HTTPKOD\ngovde"
  # 🔴 API ANAHTARI KOMUT SATIRINA YAZILMAZ (16.09.2026 denetimi).
  #    Argumanlar 'ps' ile sunucudaki her surece gorunur. Yapilandirma
  #    STDIN'den gider; orada gorunmez.
  {
    printf '%s\n' '--silent' '--max-time 60' 'write-out = "\n%{http_code}"' \
      "request = \"$1\"" "url = \"$2\"" \
      "header = \"Authorization: $API_KEY\"" \
      "header = \"wix-site-id: $SITE_ID\"" \
      'header = "Content-Type: application/json"'
    [ -n "${3:-}" ] && printf 'data-binary = "%s"\n' \
      "$(printf '%s' "$3" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  } | curl -K -
}

# --- 1) Urunleri oku (sayfalayarak) ---
URUNLER=$(mktemp); trap 'rm -f "$URUNLER"' EXIT
OFFSET=0
: > "$URUNLER"
while : ; do
  CIKTI=$(cagir POST "https://www.wixapis.com/stores-reader/v1/products/query" \
    "{\"query\":{\"paging\":{\"limit\":100,\"offset\":$OFFSET}}}")
  KOD=$(printf '%s' "$CIKTI" | tail -n1)
  GOVDE=$(printf '%s' "$CIKTI" | sed '$d')

  if [ "$KOD" != "200" ]; then hata "urun okuma HTTP $KOD"; exit 1; fi

  ADET=$(printf '%s' "$GOVDE" | jq '.products | length')
  TOPLAM=$(printf '%s' "$GOVDE" | jq '.totalResults // 0')
  printf '%s' "$GOVDE" | jq -r '.products[] | [.id, .name] | @tsv' >> "$URUNLER"

  OFFSET=$((OFFSET + ADET))
  [ "$ADET" -eq 0 ] && break
  [ "$OFFSET" -ge "$TOPLAM" ] && break
done

SAYI=$(wc -l < "$URUNLER")
# "hicbir sey bulamadi" ile "hicbir seye bakmadi" ayrimi (bkz. aktif-denetim dersi)
if [ "$SAYI" -eq 0 ]; then hata "hic urun okunamadi - sifir urun sifirlanmaz"; exit 1; fi

if [ "$KURU" -eq 1 ]; then
  echo "KURU CALISMA: $SAYI urun bulundu, hicbiri degistirilmedi. Hedef miktar: $MIKTAR"
  exit 0
fi

# --- 2) Her urun icin stok yaz ---
BASARILI=0; BASARISIZ=0
while IFS=$'\t' read -r ID AD; do
  [ -z "$ID" ] && continue
  GOVDE_YAZ=$(jq -nc --arg p "$ID" --arg v "$VARSAYILAN_VARYANT" --argjson q "$MIKTAR" \
    '{inventoryItem:{productId:$p,trackQuantity:true,variants:[{variantId:$v,inStock:true,quantity:$q}]}}')
  CIKTI=$(cagir PATCH "https://www.wixapis.com/stores/v2/inventoryItems/product/$ID" "$GOVDE_YAZ")
  KOD=$(printf '%s' "$CIKTI" | tail -n1)
  if [ "$KOD" = "200" ]; then
    BASARILI=$((BASARILI+1))
  else
    BASARISIZ=$((BASARISIZ+1))
    hata "$AD -> HTTP $KOD"
  fi
done < "$URUNLER"

echo "$(zaman) | $BASARILI basarili / $BASARISIZ basarisiz / hedef $MIKTAR" >> "$LOG"

if [ "$BASARISIZ" -gt 0 ]; then
  hata "$BASARISIZ urun guncellenemedi"
  exit 1
fi
echo "$(zaman) TAMAM: $BASARILI urun $MIKTAR'e cekildi"
exit 0
