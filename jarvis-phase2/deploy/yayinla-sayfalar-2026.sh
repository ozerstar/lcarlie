#!/bin/bash
# AYRI SAYFALAR TASARIM 2026 canliya alma (26.11.2026).
# Finans merkezi, Harcamalarim, Cari ekstreler, Fis ve faturalar, Ofis, Gorsel isleri
# 25.11 panel tasarimina tasindi: yeni katman static/sayfalar-2026.css + sayfa basliklari.
#   - yalniz webconsole/static ve webconsole/tests; Python kodu DEGISMEDI
#   - statik dosyalar her istekte diskten okunur (ETag) -> servis yeniden baslatilmaz,
#     paralel islerin canliya alinmamis app.py degisikligi istemeden devreye girmez
# Canli dosya depodaki ONCEKI surumle ayni degilse DURUR. Veri yazmaz, goc yok.
# Geri alma: yedek dizinindeki dosyalari geri kopyala, YENI-DOSYALAR.txt'tekileri sil
#            (tek satir: yedek dizininde ./geri-al.sh).
set -euo pipefail
K=${1:?kullanim: yayinla-sayfalar-2026.sh commit}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/sayfalar-2026-$(date +%Y%m%d-%H%M%S)
DEGISEN=$(git -C $DEPO diff --name-only --diff-filter=M "$K~1" "$K" -- jarvis-phase2/webconsole | sed 's#^jarvis-phase2/##')
YENI=$(git -C $DEPO diff --name-only --diff-filter=A "$K~1" "$K" -- jarvis-phase2/webconsole | sed 's#^jarvis-phase2/##')
cd $L
for f in $DEGISEN; do
  if ! git -C $DEPO show "$K~1:jarvis-phase2/$f" | cmp -s - "$f"; then
    echo "DURDU: canli $f depodaki onceki surumle ayni degil; hicbir sey kopyalanmadi"; exit 3
  fi
done
for f in $YENI; do
  if [ -e "$f" ]; then echo "DURDU: yeni dosya $f canlida zaten var; hicbir sey kopyalanmadi"; exit 3; fi
done
mkdir -p "$YEDEK"
for f in $DEGISEN; do mkdir -p "$YEDEK/$(dirname "$f")"; cp -p "$f" "$YEDEK/$f"; done
printf '%s\n' $YENI > "$YEDEK/YENI-DOSYALAR.txt"
printf '%s\n' $DEGISEN > "$YEDEK/DEGISEN-DOSYALAR.txt"
cat > "$YEDEK/geri-al.sh" <<GERI
#!/bin/bash
# $K geri alma: degisen dosyalar yedekten, yeni dosyalar silinir
set -e
cd $L
for f in \$(cat "$YEDEK/DEGISEN-DOSYALAR.txt"); do cp -p "$YEDEK/\$f" "\$f"; done
for f in \$(cat "$YEDEK/YENI-DOSYALAR.txt"); do rm -f "\$f"; done
echo "geri alindi: $K"
GERI
chmod 755 "$YEDEK/geri-al.sh"
for f in $DEGISEN $YENI; do
  mkdir -p "$(dirname "$f")"
  git -C $DEPO show "$K:jarvis-phase2/$f" > "$f.yeni"
  chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
if ! PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s webconsole/tests -t webconsole/tests -p "test_*.py" >/tmp/sayfalar-2026-test.txt 2>&1; then
  echo "TEST KIRMIZI (webconsole) -- geri aliniyor"; grep -E "^(FAIL|ERROR):" /tmp/sayfalar-2026-test.txt | head -20; "$YEDEK/geri-al.sh"; exit 4
fi
tail -3 /tmp/sayfalar-2026-test.txt
PYTHONPATH="$L:$L/webconsole" $L/venv/bin/python -m unittest discover -s tests -t tests -p "test_*.py" >/tmp/sayfalar-2026-test2.txt 2>&1 || true
grep -E "^Ran |^OK|^FAILED" /tmp/sayfalar-2026-test2.txt | tail -2
for u in /sayfalar-2026.css /finans.html /harcamalar.html /cari.html /belgeler.html /office.html /image-jobs.html /finans/core.js; do
  echo "$u $(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8091$u")"
done
echo "yedek: $YEDEK  (geri alma: $YEDEK/geri-al.sh)"
