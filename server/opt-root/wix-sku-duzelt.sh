#!/usr/bin/env bash
# wix-sku-duzelt.sh — Wix Stores V1'de bir urunun SKU'sunu duzeltir.
#
# NEDEN: BUGUARD ve SOFTGUARD ayni barkodu (8684869609301) tasiyordu.
# Sahip karari 22.10.2026: BUGUARD'inki tum platformlarda SABIT kalir,
# SOFTGUARD 8684869609608 olur.
#
# Anahtar bu dosyada DEGIL: /opt/lcarlie/n8n/.env icinde WIX_API_KEY + WIX_SITE_ID.
#
# Kullanim:
#   sudo /opt/lcarlie/wix-sku-duzelt.sh <urun_id>            # OKU (varsayilan)
#   sudo /opt/lcarlie/wix-sku-duzelt.sh <urun_id> <yeni_sku> --yaz
set -uo pipefail
ENVF=/opt/lcarlie/n8n/.env
URUN="${1:?urun_id gerekir}"
YENI="${2:-}"
YAZ=0
[ "${3:-}" = "--yaz" ] && YAZ=1

KEY=$(sed -n 's/^WIX_API_KEY=//p' "$ENVF" | head -n1)
SITE=$(sed -n 's/^WIX_SITE_ID=//p' "$ENVF" | head -n1)
[ -n "$KEY" ] || { echo "HATA: WIX_API_KEY yok"; exit 2; }

cagir() { # $1=method $2=yol $3=govde
  curl -s -X "$1" -m 40 \
    -H "Authorization: $KEY" -H "wix-site-id: $SITE" \
    -H 'Content-Type: application/json' \
    ${3:+-d "$3"} "https://www.wixapis.com$2"
}

echo "=== MEVCUT DURUM ==="
MEVCUT=$(cagir GET "/stores/v1/products/$URUN")
printf '%s' "$MEVCUT" | jq '{id: .product.id, name: .product.name,
  sku: .product.sku, manageVariants: .product.manageVariants,
  variant_adet: (.product.variants | length),
  variant_skular: [.product.variants[]?.variant.sku]}'

[ "$YAZ" -eq 0 ] && { echo; echo "Yazmak icin: ... <yeni_sku> --yaz"; exit 0; }
[ -n "$YENI" ] || { echo "HATA: yeni_sku verilmedi"; exit 2; }

ESKI=$(printf '%s' "$MEVCUT" | jq -r '.product.sku // ""')
echo
echo "=== YAZILIYOR: $ESKI -> $YENI ==="
SONUC=$(cagir PATCH "/stores/v1/products/$URUN" "{\"product\":{\"sku\":\"$YENI\"}}")
printf '%s' "$SONUC" | jq -c '{sku: .product.sku, name: .product.name}' 2>/dev/null \
  || printf '%s\n' "$SONUC" | head -c 400

echo
echo "=== GERI OKUMA (dogrulama) ==="
cagir GET "/stores/v1/products/$URUN" \
  | jq '{name: .product.name, sku: .product.sku}'
