#!/usr/bin/env bash
# =============================================================
# L'CARLIE - Ek guvenlik ve bakim araclari
# (ChatGPT denetiminden gelen 7, 8 ve SSH sertlestirme maddeleri)
# =============================================================
set -euo pipefail

BASE="/opt/lcarlie"
STACK="$BASE/n8n"
BK="$BASE/backup"

log() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }

# ---------------------------------------------------------------
log "1) TEST geri yukleme betigi (canli veriye DOKUNMAZ)"
# Yedegi n8n_test adli AYRI bir veritabanina yukler, canli n8n etkilenmez.
cat > "$BK/geri-yukle-TEST.sh" <<'SH'
#!/usr/bin/env bash
# Yedegin saglamligini CANLI VERIYE DOKUNMADAN dogrular.
# Yedek "n8n_test" adli ayri bir veritabanina yuklenir, sonra silinir.
# KULLANIM: ./geri-yukle-TEST.sh [yedek-dosyasi]   (bos birakilirsa en yeni yedek)
set -uo pipefail
STACK="/opt/lcarlie/n8n"
BK="/opt/lcarlie/backup"
set -a; . "$STACK/.env"; set +a

ARSIV="${1:-$(ls -1t "$BK"/archive/lcarlie-n8n-*.tgz.enc 2>/dev/null | head -n1)}"
[ -n "$ARSIV" ] && [ -f "$ARSIV" ] || { echo "HATA: yedek dosyasi bulunamadi"; exit 1; }
echo "Test edilen yedek: $(basename "$ARSIV")"

W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
echo "-- 1/4 sifre cozuluyor..."
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$ARSIV" -out "$W/b.tgz" -pass "env:BACKUP_ENC_KEY" \
  || { echo "BASARISIZ: sifre cozulemedi (BACKUP_ENC_KEY hatali olabilir)"; exit 1; }
echo "-- 2/4 arsiv aciliyor..."
tar -xzf "$W/b.tgz" -C "$W" || { echo "BASARISIZ: arsiv bozuk"; exit 1; }
echo "   Icerik: $(ls "$W" | tr '\n' ' ')"

echo "-- 3/4 test veritabanina yukleniyor (n8n_test)..."
docker cp "$W/n8n-db.dump" lcarlie-postgres:/tmp/test.dump
docker exec lcarlie-postgres psql -U n8n -d postgres -q -c "DROP DATABASE IF EXISTS n8n_test;"
docker exec lcarlie-postgres psql -U n8n -d postgres -q -c "CREATE DATABASE n8n_test OWNER n8n;"
if docker exec lcarlie-postgres pg_restore -U n8n -d n8n_test /tmp/test.dump 2>/dev/null; then
  WF=$(docker exec lcarlie-postgres psql -U n8n -d n8n_test -tAc \
       "SELECT count(*) FROM workflow_entity;" 2>/dev/null || echo "?")
  CR=$(docker exec lcarlie-postgres psql -U n8n -d n8n_test -tAc \
       "SELECT count(*) FROM credentials_entity;" 2>/dev/null || echo "?")
  echo "   OK - workflow sayisi: $WF, kimlik bilgisi sayisi: $CR"
  SONUC="BASARILI"
else
  echo "   BASARISIZ: pg_restore hata verdi"
  SONUC="BASARISIZ"
fi

echo "-- 4/4 test veritabani temizleniyor..."
docker exec lcarlie-postgres rm -f /tmp/test.dump
docker exec lcarlie-postgres psql -U n8n -d postgres -q -c "DROP DATABASE IF EXISTS n8n_test;"

echo
echo "======================================"
echo " YEDEK TESTI: $SONUC"
echo " Canli n8n veritabanina DOKUNULMADI."
echo "======================================"
[ "$SONUC" = "BASARILI" ]
SH
chmod 700 "$BK/geri-yukle-TEST.sh"
echo "$BK/geri-yukle-TEST.sh yazildi"

# Ayda bir otomatik yedek dogrulama testi
cat > /etc/cron.d/lcarlie-backup-test <<'CRON'
# L'CARLIE - aylik yedek saglamlik testi (her ayin 1'i 04:30)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
CRON_TZ=Europe/Istanbul
30 4 1 * * root /opt/lcarlie/backup/geri-yukle-TEST.sh >> /opt/lcarlie/backup/log/test-restore.log 2>&1
CRON
chmod 644 /etc/cron.d/lcarlie-backup-test
echo "Aylik otomatik yedek testi zamanlandi (her ayin 1'i 04:30)"

# ---------------------------------------------------------------
log "2) Guncelleme + geri alma (rollback) betigi"
cat > "$BASE/guncelle.sh" <<'SH'
#!/usr/bin/env bash
# n8n'i guvenli sekilde gunceller: once yedek alir, sonra gunceller,
# saglik kontrolu basarisizsa ESKI SURUME otomatik geri doner.
# KULLANIM: ./guncelle.sh [hedef-surum]   (bos birakilirsa en son surum)
set -uo pipefail
STACK="/opt/lcarlie/n8n"
cd "$STACK"

ESKI=$(grep '^N8N_IMAGE_TAG=' .env | cut -d= -f2)
echo "Mevcut surum: $ESKI"

echo "-- 1/5 Guncelleme oncesi yedek aliniyor..."
/opt/lcarlie/backup/backup.sh || { echo "IPTAL: yedek alinamadi, guncelleme yapilmadi."; exit 1; }

HEDEF="${1:-}"
if [ -z "$HEDEF" ]; then
  docker pull n8nio/n8n:latest >/dev/null || { echo "IPTAL: imaj cekilemedi"; exit 1; }
  HEDEF=$(docker run --rm --entrypoint n8n n8nio/n8n:latest --version 2>/dev/null | tr -d '\r' | tail -n1)
fi
[ -n "$HEDEF" ] || { echo "IPTAL: hedef surum belirlenemedi"; exit 1; }
echo "-- 2/5 Hedef surum: $HEDEF"
[ "$HEDEF" = "$ESKI" ] && { echo "Zaten guncel. Cikiliyor."; exit 0; }

echo "-- 3/5 Guncelleniyor..."
sed -i "s/^N8N_IMAGE_TAG=.*/N8N_IMAGE_TAG=$HEDEF/" .env
docker compose pull n8n && docker compose up -d n8n

echo "-- 4/5 Saglik kontrolu (90 sn)..."
OK=0
for i in $(seq 1 18); do
  sleep 5
  if docker exec lcarlie-caddy wget -q -O /dev/null --timeout=5 http://n8n:5678/healthz 2>/dev/null; then
    OK=1; break
  fi
done

if [ "$OK" = "1" ]; then
  echo "-- 5/5 BASARILI. n8n $ESKI -> $HEDEF guncellendi."
else
  echo "-- 5/5 BASARISIZ! $ESKI surumune geri donuluyor..."
  sed -i "s/^N8N_IMAGE_TAG=.*/N8N_IMAGE_TAG=$ESKI/" .env
  docker compose up -d n8n
  echo "Geri donuldu: $ESKI"
  echo "Veritabani da geri yuklenmeli ise:"
  echo "  /opt/lcarlie/backup/geri-yukle.sh <en-son-yedek>"
  exit 1
fi
SH
chmod 700 "$BASE/guncelle.sh"
echo "$BASE/guncelle.sh yazildi"

# ---------------------------------------------------------------
log "3) Anahtarlari GUVENLI sekilde gorme araci"
# Bu betigi SADECE kullanici kendi calistirir; anahtarlar hicbir loga dusmez.
cat > "$BASE/anahtarlari-goster.sh" <<'SH'
#!/usr/bin/env bash
# Anahtarlari ekrana bir kez yazar. Parola yoneticinize kaydedin.
# Bu degerler olmadan yedekleriniz ACILAMAZ ve n8n kimlik bilgileri KURTARILAMAZ.
set -euo pipefail
clear
cat <<'UYARI'
================================================================
  DIKKAT: Asagidaki degerleri SADECE parola yoneticinize kaydedin.
  Ekran goruntusu almayin, sohbete/e-postaya yapistirmayin.
  Sunucu tamamen kaybolursa yedekleri acmanin TEK yolu bunlardir.
================================================================
UYARI
echo
grep -E '^(N8N_ENCRYPTION_KEY|BACKUP_ENC_KEY|POSTGRES_PASSWORD)=' /opt/lcarlie/n8n/.env
echo
read -r -p "Kaydettiniz mi? Ekrani temizlemek icin Enter'a basin..." _
clear
echo "Ekran temizlendi."
SH
chmod 700 "$BASE/anahtarlari-goster.sh"
echo "$BASE/anahtarlari-goster.sh yazildi"

# ---------------------------------------------------------------
log "4) SSH sertlestirme (parola girisini kapatma)"
# GUVENLIK: Once anahtarla girisin CALISTIGI dogrulanir, yoksa kapatilmaz.
cat > "$BASE/ssh-sertlestir.sh" <<'SH'
#!/usr/bin/env bash
# SSH parola girisini kapatir. SADECE anahtarla giris dogrulandiktan sonra.
set -euo pipefail
AUTH="/root/.ssh/authorized_keys"
if [ ! -s "$AUTH" ]; then
  echo "IPTAL: $AUTH bos veya yok. Parola girisi kapatilirsa sunucuya GIRILEMEZ."
  exit 1
fi
echo "Kurulu anahtar sayisi: $(grep -c '^ssh-' "$AUTH")"
echo "Bu oturum anahtarla mi acildi kontrol ediliyor..."
if [ "${SSH_AUTH_METHOD:-}" != "publickey" ] && ! grep -q 'publickey' <<<"${SSH_CONNECTION:-}"; then
  echo "NOT: Otomatik dogrulanamadi. Devam etmeden once BASKA bir terminalden"
  echo "     anahtarla giris yapabildiginizi mutlaka test edin."
  read -r -p "Anahtarla giris calisiyor mu? 'EVET' yazin: " O
  [ "$O" = "EVET" ] || { echo "Iptal edildi."; exit 1; }
fi
cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.yedek-$(date +%F)"
mkdir -p /etc/ssh/sshd_config.d
# 🔴 DOSYA ADI KRITIK: sshd_config.d icindeki dosyalar ALFABETIK okunur ve
# OpenSSH'te bir ayarin ILK gorulen degeri kazanir. Ubuntu'da hazir gelen
# 50-cloud-init.conf "PasswordAuthentication yes" icerir. 99- onekiyle
# yazilirsa bizim "no" satirimiz HIC DIKKATE ALINMAZ - sessizce etkisiz kalir.
# 00- onekiyle yaziyoruz ki once okunsun ve kazansin.
cat > /etc/ssh/sshd_config.d/00-lcarlie.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 3
CONF
rm -f /etc/ssh/sshd_config.d/99-lcarlie.conf   # eski hatali adla yazildiysa temizle
sshd -t && systemctl reload ssh
echo "TAMAM: SSH artik sadece anahtarla giris kabul ediyor."
echo "DOGRULAMA (ikisi de dogru gorunmeli):"
sshd -T 2>/dev/null | grep -E '^passwordauthentication|^permitrootlogin'
echo "Geri almak icin: rm /etc/ssh/sshd_config.d/00-lcarlie.conf && systemctl reload ssh"
SH
chmod 700 "$BASE/ssh-sertlestir.sh"
echo "$BASE/ssh-sertlestir.sh yazildi (anahtar girisi dogrulanmadan CALISTIRILMAYACAK)"

log "EK ARACLAR HAZIR"
ls -la "$BASE" "$BK" | grep -E '\.sh$|^total|:$' || true
