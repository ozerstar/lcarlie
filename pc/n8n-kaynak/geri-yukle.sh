#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - YEDEKTEN GERI YUKLEME
#
# KULLANIM:
#   geri-yukle.sh <arsiv.tgz.enc>            -> onay sorarak geri yukle
#   geri-yukle.sh <arsiv.tgz.enc> --onayla   -> onay sormadan (pty yoksa)
#   geri-yukle.sh <arsiv.tgz.enc> --dogrula  -> SADECE arsivi dogrula, DOKUNMA
#   geri-yukle.sh --dokumden <dokum.dump>    -> guvenlik dokumune geri don
#
# 🔴 ONCEKI SURUMDEKI TEHLIKE (14.09.2026'da duzeltildi):
#    Betik once "DROP DATABASE n8n" calistirip SONRA pg_restore deniyordu.
#    Yani arsiv bozuksa, sifre yanlissa veya pg_restore yarida kalirsa
#    CANLI VERITABANI ZATEN SILINMIS oluyordu ve geri donecek hicbir sey
#    kalmiyordu. Ustelik silmeden once guvenlik dokumu de alinmiyordu.
#    Bir felaket kurtarma betiginin kendisi felaket sebebiydi.
#
#    Simdi sira: dogrula -> guvenlik dokumu al -> yukle -> dogrula
#                basarisizsa guvenlik dokumunden GERI DON.
# =============================================================================
set -uo pipefail
# 🔴 DOCKER_API_VERSION SABITLENMEZ (20.09.2026'da kaldirildi).
# Buraya 'export DOCKER_API_VERSION=1.43' yaziliydi. Docker yukseltilince
# daemon minimum API 1.44 istemeye basladi ve HER docker cagrisi
# "client version 1.43 is too old" ile patladi. Cagrilar 2>/dev/null ile
# susturuldugu icin hata gorunmedi: on kontrol "konteyner calismiyor" dedi,
# oysa konteyner ayaktaydi. Istemci surumu kendi pazarlar; SABITLEME.

ARSIV="${1:?Yedek dosyasi belirtin}"
STACK="/opt/lcarlie/n8n"
KAP=lcarlie-n8n
DB=lcarlie-postgres
DOKUM_DIZIN=/opt/lcarlie/backup/guvenlik-dokumu

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }
baslik()  { echo ""; echo "--- $1"; }

ONAYLA=0; SADECE_DOGRULA=0
for a in "${@:2}"; do
  [ "$a" = "--onayla" ]  && ONAYLA=1
  [ "$a" = "--dogrula" ] && SADECE_DOGRULA=1
done

set -a; . "$STACK/.env"; set +a

# --- Guvenlik dokumunden hizli geri donus -----------------------------------
# geri-yukle.sh --dokumden <dokum.dump>
# Bu betigin kendi aldigi guvenlik dokumune donmek icin; sifre cozme ve
# arsiv acma adimlari yok, dosya zaten duz pg_dump ciktisi.
if [ "$ARSIV" = "--dokumden" ]; then
  DOKUM_YOL="${2:?Dokum dosyasi belirtin}"
  [ -f "$DOKUM_YOL" ] || { kirmizi "Dokum bulunamadi: $DOKUM_YOL"; exit 1; }
  sari "Guvenlik dokumune donuluyor: $(basename "$DOKUM_YOL")"

  # 🔴 BU YOL DA DOGRULAMADAN SILIYORDU.
  # Tek kontrol dosyanin VAR olmasiydi ('-f'). Oysa burasi son care
  # kurtarma yolu: buraya ancak asil geri yukleme coktugunde gelinir.
  # Yarim kopyalanmis veya sifir baytlik bir dokumle calistirilirsa
  # veritabani silinir, restore basarisiz olur ve geriye HICBIR SEY kalmaz.
  # Dosyanin gercekten okunabilir bir dump oldugunu ONCE dogrula.
  docker cp "$DOKUM_YOL" "$DB:/tmp/dogrula-dokum.dump" >/dev/null 2>&1
  D_TABLO=$(docker exec "$DB" pg_restore --list /tmp/dogrula-dokum.dump 2>/dev/null | grep -c "TABLE DATA")
  docker exec -u 0 "$DB" rm -f /tmp/dogrula-dokum.dump >/dev/null 2>&1
  if [ "${D_TABLO:-0}" -lt 5 ]; then
    kirmizi "Dokum okunamadi veya icerigi yetersiz (TABLE DATA: ${D_TABLO:-0})."
    kirmizi "Veritabanina DOKUNULMADI."
    exit 1
  fi
  yesil "  ok  dokum gecerli - $D_TABLO tablo verisi"

  # 🔴 Durdurdugumuz kapsayiciyi ne olursa olsun geri baslat.
  # Tuzak olmadan Ctrl-C veya asili bir komut, n8n'i KAPALI ve
  # veritabanini SILINMIS halde birakiyordu.
  trap 'docker start "$KAP" >/dev/null 2>&1 || true' EXIT

  docker stop "$KAP" >/dev/null
  docker cp "$DOKUM_YOL" "$DB:/tmp/geri.dump" >/dev/null
  D_BASARISIZ=0
  docker exec "$DB" psql -U n8n -d postgres -c "DROP DATABASE IF EXISTS n8n;" >/dev/null 2>&1 || D_BASARISIZ=1
  docker exec "$DB" psql -U n8n -d postgres -c "CREATE DATABASE n8n OWNER n8n;" >/dev/null 2>&1 || D_BASARISIZ=1
  docker exec "$DB" pg_restore -U n8n -d n8n /tmp/geri.dump >/dev/null 2>&1 || true
  docker exec -u 0 "$DB" rm -f /tmp/geri.dump >/dev/null 2>&1
  docker start "$KAP" >/dev/null
  if [ "$D_BASARISIZ" -eq 1 ]; then
    kirmizi "Veritabani yeniden olusturulamadi."; exit 1
  fi
  for _ in $(seq 1 45); do
    sleep 2
    [ "$(curl -s -o /dev/null -w '%{http_code}' https://n8n.lcarlie.shop/ 2>/dev/null)" = "200" ] && break
  done
  SAYI=$(docker exec "$DB" psql -U n8n -d n8n -tAc "SELECT count(*) FROM workflow_entity;" 2>/dev/null | tr -d ' ')
  echo "  workflow: ${SAYI:-0}"
  [ "${SAYI:-0}" -gt 0 ] && { yesil "Donuldu."; exit 0; }
  kirmizi "Donus basarisiz."; exit 1
fi

[ -f "$ARSIV" ] || { kirmizi "Arsiv bulunamadi: $ARSIV"; exit 1; }

W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

# -----------------------------------------------------------------------------
baslik "1/6  ARSIVI COZ VE DOGRULA  (canli sisteme DOKUNULMUYOR)"

if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
       -in "$ARSIV" -out "$W/b.tgz" -pass "env:BACKUP_ENC_KEY" 2>"$W/hata.txt"; then
  kirmizi "  Sifre cozulemedi. BACKUP_ENC_KEY yanlis olabilir."
  sed 's/^/      /' "$W/hata.txt"
  exit 1
fi
echo "  ok  sifre cozuldu"

if ! tar -xzf "$W/b.tgz" -C "$W" 2>"$W/hata.txt"; then
  kirmizi "  Arsiv acilamadi (bozuk olabilir)."
  sed 's/^/      /' "$W/hata.txt"
  exit 1
fi
echo "  ok  arsiv acildi"

[ -f "$W/n8n-db.dump" ] || { kirmizi "  Arsivde n8n-db.dump yok."; exit 1; }

# 🔴 ASIL KONTROL: dump gercekten okunabiliyor mu?
# Bu adim olmadan bozuk bir dosya icin canli veritabani silinebiliyordu.
docker cp "$W/n8n-db.dump" "$DB:/tmp/dogrula.dump" >/dev/null 2>&1
TABLO=$(docker exec "$DB" pg_restore --list /tmp/dogrula.dump 2>/dev/null | grep -c "TABLE DATA")
docker exec -u 0 "$DB" rm -f /tmp/dogrula.dump >/dev/null 2>&1
if [ "${TABLO:-0}" -lt 5 ]; then
  kirmizi "  Dump okunamadi veya icerigi yetersiz (TABLE DATA: ${TABLO:-0})."
  kirmizi "  Canli veritabanina DOKUNULMADI."
  exit 1
fi
yesil "  ok  dump gecerli - $TABLO tablo verisi iceriyor"
echo "      arsiv: $(basename "$ARSIV")  ($(du -h "$ARSIV" | cut -f1))"

if [ "$SADECE_DOGRULA" -eq 1 ]; then
  echo ""
  yesil "  --dogrula: arsiv saglam. Hicbir degisiklik yapilmadi."
  exit 0
fi

# -----------------------------------------------------------------------------
baslik "2/6  ONAY"
MEVCUT=$(docker exec "$DB" psql -U n8n -d n8n -tAc \
  "SELECT count(*) FROM workflow_entity;" 2>/dev/null | tr -d ' ')
echo "  Su anki veritabaninda $MEVCUT workflow var."
sari "  Bu islem mevcut n8n veritabaninin UZERINE yazar."

if [ "$ONAYLA" -eq 1 ]; then
  echo "  Onay --onayla bayragi ile verildi."
elif [ -t 0 ]; then
  read -r -p "  Devam etmek icin 'EVET' yazin: " ONAY
  [ "$ONAY" = "EVET" ] || { kirmizi "  Iptal edildi. Hicbir degisiklik yapilmadi."; exit 1; }
else
  kirmizi "  Onay istenemedi: terminal (pty) yok."
  kirmizi "  Cozum: ssh -t ...  veya  geri-yukle.sh <arsiv> --onayla"
  exit 1
fi

# -----------------------------------------------------------------------------
baslik "3/6  GUVENLIK DOKUMU  (silmeden ONCE)"
# 🔴 Silmeden once mevcut hali diske al. Geri yukleme bozulursa donulecek yer.
# 🔴 Bu dokumler SIFRESIZ ve tum veritabanini iceriyor (musteri konusmalari,
#    kimlik bilgisi tablosu). Diger butun yedek dosyalari bilerek 0600/0700;
#    bunlar 0644 olarak birakiliyordu. /opt/lcarlie zaten 0700 oldugu icin
#    bugun disariya acik degil, ama tek savunma katmani kalmasin.
mkdir -p "$DOKUM_DIZIN"
chmod 700 "$DOKUM_DIZIN"
DOKUM="$DOKUM_DIZIN/oncesi-$(date +%Y%m%d-%H%M%S).dump"
if docker exec "$DB" pg_dump -U n8n -d n8n -Fc -f /tmp/guvenlik.dump >/dev/null 2>&1 \
   && docker cp "$DB:/tmp/guvenlik.dump" "$DOKUM" >/dev/null 2>&1; then
  docker exec -u 0 "$DB" rm -f /tmp/guvenlik.dump >/dev/null 2>&1
  chmod 600 "$DOKUM"
  yesil "  ok  guvenlik dokumu alindi: $(basename "$DOKUM")  ($(du -h "$DOKUM" | cut -f1))"
else
  kirmizi "  Guvenlik dokumu ALINAMADI. Geri yukleme durduruldu."
  kirmizi "  Dokum alinamadan veritabani silinmez."
  exit 1
fi
# Son 10 dokumu tut
ls -1t "$DOKUM_DIZIN"/oncesi-*.dump 2>/dev/null | tail -n +11 | xargs -r rm -f

# -----------------------------------------------------------------------------
baslik "4/6  GERI YUKLE"
docker stop "$KAP" >/dev/null
docker cp "$W/n8n-db.dump" "$DB:/tmp/restore.dump" >/dev/null

BASARISIZ=0
docker exec "$DB" psql -U n8n -d postgres -c "DROP DATABASE IF EXISTS n8n;" >/dev/null 2>&1 || BASARISIZ=1
docker exec "$DB" psql -U n8n -d postgres -c "CREATE DATABASE n8n OWNER n8n;" >/dev/null 2>&1 || BASARISIZ=1
if [ "$BASARISIZ" -eq 0 ]; then
  if ! docker exec "$DB" pg_restore -U n8n -d n8n /tmp/restore.dump >"$W/restore.log" 2>&1; then
    # pg_restore uyarilarla da 1 donebilir - gercekten veri geldi mi diye bak
    SAYI=$(docker exec "$DB" psql -U n8n -d n8n -tAc "SELECT count(*) FROM workflow_entity;" 2>/dev/null | tr -d ' ')
    if [ -z "$SAYI" ] || [ "$SAYI" = "0" ]; then BASARISIZ=1; fi
    sari "  pg_restore uyari verdi (son satirlar):"
    tail -5 "$W/restore.log" | sed 's/^/      /'
  fi
fi
docker exec -u 0 "$DB" rm -f /tmp/restore.dump >/dev/null 2>&1

# -----------------------------------------------------------------------------
if [ "$BASARISIZ" -eq 1 ]; then
  baslik "5/6  🔴 GERI YUKLEME BASARISIZ - GUVENLIK DOKUMUNE DONULUYOR"
  docker cp "$DOKUM" "$DB:/tmp/geri.dump" >/dev/null 2>&1
  docker exec "$DB" psql -U n8n -d postgres -c "DROP DATABASE IF EXISTS n8n;" >/dev/null 2>&1
  docker exec "$DB" psql -U n8n -d postgres -c "CREATE DATABASE n8n OWNER n8n;" >/dev/null 2>&1
  docker exec "$DB" pg_restore -U n8n -d n8n /tmp/geri.dump >/dev/null 2>&1
  docker exec -u 0 "$DB" rm -f /tmp/geri.dump >/dev/null 2>&1
  docker start "$KAP" >/dev/null
  sari "  Onceki hale donuldu. Dokum: $DOKUM"
  exit 1
fi

baslik "5/6  N8N BASLATILIYOR"
docker start "$KAP" >/dev/null
HAZIR=0
for _ in $(seq 1 45); do
  sleep 2
  if [ "$(curl -s -o /dev/null -w '%{http_code}' https://n8n.lcarlie.shop/ 2>/dev/null)" = "200" ]; then
    HAZIR=1; break
  fi
done
[ "$HAZIR" -eq 1 ] && echo "  ok  n8n yanit veriyor" || sari "  UYARI: n8n 90 sn icinde yanit vermedi"

# -----------------------------------------------------------------------------
baslik "6/6  DOGRULAMA"
YENI=$(docker exec "$DB" psql -U n8n -d n8n -tAc "SELECT count(*) FROM workflow_entity;" 2>/dev/null | tr -d ' ')
AKTIF=$(docker exec "$DB" psql -U n8n -d n8n -tAc "SELECT count(*) FROM workflow_entity WHERE active;" 2>/dev/null | tr -d ' ')
echo "  workflow: ${YENI:-0} (oncesinde $MEVCUT)   yayinda: ${AKTIF:-0}"

SORUN=0
[ "${YENI:-0}" -gt 0 ] || { kirmizi "  Workflow yok!"; SORUN=1; }
[ "$HAZIR" -eq 1 ]     || SORUN=1

echo ""
if [ "$SORUN" -eq 0 ]; then
  yesil "GERI YUKLEME BASARILI"
  echo "Guvenlik dokumu duruyor: $DOKUM"
  sari "NOT: N8N_ENCRYPTION_KEY ayni olmali, yoksa kimlik bilgileri acilmaz."
  exit 0
fi
kirmizi "GERI YUKLEME SUPHELI - kontrol edin."
sari "Onceki hale donmek icin:  $0 --dokumden $DOKUM"
exit 1
