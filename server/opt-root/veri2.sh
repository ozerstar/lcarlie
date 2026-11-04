#!/usr/bin/env bash
set -Eeuo pipefail
ENV=/opt/lcarlie/n8n/.env
SAYFA=1222783064240254
PC=/tmp/v2.cfg
trap 'shred -u "$PC" 2>/dev/null || rm -f "$PC"' EXIT
p () { { printf 'header = "Authorization: Bearer '
         sed -n 's/^FB_PAGE_TOKEN=//p' "$ENV" | tr -d '\r\n'
         printf '"\n'; printf 'url = "https://graph.facebook.com/v23.0/%s"\n' "$1"
         printf 'silent\nshow-error\n'; } > "$PC"; chmod 600 "$PC"
       curl --config "$PC" --max-time 120; }

echo "=== INSTAGRAM (BUYUK HARF, kucuk limit, tekrar denemeli) ==="
for i in 1 2 3; do
  p "$SAYFA/conversations?platform=INSTAGRAM&fields=id&limit=5" > /tmp/ig$i.json
  R=$(jq -c '{adet:(.data|length?), hata:.error.message}' /tmp/ig$i.json 2>/dev/null)
  echo "deneme $i -> $R"
  if jq -e '.data|length>0' /tmp/ig$i.json >/dev/null 2>&1; then
    echo "  BASARILI, ilk kayitlar:"; jq -c '.data[:3]' /tmp/ig$i.json; break
  fi
  sleep 4
done

echo
echo "=== MESSENGER: gercek musteri konusmasinin mesajlari ==="
p "$SAYFA/conversations?fields=id,message_count,participants&limit=25" > /tmp/c.json
CID=$(jq -r '[.data[] | select((.participants.data[0].name//"")|test("Meta Business Agent")|not) | select(.message_count>1)][0].id' /tmp/c.json)
AD=$(jq -r --arg c "$CID" '.data[] | select(.id==$c) | .participants.data[0].name' /tmp/c.json)
echo "konusma: $CID  ($AD)"
p "$CID/messages?fields=id,created_time,from,message&limit=15" > /tmp/m.json
jq -c '{adet:(.data|length), hata:.error.message}' /tmp/m.json
jq -r '.data[] | "  [\(.created_time|tostring)] \(.from.name//"?"): \((.message//"")|tostring|.[0:100])"' /tmp/m.json 2>/dev/null \
  || jq -c '.data[:6]' /tmp/m.json

echo
echo "=== KANAL DAGILIMI (25 konusma) ==="
jq -r '[.data[].participants.data[0].name] | group_by(.) | map({ad:.[0], n:length}) | .[] | "  \(.n)x \(.ad)"' /tmp/c.json | head -20
