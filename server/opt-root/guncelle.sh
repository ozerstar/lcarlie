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
