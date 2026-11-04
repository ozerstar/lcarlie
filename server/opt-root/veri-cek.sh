#!/usr/bin/env bash
set -Eeuo pipefail
ENV=/opt/lcarlie/n8n/.env
SAYFA=1222783064240254
PC=/tmp/vc.cfg
trap 'shred -u "$PC" 2>/dev/null || rm -f "$PC"' EXIT

p () { { printf 'header = "Authorization: Bearer '
         sed -n 's/^FB_PAGE_TOKEN=//p' "$ENV" | tr -d '\r\n'
         printf '"\n'; printf 'url = "https://graph.facebook.com/v23.0/%s"\n' "$1"
         printf 'silent\nshow-error\n'; } > "$PC"; chmod 600 "$PC"
       curl --config "$PC" --max-time 90; }

echo "=== KONUSMALAR + KATILIMCILAR (kanal tespiti icin) ==="
p "$SAYFA/conversations?fields=id,updated_time,message_count,participants&limit=25" > /tmp/conv.json
jq -c '{adet:(.data|length), hata:.error.message}' /tmp/conv.json
echo "--- ornek 2 kayit ---"
jq -c '.data[:2]' /tmp/conv.json

echo
echo "=== BIR KONUSMANIN MESAJLARI ==="
CID=$(jq -r '.data[0].id' /tmp/conv.json)
echo "konusma: $CID"
p "$CID/messages?fields=id,created_time,from,to,message&limit=10" > /tmp/msg.json
jq -c '{adet:(.data|length), hata:.error.message}' /tmp/msg.json
jq -c '.data[:4][] | {zaman:.created_time, kim:.from.name, metin:(.message|tostring|.[0:90])}' /tmp/msg.json 2>/dev/null

echo
echo "=== INSTAGRAM: alternatif denemeler ==="
for q in "$SAYFA/conversations?platform=instagram&limit=2" \
         "$SAYFA/conversations?platform=IG&limit=2" \
         "17841403255774414/conversations?limit=2"; do
  echo "-- $q"
  p "$q" | jq -c '{adet:(.data|length?), hata:.error.message}' 2>/dev/null || echo "  (ayristirilamadi)"
done
