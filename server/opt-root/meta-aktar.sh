#!/usr/bin/env bash
# Meta Sayfa gelen kutusundaki konusmalari cekip lcarlie.konusma/mesaj tablolarina yukler.
# Kullanim: meta-aktar.sh [sayfa_sayisi]   (varsayilan 3 = son ~75 konusma; "tam" = 60 sayfa)
# Konusmalar updated_time'a gore yeni->eski siralidir, bu yuzden ilk sayfalar taze olanlardir.
# Tekrar calistirmak GUVENLIDIR (upsert). Jeton ekrana basilmaz.
set -Eeuo pipefail

ENV=/opt/lcarlie/n8n/.env
SAYFA=1222783064240254
PC=/tmp/ma.cfg
OUT=/tmp/meta-konusmalar.jsonl
LOG=/opt/lcarlie/meta-aktar.log
trap 'shred -u "$PC" 2>/dev/null || rm -f "$PC"' EXIT

ARG="${1:-3}"
[ "$ARG" = "tam" ] && MAX=60 || MAX="$ARG"

kayit () { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

p () { { printf 'header = "Authorization: Bearer '
         sed -n 's/^FB_PAGE_TOKEN=//p' "$ENV" | tr -d '\r\n'
         printf '"\n'; printf 'url = "%s"\n' "$1"
         printf 'silent\nshow-error\n'; } > "$PC"; chmod 600 "$PC"
       curl --config "$PC" --max-time 120; }

# --- Sayfa jetonu gecerli mi? Degilse sistem jetonundan tazele ---
if ! p "https://graph.facebook.com/v23.0/me?fields=id" | jq -e '.id' >/dev/null 2>&1; then
  kayit "Sayfa jetonu gecersiz, tazeleniyor..."
  if bash /opt/lcarlie/sayfa-jetonu.sh >/dev/null 2>&1; then
    kayit "Sayfa jetonu tazelendi."
  else
    kayit "HATA: Sayfa jetonu tazelenemedi - sistem jetonu da gecersiz olabilir. DURDU."
    exit 1
  fi
fi

> "$OUT"
URL="https://graph.facebook.com/v23.0/$SAYFA/conversations?fields=id,updated_time,message_count,participants&limit=25"
SN=0; TK=0; TM=0

while [ -n "$URL" ] && [ "$SN" -lt "$MAX" ]; do
  SN=$((SN+1))
  p "$URL" > /tmp/ma_conv.json
  HATA=$(jq -r '.error.message // empty' /tmp/ma_conv.json)
  [ -n "$HATA" ] && { kayit "HATA (sayfa $SN): $HATA"; exit 1; }
  N=$(jq '.data|length' /tmp/ma_conv.json)
  [ "$N" = "0" ] && break

  for i in $(seq 0 $((N-1))); do
    CID=$(jq -r ".data[$i].id" /tmp/ma_conv.json)
    MAD=$(jq -r --arg s "$SAYFA" ".data[$i].participants.data[] | select(.id != \$s) | .name" /tmp/ma_conv.json | head -1)
    MID=$(jq -r --arg s "$SAYFA" ".data[$i].participants.data[] | select(.id != \$s) | .id" /tmp/ma_conv.json | head -1)
    [ -z "$MID" ] && continue
    p "https://graph.facebook.com/v23.0/$CID/messages?fields=id,created_time,from,message&limit=50" > /tmp/ma_msg.json
    TM=$((TM + $(jq '.data|length // 0' /tmp/ma_msg.json)))
    jq -c --arg cid "$CID" --arg ad "$MAD" --arg mid "$MID" --arg s "$SAYFA" '
      {kanal:"messenger", harici_id:$cid, musteri_ref:$mid, musteri_ad:$ad,
       notlar:{kaynak:"graph-api", sayfa:$s},
       mesajlar: [ .data[] | {
         harici_id: .id, zaman: .created_time,
         yon: (if (.from.id == $s) then "giden" else "gelen" end),
         gonderen: (if (.from.id == $s) then "insan" else "musteri" end),
         metin: (.message // ""), ek: {gonderen_ad: (.from.name // "")} } ] }' /tmp/ma_msg.json >> "$OUT"
    TK=$((TK+1))
  done
  URL=$(jq -r '.paging.next // empty' /tmp/ma_conv.json)
done

kayit "Cekildi: $TK konusma / $TM mesaj ($SN sayfa)"
ONCE=$(docker exec lcarlie-postgres psql -U n8n -d n8n -tAc "SELECT (SELECT count(*) FROM lcarlie.konusma)||'/'||(SELECT count(*) FROM lcarlie.mesaj)")
/opt/lcarlie/konusma-yukle.sh "$OUT" >/dev/null
SONRA=$(docker exec lcarlie-postgres psql -U n8n -d n8n -tAc "SELECT (SELECT count(*) FROM lcarlie.konusma)||'/'||(SELECT count(*) FROM lcarlie.mesaj)")
kayit "Veritabani konusma/mesaj: $ONCE -> $SONRA"
rm -f "$OUT"
