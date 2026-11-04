#!/usr/bin/env bash
# L'CARLIE VDS - SADECE OKUMA / DURUM TESPITI. Hicbir sey degistirmez.
echo "===== 1. ISLETIM SISTEMI ====="
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME"
uname -r
echo "Uptime: $(uptime -p 2>/dev/null)"
echo "Timezone: $(timedatectl show -p Timezone --value 2>/dev/null)"

echo; echo "===== 2. CPU / RAM / DISK ====="
echo "CPU cekirdek: $(nproc)"
free -h
echo "---"
df -hT / /var 2>/dev/null | sort -u
echo "--- swap ---"
swapon --show || echo "swap yok"

echo; echo "===== 3. DOCKER ====="
docker --version 2>&1 || echo "DOCKER YOK"
docker compose version 2>&1 || echo "COMPOSE PLUGIN YOK"
echo "--- calisan/duran container'lar ---"
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1
echo "--- volume'ler ---"
docker volume ls 2>&1
echo "--- network'ler ---"
docker network ls 2>&1
echo "--- mevcut compose projeleri ---"
docker compose ls 2>&1 || true

echo; echo "===== 4. DINLENEN PORTLAR ====="
ss -tulpn 2>/dev/null | grep -v '127.0.0.1\|::1' || netstat -tulpn 2>/dev/null

echo; echo "===== 5. UFW ====="
ufw status verbose 2>&1 || echo "UFW YOK"

echo; echo "===== 6. IP ADRESLERI ====="
echo "-- yerel --"
ip -4 -br addr show scope global 2>/dev/null
echo "-- dis IPv4 --"
curl -4 -s --max-time 10 https://api.ipify.org 2>/dev/null || echo "(dis IP alinamadi)"
echo
echo "-- dis IPv6 --"
curl -6 -s --max-time 8 https://api64.ipify.org 2>/dev/null || echo "(IPv6 yok)"
echo

echo; echo "===== 7. DNS KONTROL: n8n.lcarlie.shop ====="
getent hosts n8n.lcarlie.shop || echo "A KAYDI YOK (beklenen - henuz olusturulmadi)"

echo; echo "===== 8. MEVCUT /opt ICERIGI ====="
ls -la /opt 2>/dev/null

echo; echo "===== 9. GEREKLI ARACLAR ====="
for t in openssl curl cron tar gzip rclone msmtp; do
  printf '%-10s %s\n' "$t" "$(command -v $t || echo 'YOK')"
done

echo; echo "===== INCELEME TAMAM ====="
