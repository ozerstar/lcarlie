#!/usr/bin/env bash
# idefix-kesif2.sh — marka kimligi + kozmetik kategori yapraklari. SALT OKUNUR.
set -u
. /etc/lcarlie/idefix.env
TOK=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)
T=https://merchantapi.idefix.com
g() { curl -s -m 30 -H "X-API-KEY: $TOK" -H 'Accept: application/json' "$1"; }

echo "=== MARKA UCU: sure parametreleri ==="
for p in "name=LCARLIE" "title=LCARLIE" "q=LCARLIE" "search=LCARLIE" "keyword=LCARLIE"; do
  n=$(g "$T/pim/brand?$p" | jq 'if type=="array" then length else 0 end' 2>/dev/null)
  ilk=$(g "$T/pim/brand?$p" | jq -r 'if type=="array" then (.[0].title // "-") else "-" end' 2>/dev/null)
  echo "  ?$p -> $n kayit, ilk: $ilk"
done

echo
echo "=== MARKA: LCARLIE / CARLIE gecen var mi (ilk 10 sayfa taranir) ==="
: > /tmp/markalar.jsonl
for s in 1 2 3 4 5 6 7 8 9 10; do
  r=$(g "$T/pim/brand?page=$s&limit=200")
  n=$(printf '%s' "$r" | jq 'if type=="array" then length else 0 end' 2>/dev/null)
  [ "${n:-0}" -eq 0 ] && break
  printf '%s' "$r" | jq -c '.[] | {id, title}' >> /tmp/markalar.jsonl
done
echo "  taranan marka: $(wc -l < /tmp/markalar.jsonl)"
grep -iE "carlie|lcarl|l.carli" /tmp/markalar.jsonl || echo "  LCARLIE BULUNAMADI"
echo "  ornek ilk 5:"; head -5 /tmp/markalar.jsonl | sed 's/^/    /'
rm -f /tmp/markalar.jsonl

echo
echo "=== KOZMETIK / KISISEL BAKIM UST KATEGORILERI ==="
g "$T/pim/product-category" > /tmp/kat.json
jq -r '.[] | "\(.id)  \(.name)"' /tmp/kat.json

echo
echo "=== Kozmetik agacindaki KREM/GUNES/BAKIM yapraklari ==="
jq -r '
  def yuru(yol): .[]? | . as $d
    | (yol + [$d.name]) as $y
    | (if ($d.subs|length)==0 then ($d.id|tostring)+"  "+($y|join(" > ")) else empty end),
      ($d.subs | yuru($y));
  yuru([])
' /tmp/kat.json > /tmp/yaprak.txt
echo "  toplam yaprak: $(wc -l < /tmp/yaprak.txt)"
grep -iE "kozmetik|kişisel bakım" /tmp/yaprak.txt \
  | grep -iE "krem|güneş|losyon|roll|sprey|jel|bakım|temizle|vücut|el ve|ayak" | head -45
rm -f /tmp/kat.json /tmp/yaprak.txt
