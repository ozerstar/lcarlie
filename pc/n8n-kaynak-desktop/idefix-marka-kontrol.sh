#!/usr/bin/env bash
# idefix-marka-kontrol.sh — L'CARLIE markasi Idefix marka listesine DUSTU MU?
# Marka ekleme talebi 22.10.2026 19:28'de yuklendi ve "Basarili Yuklemeler"
# dendi; ama KABUL EDILDI, ONAYLANDI DEMEK DEGIL. API marka listesinde
# gorunene kadar brandId yok, urun yuklenemez. Bu betik onu olcer.
# Kullanim: sudo /opt/lcarlie/idefix-marka-kontrol.sh
set -u
. /etc/lcarlie/idefix.env
TOK=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)

for q in "L%27CARLIE" "LCARLIE" "L%27CARLI%C3%89"; do
  y=$(curl -s -m 25 -H "X-API-KEY: $TOK" -H 'Accept: application/json' \
      "https://merchantapi.idefix.com/pim/brand?title=$q")
  n=$(printf '%s' "$y" | jq 'if type=="array" then length else 0 end' 2>/dev/null)
  if [ "${n:-0}" -gt 0 ]; then
    echo "MARKA ACILDI: $(printf '%s' "$y" | jq -c '.[0]|{id,title}')"
    echo "-> brandId artik var; urun yukleme Excel'i doldurulabilir."
    exit 0
  fi
  echo "  ?title=$q -> bos"
done
echo "MARKA HENUZ YOK -- talep Idefix tarafinda bekliyor."
echo "Panel: satici.idefix.com > Urunlerim > Yeni Urun Ekle > Marka Ekleme Talepleri"
exit 1
