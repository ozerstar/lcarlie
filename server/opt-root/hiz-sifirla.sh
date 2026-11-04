#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - HIZ SINIRI SAYACLARINI SIFIRLA
#
# Ne zaman gerekir?
#   Gercek bir musteri sinira takilirsa. En olasi sebep ORTAK IP:
#   bir ofis, otel, universite veya mobil operator NAT'i arkasindaki
#   onlarca kisi tek IP olarak gorunur ve 10 dakikada 60 mesaji birlikte
#   doldurabilir. O zaman hepsine "cok sayida mesaj aldik" doner.
#
#   Musteri "yazamiyorum / cevap vermiyor" diyorsa once BUNU kontrol edin.
#
# Kullanim:
#   hiz-sifirla.sh            -> durumu goster (hicbir sey degistirmez)
#   hiz-sifirla.sh --sifirla  -> sayaclari temizle
#
# 🔴 Sadece hiz sayaclarini temizler.
#    Eskalasyonlar, konusma kayitlari ve istatistikler KORUNUR.
# =============================================================================
set -uo pipefail
# 🔴 DOCKER_API_VERSION SABITLENMEZ (20.09.2026'da kaldirildi).
# Buraya 'export DOCKER_API_VERSION=1.43' yaziliydi. Docker yukseltilince
# daemon minimum API 1.44 istemeye basladi ve HER docker cagrisi
# "client version 1.43 is too old" ile patladi. Cagrilar 2>/dev/null ile
# susturuldugu icin hata gorunmedi: on kontrol "konteyner calismiyor" dedi,
# oysa konteyner ayaktaydi. Istemci surumu kendi pazarlar; SABITLEME.

KAP=lcarlie-n8n
DB=lcarlie-postgres
WF=lcarlieSohbet01

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }

Q() { docker exec "$DB" psql -U n8n -d n8n -tAc "$1" 2>/dev/null; }

durum() {
  Q "SELECT
       (SELECT count(*) FROM jsonb_object_keys(COALESCE((((\"staticData\"::jsonb)->'global')->'ipHiz'),'{}'::jsonb)))
       || ' IP kovasi / ' ||
       (SELECT count(*) FROM jsonb_object_keys(COALESCE((((\"staticData\"::jsonb)->'global')->'hiz'),'{}'::jsonb)))
       || ' kisi kovasi / ' ||
       COALESCE(jsonb_array_length(((\"staticData\"::jsonb)->'global')->'toplam'),0)::text
       || ' saatlik mesaj / ' ||
       COALESCE(jsonb_array_length(((\"staticData\"::jsonb)->'global')->'eskalasyonlar'),0)::text
       || ' eskalasyon'
     FROM workflow_entity WHERE id='$WF';"
}

echo "Su anki durum:"
echo "  $(durum)"

if [ "${1:-}" != "--sifirla" ]; then
  echo ""
  echo "Sifirlamak icin: $0 --sifirla"
  exit 0
fi

# 🔴 n8n statik veriyi BELLEKTE tutar ve calisma bitince veritabanina
#    geri yazar. Calisirken degistirilirse degisiklik EZILIR.
#    Bu yuzden once durdur, sonra degistir, sonra baslat.
echo ""
sari "n8n durduruluyor (sohbet birkac saniye cevap vermez)..."
docker stop "$KAP" >/dev/null

# staticData kolonu 'json' tipinde - jsonb sonucunu ::text::json ile geri ver
# 🔴 'psql -c UPDATE' HICBIR SATIR ESLESMESE DE 0 DONER.
# Onceki hali buna bakip "sayaclar temizlendi" diye YESIL yaziyordu.
# Workflow id degisirse (yeni ID ile ice aktarim, eski bir dokumden geri
# yukleme) hicbir sey guncellenmez ama operator sorunun cozuldugunu sanir -
# musteri hala sinira takili kalir. Ayrica hata dali yalnizca kirmizi yazi
# basiyordu, cikis kodunu etkilemiyordu.
# Cozum: RETURNING ile GERCEKTEN kac satir degistigini say.
BASARISIZ=0
ETKILENEN=$(docker exec "$DB" psql -U n8n -d n8n -tAc \
"WITH g AS (
   UPDATE workflow_entity
      SET \"staticData\" = jsonb_set(
            jsonb_set(
              jsonb_set(\"staticData\"::jsonb, '{global,ipHiz}', '{}'::jsonb, true),
              '{global,hiz}', '{}'::jsonb, true),
            '{global,toplam}', '[]'::jsonb, true)::text::json
    WHERE id='$WF'
    RETURNING 1)
 SELECT count(*) FROM g;" 2>/dev/null | tr -d ' ')

if [ "${ETKILENEN:-0}" = "1" ]; then
  yesil "  sayaclar temizlendi"
else
  kirmizi "  HATA: '$WF' guncellenmedi (eslesen satir: ${ETKILENEN:-?})"
  kirmizi "  Workflow ID degismis olabilir - kontrol edin."
  BASARISIZ=1
fi

docker start "$KAP" >/dev/null
echo "  n8n baslatildi, hazir olmasi bekleniyor..."
HAZIR=0
for _ in $(seq 1 45); do
  sleep 2
  if [ "$(curl -s -o /dev/null -w '%{http_code}' https://n8n.lcarlie.shop/ 2>/dev/null)" = "200" ]; then
    HAZIR=1; break
  fi
done
[ "$HAZIR" -eq 1 ] || sari "  UYARI: n8n 90 sn icinde yanit vermedi"

echo ""
echo "Yeni durum:"
echo "  $(durum)"

echo ""
echo "Canli kontrol:"
if curl -s --max-time 30 --connect-timeout 5 -X POST https://n8n.lcarlie.shop/webhook/sohbet \
     -H "Content-Type: application/json" \
     -d '{"mesaj":"lipvora fiyat","musteriId":"hiz-sifirla-kontrol"}' 2>/dev/null | grep -q 'LIPVORA'; then
  yesil "  OK - sohbet normal cevap veriyor"
else
  kirmizi "  SORUN - sohbet cevap vermiyor"
  BASARISIZ=1
fi

# 🔴 Cikis kodu SADECE duman testine bakmamali.
# Guncelleme hic satir etkilemese bile sohbet calisiyorsa 0 doner ve
# cagiran "sifirlama basarili" sanirdi.
echo ""
[ "$BASARISIZ" -eq 0 ] || exit 1
exit 0
