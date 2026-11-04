#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - AI SAGLAYICI TANISI
#
# NEDEN VAR
# Kirmizi takim kurulu her karar icin en az IKI bagimsiz gorus ister.
# 22.09.2026'da olculdu: dort saglayicidan yalnizca BIRI donuyordu, kurul
# yeter sayiya ulasamiyor ve her karara "INSUFFICIENT_EVIDENCE" diyordu.
# Sebepler kayitliydi (core.ai_red_team_attempt.failover_reason) ama
# KIMSE OKUMUYORDU. gemini saglayicisi ALTI GUNDUR "not configured"
# duserken bu hicbir ekranda gorunmedi; elle kazarak bulundu.
#
# 🔴 Kayit tutmak ogrenmek degildir. Bu betik ham hata metinlerini
#    EYLEME DONUSEBILIR siniflara cevirir ve her sinif icin ne
#    yapilmasi gerektigini yazar.
#
# 🔴 E-POSTA GONDERMEZ. Sahip zaten alarm selinden sikayetciydi; bu bir
#    durum ekranidir, yeni bir alarm kaynagi degil.
#
# Kullanim:
#   ./ai-saglayici-tani.sh            Insan icin rapor
#   ./ai-saglayici-tani.sh --satir    saglik.sh icin tek satirlik ozet
#   ./ai-saglayici-tani.sh --siniflandir < dosya
#       stdin'den 'saglayici|sonuc|sebep' satirlari okur, siniflandirir.
#       Veritabani gerektirmez - testler bu kapidan girer.
# =============================================================================
set -uo pipefail

KOK="${LCARLIE_KOK:-/opt/lcarlie}"
GUN="${AI_TANI_GUN:-7}"
PSQL="${AI_TANI_PSQL:-docker exec lcarlie-postgres psql -U n8n -d n8n -tAc}"

# -----------------------------------------------------------------------------
# Ham hata metnini eyleme donusebilir sinifa cevirir.
# Cikti: SINIF|NE YAPILMALI
# -----------------------------------------------------------------------------
siniflandir() {
  local s
  s="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  case "$s" in
    *"not configured"*|*"no adapter"*)
      echo "ADAPTOR_YOK|Saglayici zincirde tanimli ama kodu yok. Zincirden cikar ya da adaptorunu yaz." ;;
    *"http 401"*|*"oauth"*|*"invalid authentication"*|*"unauthorized"*)
      echo "KIMLIK_401|Anahtar reddedildi. Google uclarinda anahtari '?key=' ile DEGIL 'x-goog-api-key' basligiyla gonder; digerlerinde anahtari yenile." ;;
    *"http 403"*|*"permission denied"*|*"forbidden"*)
      echo "YETKI_403|Anahtar gecerli ama bu API/proje icin yetkisi yok. Ilgili API'yi projede etkinlestir." ;;
    *"http 429"*|*"rate limit"*|*"quota"*|*"resource_exhausted"*)
      echo "KOTA_429|Kota veya hiz siniri. Zincirde bu saglayiciyi geriye al ya da kotayi yukselt." ;;
    *truncated*|*"max_tokens"*|*"max_output_tokens"*)
      echo "KESILDI|Cevap token sinirinda kesildi. Dusunme bahcesini sinirla (thinkingBudget/effort) ve RED_TEAM_MAX_TOKENS'i yukselt." ;;
    *"http 400"*|*"invalid argument"*|*"invalid_request"*)
      echo "ISTEK_400|Istek bicimi modele uymuyor. Model adini ve gonderilen parametreleri dogrula (ornek: bazi modeller thinkingConfig kabul etmez)." ;;
    *"no json"*|*"invalid output"*)
      echo "BICIM|Model JSON uretmedi. responseMimeType/response_format ayarini ve istemi kontrol et." ;;
    *"unsafe output"*)
      echo "GUVENLIK|Cikti guvenlik suzgecine takildi. Bu bir HATA DEGIL, kapinin calistigi anlamina gelir." ;;
    *timeout*|*abort*|*"etimedout"*|*"econnrefused"*|*"enotfound"*)
      echo "AG|Uca ulasilamadi veya zaman asimi. DNS/cikis erisimini ve ucun durumunu kontrol et." ;;
    ""|*"council opinion"*)
      echo "OK|-" ;;
    *)
      echo "BILINMEYEN|Siniflandirilamadi. Ham metni oku ve bu betige yeni bir kural ekle." ;;
  esac
}

# --- --siniflandir: veritabanisiz kapi (testler buradan girer) ---------------
if [ "${1:-}" = "--siniflandir" ]; then
  # 🔴 DEVAM SATIRLARI ATLANIR.
  #    Bir hata sebebi cok satirli JSON govdesi olabilir; o zaman 2. ve
  #    sonraki satirlar ('  "code": 401,' gibi) ayri birer kayit sanilir
  #    ve ilk alanlari saglayici adi yerine gecer. Ilk surumde raporda
  #    '"code": 401,' diye bir "saglayici" belirdi. Gercek saglayici adi
  #    daima tek kelimedir; oyle olmayan satir bir onceki kaydin
  #    devamidir ve kendi basina siniflandirilmaz.
  ONCEKI_SEBEP=""
  while IFS='|' read -r sag sonuc sebep; do
    case "${sag:-}" in
      *[!A-Za-z0-9_-]*|"")
        # Devam satiri: sebebe eklenir, ayri kayit olarak BASILMAZ.
        ONCEKI_SEBEP="$ONCEKI_SEBEP $sag $sonuc $sebep"
        continue ;;
    esac
    if [ "$sonuc" = "SUCCESS" ]; then
      printf '%s|OK|-\n' "$sag"
      ONCEKI_SEBEP=""
    else
      ONCEKI_SEBEP="${sebep:-}"
      printf '%s|%s\n' "$sag" "$(siniflandir "$ONCEKI_SEBEP")"
    fi
  done
  exit 0
fi

sorgu() { $PSQL "$1" 2>/dev/null; }

# --- Saglayici basina son GUN gunun ozeti ------------------------------------
# 🔴 SATIR SONLARI SORGUDA TEMIZLENIR.
#    failover_reason cogu zaman COK SATIRLI bir JSON hata govdesi tutuyor
#    ("HTTP 401 {\n  \"error\": {\n ..."). psql -tAc her satiri ayri
#    basar; ilk surumde bu satirlar ayri birer saglayici sanildi ve
#    raporda '"code": 401,' diye bir "saglayici" belirdi. Alan ayraci
#    '|' ile birlikte satir sonlari da kaynakta duzlestirilir.
HAM="$(sorgu "
  SELECT provider, result_class,
         left(regexp_replace(
                replace(coalesce(failover_reason, ''), '|', '/'),
                '[[:space:]]+', ' ', 'g'), 200)
  FROM core.ai_red_team_attempt
  WHERE started_at > now() - interval '$GUN days'
  ORDER BY attempt_id;")"

# --- Kurul yeter sayisi: son 10 kararda kac gorus toplandi -------------------
KURUL="$(sorgu "
  SELECT count(*) FILTER (WHERE gorus >= 2), count(*)
  FROM (
    SELECT job_id, count(*) FILTER (WHERE result_class='SUCCESS') AS gorus
    FROM core.ai_red_team_attempt
    WHERE started_at > now() - interval '$GUN days'
    GROUP BY job_id ORDER BY max(attempt_id) DESC LIMIT 10
  ) t;")"
YETER="${KURUL%%|*}"; TOPLAM="${KURUL##*|}"
case "$YETER" in (''|*[!0-9]*) YETER=0 ;; esac
case "$TOPLAM" in (''|*[!0-9]*) TOPLAM=0 ;; esac

# --- --satir: saglik.sh icin tek satir ---------------------------------------
if [ "${1:-}" = "--satir" ]; then
  if [ "$TOPLAM" -eq 0 ]; then
    echo "KONSEY|NO_DATA|0/0|son $GUN gunde kirmizi takim isi yok"
    exit 0
  fi
  # 🔴 Yalniz gercek saglayici adlari: harf/rakam/tire/alt cizgi. Bozuk bir
  #    kayit saglayici adi yerine hata metninin bir parcasini tasirsa,
  #    durum satiri okunamaz hale gelir - ilk surumde tam bu oldu.
  BOZUK="$(printf '%s\n' "$HAM" \
    | awk -F'|' '$2!="SUCCESS" && $1 ~ /^[A-Za-z0-9_-]+$/ {print $1}' \
    | sort -u | paste -sd, - | cut -c1-80)"
  if [ "$YETER" -eq "$TOPLAM" ]; then
    echo "KONSEY|SUCCESS|$YETER/$TOPLAM|son $TOPLAM kararin hepsi iki gorus aldi${BOZUK:+ (duzensiz: $BOZUK)}"
  else
    # 🔴 Alarm/e-posta URETMEZ - yalnizca gosterge. Karar incelenmeden
    #    gecmis olmasi onemlidir ama sahibin gelen kutusuna dusmemeli.
    echo "KONSEY|DEGRADED|$YETER/$TOPLAM|$((TOPLAM-YETER)) karar iki bagimsiz gorus almadan gecti${BOZUK:+ · dusen: $BOZUK}"
  fi
  exit 0
fi

# --- Insan icin rapor ---------------------------------------------------------
printf '=== AI SAGLAYICI TANISI (son %s gun) ===\n\n' "$GUN"
printf 'Kurul yeter sayisi : %s/%s karar iki bagimsiz gorus aldi\n\n' "$YETER" "$TOPLAM"

if [ -z "$HAM" ]; then
  echo "Bu pencerede hic deneme yok."
  exit 0
fi

printf '%-10s %-8s %-8s %s\n' "SAGLAYICI" "BASARI" "DENEME" "BASKIN SORUN"
printf -- '-%.0s' $(seq 1 78); printf '\n'

printf '%s\n' "$HAM" | awk -F'|' '$1 ~ /^[A-Za-z0-9_-]+$/ {print $1}' | sort -u | while read -r P; do
  TOP="$(printf '%s\n' "$HAM" | awk -F'|' -v p="$P" '$1==p' | wc -l)"
  OK="$(printf '%s\n' "$HAM" | awk -F'|' -v p="$P" '$1==p && $2=="SUCCESS"' | wc -l)"
  SEBEP="$(printf '%s\n' "$HAM" | awk -F'|' -v p="$P" '$1==p && $2!="SUCCESS"{print $3}' \
           | sort | uniq -c | sort -rn | head -1 | sed 's/^ *[0-9]* *//')"
  if [ "$TOP" -gt 0 ]; then ORAN=$(( OK * 100 / TOP )); else ORAN=0; fi
  if [ -n "$SEBEP" ]; then
    TANI="$(siniflandir "$SEBEP")"
    printf '%-10s %-8s %-8s %s\n' "$P" "%$ORAN" "$TOP" "${TANI%%|*}"
    printf '%-28s -> %s\n' "" "${TANI#*|}"
  else
    printf '%-10s %-8s %-8s %s\n' "$P" "%$ORAN" "$TOP" "-"
  fi
done

echo
echo "Ham sebepler (son 5 basarisiz deneme):"
printf '%s\n' "$HAM" | awk -F'|' '$2!="SUCCESS" && $1!=""' | tail -5 \
  | while IFS='|' read -r p r s; do printf '  %-10s %s\n' "$p" "${s:0:64}"; done
