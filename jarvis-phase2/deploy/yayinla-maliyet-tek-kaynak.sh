#!/bin/bash
# Maliyet tek kaynak (4477e2a, 15.11.2026): panel fiyat onizleme formulu + metinler.
# DB tarafi ve saatlik timer zaten uygulandi; bu betik yalniz canli Python dosyalarini gunceller.
# app.py degistigi icin panel birkac saniyeligine yeniden baslar. Canli dosya degismisse durur.
set -euo pipefail
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1; L=/opt/lcarlie/jarvis-phase2; K=4477e2a
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/maliyet-tek-kaynak-$(date +%Y%m%d-%H%M%S)
cd $L
sha256sum -c --quiet - <<OZET || { echo "DURDU: canli dosya degismis, hicbir sey kopyalanmadi"; exit 3; }
3bb441803f74c15ca334251ce039a93a3f64ff752348da2678bcfa276b2a8959  webconsole/app.py
3d996cbb6de3d8ef456663ece125e212be38bbde8b0939d23eefec74b9221efc  scripts/gunluk-rapor.py
d1a470142280e56e45f2eaf63d102034e1c161ad51909f9ac7ad2bd765e861eb  scripts/kreatif-brief.py
7e1be94756d0401f6b553b0a6a6f8f10b8e049b443a41ee2be7a9745ada47ce9  tools/urun-bilgi-uret.py
OZET
for f in webconsole/app.py scripts/gunluk-rapor.py scripts/kreatif-brief.py tools/urun-bilgi-uret.py scripts/finans-maliyet-aktar.py; do
  mkdir -p "$YEDEK/$(dirname $f)"; [ -f "$f" ] && cp -p "$f" "$YEDEK/$f"
  git -C $DEPO show $K:jarvis-phase2/$f > "$f.yeni"; chmod --reference="$YEDEK/$f" "$f.yeni" 2>/dev/null || chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
chmod 755 scripts/finans-maliyet-aktar.py
cp -p /opt/lcarlie/idefix-marj.py "$YEDEK/idefix-marj.py"
git -C $DEPO show $K:server/opt-root/idefix-marj.py > /opt/lcarlie/idefix-marj.py
systemctl restart jarvis-web
for i in $(seq 1 20); do k=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ || true); [ "$k" = 200 ] && break; sleep 1; done
echo "panel: HTTP $k · yedek: $YEDEK"
