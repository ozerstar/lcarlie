#!/usr/bin/env bash
# Instagram Graph API sorgulayici. Jetonu .env'den okur, ASLA ekrana basmaz.
# Kullanim: ig-sorgu.sh "<yol ve sorgu>"
set -Eeuo pipefail
ENV=/opt/lcarlie/n8n/.env
CFG=$(mktemp /tmp/igcfg.XXXXXX); chmod 600 "$CFG"
trap 'shred -u "$CFG" 2>/dev/null || rm -f "$CFG"' EXIT

YOL="${1:?yol verilmedi}"
{
  printf 'header = "Authorization: Bearer '
  sed -n 's/^IG_ACCESS_TOKEN=//p' "$ENV" | tr -d '\r\n'
  printf '"\n'
  printf 'url = "https://graph.instagram.com/v23.0/%s"\n' "$YOL"
  printf 'silent\n'
  printf 'show-error\n'
} > "$CFG"
curl --config "$CFG" --max-time 45
