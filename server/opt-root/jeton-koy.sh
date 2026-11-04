#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - JETONU DOSYADAN .env'E KOY
#
# 🔴 JETON DEGERI HICBIR ZAMAN EKRANA BASILMAZ, LOGA YAZILMAZ, KOMUT
#    SATIRINA KONMAZ. Komut satiri argumanlari 'ps' ile herkese gorunur;
#    bu yuzden deger DOSYADAN okunur, arguman olarak gecilmez.
#
# 🔴 Islem bitince kaynak dosya 'shred' ile silinir - 'rm' diskte veriyi
#    birakir.
#
# 🔴 .env DEGISMEDEN once yedeklenir. Bozuk bir .env tum hatti durdurur.
#
# Kullanim: jeton-koy.sh <ANAHTAR_ADI> <DOSYA_YOLU> [--sakla]
#           --sakla : kaynak dosyayi silme (test icin)
# =============================================================================
set -uo pipefail

ENV=/opt/lcarlie/n8n/.env
ANAHTAR="${1:-}"
DOSYA="${2:-}"
SAKLA=0
[ "${3:-}" = "--sakla" ] && SAKLA=1

if [ -z "$ANAHTAR" ] || [ -z "$DOSYA" ]; then
  echo "Kullanim: jeton-koy.sh <ANAHTAR_ADI> <DOSYA_YOLU> [--sakla]" >&2
  exit 1
fi
if ! [[ "$ANAHTAR" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
  echo "HATA: anahtar adi yalniz BUYUK harf, rakam ve _ icerebilir." >&2
  exit 1
fi
if [ ! -f "$DOSYA" ]; then
  echo "HATA: dosya yok: $DOSYA" >&2
  exit 1
fi
if [ ! -f "$ENV" ]; then
  echo "HATA: .env bulunamadi: $ENV" >&2
  exit 1
fi

# Degeri oku - ekrana BASMADAN. CR/LF ve bas/son bosluklari temizle.
DEGER="$(tr -d '\r\n' < "$DOSYA" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
UZUNLUK=${#DEGER}

# 🔴 Bos/kisa deger sessizce yazilmaz. Yanlis jetonla calisan bir hat,
#    hic calismayan hattan daha kotudur: "bagli" gorunur ama veri gelmez.
if [ "$UZUNLUK" -lt 40 ]; then
  echo "HATA: deger cok kisa ($UZUNLUK karakter). Kopyalama eksik olabilir." >&2
  exit 1
fi
case "$DEGER" in
  *[[:space:]]*) echo "HATA: deger bosluk iceriyor - kopyalamada fazlalik var." >&2; exit 1 ;;
esac

YEDEK="$ENV.yedek-$(date +%Y%m%d-%H%M%S)"
cp -p "$ENV" "$YEDEK" || { echo "HATA: .env yedeklenemedi." >&2; exit 1; }

# Yazma islemi python ile: sed kullanilsa jetondaki /, &, \ karakterleri
# ifadeyi bozardi.
ANAHTAR="$ANAHTAR" DEGER="$DEGER" ENVYOL="$ENV" python3 - <<'PY'
import os, re, sys
anahtar = os.environ["ANAHTAR"]; deger = os.environ["DEGER"]; yol = os.environ["ENVYOL"]
with open(yol, "r", encoding="utf-8") as f:
    satirlar = f.read().split("\n")
desen = re.compile(r"^" + re.escape(anahtar) + r"=")
bulundu = False
for i, s in enumerate(satirlar):
    if desen.match(s):
        satirlar[i] = "%s=%s" % (anahtar, deger); bulundu = True; break
if not bulundu:
    while satirlar and satirlar[-1] == "":
        satirlar.pop()
    satirlar.append("%s=%s" % (anahtar, deger))
    satirlar.append("")
with open(yol, "w", encoding="utf-8") as f:
    f.write("\n".join(satirlar))
print("  %s %s" % ("degistirildi" if bulundu else "eklendi", anahtar))
PY
KOD=$?

if [ "$KOD" -ne 0 ]; then
  cp -p "$YEDEK" "$ENV"
  echo "HATA: yazma basarisiz, .env geri alindi." >&2
  exit 1
fi

# Dogrula: anahtar var mi ve uzunlugu tuttu mu (DEGERI BASMADAN)
OKUNAN="$(grep -m1 "^${ANAHTAR}=" "$ENV" | cut -d= -f2-)"
if [ "${#OKUNAN}" -ne "$UZUNLUK" ]; then
  cp -p "$YEDEK" "$ENV"
  echo "HATA: yazilan uzunluk tutmadi (${#OKUNAN} != $UZUNLUK), .env geri alindi." >&2
  exit 1
fi

chmod 600 "$ENV"
echo "  $ANAHTAR yazildi ($UZUNLUK karakter) - deger hicbir yere basilmadi"
echo "  yedek: $YEDEK"

if [ "$SAKLA" -eq 0 ]; then
  shred -u "$DOSYA" 2>/dev/null || rm -f "$DOSYA"
  echo "  kaynak dosya shred ile silindi"
fi
exit 0
