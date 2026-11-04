#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - n8n GERI DONUS
#
# n8n-yayinla.sh her yayinlamadan ONCE mevcut workflow'lari
# /opt/lcarlie/geri-donus/ altina disa aktarir. Bu betik onlari geri yukler.
#
# Kullanim:
#   n8n-geri-don.sh              -> son yayinlama oncesine don
#   n8n-geri-don.sh --liste      -> geri donus noktalarini goster
#   n8n-geri-don.sh --nesil AD   -> belirli bir nesle don (--liste'den ad alin)
#   n8n-geri-don.sh --onayla     -> onay sormadan calis (pty yoksa)
#
# 🔴 CIKIS KODLARI onemli: yayinla.ps1 bu kodu okuyor.
#    0 = geri yukleme yapildi ve dogrulandi
#    1 = hata / dosya yok / onay alinamadi / iptal
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
GERI_DONUS=/opt/lcarlie/geri-donus

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }

LISTE=0; ONAYLA=0; NESIL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --liste)   LISTE=1 ;;
    --onayla)  ONAYLA=1 ;;
    --nesil)   shift; NESIL="${1:-}" ;;
    *)         kirmizi "Bilinmeyen secenek: $1"; exit 1 ;;
  esac
  shift
done

if [ ! -d "$GERI_DONUS" ] || [ -z "$(ls -A "$GERI_DONUS"/*.json 2>/dev/null)" ]; then
  kirmizi "Geri donus dosyasi yok ($GERI_DONUS)."
  kirmizi "n8n-yayinla.sh en az bir kez calismis olmali."
  exit 1
fi

echo "Guncel geri donus noktasi:"
for f in "$GERI_DONUS"/*.json; do
  echo "  $(basename "$f")   $(date -r "$f" '+%d.%m.%Y %H:%M')"
done

# n8n-yayinla.sh her yayinlamada zaman damgali bir nesil birakir (son 5)
ESKI_NESILLER=$(ls -1dt "$GERI_DONUS"/2* 2>/dev/null || true)
if [ -n "$ESKI_NESILLER" ]; then
  echo ""
  echo "Onceki nesiller (--nesil AD ile secilebilir):"
  echo "$ESKI_NESILLER" | while read -r d; do
    echo "  $(basename "$d")   ($(ls -1 "$d"/*.json 2>/dev/null | wc -l) workflow)"
  done
fi

[ "$LISTE" -eq 1 ] && exit 0

# Kaynak klasoru sec
KAYNAK="$GERI_DONUS"
if [ -n "$NESIL" ]; then
  KAYNAK="$GERI_DONUS/$NESIL"
  if [ ! -d "$KAYNAK" ] || [ -z "$(ls -A "$KAYNAK"/*.json 2>/dev/null)" ]; then
    kirmizi "Nesil bulunamadi veya bos: $NESIL"
    exit 1
  fi
  sari "Secilen nesil: $NESIL"
fi

echo ""
sari "Bu islem workflow'lari yayinlama ONCESI haline dondurur."

# 🔴 ONAY: pty yoksa read bos okur.
# Eski hali bu durumda "Iptal edildi" deyip EXIT 0 ile cikiyordu; yani
# `.\yayinla.ps1 -GeriDon` HICBIR SEY YAPMADAN "tamamlandi" goruntusu
# veriyordu - canli sistem bozukken. Artik onay alinamazsa cikis kodu 1.
if [ "$ONAYLA" -eq 1 ]; then
  echo "Onay --onayla bayragi ile verildi."
elif [ -t 0 ]; then
  read -r -p "Devam edilsin mi? (EVET yazin): " ONAY
  if [ "$ONAY" != "EVET" ]; then
    kirmizi "Iptal edildi. Geri yukleme YAPILMADI."
    exit 1
  fi
else
  kirmizi "Onay istenemedi: terminal (pty) yok."
  kirmizi "Cozum: 'ssh -t lcarlie /opt/lcarlie/n8n-geri-don.sh'"
  kirmizi "   veya onaylayarak: '... n8n-geri-don.sh --onayla'"
  exit 1
fi

echo ""
HATA_SAYISI=0
# 🔴 KAPSAYICIYA 'onceki-<ID>.json' ADIYLA KOPYALAMAYIN.
#
# 'docker cp' dosyayi ROOT sahipli olusturur. n8n ise kapsayici icinde
# uid 1000 (node) ile calisir ve /tmp sticky bit'li oldugu icin bu
# dosyalari ne silebilir ne uzerine yazabilir.
#
# Tam da bu adlari n8n-yayinla.sh export hedefi olarak kullaniyor.
# Sonuc: BIR KEZ geri donus yapildiginda, sonraki TUM yayinlamalarda
#        'EACCES: permission denied' ile yedek alinamaz hale geliyordu.
#        Yani geri donus, geri donus mekanizmasini bozuyordu.
#        (14.09.2026'da canli sistemde tespit edildi.)
#
# Cozum: ayri bir ad kullan ve isi bitince ROOT olarak temizle.
for f in "$KAYNAK"/*.json; do
  AD=$(basename "$f")
  ID=$(echo "$AD" | sed 's/^onceki-//; s/\.json$//')
  HEDEF="/tmp/geriyukle-$ID.json"
  docker cp "$f" "$KAP:$HEDEF" >/dev/null
  if docker exec "$KAP" n8n import:workflow --input="$HEDEF" >/dev/null 2>&1; then
    docker exec "$KAP" n8n update:workflow --id="$ID" --active=true >/dev/null 2>&1
    yesil "  geri yuklendi  $ID"
  else
    kirmizi "  HATA          $ID"
    HATA_SAYISI=$((HATA_SAYISI + 1))
  fi
  # root sahipli dosyayi yine root olarak sil - node kullanicisi silemez
  docker exec -u 0 "$KAP" rm -f "$HEDEF" >/dev/null 2>&1
done

echo ""
echo "n8n yeniden baslatiliyor..."
docker restart "$KAP" >/dev/null
# Sabit sleep yerine hazir olana kadar bekle (en fazla 90 sn)
HAZIR=0
for _ in $(seq 1 45); do
  sleep 2
  if [ "$(curl -s -o /dev/null -w '%{http_code}' https://n8n.lcarlie.shop/ 2>/dev/null)" = "200" ]; then
    HAZIR=1; break
  fi
done
[ "$HAZIR" -eq 1 ] || sari "  UYARI: n8n 90 sn icinde yanit vermedi"

echo ""
echo "Yayin durumu:"
docker exec "$DB" psql -U n8n -d n8n -tAc \
  "SELECT '  ' || name || '  ->  ' || CASE WHEN active THEN 'AKTIF' ELSE 'KAPALI' END
     FROM workflow_entity ORDER BY name;"
curl -s -o /dev/null -w "  panel HTTP %{http_code}\n" https://n8n.lcarlie.shop/

# Yayinda olmasi gereken ama kapali kalan var mi?
KAPALI=$(docker exec "$DB" psql -U n8n -d n8n -tAc \
  "SELECT count(*) FROM workflow_entity WHERE active = false;" 2>/dev/null | tr -d ' ')

echo ""
if [ "$HATA_SAYISI" -gt 0 ]; then
  kirmizi "GERI DONUS EKSIK: $HATA_SAYISI workflow geri yuklenemedi."
  exit 1
fi
if [ "${KAPALI:-0}" != "0" ]; then
  kirmizi "GERI DONUS EKSIK: $KAPALI workflow KAPALI kaldi."
  exit 1
fi
yesil "Geri donus tamamlandi."
exit 0
