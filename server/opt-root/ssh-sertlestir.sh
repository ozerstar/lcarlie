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
