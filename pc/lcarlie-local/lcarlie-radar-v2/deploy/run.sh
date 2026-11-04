#!/usr/bin/env bash
# Tek giriş noktası: systemd (lcarlie-radar@<iş>.service) buradan çağırır, her çalışma loglanır.
# 29.10.2026: cron yerine systemd zamanlayıcıları (Jarvis'teki iş üretici ile aynı düzen);
# özet/aylık/sağlık sonrası gönderim ve panel dosyası yenileme buraya alındı.
set -uo pipefail
DIR="${RADAR_DIR:-/opt/lcarlie/radar}"
cd "$DIR"
set -a; [ -f .env ] && . ./.env; set +a
mkdir -p logs scans
LOG="logs/$(date +%Y-%m).log"
ts() { date '+%F %T'; }
radar() { python3 -m radar "$@" >> "$LOG" 2>&1; }

case "${1:-}" in
  jarvis-tarama|jarvis-teyit)
    # Ajan (deploy/jarvis_rakip_ajani.py) TASK.md'deki işi yapar ve sonucu scans/ klasörüne JSON yazar.
    MODE="${1#jarvis-}"
    OUT="scans/$(date +%Y%m%d-%H%M)-$MODE.json"
    if [ -z "${JARVIS_AGENT_CMD:-}" ]; then
      echo "$(ts) [$1] JARVIS_AGENT_CMD tanımlı değil, atlandı" >> "$LOG"; exit 0
    fi
    python3 -m radar teyit-listesi > scans/teyit.json 2>>"$LOG"
    python3 -m radar izlenenler > scans/izlenen.json 2>>"$LOG"
    timeout 3000 $JARVIS_AGENT_CMD --mode "$MODE" --task "$DIR/TASK.md" \
      --recheck scans/teyit.json --watch scans/izlenen.json --out "$OUT" >> "$LOG" 2>&1
    if [ -s "$OUT" ]; then
      echo "$(ts) [$1] ingest $OUT" >> "$LOG"
      radar ingest "$OUT"
    else
      echo "$(ts) [$1] HATA: ajan çıktı üretmedi" >> "$LOG"
      echo "{\"source\":\"jarvis-$MODE\",\"source_status\":[{\"source\":\"jarvis-$MODE\",\"ok\":false,\"error\":\"cikti yok\"}],\"brands\":[]}" \
        | python3 -m radar ingest - >> "$LOG" 2>&1
    fi
    find scans -name '*.json' -mtime +30 -delete ;;
  ozet|aylik|saglik)
    echo "$(ts) [$1]" >> "$LOG"
    radar "$1" && radar gonder || echo "$(ts) HATA: $1" >> "$LOG" ;;
  *)
    echo "$(ts) [$*]" >> "$LOG"
    radar "$@" || echo "$(ts) HATA: $*" >> "$LOG" ;;
esac
radar panel || echo "$(ts) HATA: panel" >> "$LOG"
