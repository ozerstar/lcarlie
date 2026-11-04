#!/usr/bin/env bash
# idefix-sinama.sh — idefix-cek.sh'in jq birlestirmesini ve iki SQL dosyasini
# UYDURMA veriyle sinar. Idefix'e cagri YOK, anahtar GEREKMEZ.
# Yazma sinamasinda idefix-yaz.sql'in kendi COMMIT'i ROLLBACK'e cevrilir --
# "BEGIN; \i dosya; ROLLBACK;" kuru calistirma DEGILDIR (bilinen tuzak).
set -uo pipefail
D=$(mktemp -d /tmp/idefix-sinama.XXXXXX)
trap 'rm -rf "$D"' EXIT

# 1 nolu urun: Wix'te GERCEKTEN var olan barkod (eslesme yolu sinanir)
# 2 nolu urun: Wix'te olmayan barkod (eslesmeyen yolu sinanir)
cat > "$D/havuz.jsonl" <<'JSON'
{"barcode":"8684869609394","title":"BRIGHT SMILE Test","vendorStockCode":"BS-01","reference":111,"status":"APPROVED","price":100,"inventoryQuantity":5,"images":[{"url":"x"}]}
{"barcode":"9999999999999","title":"Baska Marka Urun","vendorStockCode":"ZZ-01","reference":222,"status":"WAITING","price":50,"inventoryQuantity":0}
JSON
cat > "$D/envanter.jsonl" <<'JSON'
{"barcode":"8684869609394","stockCode":"BS-01","price":249.9,"comparePrice":299.9,"inventoryQuantity":7}
JSON

jq -s -c '
  (.[0] | map(select(.barcode != null)) | INDEX(.barcode)) as $env
  | .[1] | map(select(.barcode != null)
      | . as $p
      | (($env[$p.barcode]) // {}) as $e
      | {barcode: $p.barcode,
         stockCode: ($p.vendorStockCode // $e.stockCode),
         reference: $p.reference,
         title: $p.title,
         status: $p.status,
         price: ($e.price // $p.price),
         comparePrice: ($e.comparePrice // $p.comparePrice),
         inventoryQuantity: ($e.inventoryQuantity // $p.inventoryQuantity),
         ham: ($p + {_envanter: $e})})
' <(jq -s '.' "$D/envanter.jsonl") <(jq -s '.' "$D/havuz.jsonl") > "$D/birlesik.json"

echo "=== 1) jq birlestirme ==="
jq -c '.[] | {barcode, price, inventoryQuantity, stockCode}' "$D/birlesik.json"
# Envanter fiyati havuz fiyatini EZMELI: 100 degil 249.9 beklenir
BEKLENEN=$(jq -r '.[] | select(.barcode=="8684869609394") | .price' "$D/birlesik.json")
[ "$BEKLENEN" = "249.9" ] && echo "   OK envanter fiyati otorite (249.9)" \
                          || { echo "   BASARISIZ: fiyat $BEKLENEN"; exit 1; }
STOK=$(jq -r '.[] | select(.barcode=="8684869609394") | .inventoryQuantity' "$D/birlesik.json")
[ "$STOK" = "7" ] && echo "   OK envanter stogu otorite (7)" \
                  || { echo "   BASARISIZ: stok $STOK"; exit 1; }

VERI=$(jq -c '.' "$D/birlesik.json")
psqlc() { docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -v veri="$VERI" -f -; }

echo
echo "=== 2) idefix-kuru.sql (salt okunur) ==="
psqlc < /opt/lcarlie/idefix-kuru.sql | head -40

echo
echo "=== 3) idefix-yaz.sql (COMMIT -> ROLLBACK cevrilmis) ==="
sed 's/^COMMIT;$/ROLLBACK;/' /opt/lcarlie/idefix-yaz.sql > "$D/yaz-kuru.sql"
grep -c '^ROLLBACK;$' "$D/yaz-kuru.sql" | xargs -I{} echo "   ROLLBACK sayisi: {}"
psqlc < "$D/yaz-kuru.sql" | tail -12

echo
echo "=== 4) Geri alindi mi? (ayna bos olmali) ==="
docker exec -i lcarlie-postgres psql -U n8n -d n8n -At -c \
  "select 'raw.idefix_urun='||count(*) from raw.idefix_urun;
   select 'idefix_fiyat_gozlem='||count(*) from core.urun_platform_fiyat where platform_kod='idefix';"
