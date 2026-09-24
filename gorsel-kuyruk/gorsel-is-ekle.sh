#!/bin/bash
# Kuyruga bir gorsel isi ekler.
#
# Kullanim:
#   gorsel-is-ekle.sh "<istem>" [adet] [negatif]
#
# Is JSON olarak bekleyen/ dizinine dusuyor. PC-2'deki hakem 20 sn icinde
# goruyor, LLM'i birakip ComfyUI'yi aciyor, uretip geri donuyor.
#
# 🔴 PC-2'nin VRAM'i LLM ile gorsel uretimini AYNI ANDA tasiyamiyor
# (olculdu: 10,4 GB gerekli, 8,15 GB var). Yani bir gorsel isi, LLM'i
# yaklasik bir dakikaligina dusurur. Bu bir hata degil, tasarim.
set -euo pipefail
K=/opt/lcarlie/gorsel-kuyruk
[ $# -ge 1 ] || { echo "kullanim: $0 \"<istem>\" [adet] [negatif]" >&2; exit 2; }
ISTEM="$1"; ADET="${2:-1}"; NEG="${3:-bottle, jar, tube, box, container, vase, podium, pedestal, any object in the centre, text, logo, watermark, people, hands, clutter, low quality, blurry}"
ID="is-$(date +%Y%m%dT%H%M%S)-$RANDOM"
python3 - "$K/bekleyen/$ID.json" "$ID" "$ISTEM" "$NEG" "$ADET" <<'PY'
import json, sys, datetime
yol, kimlik, istem, negatif, adet = sys.argv[1:6]
json.dump({
    "id": kimlik,
    "olusturuldu": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "istem": istem,
    "negatif": negatif,
    "adet": int(adet),
    "genislik": 1024, "yukseklik": 1024,
    "adim": 28, "cfg": 8.5,
}, open(yol, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
echo "kuyruga alindi: $ID"
echo "  bekleyen: $(ls -1 $K/bekleyen/*.json 2>/dev/null | wc -l)"
