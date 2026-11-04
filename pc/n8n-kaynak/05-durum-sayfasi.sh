#!/usr/bin/env bash
# =============================================================
# L'CARLIE - SUNUCU DURUM SAYFASI
# Sessiz arizayi onler: yedek basarisiz olsa, container dusse,
# sertifika bitse telefondan gorulebilir.
# =============================================================
set -euo pipefail

BASE="/opt/lcarlie"
WEB="$BASE/durum"
mkdir -p "$WEB"

# --- Gizli yol anahtari ---
if ! grep -q "^DURUM_TOKEN=" "$BASE/n8n/.env" 2>/dev/null; then
  echo "DURUM_TOKEN=$(openssl rand -hex 12)" >> "$BASE/n8n/.env"
fi
DURUM_TOKEN=$(grep "^DURUM_TOKEN=" "$BASE/n8n/.env" | cut -d= -f2)

# --- Durum uretici betik ---
cat > "$BASE/durum-uret.sh" <<'SH'
#!/usr/bin/env bash
# Durum sayfasini uretir. Cron ile 15 dakikada bir calisir.
set -uo pipefail
WEB="/opt/lcarlie/durum"
BK="/opt/lcarlie/backup"
mkdir -p "$WEB"

ok()   { echo "<span class=ok>✔ $1</span>"; }
kotu() { echo "<span class=kotu>✘ $1</span>"; }
uyar() { echo "<span class=uyar>▲ $1</span>"; }

# 1) Container'lar
CONT=""
SORUNLU=0
for c in lcarlie-n8n lcarlie-postgres lcarlie-caddy; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
    UP=$(docker inspect -f '{{.State.StartedAt}}' "$c" | cut -dT -f1,2 | tr T ' ' | cut -d. -f1)
    CONT="$CONT<tr><td>$c</td><td>$(ok 'çalışıyor')</td><td>$UP</td></tr>"
  else
    CONT="$CONT<tr><td>$c</td><td>$(kotu 'DURMUŞ')</td><td>-</td></tr>"
    SORUNLU=1
  fi
done

# 2) Son yedek
SON_LOG=$(ls -1t "$BK"/log/backup-*.log 2>/dev/null | head -n1 || true)
if [ -n "${SON_LOG:-}" ] && [ -f "$SON_LOG" ]; then
  SON_SATIR=$(grep "Yedekleme bitti" "$SON_LOG" | tail -n1 || echo "")
  SON_ZAMAN=$(echo "$SON_SATIR" | grep -oE '\[[^]]+\]' | tr -d '[]' || echo "?")
  if echo "$SON_SATIR" | grep -q "BASARILI"; then
    YEDEK_DURUM=$(ok "başarılı")
  else
    YEDEK_DURUM=$(kotu "BAŞARISIZ"); SORUNLU=1
  fi
  DRIVE=$(grep "Harici depolamaya aktarildi" "$SON_LOG" | tail -n1 >/dev/null 2>&1 && ok "Drive'a aktarıldı" || uyar "Drive aktarımı görülmedi")
else
  YEDEK_DURUM=$(uyar "log bulunamadı"); SON_ZAMAN="?"; DRIVE="-"
fi

# Yedek yasi (24 saatten eskiyse uyar)
SON_DOSYA=$(ls -1t "$BK"/archive/*.tgz.enc 2>/dev/null | head -n1 || true)
if [ -n "${SON_DOSYA:-}" ]; then
  YAS_SAAT=$(( ( $(date +%s) - $(stat -c %Y "$SON_DOSYA") ) / 3600 ))
  ADET=$(ls -1 "$BK"/archive/*.tgz.enc 2>/dev/null | wc -l)
  BOYUT=$(du -h "$SON_DOSYA" | cut -f1)
  if [ "$YAS_SAAT" -gt 26 ]; then YEDEK_YAS=$(kotu "${YAS_SAAT} saat önce"); SORUNLU=1
  else YEDEK_YAS=$(ok "${YAS_SAAT} saat önce"); fi
else
  YEDEK_YAS=$(kotu "yedek dosyası yok"); ADET=0; BOYUT="-"; SORUNLU=1
fi

# 3) Disk / bellek
DISK_YUZDE=$(df / | awk 'NR==2{print $5}' | tr -d '%')
DISK_TXT="$(df -h / | awk 'NR==2{print $3" / "$2" ("$5")"}')"
if [ "$DISK_YUZDE" -gt 85 ]; then DISK=$(kotu "$DISK_TXT"); SORUNLU=1
elif [ "$DISK_YUZDE" -gt 70 ]; then DISK=$(uyar "$DISK_TXT")
else DISK=$(ok "$DISK_TXT"); fi
BELLEK=$(free -h | awk 'NR==2{print $3" / "$2}')

# 4) Sertifika
SON_GUN=$(echo | openssl s_client -connect n8n.lcarlie.shop:443 -servername n8n.lcarlie.shop 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")
if [ -n "$SON_GUN" ]; then
  KALAN=$(( ( $(date -d "$SON_GUN" +%s) - $(date +%s) ) / 86400 ))
  if [ "$KALAN" -lt 10 ]; then SERT=$(kotu "$KALAN gün kaldı"); SORUNLU=1
  elif [ "$KALAN" -lt 25 ]; then SERT=$(uyar "$KALAN gün kaldı")
  else SERT=$(ok "$KALAN gün kaldı"); fi
else
  SERT=$(kotu "okunamadı"); SORUNLU=1
fi

# 5) n8n workflow durumu ve son hatalar
WF=$(docker exec lcarlie-postgres psql -U n8n -d n8n -tAc \
  "SELECT name || '|' || active FROM workflow_entity ORDER BY name;" 2>/dev/null || echo "")
WF_SATIR=""
while IFS='|' read -r ad akt; do
  [ -z "$ad" ] && continue
  if [ "$akt" = "t" ]; then D=$(ok "yayında"); else D=$(uyar "yayında değil"); fi
  WF_SATIR="$WF_SATIR<tr><td>$ad</td><td>$D</td></tr>"
done <<< "$WF"

HATA=$(docker exec lcarlie-postgres psql -U n8n -d n8n -tAc \
  "SELECT count(*) FROM execution_entity WHERE status='error' AND \"startedAt\" > now() - interval '24 hours';" 2>/dev/null | tr -d ' ' || echo "?")
if [ "$HATA" = "0" ]; then HATA_TXT=$(ok "24 saatte hata yok"); else HATA_TXT=$(kotu "$HATA hatalı çalıştırma"); SORUNLU=1; fi

if [ "$SORUNLU" -eq 0 ]; then BASLIK="Her şey yolunda"; RENK="#16a34a"; else BASLIK="DİKKAT GEREKTİREN DURUM VAR"; RENK="#dc2626"; fi

cat > "$WEB/index.html" <<HTML
<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>L'CARLIÉ · Sunucu Durumu</title>
<style>
 body{font-family:system-ui,-apple-system,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:1rem}
 h1{font-size:1.05rem;margin:.2rem 0 .1rem}
 .ust{background:$RENK;color:#fff;padding:.9rem 1rem;border-radius:10px;margin-bottom:1rem}
 .kart{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:.9rem 1rem;margin-bottom:.9rem}
 .kart h2{font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;color:#64748b;margin:0 0 .6rem}
 table{width:100%;border-collapse:collapse;font-size:.9rem}
 td{padding:.35rem 0;border-bottom:1px solid #f1f5f9}
 td:first-child{color:#475569}
 .ok{color:#16a34a;font-weight:600}.kotu{color:#dc2626;font-weight:700}.uyar{color:#d97706;font-weight:600}
 .alt{font-size:.75rem;color:#94a3b8;text-align:center;margin-top:1rem}
</style></head><body>
<div class="ust"><div style="font-size:.75rem;opacity:.9">L'CARLIÉ SUNUCU</div>
<div style="font-size:1.15rem;font-weight:700">$BASLIK</div></div>

<div class="kart"><h2>Servisler</h2><table>$CONT</table></div>

<div class="kart"><h2>Yedekleme</h2><table>
<tr><td>Son yedek</td><td>$YEDEK_YAS</td></tr>
<tr><td>Sonuç</td><td>$YEDEK_DURUM</td></tr>
<tr><td>Google Drive</td><td>$DRIVE</td></tr>
<tr><td>Sunucudaki yedek</td><td>$ADET adet · son $BOYUT</td></tr>
<tr><td>Son çalışma</td><td>$SON_ZAMAN</td></tr>
</table></div>

<div class="kart"><h2>n8n</h2><table>$WF_SATIR
<tr><td>Hatalı çalıştırma</td><td>$HATA_TXT</td></tr>
</table></div>

<div class="kart"><h2>Sistem</h2><table>
<tr><td>Disk</td><td>$DISK</td></tr>
<tr><td>Bellek</td><td>$BELLEK</td></tr>
<tr><td>HTTPS sertifikası</td><td>$SERT</td></tr>
<tr><td>Çalışma süresi</td><td>$(uptime -p)</td></tr>
</table></div>

<div class="alt">Güncelleme: $(date '+%d.%m.%Y %H:%M') · 5 dakikada bir tazelenir</div>
</body></html>
HTML
SH
chmod 700 "$BASE/durum-uret.sh"

# --- Caddy'ye gizli yol ekle ---
CADDY="$BASE/n8n/Caddyfile"
if ! grep -q "durum-" "$CADDY"; then
  # n8n blogunun icine, reverse_proxy'den ONCE ekle
  python3 - "$CADDY" "$DURUM_TOKEN" <<'PY'
import sys
yol, tok = sys.argv[1], sys.argv[2]
s = open(yol, encoding='utf-8').read()
blok = (
    "\n\t# Sunucu durum sayfasi - gizli yol\n"
    "\thandle_path /durum-" + tok + "* {\n"
    "\t\troot * /durum\n"
    "\t\tfile_server\n"
    "\t}\n\n"
)
s = s.replace("\n\treverse_proxy n8n:5678 {", blok + "\treverse_proxy n8n:5678 {", 1)
open(yol, 'w', encoding='utf-8').write(s)
print("Caddyfile guncellendi")
PY
else
  echo "Caddyfile zaten guncel"
fi

# --- Caddy'ye klasoru bagla ---
COMPOSE="$BASE/n8n/docker-compose.yml"
if ! grep -q "/durum:ro" "$COMPOSE"; then
  sed -i 's#      - ./Caddyfile:/etc/caddy/Caddyfile:ro#      - ./Caddyfile:/etc/caddy/Caddyfile:ro\n      - /opt/lcarlie/durum:/durum:ro#' "$COMPOSE"
  echo "docker-compose.yml guncellendi"
fi

# --- Ilk uretim + cron ---
"$BASE/durum-uret.sh"
cat > /etc/cron.d/lcarlie-durum <<'CRON'
# L'CARLIE durum sayfasi - 15 dakikada bir
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
CRON_TZ=Europe/Istanbul
*/15 * * * * root /opt/lcarlie/durum-uret.sh >/dev/null 2>&1
CRON
chmod 644 /etc/cron.d/lcarlie-durum
systemctl restart cron

echo "TAMAM. Caddy yeniden baslatilmali."
