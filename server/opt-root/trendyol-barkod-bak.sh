#!/usr/bin/env bash
# trendyol-barkod-bak.sh — Trendyol'da bir barkodun CANLI durumu. SALT OKUNUR.
# Lonca konteynerine gerek yok: Basic auth ile tek GET.
# Anahtar: /etc/lcarlie/trendyol.env (600, root)
# Kullanim: sudo /opt/lcarlie/trendyol-barkod-bak.sh <barkod> [<barkod> ...]
set -u
. /etc/lcarlie/trendyol.env
: "${TRENDYOL_SELLER_ID:?}" "${TRENDYOL_API_KEY:?}" "${TRENDYOL_API_SECRET:?}"
B64=$(printf '%s:%s' "$TRENDYOL_API_KEY" "$TRENDYOL_API_SECRET" | base64 -w0)
UA="${TRENDYOL_SELLER_ID} - SelfIntegration"

for barkod in "$@"; do
  y=$(curl -s -m 30 -H "Authorization: Basic $B64" -H "User-Agent: $UA" \
      "https://apigw.trendyol.com/integration/product/sellers/${TRENDYOL_SELLER_ID}/products?barcode=${barkod}")
  echo "=== $barkod ==="
  printf '%s' "$y" | jq -c 'if .content then
      {toplam: .totalElements,
       kayitlar: [.content[] | {barcode, title: (.title[0:52]), approved, archived,
                                onSale, quantity, productMainId, productCode}]}
    else . end' 2>/dev/null || printf '%s\n' "$y" | head -c 300
  echo
done
