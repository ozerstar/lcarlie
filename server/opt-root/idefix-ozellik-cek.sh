#!/usr/bin/env bash
# idefix-ozellik-cek.sh — Secilen kategorilerin ZORUNLU ozelliklerini cikarir.
# SALT OKUNUR. Doldurulamayan zorunlu ozellik varsa o kategori YUKLENEMEZ.
# Kullanim: sudo /opt/lcarlie/idefix-ozellik-cek.sh
set -u
. /etc/lcarlie/idefix.env
TOK=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)
CSV=/opt/lcarlie/idefix-hazirlik/urunler.csv
CIKTI=/opt/lcarlie/idefix-hazirlik/KATEGORI-OZELLIK.md

baslik=$(head -1 "$CSV" | tr ';' '\n' | grep -n "^kategori_id$" | cut -d: -f1)
badi=$(head -1 "$CSV" | tr ';' '\n' | grep -n "^kategori_secimi$" | cut -d: -f1)
[ -n "$baslik" ] || { echo "kategori_id sutunu yok"; exit 2; }

{
  echo "# Idefix kategori zorunlu ozellikleri"
  echo
  echo "Kaynak: \`GET /pim/category-attribute/{categoryId}\` — $(date +%d.%m.%Y\ %H:%M)"
  echo
  echo "| Kategori | ID | Urun | Zorunlu ozellik | Varyant/slicer | Ozellik sayisi |"
  echo "|---|---|---|---|---|---|"
} > "$CIKTI"

tail -n +2 "$CSV" | awk -F';' -v a="$baslik" -v b="$badi" '{print $a"\t"$b}' \
  | sort | uniq -c | sort -rn | while read -r adet kid yol; do
  y=$(curl -s -m 30 -H "X-API-KEY: $TOK" -H 'Accept: application/json' \
      "https://merchantapi.idefix.com/pim/category-attribute/$kid")
  # Ozellikler .categoryAttributes[] altinda; etiket attributeTitle,
  # zorunluluk required. Onceki surum .. ile tum nesneleri tariyordu ve
  # attributeValues'lari da sayiyordu -- "1410 ozellik" o yuzden cikti.
  toplam=$(printf '%s' "$y" | jq '(.categoryAttributes // []) | length' 2>/dev/null)
  zorunlu=$(printf '%s' "$y" | jq -r '
      [(.categoryAttributes // [])[] | select(.required == true) | .attributeTitle]
      | join(", ")' 2>/dev/null)
  varyant=$(printf '%s' "$y" | jq -r '
      [(.categoryAttributes // [])[] | select(.isVariant == true or .isSlicer == true)
       | .attributeTitle] | join(", ")' 2>/dev/null)
  kisa=$(printf '%s' "$yol" | sed 's/.* > \([^>]*> [^>]*\)$/\1/')
  printf '| %s | `%s` | %s | %s | %s | %s |\n' "$kisa" "$kid" "$adet" \
    "${zorunlu:-yok}" "${varyant:-yok}" "${toplam:-?}" >> "$CIKTI"
done

echo "yazildi: $CIKTI"
grep -c '^|' "$CIKTI"
