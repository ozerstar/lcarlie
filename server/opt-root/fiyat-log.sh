#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - GUNLUK FIYAT GECMISI LOGU
#
# Amac: 10 gunluk referans fiyat kuralinin ispat kulfetini karsilamak
#       (Fiyat Etiketi Yonetmeligi m.11/1). Indirim yapildiginda "onceki 10
#       gunun en dusuk fiyati" gosterilmeli; bu dosya o ispatin kaydidir.
#
# Wix Stores V1 /stores/v1/products/query ile urunlerin price/discountedPrice
# alanlarini tarihli olarak JSONL dosyasina ekler. Cron: her gun 09:00.
#
# 🔴 ANAHTAR BU DOSYADA DEGIL, /opt/lcarlie/n8n/.env ICINDE.
#    Onceki surumde WIX_API_KEY dogrudan betigin govdesine yazilmisti;
#    o yuzden dosya surumlenemiyor, kaynak klasorde tutulamiyordu.
#    .env satiri:  WIX_API_KEY=...
# =============================================================================
set -uo pipefail

ENV_DOSYA=/opt/lcarlie/n8n/.env
LOG_DIR=/opt/lcarlie/fiyat-log
TARIH=$(date +%Y-%m-%d)
TS=$(date -Iseconds)
OUT_FILE="${LOG_DIR}/fiyatlar-${TARIH}.json"
JSONL_FILE="${LOG_DIR}/fiyat-gecmisi.jsonl"
HATA_LOG="${LOG_DIR}/hata.log"
CALISMA_LOG="${LOG_DIR}/calisma.log"

mkdir -p "$LOG_DIR"

hata() {
  echo "$(date -Iseconds) HATA: $1" >> "$HATA_LOG"
  echo "$(date -Iseconds) HATA: $1" >> "$CALISMA_LOG"
  exit 1
}

WIX_API_KEY=$(sed -n 's/^WIX_API_KEY=//p' "$ENV_DOSYA" 2>/dev/null | head -n1)
WIX_SITE_ID=$(sed -n 's/^WIX_SITE_ID=//p' "$ENV_DOSYA" 2>/dev/null | head -n1)
[ -n "$WIX_API_KEY" ] || hata "WIX_API_KEY .env icinde yok"
[ -n "$WIX_SITE_ID" ] || hata "WIX_SITE_ID .env icinde yok"

# 🔴 03.11.2026: site Wix Catalog V3'e gecti; V1 ucu 29.10'dan beri 501
#    ("not supported for sites using Catalog V3") donuyordu ve fiyat gecmisi
#    6 gun yazilmadi. V3'te fiyat urunde degil fiyat ARALIGINDA durur.
BODY='{"query":{"cursorPaging":{"limit":100}}}'

# 🔴 HTTP DURUM KODU KONTROL EDILIR.
#
# Onceki surum yalnizca govdeyi aliyordu. Anahtarin suresi dolsa (401),
# yetki kaldirilsa (403) ya da kota assa (429), '.products[]?' hicbir sey
# uretmiyor - JSONL dosyasina SATIR EKLENMIYOR - ama betik yine de
# "OK: ? urun loglandi" yaziyordu. Yani fiyat gecmisi sessizce durur,
# calisma logu aylarca "OK" der ve indirim yapildiginda ispat kaydi
# BULUNMAZ. Tam da bu kaydin var olma sebebi o an ortadan kalkar.
#
# --max-time de sart: onceki surumde yoktu, asili bir baglanti cron isini
# suresiz tutabilirdi.
# 🔴 API ANAHTARI KOMUT SATIRINA YAZILMAZ (16.09.2026 denetimi).
#    Komut satiri argumanlari /proc uzerinden sunucudaki HER surece gorunur;
#    'ps aux' yeter. Bu betik HER GUN 09:00'da calisiyor, yani Wix anahtari
#    gunde bir kez 'ps' penceresinde aciliyordu.
#    curl'un -K secenegi yapilandirmayi STDIN'den okur - orada gorunmez.
#    (Ayni desen raw-yukle.py ve meta-harcama-yukle.py'de de kullaniliyor.)
sayfa_al() {   # sayfa_al <govde> <cikti>
  HTTP=$(printf '%s\n' \
  '--silent' '--show-error' '--max-time 60' '--connect-timeout 10' \
  "output = \"$2\"" \
  'write-out = "%{http_code}"' \
  'request = POST' \
  'url = "https://www.wixapis.com/stores/v3/products/query"' \
  "header = \"Authorization: ${WIX_API_KEY}\"" \
  "header = \"wix-site-id: ${WIX_SITE_ID}\"" \
  'header = "Content-Type: application/json"' \
  "data = \"$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')\"" \
  | curl -K - 2>>"$HATA_LOG") || hata "curl basarisiz (ag veya zaman asimi)"
  [ "$HTTP" = "200" ] || hata "Wix API HTTP $HTTP dondu - fiyat gecmisi GUNCELLENMEDI"
}

# V3 sayfalama: sonraki sayfa query.cursorPaging.cursor ile istenir. Imlec query DISINA
# konursa Wix SESSIZCE ilk sayfayi tekrar dondurur (03.11: 20 x ayni 100 urun).
# 03.11'de urun sayisi 100'u gecti; tek sayfa okumak kalanini sessizce dusururdu.
SAYFA_DIZIN=$(mktemp -d)
trap 'rm -rf "$SAYFA_DIZIN"' EXIT
sayfa_al "$BODY" "$SAYFA_DIZIN/1.json"
n=1
while [ "$(jq -r '.pagingMetadata.hasNext // false' "$SAYFA_DIZIN/$n.json")" = "true" ] && [ "$n" -lt 20 ]; do
  CURSOR=$(jq -r '.pagingMetadata.cursors.next // empty' "$SAYFA_DIZIN/$n.json")
  [ -n "$CURSOR" ] || break
  n=$((n + 1))
  sayfa_al "{\"query\":{\"cursorPaging\":{\"limit\":100,\"cursor\":\"$CURSOR\"}}}" "$SAYFA_DIZIN/$n.json"
done
jq -s '{products: (map(.products // []) | add)}' "$SAYFA_DIZIN"/*.json > "$OUT_FILE" \
  || hata "sayfalar birlestirilemedi"


ADET=$(jq '.products | length' "$OUT_FILE" 2>/dev/null || echo 0)
if [ "${ADET:-0}" -lt 1 ]; then
  hata "Yanit 200 ama urun yok (adet=${ADET:-?}) - fiyat gecmisi GUNCELLENMEDI"
fi

# Kompakt satir: tarih + her urun icin id/name/price/discountedPrice
if ! jq -c --arg ts "$TS" '
  .products[] | {
    ts: $ts,
    id: .id,
    name: .name,
    # V1 sozlesmesi korunur: price = liste (ustu cizili) fiyat,
    # discountedPrice = satis fiyati. V3 indirim yoksa compareAt bos dondurur.
    price: ((.compareAtPriceRange.minValue.amount // .actualPriceRange.minValue.amount) | tonumber?),
    discountedPrice: (.actualPriceRange.minValue.amount | tonumber?),
    visible: .visible
  }
' "$OUT_FILE" >> "$JSONL_FILE" 2>>"$HATA_LOG"; then
  hata "JSONL yazimi basarisiz"
fi

echo "$(date -Iseconds) OK: $ADET urun loglandi." >> "$CALISMA_LOG"

# Ham gunluk yanitlari 40 gun tut (10 gunluk kural icin fazlasiyla yeterli)
find "$LOG_DIR" -name 'fiyatlar-*.json' -mtime +40 -delete 2>/dev/null || true
exit 0
