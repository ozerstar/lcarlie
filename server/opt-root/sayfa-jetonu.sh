#!/usr/bin/env bash
# Sistem jetonundan SAYFA erisim jetonu turetir, .env'e yazar, konusmalari test eder.
# Hicbir jeton ekrana basilmaz.
set -Eeuo pipefail
ENV=/opt/lcarlie/n8n/.env
SAYFA=1222783064240254
SC=/tmp/sc.cfg     # sistem jetonu config
PT=/tmp/pt.txt     # sayfa jetonu
PC=/tmp/pc.cfg     # sayfa jetonu config
trap 'shred -u "$SC" "$PT" "$PC" 2>/dev/null || rm -f "$SC" "$PT" "$PC"' EXIT

# 1) Sistem jetonuyla sayfa jetonunu cek
{ printf 'header = "Authorization: Bearer '
  sed -n 's/^META_SYSTEM_TOKEN=//p' "$ENV" | tr -d '\r\n'
  printf '"\n'
  printf 'url = "https://graph.facebook.com/v23.0/%s?fields=access_token"\n' "$SAYFA"
  printf 'silent\nshow-error\n'; } > "$SC"
chmod 600 "$SC"
curl --config "$SC" --max-time 45 | jq -r '.access_token // empty' > "$PT"

UZ=$(wc -c < "$PT")
echo "Sayfa jetonu uzunlugu: $UZ"
[ "$UZ" -lt 50 ] && { echo "HATA: sayfa jetonu alinamadi"; echo "--- ham yanit ---"; curl --config "$SC" --max-time 45 | head -c 400; exit 1; }

sed -i '/^FB_PAGE_TOKEN=/d' "$ENV"
{ printf 'FB_PAGE_TOKEN='; tr -d '\r\n' < "$PT"; printf '\n'; } >> "$ENV"
chmod 600 "$ENV"
echo ".env'e FB_PAGE_TOKEN yazildi"

psorgu () {
  { printf 'header = "Authorization: Bearer '; tr -d '\r\n' < "$PT"; printf '"\n'
    printf 'url = "https://graph.facebook.com/v23.0/%s"\n' "$1"
    printf 'silent\nshow-error\n'; } > "$PC"
  chmod 600 "$PC"
  curl --config "$PC" --max-time 60
}

echo
echo "=== INSTAGRAM KONUSMALARI ==="
psorgu "$SAYFA/conversations?platform=instagram&fields=id,updated_time,message_count&limit=25" > /tmp/ig_conv.json
jq '{adet: (.data|length), hata: .error.message, ilk3: [.data[:3][] | {id, updated_time, message_count}]}' /tmp/ig_conv.json 2>/dev/null || head -c 400 /tmp/ig_conv.json

echo
echo "=== MESSENGER KONUSMALARI ==="
psorgu "$SAYFA/conversations?fields=id,updated_time,message_count&limit=25" > /tmp/ms_conv.json
jq '{adet: (.data|length), hata: .error.message}' /tmp/ms_conv.json 2>/dev/null || head -c 300 /tmp/ms_conv.json
