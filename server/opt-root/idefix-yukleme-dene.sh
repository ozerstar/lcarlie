#!/usr/bin/env bash
# idefix-yukleme-dene.sh — Marka ONAYI GELMEDEN urun yuklenebiliyor mu?
#
# NE YAPAR
# Tek urunluk (BRIGHT SMILE) bir havuz gonderimi dener. `brandId` ZORUNLU bir
# alan ve L'CARLIE markasi Idefix listesinde henuz YOK; bu yuzden gonderim
# gecersiz bir marka kimligiyle yapilir. Beklenen sonuc DOGRULAMA HATASI.
#
# NEDEN BOYLE
# Idefix'te urun bilgisi API ile GUNCELLENEMIYOR. Gecerli bir gonderim kazayla
# basarili olursa duzeltilemeyen bir baslik/aciklama canliya girerdi. Gecersiz
# marka kimligi, denemenin canli liste URETEMEMESINI garanti eder.
#
# Gonderimden SONRA havuz listesi okunur: gercekten bir kayit dustu mu?
set -u
. /etc/lcarlie/idefix.env
TOK=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)
V="$IDEFIX_SELLER_ID"
T=https://merchantapi.idefix.com
BARKOD=8684869609394

echo "=== ONCE: havuzda bu barkod var mi? ==="
curl -s -m 30 -H "X-API-KEY: $TOK" "$T/pim/pool/$V/list?page=1&limit=10&barcode=$BARKOD" \
  | jq -c '{urun: ((.products // []) | length)}'

cat > /tmp/idefix-deneme.json <<JSON
{
  "products": [
    {
      "barcode": "$BARKOD",
      "title": "L'CARLIE BRIGHT SMILE Dis Macunu 50 ml",
      "productMainId": "$BARKOD",
      "brandId": 0,
      "categoryId": 440253038,
      "inventoryQuantity": 10,
      "vendorStockCode": "$BARKOD",
      "description": "Bitkisel icerikli dis macunu. 50 ml.",
      "price": 950,
      "vatRate": 20,
      "deliveryDuration": 3,
      "deliveryType": "regular",
      "cargoCompanyId": 84,
      "shipmentAddressId": 65271,
      "returnAddressId": 65270,
      "images": [{"url": "https://n8n.lcarlie.shop/urun-gorsel/$BARKOD-01.jpg"}],
      "attributes": []
    }
  ]
}
JSON

echo
echo "=== GONDERIM: POST /pim/pool/$V/create (brandId=0, gecersiz) ==="
kod=$(curl -s -o /tmp/idefix-yanit.json -w '%{http_code}' -m 60 -X POST \
      -H "X-API-KEY: $TOK" -H 'Content-Type: application/json' \
      -d @/tmp/idefix-deneme.json "$T/pim/pool/$V/create")
echo "HTTP $kod"
jq . /tmp/idefix-yanit.json 2>/dev/null || head -c 600 /tmp/idefix-yanit.json
echo

PARTI=$(jq -r '.batchRequestId // empty' /tmp/idefix-yanit.json 2>/dev/null)
echo "batchRequestId: ${PARTI:-YOK}"

if [ -n "${PARTI:-}" ]; then
  for bekle in 5 15 30; do
    sleep "$bekle"
    echo "--- batch-result (${bekle}s sonra) ---"
    curl -s -m 30 -H "X-API-KEY: $TOK" -H 'Accept: application/json'       "$T/pim/pool/$V/batch-result/$PARTI" | head -c 700
    echo
  done
fi

echo
echo "=== SONRA: havuza kayit dustu mu? ==="
sleep 5
curl -s -m 30 -H "X-API-KEY: $TOK" "$T/pim/pool/$V/list?page=1&limit=10&barcode=$BARKOD" \
  | jq -c '{urun: ((.products // []) | length),
            kayitlar: [(.products // [])[] | {barcode, title, status, failureReasons}]}'

echo
echo "=== Toplam havuz sayisi (butun urunler) ==="
curl -s -m 30 -H "X-API-KEY: $TOK" "$T/pim/pool/$V/list?page=1&limit=100" \
  | jq -c '{toplam: ((.products // []) | length)}'
rm -f /tmp/idefix-deneme.json /tmp/idefix-yanit.json
