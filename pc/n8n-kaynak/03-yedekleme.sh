#!/usr/bin/env bash
# =============================================================
# L'CARLIE - Yedekleme sistemi kurulumu
# Gece 03:30 (Europe/Istanbul) sifreli yedek + 7 gun saklama
# + Google Drive / harici depolama aktarimina hazir (rclone)
# + e-posta bildirimi (msmtp)
# =============================================================
set -euo pipefail

BASE="/opt/lcarlie"
STACK="$BASE/n8n"
BK="$BASE/backup"

log() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

mkdir -p "$BK/archive" "$BK/log"
chmod 700 "$BK/archive"

# ---------------------------------------------------------------
log "1) Gerekli araclar (rclone + msmtp)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq rclone msmtp msmtp-mta ca-certificates cron >/dev/null
systemctl enable --now cron >/dev/null 2>&1 || true
echo "rclone : $(rclone version 2>/dev/null | head -n1)"
echo "msmtp  : $(msmtp --version 2>/dev/null | head -n1)"

# ---------------------------------------------------------------
log "2) Yapilandirma dosyasi"
if [ ! -f "$BK/backup.conf" ]; then
cat > "$BK/backup.conf" <<'CONF'
# --- L'CARLIE yedekleme ayarlari ---

# Kac gunluk yedek sunucuda tutulsun
RETENTION_DAYS=7

# Harici depolama (Google Drive vb.). Bos birakilirsa aktarim yapilmaz.
# Ornek: RCLONE_REMOTE="gdrive:LCARLIE-Yedek"
# Kurmak icin:  rclone config   (rehber: /opt/lcarlie/backup/README-GDRIVE.txt)
RCLONE_REMOTE=""

# Harici depolamada kac gun tutulsun
REMOTE_RETENTION_DAYS=30

# Bildirim e-postasi. Bos birakilirsa e-posta gonderilmez.
NOTIFY_EMAIL=""

# Basarili yedeklerde de e-posta gelsin mi? (1=evet, 0=sadece hata)
NOTIFY_ON_SUCCESS=1
CONF
  chmod 600 "$BK/backup.conf"
  echo "$BK/backup.conf olusturuldu."
else
  echo "Mevcut backup.conf korundu."
fi

# ---------------------------------------------------------------
log "3) Yedekleme betigi"
cat > "$BK/backup.sh" <<'SH'
#!/usr/bin/env bash
# L'CARLIE gece yedeklemesi. Ciktilar SIFRELIDIR (AES-256).
set -uo pipefail

BASE="/opt/lcarlie"
STACK="$BASE/n8n"
BK="$BASE/backup"
TS="$(date +%Y-%m-%d_%H%M)"
LOG="$BK/log/backup-$(date +%Y-%m).log"
STATUS="BASARILI"
DETAY=""

mkdir -p "$BK/log" "$BK/archive"
exec 3>&1
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG" >&3; }
fail() { STATUS="BASARISIZ"; DETAY="${DETAY}
- $*"; say "HATA: $*"; }

say "===== Yedekleme basladi ($TS) ====="

# ayarlar + gizli anahtarlar
# shellcheck disable=SC1090
. "$BK/backup.conf"
set -a; . "$STACK/.env"; set +a

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 1) PostgreSQL ---
if docker exec lcarlie-postgres pg_dump -U n8n -d n8n -Fc -f /tmp/n8n.dump 2>>"$LOG" \
   && docker cp lcarlie-postgres:/tmp/n8n.dump "$WORK/n8n-db.dump" 2>>"$LOG"; then
  docker exec lcarlie-postgres rm -f /tmp/n8n.dump 2>/dev/null
  say "PostgreSQL dump alindi ($(du -h "$WORK/n8n-db.dump" | cut -f1))"
else
  fail "PostgreSQL dump alinamadi"
fi

# --- 2) n8n workflow disa aktarimi (kimlik bilgileri DAHIL DEGIL) ---
if docker exec lcarlie-n8n n8n export:workflow --all --output=/tmp/workflows.json >>"$LOG" 2>&1 \
   && docker cp lcarlie-n8n:/tmp/workflows.json "$WORK/workflows.json" 2>>"$LOG"; then
  docker exec lcarlie-n8n rm -f /tmp/workflows.json 2>/dev/null
  say "Workflow'lar disa aktarildi"
else
  say "NOT: workflow disa aktarimi atlandi (henuz workflow yok olabilir)"
  echo '[]' > "$WORK/workflows.json"
fi

# --- 3) Yapilandirma (gizli .env HARIC) ---
cp "$STACK/docker-compose.yml" "$STACK/Caddyfile" "$WORK/" 2>/dev/null
echo "n8n_image=${N8N_IMAGE_TAG:-latest}" > "$WORK/SURUM.txt"

# --- 4) Paketle ve SIFRELE ---
OUT="$BK/archive/lcarlie-n8n-$TS.tgz.enc"
if tar -czf "$WORK/bundle.tgz" -C "$WORK" n8n-db.dump workflows.json docker-compose.yml Caddyfile SURUM.txt 2>>"$LOG" \
   && openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
        -in "$WORK/bundle.tgz" -out "$OUT" -pass "env:BACKUP_ENC_KEY" 2>>"$LOG"; then
  chmod 600 "$OUT"
  say "Sifreli yedek olusturuldu: $(basename "$OUT") ($(du -h "$OUT" | cut -f1))"
else
  fail "Sifreleme/paketleme basarisiz"
fi

# --- 5) Harici depolamaya aktar ---
if [ -n "${RCLONE_REMOTE:-}" ]; then
  if rclone copy "$OUT" "$RCLONE_REMOTE/" --config /root/.config/rclone/rclone.conf >>"$LOG" 2>&1; then
    say "Harici depolamaya aktarildi: $RCLONE_REMOTE"
    rclone delete "$RCLONE_REMOTE/" --min-age "${REMOTE_RETENTION_DAYS:-30}d" \
      --config /root/.config/rclone/rclone.conf >>"$LOG" 2>&1 || true
  else
    fail "Harici depolamaya aktarim basarisiz ($RCLONE_REMOTE)"
  fi
else
  say "NOT: RCLONE_REMOTE bos - yedek sunucuda kaldi. Harici hedef tanimlanmali."
fi

# --- 6) Eski yedekleri temizle ---
find "$BK/archive" -name 'lcarlie-n8n-*.tgz.enc' -mtime "+${RETENTION_DAYS:-7}" -delete 2>>"$LOG"
ADET=$(find "$BK/archive" -name 'lcarlie-n8n-*.tgz.enc' | wc -l)
say "Sunucuda tutulan yedek adedi: $ADET (son ${RETENTION_DAYS:-7} gun)"

# --- 7) E-posta bildirimi ---
if [ -n "${NOTIFY_EMAIL:-}" ] && [ -f /root/.msmtprc ]; then
  if [ "$STATUS" = "BASARISIZ" ] || [ "${NOTIFY_ON_SUCCESS:-1}" = "1" ]; then
    {
      echo "Subject: [L'CARLIE n8n] Yedekleme $STATUS - $TS"
      echo "To: $NOTIFY_EMAIL"
      echo "Content-Type: text/plain; charset=UTF-8"
      echo
      echo "Durum   : $STATUS"
      echo "Tarih   : $TS"
      echo "Dosya   : $(basename "$OUT")"
      echo "Boyut   : $(du -h "$OUT" 2>/dev/null | cut -f1)"
      echo "Sunucuda: $ADET yedek"
      echo "Harici  : ${RCLONE_REMOTE:-tanimli degil}"
      [ -n "$DETAY" ] && { echo; echo "Sorunlar:$DETAY"; }
      echo
      echo "Log: $LOG"
    } | msmtp --read-envelope-from "$NOTIFY_EMAIL" >>"$LOG" 2>&1 \
      && say "Bildirim e-postasi gonderildi" || say "NOT: e-posta gonderilemedi"
  fi
else
  say "NOT: e-posta bildirimi yapilandirilmadi (NOTIFY_EMAIL / /root/.msmtprc)"
fi

say "===== Yedekleme bitti: $STATUS ====="
[ "$STATUS" = "BASARILI" ] || exit 1
exit 0
SH
chmod 700 "$BK/backup.sh"
echo "$BK/backup.sh yazildi."

# ---------------------------------------------------------------
log "4) Geri yukleme betigi"
cat > "$BK/geri-yukle.sh" <<'SH'
#!/usr/bin/env bash
# L'CARLIE - yedekten geri yukleme.
# KULLANIM: ./geri-yukle.sh /opt/lcarlie/backup/archive/lcarlie-n8n-XXXX.tgz.enc
# DIKKAT: mevcut n8n veritabaninin UZERINE yazar.
set -euo pipefail
ARSIV="${1:?Yedek dosyasi belirtin}"
STACK="/opt/lcarlie/n8n"
set -a; . "$STACK/.env"; set +a

echo "!!! Bu islem mevcut n8n veritabanini SILIP yedekten geri yukleyecek."
read -r -p "Devam etmek icin 'EVET' yazin: " ONAY
[ "$ONAY" = "EVET" ] || { echo "Iptal edildi."; exit 1; }

W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$ARSIV" -out "$W/b.tgz" -pass "env:BACKUP_ENC_KEY"
tar -xzf "$W/b.tgz" -C "$W"

docker stop lcarlie-n8n
docker cp "$W/n8n-db.dump" lcarlie-postgres:/tmp/restore.dump
docker exec lcarlie-postgres psql -U n8n -d postgres -c "DROP DATABASE IF EXISTS n8n;"
docker exec lcarlie-postgres psql -U n8n -d postgres -c "CREATE DATABASE n8n OWNER n8n;"
docker exec lcarlie-postgres pg_restore -U n8n -d n8n /tmp/restore.dump
docker exec lcarlie-postgres rm -f /tmp/restore.dump
docker start lcarlie-n8n
echo "Geri yukleme tamamlandi. NOT: N8N_ENCRYPTION_KEY ayni olmali, yoksa kimlik bilgileri acilmaz."
SH
chmod 700 "$BK/geri-yukle.sh"

# ---------------------------------------------------------------
log "5) Google Drive rehberi"
cat > "$BK/README-GDRIVE.txt" <<'TXT'
GOOGLE DRIVE'A YEDEK AKTARIMI (ucretsiz, rclone ile)
====================================================
Sunucuda SSH ile su komutu calistirin:

    rclone config

Adimlar:
  n  -> New remote
  name>  gdrive
  Storage>  drive          (listede "Google Drive")
  client_id>     (bos birakin, Enter)
  client_secret> (bos birakin, Enter)
  scope>  1                (Full access)
  root_folder_id> (bos birakin, Enter)
  service_account_file> (bos, Enter)
  Edit advanced config?  n
  Use web browser to automatically authenticate?  n   <-- SUNUCUDA "n" SECIN
      -> Ekranda bir komut cikar. O komutu KENDI BILGISAYARINIZDA calistirin
         (once bilgisayariniza rclone kurun: https://rclone.org/downloads/)
      -> Tarayici acilir, Google hesabinizla izin verin
      -> Cikan uzun kodu sunucudaki ekrana yapistirin
  Configure this as a Shared Drive? n
  y -> onayla,  q -> cikis

Sonra Drive'da bir klasor olusturun (orn. "LCARLIE-Yedek") ve su dosyayi duzenleyin:

    nano /opt/lcarlie/backup/backup.conf
    RCLONE_REMOTE="gdrive:LCARLIE-Yedek"

Test:
    /opt/lcarlie/backup/backup.sh

ONEMLI: Yedekler AES-256 ile sifrelidir. Sifre cozme anahtari
/opt/lcarlie/n8n/.env icindeki BACKUP_ENC_KEY degeridir.
BU ANAHTARI VE N8N_ENCRYPTION_KEY DEGERINI SUNUCU DISINDA da saklayin
(sifre yoneticisi), yoksa sunucu kaybinda yedekler acilamaz.
TXT

# ---------------------------------------------------------------
log "6) E-posta (msmtp) sablonu"
if [ ! -f /root/.msmtprc ]; then
cat > /root/.msmtprc <<'TXT'
# L'CARLIE yedekleme bildirimi - SMTP ayarlari
# Gmail icin: hesabinizda 2 adimli dogrulama acik olmali ve
# "Uygulama sifresi" (App password) uretmelisiniz.
# Doldurduktan sonra: chmod 600 /root/.msmtprc
defaults
auth           on
tls            on
tls_trust_file /etc/ssl/certs/ca-certificates.crt
logfile        /opt/lcarlie/backup/log/msmtp.log

account        lcarlie
host           smtp.gmail.com
port           587
from           BURAYA_GONDEREN_EPOSTA
user           BURAYA_GONDEREN_EPOSTA
password       BURAYA_UYGULAMA_SIFRESI

account default : lcarlie
TXT
  chmod 600 /root/.msmtprc
  echo "/root/.msmtprc sablonu olusturuldu (doldurulmayi bekliyor)."
else
  echo "Mevcut /root/.msmtprc korundu."
fi

# ---------------------------------------------------------------
log "7) Zamanlama (her gece 03:30)"
cat > /etc/cron.d/lcarlie-backup <<'CRON'
# L'CARLIE n8n gece yedeklemesi
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
CRON_TZ=Europe/Istanbul
30 3 * * * root /opt/lcarlie/backup/backup.sh >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/lcarlie-backup
systemctl restart cron
echo "Cron kaydi: her gece 03:30 (Europe/Istanbul)"

log "YEDEKLEME SISTEMI KURULDU"
ls -la "$BK"
