#!/usr/bin/env bash
# =============================================================
# L'CARLIE - n8n uretim kurulumu (Ubuntu 24.04 + Docker)
# Idempotent: tekrar calistirilabilir, mevcut veriyi silmez.
# =============================================================
set -euo pipefail

DOMAIN="n8n.lcarlie.shop"
BASE="/opt/lcarlie"
STACK="$BASE/n8n"
BACKUP_DIR="$BASE/backup"
TZ_NAME="Europe/Istanbul"

log() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[UYARI] %s\033[0m\n' "$*"; }

# ---------------------------------------------------------------
log "0) On kontrol"
[ "$(id -u)" -eq 0 ] || { echo "root olarak calistirilmali"; exit 1; }
command -v docker >/dev/null || { echo "HATA: docker yok"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "HATA: docker compose plugin yok"; exit 1; }

# Mevcut docker yapilarini bozmama kontrolu
CONFLICT=0
for c in lcarlie-n8n lcarlie-postgres lcarlie-caddy; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$c"; then
    warn "$c container'i zaten mevcut - compose onu guncelleyecek (veri volume'leri korunur)."
    CONFLICT=1
  fi
done
# 80/443'u baskasi tutuyor mu?
if ss -tulpn 2>/dev/null | grep -qE ':(80|443)\s'; then
  warn "80 veya 443 portu baska bir servis tarafindan dinleniyor:"
  ss -tulpn | grep -E ':(80|443)\s' || true
  echo "Caddy baslatilamayabilir. Devam ediliyor, sonda kontrol edilecek."
fi

# ---------------------------------------------------------------
log "1) Saat dilimi: $TZ_NAME"
timedatectl set-timezone "$TZ_NAME" || warn "timezone ayarlanamadi"
timedatectl show -p Timezone --value

# ---------------------------------------------------------------
log "2) Klasorler"
mkdir -p "$STACK/files" "$BACKUP_DIR/archive" "$BACKUP_DIR/log"
chmod 700 "$BASE"
chmod 700 "$BACKUP_DIR/archive"

# ---------------------------------------------------------------
log "3) Gizli anahtarlar (.env)"
if [ -f "$STACK/.env" ]; then
  echo "Mevcut $STACK/.env korundu - anahtarlar YENIDEN URETILMEDI."
else
  N8N_ENC=$(openssl rand -hex 32)
  PG_PASS=$(openssl rand -hex 24)
  BK_KEY=$(openssl rand -hex 32)
  cat > "$STACK/.env" <<EOF
# L'CARLIE n8n - GIZLI. Bu dosyayi kimseyle paylasmayin.
# Olusturulma: $(date -Is)
N8N_IMAGE_TAG=latest
POSTGRES_PASSWORD=$PG_PASS
N8N_ENCRYPTION_KEY=$N8N_ENC
BACKUP_ENC_KEY=$BK_KEY
EOF
  echo "Yeni anahtarlar uretildi."
fi
chmod 600 "$STACK/.env"
chown root:root "$STACK/.env"

# ---------------------------------------------------------------
log "4) docker-compose.yml"
cat > "$STACK/docker-compose.yml" <<'YAML'
name: lcarlie

services:
  postgres:
    image: postgres:17-alpine
    container_name: lcarlie-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: n8n
      POSTGRES_DB: n8n
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      TZ: Europe/Istanbul
    volumes:
      - pgdata17:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U n8n -d n8n"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 30s
    networks: [dahili]
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }

  n8n:
    image: n8nio/n8n:${N8N_IMAGE_TAG}
    container_name: lcarlie-n8n
    restart: unless-stopped
    depends_on:
      postgres: { condition: service_healthy }
    environment:
      # --- veritabani ---
      DB_TYPE: postgresdb
      DB_POSTGRESDB_HOST: postgres
      DB_POSTGRESDB_PORT: "5432"
      DB_POSTGRESDB_DATABASE: n8n
      DB_POSTGRESDB_USER: n8n
      DB_POSTGRESDB_PASSWORD: ${POSTGRES_PASSWORD}
      # --- kimlik / sifreleme ---
      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}
      # --- adres / reverse proxy ---
      N8N_HOST: n8n.lcarlie.shop
      N8N_PORT: "5678"
      N8N_LISTEN_ADDRESS: 0.0.0.0
      N8N_PROTOCOL: https
      N8N_EDITOR_BASE_URL: https://n8n.lcarlie.shop/
      N8N_WEBHOOK_URL: https://n8n.lcarlie.shop/
      N8N_PROXY_HOPS: "1"
      # --- guvenlik ---
      N8N_SECURE_COOKIE: "true"
      N8N_BLOCK_ENV_ACCESS_IN_NODE: "true"
      N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS: "true"
      N8N_DIAGNOSTICS_ENABLED: "false"
      N8N_VERSION_NOTIFICATIONS_ENABLED: "true"
      N8N_HIRING_BANNER_ENABLED: "false"
      # --- calisma / bakim ---
      # Topluluk paketleri dogrulanmamis kod calistirabilir - uretimde kapali.
      N8N_UNVERIFIED_PACKAGES_ENABLED: "false"
      # Yapay zeka cagrilari uzun surebilir; varsayilan 60sn'ye dusecek, 300'de sabitliyoruz.
      N8N_RUNNERS_TASK_TIMEOUT: "300"
      EXECUTIONS_DATA_PRUNE: "true"
      EXECUTIONS_DATA_MAX_AGE: "336"
      EXECUTIONS_DATA_PRUNE_MAX_COUNT: "50000"
      N8N_LOG_LEVEL: info
      GENERIC_TIMEZONE: Europe/Istanbul
      TZ: Europe/Istanbul
      NODE_ENV: production
    volumes:
      - n8ndata:/home/node/.n8n
      - ./files:/files
    networks: [dahili, web]
    # 5678 BILEREK host'a aciLMADI - sadece Caddy uzerinden erisilir.
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }

  caddy:
    image: caddy:2-alpine
    container_name: lcarlie-caddy
    restart: unless-stopped
    depends_on: [n8n]
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      TZ: Europe/Istanbul
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddydata:/data
      - caddyconfig:/config
    networks: [web]
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }

networks:
  dahili:
    driver: bridge
    internal: true      # postgres disariya cikamaz
  web:
    driver: bridge

volumes:
  pgdata17:
  n8ndata:
  caddydata:
  caddyconfig:
YAML

# ---------------------------------------------------------------
log "5) Caddyfile (HTTPS + guvenlik basliklari)"
cat > "$STACK/Caddyfile" <<'CADDY'
{
	servers {
		trusted_proxies static private_ranges
	}
}

n8n.lcarlie.shop {
	encode zstd gzip

	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "SAMEORIGIN"
		Referrer-Policy "strict-origin-when-cross-origin"
		Permissions-Policy "geolocation=(), microphone=(), camera=()"
		-Server
	}

	reverse_proxy n8n:5678 {
		flush_interval -1
	}

	log {
		output file /data/access.log {
			roll_size 10MiB
			roll_keep 5
		}
	}
}

# Alan adi disindaki tum istekleri (dogrudan IP dahil) reddet
:80, :443 {
	respond "Not found" 404
}
CADDY

# ---------------------------------------------------------------
log "6) UFW guvenlik duvari"
ufw allow 22/tcp   comment 'SSH'          >/dev/null 2>&1 || true
ufw allow 80/tcp   comment 'HTTP-ACME'    >/dev/null 2>&1 || true
ufw allow 443/tcp  comment 'HTTPS'        >/dev/null 2>&1 || true
ufw allow 443/udp  comment 'HTTP3'        >/dev/null 2>&1 || true
ufw deny 5678      comment 'n8n dogrudan erisim yasak' >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
ufw status verbose

# ---------------------------------------------------------------
log "7) Docker imajlari indiriliyor"
cd "$STACK"
docker compose pull

log "8) Servisler baslatiliyor"
docker compose up -d

echo "Konteynerlerin hazir olmasi bekleniyor (60 sn)..."
for i in $(seq 1 20); do
  sleep 3
  if docker inspect -f '{{.State.Health.Status}}' lcarlie-postgres 2>/dev/null | grep -q healthy; then break; fi
done
docker compose ps

# ---------------------------------------------------------------
log "9) n8n surumu sabitleniyor (uretim kararliligi)"
sleep 20
N8N_VER=$(docker exec lcarlie-n8n n8n --version 2>/dev/null | tr -d '\r' | tail -n1 || echo "")
if [ -n "$N8N_VER" ]; then
  echo "Calisan n8n surumu: $N8N_VER"
  sed -i "s/^N8N_IMAGE_TAG=.*/N8N_IMAGE_TAG=$N8N_VER/" "$STACK/.env"
  echo "N8N_IMAGE_TAG=$N8N_VER olarak sabitlendi (latest surukleme riski kaldirildi)."
else
  warn "n8n surumu okunamadi, N8N_IMAGE_TAG=latest kaldi."
fi

log "KURULUM ADIMI TAMAM"
docker compose ps
