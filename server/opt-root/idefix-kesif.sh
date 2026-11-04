#!/usr/bin/env bash
# idefix-kesif.sh — Idefix tarafindaki ZORUNLU kimlikleri cikarir.
# SALT OKUNUR: yalniz GET. Hicbir sey olusturmaz, hicbir sey yazmaz.
#
# Urun olusturma zorunlu alanlari (developer.idefix.com/api/urun-entegrasyonu/
# urun-olusturma): barcode, title, productMainId, brandId, categoryId,
# inventoryQuantity, vendorStockCode, description, price, vatRate,
# images.url, attributes.attributeId
# Bu betik bunlardan Idefix'e ait olanlari (brandId, categoryId, kargo,
# adres) bulur; kalanlar bizim verimizden gelir.
set -u
. /etc/lcarlie/idefix.env
TOK=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)
V="$IDEFIX_SELLER_ID"
T=https://merchantapi.idefix.com
g() { curl -s -m 30 -w '\n__KOD:%{http_code}' -H "X-API-KEY: $TOK" \
         -H 'Accept: application/json' "$1"; }

bolum() { echo; echo "=== $1 ==="; }

bolum "KARGO FIRMALARI  /pim/cargo-company"
r=$(g "$T/pim/cargo-company"); kod=${r##*__KOD:}; govde=${r%$'\n'__KOD:*}
echo "HTTP $kod"
[ "$kod" = 200 ] && printf '%s' "$govde" | jq -c 'if type=="array" then .[] else . end' 2>/dev/null | head -20

bolum "SATICI KARGO PROFILI  /pim/cargo-company/$V/profile/list"
r=$(g "$T/pim/cargo-company/$V/profile/list"); kod=${r##*__KOD:}; govde=${r%$'\n'__KOD:*}
echo "HTTP $kod"; printf '%s' "$govde" | head -c 600; echo

bolum "GONDERIM/IADE ADRESLERI  /pim/vendor/$V/address"
r=$(g "$T/pim/vendor/$V/address"); kod=${r##*__KOD:}; govde=${r%$'\n'__KOD:*}
echo "HTTP $kod"; printf '%s' "$govde" | head -c 800; echo

bolum "MARKA ARAMA (aday uclar)"
for u in "pim/brand?name=LCARLIE" "pim/brand/list?name=LCARLIE" "pim/brands?name=LCARLIE" \
         "pim/brand?page=1&limit=5" "pim/brand/search?name=LCARLIE"; do
  r=$(g "$T/$u"); kod=${r##*__KOD:}; govde=${r%$'\n'__KOD:*}
  echo "[$u] HTTP $kod :: $(printf '%s' "$govde" | head -c 180)"
done

bolum "KATEGORI AGACINDA KOZMETIK/KISISEL BAKIM"
r=$(g "$T/pim/product-category"); govde=${r%$'\n'__KOD:*}
printf '%s' "$govde" > /tmp/idefix-kat.json
jq -r '
  def yuru(yol): .[]? | . as $d
    | (yol + [$d.name]) as $y
    | (if ($d.subs | length) == 0 then ($d.id|tostring) + "  " + ($y|join(" > "))
       else empty end),
      ($d.subs | yuru($y));
  yuru([])
' /tmp/idefix-kat.json 2>/dev/null \
  | grep -iE "kozmetik|kisisel|kişisel|bakim|bakım|saglik|sağlık|bebek|krem" | head -40
echo "--- toplam yaprak kategori: $(jq -r '
  def say: .[]? | . as $d | (if ($d.subs|length)==0 then 1 else empty end), ($d.subs|say);
  [say] | length' /tmp/idefix-kat.json 2>/dev/null) ---"
rm -f /tmp/idefix-kat.json
