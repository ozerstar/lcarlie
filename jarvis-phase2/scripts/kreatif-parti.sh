#!/usr/bin/env bash
# KREATİF PARTİSİ (4 GÜNDE BİR) — TÜM ÜRÜNLER için brief ve promptlar.
#
# 🔴 SAHİP KARARI (21.09.2026), verbatim:
#    "brief verilsin, üretim benim onayım olmadan yapılmasın ama promptlar
#     hazırlansın. bu tüm ürünler için yapılacak, araştırılacak, haftalık tüm
#     ürünler için konu bulunacak, promptlar hazırlanacak, rakipler ne yapmış
#     ne tutuyor ne iyi ne kötü bakılacak."
#
# Bu betik HİÇ GÖRSEL ÜRETMEZ. Ürettiği şey araştırmadır:
#   ürün gerçeği · rakip fiyatı · rakibin satış cümleleri · alıcı itirazları ·
#   RAKİBİN KREATİFİ (format, tutan gönderi, zayıf kalan yaklaşım) ·
#   15 departmanın veriye bakınca söylediği · denetimden geçmiş satış
#   cümleleri · image modeline yapıştırılacak hazır promptlar.
#
# Her ürün için bir öneri açılır; onaylanan ürünün görselleri üretilir.
# Görsel üretimi `kreatif-uret.sh` işidir ve onaydan SONRA koşar.
set -uo pipefail   # -e YOK: bir ürünün patlaması partiyi bitirmemeli

KOK="/opt/lcarlie/jarvis-phase2"
PY="$KOK/venv/bin/python"
export JARVIS_MEMORY_TRANSPORT="${JARVIS_MEMORY_TRANSPORT:-local-docker}"
GORSEL_SAYISI="${KREATIF_PROMPT_SAYISI:-4}"
# 🔴 Sınır var ve bilerek var: her ürün 4 grounded arama + 3 model çağrısı
# demek. Sınırsız koşmak faturayı ve onay kuyruğunu aynı anda şişirir.
AZAMI="${KREATIF_AZAMI_URUN:-40}"

# 🔴 SENARYO HER ÜRÜNDE. Kreatif hattı 21.09.2026'ya kadar yalnız durağan
# görsel üretiyordu; UGC video senaryosu katmanı eklendi ve zamanlayıcıya
# BAĞLANMAMIŞTI -- yani elle çalıştırdığımda var olan bir yetenekti.
SENARYO_SAYISI="${KREATIF_SENARYO_SAYISI:-3}"

# 🔴 DERİN ARAŞTIRMA VE GÜÇLÜ MODEL DÖNÜŞÜMLÜ KOŞAR, HEPSİNDE DEĞİL.
# Ölçülen maliyet: derin araştırma ürün başına 11 grounded arama (temel 4),
# güçlü model ise ÜCRETLİ dış sağlayıcıya gidiyor. 36 ürüne her koşuda
# uygulamak 4 günde bir ~400 arama + ~180 ücretli çağrı demekti.
#
# Bunun yerine her koşuda DERIN_URUN kadar ürün tam donanımla işlenir ve
# başlangıç noktası her koşuda kayar; böylece bütün katalog birkaç turda
# dolaşılır, maliyet ise koşu başına sabit kalır.
DERIN_URUN="${KREATIF_DERIN_URUN:-6}"
KAYDIRMA_DOSYASI="$KOK/state/kreatif-parti-kaydirma"

cd "$KOK"

echo "=== KREATİF PARTİSİ · $(date -Is) ==="

# Ürün listesi katalogdan. Sırayı KARIŞTIRMIYORUZ: aynı sıra her hafta aynı
# ürünle başlasın ki bir ürün sürekli sona kalıp hiç işlenmesin.
mapfile -t URUNLER < <("$PY" - <<'PY'
import sys
sys.path.insert(0, "/opt/lcarlie/jarvis-phase2")
from jarvis.memory import CompanyMemory
try:
    kayitlar = CompanyMemory(host=None)._fetch("urun_karti").records
except Exception as hata:            # noqa: BLE001
    print(f"KATALOG_OKUNAMADI {hata}", file=sys.stderr)
    raise SystemExit(1)
gorulen = set()
for k in kayitlar:
    ad = str(k.get("urun_adi") or "").split("|")[0].strip()
    # Yayında olmayan ürüne kreatif üretmek bosa istir.
    if not ad or ad in gorulen or not k.get("wix_yayinda"):
        continue
    gorulen.add(ad)
    print(ad)
PY
)

TOPLAM="${#URUNLER[@]}"
if [ "$TOPLAM" -eq 0 ]; then
  echo "katalogdan yayinda urun okunamadi" >&2
  exit 1
fi
echo "katalogda yayinda ${TOPLAM} urun · bu kosuda en fazla ${AZAMI}"

# Kaydırma: bu koşuda hangi ürünler tam donanımla işlenecek.
KAYDIRMA=0
[ -f "$KAYDIRMA_DOSYASI" ] && KAYDIRMA="$(cat "$KAYDIRMA_DOSYASI" 2>/dev/null || echo 0)"
case "$KAYDIRMA" in ''|*[!0-9]*) KAYDIRMA=0 ;; esac

# 🔴 PENCERE İŞLENEN DİLİME GÖRE HESAPLANIR, TÜM KATALOĞA GÖRE DEĞİL.
# Ölçüldü (22.09.2026 doğrulama koşusu): AZAMI=1, KAYDIRMA=1, TOPLAM=36 iken
# pencere 1. üründe başlıyordu ama koşu yalnız 0. ürünü işliyordu -- log
# "derin/guclu kosacak urun sayisi: 1" diyor, ürün TEMEL modda işleniyordu.
# Sessiz bir tutarsızlık: sayı doğru yazılıyor, iş yapılmıyor.
# KREATIF_AZAMI_URUN katalogdan küçük ayarlandığında üretimde de olur.
ISLENEN=$(( AZAMI < TOPLAM ? AZAMI : TOPLAM ))
[ "$ISLENEN" -gt 0 ] || ISLENEN=1
KAYDIRMA=$(( KAYDIRMA % ISLENEN ))
echo "derin/guclu kosacak urun sayisi: ${DERIN_URUN} (kaydirma ${KAYDIRMA}, islenen ${ISLENEN})"

BASARI=0; HATA=0; SIRA=0; DERIN_SAYAC=0
for URUN in "${URUNLER[@]:0:$AZAMI}"; do
  # Bu ürün tam donanım penceresinde mi?
  EK_BAYRAK=()
  if [ "$DERIN_URUN" -gt 0 ]; then
    UZAKLIK=$(( (SIRA - KAYDIRMA + ISLENEN) % ISLENEN ))
    if [ "$UZAKLIK" -lt "$DERIN_URUN" ]; then
      EK_BAYRAK=(--derin --guclu)
      DERIN_SAYAC=$((DERIN_SAYAC+1))
    fi
  fi
  SIRA=$((SIRA+1))
  echo
  echo "--- $URUN ---"
  [ "${#EK_BAYRAK[@]}" -gt 0 ] && echo "  (derin arastirma + guclu model)"
  if ! "$PY" scripts/kreatif-brief.py "$URUN" \
        --gorsel "$GORSEL_SAYISI" --senaryo "$SENARYO_SAYISI" \
        "${EK_BAYRAK[@]+"${EK_BAYRAK[@]}"}"; then
    echo "  BRIEF HATASI, atlandi: $URUN" >&2
    HATA=$((HATA+1))
    continue
  fi
  BRIEF="$(ls -1t state/kreatif-brief/*.json 2>/dev/null | head -n1)"
  PARTI="$(basename "${BRIEF%.json}")"
  if ! "$KOK/bin/jarvis-operator" create-task KREATIF_BRIEF "$PARTI" >/dev/null; then
    echo "  GOREV ACILAMADI: $PARTI" >&2
    HATA=$((HATA+1))
    continue
  fi
  echo "  -> onay kuyruguna: $PARTI"
  BASARI=$((BASARI+1))
done

# Kaydırmayı ilerlet ki bir sonraki koşuda SIRADAKİ ürünler tam donanım
# alsın. Yazamazsak koşu başarısız sayılmaz -- sadece aynı pencere tekrarlanır.
if [ "$DERIN_URUN" -gt 0 ] && [ "$ISLENEN" -gt 0 ]; then
  YENI_KAYDIRMA=$(( (KAYDIRMA + DERIN_URUN) % ISLENEN ))
  mkdir -p "$(dirname "$KAYDIRMA_DOSYASI")"
  echo "$YENI_KAYDIRMA" > "$KAYDIRMA_DOSYASI" 2>/dev/null \
    || echo "  kaydirma yazilamadi, ayni pencere tekrarlanacak" >&2
fi

echo
echo "=== PARTI BITTI: $BASARI brief onay kuyrugunda, $HATA hata ==="
echo "    tam donanimla islenen: $DERIN_SAYAC urun"
[ "$BASARI" -gt 0 ] || exit 1
