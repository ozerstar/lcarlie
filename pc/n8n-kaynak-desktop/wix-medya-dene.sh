#!/usr/bin/env bash
# wix-medya-dene.sh — Mevcut Wix API anahtari MEDYA yukleme yetkisine sahip mi?
# Sadece upload-url ister; dosya yuklemez. Idefix "images.url" icin herkese
# acik HTTPS adres gerekiyor; Wix medya CDN'i (static.wixstatic.com) aday 1.
set -u
ENVF=/opt/lcarlie/n8n/.env
KEY=$(sed -n 's/^WIX_API_KEY=//p' "$ENVF" | head -n1)
SITE=$(sed -n 's/^WIX_SITE_ID=//p' "$ENVF" | head -n1)

echo "=== /site-media/v1/files/generate-upload-url ==="
curl -s -m 30 -X POST \
  -H "Authorization: $KEY" -H "wix-site-id: $SITE" \
  -H 'Content-Type: application/json' \
  -d '{"mimeType":"image/jpeg","fileName":"idefix-deneme.jpg","parentFolderId":"visitor-uploads"}' \
  "https://www.wixapis.com/site-media/v1/files/generate-upload-url" | head -c 500
echo; echo
echo "=== klasor listesi (yetki kontrolu) ==="
curl -s -m 30 -H "Authorization: $KEY" -H "wix-site-id: $SITE" \
  "https://www.wixapis.com/site-media/v1/folders" | head -c 400
echo
