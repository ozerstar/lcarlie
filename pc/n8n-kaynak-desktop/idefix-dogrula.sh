#!/usr/bin/env bash
# idefix-dogrula.sh — Idefix Satici API kimligini SALT OKUNUR uclarla sinar.
# Anahtar hicbir zaman stdout'a yazilmaz; yalniz HTTP kodu ve kisa govde dondurulur.
# Kullanim: sudo /opt/lcarlie/idefix-dogrula.sh
set -u
ENVF=/etc/lcarlie/idefix.env
[ -r "$ENVF" ] || { echo "DURUM=OKUNAMADI dosya=$ENVF (root gerekir)"; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENVF"; set +a

: "${IDEFIX_SELLER_ID:=}"
: "${IDEFIX_API_KEY:=}"
IDEFIX_API_SECRET="${IDEFIX_API_SECRET:-}"

echo "seller_id_dolu=$([ -n "$IDEFIX_SELLER_ID" ] && echo EVET || echo HAYIR)"
echo "api_key_dolu=$([ -n "$IDEFIX_API_KEY" ] && echo EVET || echo HAYIR)"
echo "api_secret_dolu=$([ -n "$IDEFIX_API_SECRET" ] && echo EVET || echo HAYIR)"

dene() { # $1=etiket $2=token_ham $3=url
  local tok code govde
  tok=$(printf '%s' "$2" | base64 -w0)
  code=$(curl -s -o /tmp/idefix-dogrula.$$ -w '%{http_code}' -m 25 \
         -H "X-API-KEY: $tok" -H 'Accept: application/json' "$3")
  govde=$(head -c 220 /tmp/idefix-dogrula.$$ | tr -d '\n')
  rm -f /tmp/idefix-dogrula.$$
  echo "[$1] HTTP $code :: $govde"
}

URL_KAT='https://merchantapi.idefix.com/pim/product-category'
echo "--- kategori ucu (salt okunur) ---"
if [ -n "$IDEFIX_API_SECRET" ]; then
  dene "key:secret" "$IDEFIX_API_KEY:$IDEFIX_API_SECRET" "$URL_KAT"
else
  echo "UYARI: secret yok -> dokumantasyona gore base64(ApiKey:ApiSecret) kurulamaz."
  dene "yalniz-key" "$IDEFIX_API_KEY" "$URL_KAT"
  dene "key-ve-bos" "$IDEFIX_API_KEY:" "$URL_KAT"
fi
