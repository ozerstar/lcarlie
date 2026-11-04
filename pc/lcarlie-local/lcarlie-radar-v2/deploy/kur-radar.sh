#!/bin/bash
# L'CARLİÉ Radar v2 kurulumu. Sunucuda root:  bash /tmp/lcarlie-radar-v2/deploy/kur-radar.sh
# Ne yapar: /opt/lcarlie/radar'a kurar, testleri koşar, (istenirse) başsız tarayıcıyı kurar, systemd
# zamanlayıcılarını açar, Jarvis paneline Radar bölümünü ekler, ilk turu GERÇEK veriyle çalıştırır.
# Ne YAPMAZ: üçüncü kişiye mesaj göndermez (taslaklar onaya düşer), ücretli API açmaz, anahtar eklemez.
# Tarayıcı (Rossmann sayfaları için Playwright+Chromium, ~300 MB): RADAR_TARAYICI=evet bash kur-radar.sh
# Geri alma: bash /tmp/lcarlie-radar-v2/deploy/geri-al-radar.sh /opt/lcarlie/backup-radar-<zaman>
set -euo pipefail
S="$(cd "$(dirname "$0")/.." && pwd)"; R=/opt/lcarlie/radar; J=/opt/lcarlie/jarvis-phase2
Y=/opt/lcarlie/backup-radar-$(date +%Y%m%d-%H%M%S); mkdir -p "$Y"
PANEL_ONCEKI=59960cc12720266958beb638981d7fc2010b587209df2cfe7bca0aa0d2ffb9bb

python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version' || { echo "python3 >= 3.9 gerekli"; exit 2; }

# Jarvis paneli: sunucudaki ekip_isleri.py bizim bildiğimiz sürüm değilse (ör. Codex değiştirdi) dokunma.
P=$J/webconsole/ekip_isleri.py
PANEL=evet
if [ -f "$P" ]; then
  h=$(tr -d '\r' < "$P" | sha256sum | cut -d' ' -f1)   # satır sonu (CRLF/LF) farkı yok sayılır (v4 dosyası CRLF)
  if [ "$h" != "$PANEL_ONCEKI" ] && ! cmp -s "$P" "$S/deploy/jarvis-panel/ekip_isleri.py"; then
    echo "UYARI: $P beklenen sürüm değil (başkası değiştirmiş olabilir); panel adımı ATLANDI. sha=$h"; PANEL=hayir
  fi
else
  echo "UYARI: $P yok; panel adımı atlandı."; PANEL=hayir
fi

# Kod (veri, ayar ve anahtarlar korunur)
if [ -d "$R" ]; then cp -a "$R" "$Y/radar"; fi
install -d -m 0750 "$R" "$R/deploy" "$R/radar" "$R/tests" "$R/data"
install -m 0644 "$S"/radar/*.py "$R/radar/"
install -m 0644 "$S"/tests/*.py "$R/tests/"
install -m 0644 "$S/README.md" "$S/TASK.md" "$S/config.example.json" "$R/"
install -m 0644 "$S/deploy/env.example" "$S/deploy/jarvis_rakip_ajani.py" "$R/deploy/"
install -m 0755 "$S/deploy/run.sh" "$R/run.sh"
install -m 0644 "$S/data/fiyat_listesi.json" "$R/data/fiyat_listesi.json"
[ -f "$R/config.json" ] || install -m 0640 "$S/config.example.json" "$R/config.json"
[ -f "$R/.env" ] || install -m 0600 "$S/deploy/env.example" "$R/.env"

echo "== testler"
(cd "$R" && python3 -m unittest discover -s tests -q)
(cd "$R" && RADAR_CONFIG=$R/config.json python3 -m radar init)
# Sahibin Chrome'unda okunan Trendyol kartları (data/trendyol-*.tsv) ilk kurulumda içeri alınır.
for f in "$S"/data/trendyol-*.tsv; do
  [ -e "$f" ] || continue
  install -m 0640 "$f" "$R/data/"
  (cd "$R" && RADAR_CONFIG=$R/config.json python3 -m radar trendyol-ekle "$R/data/$(basename "$f")" | head -5)
done

if [ "${RADAR_TARAYICI:-hayir}" = evet ]; then
  echo "== başsız tarayıcı (Playwright + Chromium) -> $R/.tarayici"
  $J/venv/bin/pip install -q playwright==1.47.0
  PLAYWRIGHT_BROWSERS_PATH=$R/.tarayici $J/venv/bin/python -m playwright install --with-deps chromium
else
  echo "(tarayıcı kurulmadı: Rossmann liste sayfaları düz HTML ile okunur ve fiyat çıkmaz; eczane/Gratis etkilenmez)"
fi

if [ "$PANEL" = evet ]; then
  cp -a "$P" "$Y/ekip_isleri.py"
  install -m 0644 "$S/deploy/jarvis-panel/ekip_isleri.py" "$P"
  systemctl restart jarvis-web.service && sleep 3 && systemctl is-active jarvis-web.service
fi

install -m 0644 "$S"/deploy/lcarlie-radar@.service "$S"/deploy/lcarlie-radar-*.timer /etc/systemd/system/
systemctl daemon-reload
for t in "$S"/deploy/lcarlie-radar-*.timer; do systemctl enable --now "$(basename "$t")"; done

echo "== ilk tur (gerçek veri)"
systemctl start lcarlie-radar@mevzuat.service || true          # TİTCK sayfası için taban
echo "(eczane + Gratis taraması ~2-3 dk)"
systemctl start lcarlie-radar@kaynak-tara.service || true
echo "(rakip ajanı 2-15 dk: arama + sayfa doğrulama)"
systemctl start lcarlie-radar@jarvis-tarama.service || true
systemctl start lcarlie-radar@musteri-bul.service || true
systemctl start lcarlie-radar@satis.service || true
systemctl start lcarlie-radar@ozet.service || true
tail -n 60 "$R/logs/$(date +%Y-%m).log"
echo "== sabah özeti (panelde de görünür)"; (cd "$R" && set -a && . ./.env && set +a && python3 -m radar ozet-onizle | head -60)
systemctl list-timers 'lcarlie-radar-*' --no-pager | head -14
echo "TAMAM. Yedek: $Y"
echo "Telegram için: .env'e TELEGRAM_BOT_TOKEN yazın, bota mesaj atın, sonra: cd $R && set -a && . ./.env && set +a && python3 -m radar telegram-kimlik"
