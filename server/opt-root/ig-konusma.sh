#!/usr/bin/env bash
# Sayfa jetonuyla Instagram konusmalarini ceker. Jeton ekrana basilmaz.
set -Eeuo pipefail
ENV=/opt/lcarlie/n8n/.env
SAYFA=1222783064240254
PC=/tmp/pc.cfg
trap 'shred -u "$PC" 2>/dev/null || rm -f "$PC"' EXIT

p () {
  { printf 'header = "Authorization: Bearer '
    sed -n 's/^FB_PAGE_TOKEN=//p' "$ENV" | tr -d '\r\n'
    printf '"\n'
    printf 'url = "https://graph.facebook.com/v23.0/%s"\n' "$1"
    printf 'silent\nshow-error\n'; } > "$PC"
  chmod 600 "$PC"
  curl --config "$PC" --max-time 60
}

for L in 3 5 10; do
  echo "=== limit=$L, yalniz id ==="
  p "$SAYFA/conversations?platform=instagram&fields=id&limit=$L" > /tmp/c.json
  jq -c '{adet:(.data|length), hata:.error.message, sonrakiVar:(.paging.next!=null)}' /tmp/c.json 2>/dev/null || head -c 250 /tmp/c.json
  echo
done

echo "=== limit=5, id+updated_time ==="
p "$SAYFA/conversations?platform=instagram&fields=id,updated_time&limit=5" > /tmp/c2.json
jq -c '{adet:(.data|length), hata:.error.message}' /tmp/c2.json 2>/dev/null || head -c 250 /tmp/c2.json
echo
echo "--- ilk konusma ornegi ---"
jq -c '.data[0] // "yok"' /tmp/c2.json 2>/dev/null
