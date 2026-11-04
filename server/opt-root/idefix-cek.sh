#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - IDEFIX URUN/FIYAT/STOK CEKIMI  (DISARI SALT OKUNUR)
#
# Amac: Idefix Satici API'sinden kendi urunlerimizin baslik/fiyat/stok
#       bilgisini cekip raw.idefix_urun aynasina ve (barkodla eslesenler icin)
#       core.urun_platform_fiyat gozlemine yazmak. Trendyol ile ayni desen.
#
# BU BETIK IDEFIX'E HICBIR SEY YAZMAZ. Yalniz GET cagrilari yapar.
#    Platform satirinda yazma_izni=false; disari yazma ayri bir karardir.
#
# KOMISYON: Idefix yanitlarinda komisyon alani YOK. Bu betik
#    core.urun_platform_komisyon'a DOKUNMAZ. Uyduruk oran girilmez.
#
# Anahtarlar bu dosyada DEGIL: /etc/lcarlie/idefix.env (600, root)
#   IDEFIX_SELLER_ID=  IDEFIX_API_KEY=  IDEFIX_API_SECRET=
# Kimlik: X-API-KEY: base64(ApiKey:ApiSecret)   (developer.idefix.com)
#
# Kullanim:
#   sudo /opt/lcarlie/idefix-cek.sh          # KURU CALISTIRMA (varsayilan)
#   sudo /opt/lcarlie/idefix-cek.sh --yaz    # veritabanina yazar
# =============================================================================
set -uo pipefail

ENVF=/etc/lcarlie/idefix.env
SQL_DIZIN=$(cd "$(dirname "$0")" && pwd)
TABAN=https://merchantapi.idefix.com
IS_DIZIN=$(mktemp -d /tmp/idefix-cek.XXXXXX)
YAZ=0
[ "${1:-}" = "--yaz" ] && YAZ=1
trap 'rm -rf "$IS_DIZIN"' EXIT

hata() { echo "HATA: $1" >&2; exit 1; }

[ -r "$ENVF" ] || hata "$ENVF okunamadi (root gerekir)"
set -a; . "$ENVF"; set +a
: "${IDEFIX_SELLER_ID:?IDEFIX_SELLER_ID yok}"
: "${IDEFIX_API_KEY:?IDEFIX_API_KEY yok}"
[ -n "${IDEFIX_API_SECRET:-}" ] || hata "IDEFIX_API_SECRET yok -- kimlik base64(ApiKey:ApiSecret) ister, secret olmadan kurulamaz"

TOKEN=$(printf '%s:%s' "$IDEFIX_API_KEY" "$IDEFIX_API_SECRET" | base64 -w0)
VID="$IDEFIX_SELLER_ID"

# ---- GET: 429'da Retry-After kadar bekler, en fazla 3 deneme ---------------
cek() { # $1=url $2=cikti_dosya
  local url="$1" out="$2" deneme kod bekle
  for deneme in 1 2 3; do
    kod=$(curl -s -o "$out" -D "$out.h" -w '%{http_code}' -m 60 \
          -H "X-API-KEY: $TOKEN" -H 'Accept: application/json' "$url")
    case "$kod" in
      200) return 0 ;;
      429) bekle=$(sed -n 's/^[Rr]etry-[Aa]fter: *\([0-9]*\).*/\1/p' "$out.h" | head -n1)
           bekle=${bekle:-10}
           echo "  429 -- ${bekle}s bekleniyor (deneme $deneme/3)" >&2
           sleep "$bekle" ;;
      401) hata "401 $(head -c 120 "$out") -- idefix.env icindeki anahtar/secret yanlis" ;;
      *)   echo "  HTTP $kod (deneme $deneme/3): $(head -c 160 "$out")" >&2
           sleep 3 ;;
    esac
  done
  hata "$url cekilemedi"
}

# ---- 1) Urun havuzu: baslik, stok kodu, referans, durum -------------------
echo "1) urun havuzu cekiliyor..."
: > "$IS_DIZIN/havuz.jsonl"
# Sayfalar 1 TABANLI: envanter ucune page=0 gonderildiginde yanit
# currentPage=1 dondu, yani 0 sessizce 1'e cevriliyor.
sayfa=1
while : ; do
  cek "$TABAN/pim/pool/$VID/list?page=$sayfa&limit=100" "$IS_DIZIN/s.json"
  adet=$(jq '[.products // .content // .items // []] | flatten | length' "$IS_DIZIN/s.json")
  [ "$adet" -eq 0 ] && break
  jq -c '[.products // .content // .items // []] | flatten | .[]' "$IS_DIZIN/s.json" >> "$IS_DIZIN/havuz.jsonl"
  echo "   sayfa $sayfa: $adet urun"
  [ "$adet" -lt 100 ] && break
  sayfa=$((sayfa+1))
  [ "$sayfa" -gt 50 ] && break
done
HAVUZ=$(wc -l < "$IS_DIZIN/havuz.jsonl")

# ---- 2) Stok ve fiyat guncel durum (fiyat/stok otoritesi burasi) ----------
echo "2) stok ve fiyat cekiliyor..."
# Bu uc SAYFALI: varsayilan limit=10, yanitta totalCount/pageCount/currentPage
# doner. Tek cagriyla yetinmek urunlerin ilk 10'u disini SESSIZCE dusururdu.
: > "$IS_DIZIN/envanter.jsonl"
esayfa=1
while : ; do
  cek "$TABAN/pim/catalog/$VID/inventory/list?page=$esayfa&limit=100" "$IS_DIZIN/e.json"
  eadet=$(jq '[.items // .content // .products // []] | flatten | length' "$IS_DIZIN/e.json")
  [ "$esayfa" = "1" ] && echo "   envanter totalCount=$(jq -r '.totalCount // "?"' "$IS_DIZIN/e.json")"
  [ "$eadet" -eq 0 ] && break
  jq -c '[.items // .content // .products // []] | flatten | .[]' "$IS_DIZIN/e.json" \
    >> "$IS_DIZIN/envanter.jsonl"
  echo "   envanter sayfa $esayfa: $eadet satir"
  [ "$eadet" -lt 100 ] && break
  esayfa=$((esayfa+1))
  [ "$esayfa" -gt 50 ] && break
done
ENV_ADET=$(wc -l < "$IS_DIZIN/envanter.jsonl")

# ---- 3) Barkodla birlestir: havuz = icerik, envanter = fiyat/stok ---------
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
' <(jq -s '.' "$IS_DIZIN/envanter.jsonl") <(jq -s '.' "$IS_DIZIN/havuz.jsonl") \
  > "$IS_DIZIN/birlesik.json"

BIRLESIK=$(jq 'length' "$IS_DIZIN/birlesik.json")
echo "   havuz=$HAVUZ  envanter=$ENV_ADET  birlesik=$BIRLESIK"
if [ "$BIRLESIK" -eq 0 ]; then
  # Bos katalog HATA DEGILDIR: Idefix hesabinda hic urun listelenmemis
  # olabilir. Yoklugun sebebini bilmeden "hata" diye raporlama.
  echo
  echo "SONUC: Idefix'te barkodlu urun YOK (havuz=$HAVUZ, envanter=$ENV_ADET)."
  echo "       Cagrilar 200 dondu -- bu bir baglanti sorunu DEGIL, hesapta"
  echo "       listelenmis urun bulunmamasi. Veritabanina hicbir sey yazilmadi."
  exit 0
fi

VERI=$(jq -c '.' "$IS_DIZIN/birlesik.json")

psqlc() { docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1 -v veri="$VERI" -f -; }

# ---- 4) Kuru calistirma: karsilastir, HICBIR SEY yazma --------------------
if [ "$YAZ" -eq 0 ]; then
  echo
  echo "=== KURU CALISTIRMA (yazma yok) ==="
  psqlc < "$SQL_DIZIN/idefix-kuru.sql"
  echo
  echo "Yazmak icin: sudo /opt/lcarlie/idefix-cek.sh --yaz"
  exit 0
fi

# ---- 5) Yazma: ayna upsert + fiyat gozlemi versiyonlama ------------------
echo
echo "=== YAZMA ==="
psqlc < "$SQL_DIZIN/idefix-yaz.sql"
