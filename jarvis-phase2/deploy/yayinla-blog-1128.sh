#!/bin/bash
# BLOG HATTI 28.11.2026 kurallari canliya alma.
# Sahip 28.11: "Bloglarda asla olumsuz bir sey istemiyorum; gorselleri GPT'ye en guzel
# mockup olarak urettir; SEO ve GEO'da ciksin, bos yazi olmasin. 10/10 istiyorum."
#   - jarvis/blog_hatti.py : olumsuz dil kapisi, SEO/GEO kapisi, INCI'ye dayali urun-konu
#                            secimi, etiket (ambalaj) OCR denetimi, gorunum hazirligi
#                            (baglanti rengi, tipografik tirnak, genis tablo -> liste,
#                            Guncellendi satiri, urun yonlendirmesi), SSS semasi govdeden
#   - scripts/blog-hatti.py: olumlu yeniden yazim, ChatGPT kapak (gercek urun referansli)
#                            + ic gorsel, kapak yazinin basinda, yenile/denetle komutlari
# Yalniz depodaki commit'te degisen dosyalari kopyalar; canli dosya depodaki ONCEKI
# surumle ayni degilse DURUR. Servis yeniden baslatmaz (blog hatti tek seferlik kosar).
# Geri alma: yedek dizinindeki dosyalari geri kopyala.
set -euo pipefail
K=${1:?kullanim: yayinla-blog-1128.sh commit [onceki-commit]}
O=${2:-$K~1}
DEPO=/opt/lcarlie/source/lcarlie-jarvis-v1
L=/opt/lcarlie/jarvis-phase2
YEDEK=/opt/lcarlie/backup/jarvis-webconsole/blog-1128-$(date +%Y%m%d-%H%M%S)
DEGISEN=$(git -C $DEPO diff --name-only --diff-filter=M "$O" "$K" -- jarvis-phase2/jarvis/blog_hatti.py jarvis-phase2/scripts/blog-hatti.py jarvis-phase2/tests/test_blog_hatti.py | sed 's#^jarvis-phase2/##')
[ -n "$DEGISEN" ] || { echo "degisen dosya yok"; exit 0; }
cd $L
for f in $DEGISEN; do
  if [ -f "$f" ] && ! git -C $DEPO show "$O:jarvis-phase2/$f" | cmp -s - "$f"; then
    echo "DURDU: canli $f depodaki onceki surumle ayni degil; hicbir sey kopyalanmadi"; exit 3
  fi
done
if systemctl is-active --quiet lcarlie-blog-hatti.service; then echo "DURDU: blog hatti su an kosuyor"; exit 5; fi
mkdir -p "$YEDEK"
for f in $DEGISEN; do
  mkdir -p "$YEDEK/$(dirname "$f")" "$(dirname "$f")"
  if [ -f "$f" ]; then cp -p "$f" "$YEDEK/$f"; fi
  git -C $DEPO show "$K:jarvis-phase2/$f" > "$f.yeni"
  chmod 644 "$f.yeni"; mv "$f.yeni" "$f"
done
chmod 755 scripts/blog-hatti.py
geri_al() { for f in $DEGISEN; do [ -f "$YEDEK/$f" ] && cp -p "$YEDEK/$f" "$f"; done; }
if ! $L/venv/bin/python -m unittest tests.test_blog_hatti >/tmp/blog-1128-test.txt 2>&1; then
  echo "TEST KIRMIZI -- geri aliniyor"; tail -25 /tmp/blog-1128-test.txt; geri_al; exit 4
fi
tail -3 /tmp/blog-1128-test.txt
$L/venv/bin/python scripts/blog-hatti.py denetle | tail -1
echo "yedek: $YEDEK"
