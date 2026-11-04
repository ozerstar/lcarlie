#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - ALARM MERKEZI
#
# CR-002 madde 8 · 15.09.2026
#
# Sistemdeki TEK bildirim kapisi. Yedekleme, saglik toplayici ve fiyat
# logu bu betigi cagirir.
#
# 🔴 NEDEN AYRI BIR BETIK:
#    Onceki halinde bildirim mantigi yalniz backup.sh icindeydi ve
#    (a) tekrar bastirma (dedup) yoktu -> ayni ariza her gece mail atardi,
#    (b) mail gonderilemezse olay HICBIR YERDE kalmiyordu,
#    (c) baska hicbir betik alarm uretemiyordu.
#
# 🔴 EN ONEMLI KURAL: E-POSTA IKINCIL, LOG BIRINCILDIR.
#    CR-002 sirasinda /root/.msmtprc'nin DOLDURULMAMIS bir sablon oldugu
#    ortaya cikti (user=BURAYA_GONDEREN_EPOSTA, SMTP 535 BadCredentials).
#    Yani "alarm = e-posta" varsayan bir tasarim, kurulumundan beri
#    tek bir alarm bile uretmemis olurdu ve kimse fark etmezdi.
#    Bu yuzden her olay ONCE diske yazilir; e-posta sonra DENENIR ve
#    denemenin sonucu da ayrica kaydedilir.
#
# 🔴 CIKIS KODU HER ZAMAN 0.
#    Alarm mekanizmasi, kendisini cagiran uretim betigini asla dusurmez.
#
# Kullanim:
#   alarm.sh <SEVIYE> <ANAHTAR> <BASLIK> [DETAY...]
#   ... | alarm.sh <SEVIYE> <ANAHTAR> <BASLIK>        (detay stdin'den)
#
#   SEVIYE : FAILED | DEGRADED | UYARI | BILGI | COZULDU
#   ANAHTAR: olayin kimligi (dedup bunun uzerinden yapilir)
#            ornek: backup.drive, wf.lcarlieInsta01.failed, sys.disk
#
#   COZULDU : dedup durumunu temizler, "duzeldi" bilgisi gonderir.
#
# Ortam degiskeni ile gecici olarak: ALARM_DEDUP_DK=0 alarm.sh ... (dedup kapali)
# =============================================================================
set -uo pipefail

# 🔴 LCARLIE_KOK yalnizca TEST icindir. Uretimde ayarlanmaz ve varsayilan
#    /opt/lcarlie kullanilir. Sabit kodluyken bu betigin davranisi hic
#    sinanamiyordu: "islemsiz COZULDU gunluge yazilmasin" gibi bir kurali
#    dogrulamanin tek yolu uretim gunlugune yazmakti.
KOK="${LCARLIE_KOK:-/opt/lcarlie}"
CONF="$KOK/uretim-workflowlari.conf"
BCONF="$KOK/backup/backup.conf"
# 🔴 Yoklama gibi test kosumlari gercek posta hesabina baglanmasin diye
#    yapilandirma yolu da geçersiz kilinabilir; uretimde sabit kalir.
MSMTPRC="${MSMTPRC:-/root/.msmtprc}"

ALARM_LOG="$KOK/alarm.log"                    # BIRINCIL kalici kayit
GONDERILEMEDI="$KOK/alarm-gonderilemedi.log"  # IKINCIL: mail gidemeyen olaylar
DURUM_DIZIN="$KOK/alarm-durum"                # dedup durumu
SAYAC="$DURUM_DIZIN/_saatlik.sayac"

# --- Varsayilanlar (conf yoksa da calisir) -----------------------------------
ALARM_DEDUP_DK_VARSAYILAN=360
ALARM_SAATLIK_TAVAN_VARSAYILAN=12

# shellcheck disable=SC1090
[ -r "$CONF" ] && . "$CONF"
DEDUP_DK="${ALARM_DEDUP_DK:-$ALARM_DEDUP_DK_VARSAYILAN}"
TAVAN="${ALARM_SAATLIK_TAVAN:-$ALARM_SAATLIK_TAVAN_VARSAYILAN}"

NOTIFY_EMAIL=""
# shellcheck disable=SC1090
[ -r "$BCONF" ] && . "$BCONF"

mkdir -p "$DURUM_DIZIN" 2>/dev/null || true

# --- Girdi -------------------------------------------------------------------
SEVIYE="${1:-BILGI}"
ANAHTAR="${2:-genel}"
BASLIK="${3:-(baslik yok)}"
shift 3 2>/dev/null || true
DETAY="${*:-}"

# stdin'den detay okuma (boru ile cagrilabilsin)
#
# 🔴 BURASI BETIGI ASTI - CR-002 sirasinda canlida yasandi.
#    Onceki hali yalnizca '[ ! -t 0 ]' bakiyordu: "terminal degilse oku".
#    Ama stdin bir SOKET de olabilir (ssh ile calistirinca oyle oluyor) ve
#    'cat' EOF gelmedigi icin SONSUZA KADAR BEKLIYOR. alarm.sh'i backup.sh,
#    saglik.sh ve cron cagiriyor; asili bir alarm GECE YEDEGINI bloke eder.
#    Yani bildirim mekanizmasi, bildirecegi sistemi durdurabilirdi.
#
#    Iki katmanli koruma:
#      1) Yalnizca BORU (-p) veya DUZ DOSYA (-f) ise oku - soket/tty asla
#      2) O durumda bile 'timeout 5' ile sinirla
#      3) Detay zaten argumanla verildiyse stdin'e HIC bakma - bugunku tum
#         cagiranlar (backup.sh, saglik.sh) detayi arguman olarak veriyor,
#         yani normal isleyiste bu blok hic calismaz ve gecikme olmaz.
if [ -z "$DETAY" ] && { [ -p /dev/stdin ] || { [ ! -t 0 ] && [ -f /dev/stdin ]; }; }; then
  STDIN_DETAY="$(timeout 5 cat 2>/dev/null || true)"
  [ -n "$STDIN_DETAY" ] && DETAY="${DETAY:+$DETAY
}$STDIN_DETAY"
fi

ZAMAN="$(date -Is)"
SAAT_EPOCH="$(date +%s)"
# Anahtari dosya adina cevir (yol gezinmesi olmasin)
GUVENLI_ANAHTAR="$(printf '%s' "$ANAHTAR" | tr -c 'A-Za-z0-9._-' '_')"
DURUM_DOSYA="$DURUM_DIZIN/$GUVENLI_ANAHTAR"

# -----------------------------------------------------------------------------
# 1) BIRINCIL KAYIT - her zaman, kosulsuz
# -----------------------------------------------------------------------------
# Tek satir, boru ile ayrilmis; satir sonlari detayda ' / ' olur.
# 🔴 '|' AYIRICI OLDUGU ICIN DETAYDAN TEMIZLENIR.
#    Detayda bir '|' kalirsa log satirini okuyan taraf (durum sayfasi)
#    alanlari kaydirir ve "posta" sutununda detay parcasi gorunur -
#    yani gonderim durumu YANLIS okunur.
DETAY_TEK_SATIR="$(printf '%s' "$DETAY" | tr '\n|' '/ ' | tr -s '/' | cut -c1-600)"
yaz_log() {
  printf '%s|%s|%s|%s|%s|posta=%s\n' \
    "$ZAMAN" "$SEVIYE" "$ANAHTAR" "$BASLIK" "$DETAY_TEK_SATIR" "$1" >>"$ALARM_LOG" 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# 2) COZULDU - dedup durumunu temizle
# -----------------------------------------------------------------------------
if [ "$SEVIYE" = "COZULDU" ]; then
  if [ -f "$DURUM_DOSYA" ]; then
    rm -f "$DURUM_DOSYA" 2>/dev/null || true
    # Yalnizca gercekten acik bir alarm varsa "duzeldi" bildirimi gonderilir.
    GONDER=1
  else
    GONDER=0
  fi
else
  GONDER=1
fi

# -----------------------------------------------------------------------------
# 3) DEDUP - ayni anahtar+seviye icin pencere icinde tekrar mail yok
#    (LOG YINE YAZILIR - olay kaybolmaz, yalnizca mail bastirilir)
# -----------------------------------------------------------------------------
BASTIRILDI=0
if [ "$GONDER" = "1" ] && [ "$SEVIYE" != "COZULDU" ] && [ "$DEDUP_DK" -gt 0 ] 2>/dev/null; then
  if [ -f "$DURUM_DOSYA" ]; then
    ONCEKI="$(cut -d'|' -f1 "$DURUM_DOSYA" 2>/dev/null)"
    ONCEKI_SEV="$(cut -d'|' -f2 "$DURUM_DOSYA" 2>/dev/null)"
    case "$ONCEKI" in (''|*[!0-9]*) ONCEKI=0 ;; esac
    GECEN_DK=$(( (SAAT_EPOCH - ONCEKI) / 60 ))
    # Seviye kotulestiyse dedup uygulanmaz - yukselen olay bildirilmeli.
    if [ "$ONCEKI_SEV" = "$SEVIYE" ] && [ "$GECEN_DK" -lt "$DEDUP_DK" ]; then
      BASTIRILDI=1
    fi
  fi
fi

# -----------------------------------------------------------------------------
# 4) FLOOD KORUMASI - saatlik tavan
# -----------------------------------------------------------------------------
if [ "$BASTIRILDI" = "0" ] && [ "$GONDER" = "1" ]; then
  SAAT_ETIKET="$(date +%Y%m%d%H)"
  MEVCUT_ETIKET=""; MEVCUT_SAYI=0
  if [ -f "$SAYAC" ]; then
    MEVCUT_ETIKET="$(cut -d'|' -f1 "$SAYAC" 2>/dev/null)"
    MEVCUT_SAYI="$(cut -d'|' -f2 "$SAYAC" 2>/dev/null)"
    case "$MEVCUT_SAYI" in (''|*[!0-9]*) MEVCUT_SAYI=0 ;; esac
  fi
  [ "$MEVCUT_ETIKET" != "$SAAT_ETIKET" ] && MEVCUT_SAYI=0
  if [ "$MEVCUT_SAYI" -ge "$TAVAN" ]; then
    BASTIRILDI=2   # flood tavani
  else
    printf '%s|%s\n' "$SAAT_ETIKET" "$((MEVCUT_SAYI + 1))" >"$SAYAC" 2>/dev/null || true
  fi
fi

# -----------------------------------------------------------------------------
# 5) E-POSTA DENEMESI
# -----------------------------------------------------------------------------
posta_gonder() {
  # Yapilandirma eksikse dene bile deme - sebebi cagiran anlasin diye don.
  [ -n "${NOTIFY_EMAIL:-}" ] || { echo "ALICI_YOK"; return 1; }
  [ -r "$MSMTPRC" ]          || { echo "MSMTPRC_YOK"; return 1; }
  command -v msmtp >/dev/null 2>&1 || { echo "MSMTP_KURULU_DEGIL"; return 1; }

  # 🔴 msmtp'nin 'from' alani .msmtprc'den okunur ve From: basligi olarak
  #    yazilir. Onceki backup.sh 'msmtp --read-envelope-from' kullaniyordu
  #    ama uretilen mailde From: BASLIGI HIC YOKTU; msmtp bu durumda
  #    "envelope-from address is missing" deyip EX_NOPERM(78) ile cikiyordu.
  #    Yani NOTIFY_EMAIL doldurulmus olsa bile TEK BIR MAIL GITMEZDI.
  #    CR-002 testinde birebir dogrulandi.
  local MAIL_FROM
  MAIL_FROM="$(awk '$1=="from"{print $2; exit}' "$MSMTPRC" 2>/dev/null)"

  # Sablon hala doldurulmamissa mail denemesi anlamsiz - net sebep don.
  case "$MAIL_FROM" in
    ''|BURAYA_*) echo "MSMTPRC_DOLDURULMAMIS"; return 1 ;;
  esac

  # 🔴 ZAMAN ASIMI SART.
  #    CR-002 testinde msmtp, gecersiz kimlik bilgileriyle Gmail'e
  #    baglanirken DAKIKALARCA asili kaldi. alarm.sh'i backup.sh, saglik.sh
  #    ve cron cagiriyor; asili bir mail denemesi GECE YEDEGINI bloke eder
  #    ve tek slotlu sistemde zincirleme gecikme yaratir. Yani "haber verme"
  #    mekanizmasi, haber verecegi sistemi durdurabilirdi.
  #    25 sn: SMTP el sikismasi icin fazlasiyla yeterli, bekleme icin kisa.
  local CIKTI
  CIKTI="$( { printf 'From: %s\n' "$MAIL_FROM"
              printf 'To: %s\n' "$NOTIFY_EMAIL"
              printf 'Subject: [LCARLIE %s] %s\n' "$SEVIYE" "$BASLIK"
              printf 'Content-Type: text/plain; charset=utf-8\n'
              printf '\n'
              printf 'Seviye : %s\n' "$SEVIYE"
              printf 'Olay   : %s\n' "$ANAHTAR"
              printf 'Zaman  : %s\n' "$ZAMAN"
              printf 'Sunucu : 185.169.180.68\n'
              printf '\n%s\n' "$DETAY"
              printf '\n---\nTum alarm gecmisi: %s\n' "$ALARM_LOG"
            } | timeout 25 msmtp "$NOTIFY_EMAIL" 2>&1 )"
  local RC=$?
  if [ "$RC" -eq 0 ]; then
    echo "OK"; return 0
  fi
  if [ "$RC" -eq 124 ]; then
    echo "ZAMAN_ASIMI_25SN"; return 1
  fi
  # Hata metnini tek satira indir, sirlari tasimaz (msmtp sifre basmaz)
  printf '%s' "$CIKTI" | tr '\n' ' ' | cut -c1-300
  return 1
}

POSTA_SONUC="atlandi"
if [ "$GONDER" = "0" ]; then
  POSTA_SONUC="gereksiz"
elif [ "$BASTIRILDI" = "1" ]; then
  POSTA_SONUC="bastirildi-dedup"
elif [ "$BASTIRILDI" = "2" ]; then
  POSTA_SONUC="bastirildi-flood"
else
  # 🔴 BILGI seviyesi de e-posta gonderir - mevcut politika korunur.
  #    backup.conf'ta NOTIFY_ON_SUCCESS=1 yaziyor; "basarili yedek de
  #    bildirilsin" istenmis. Bunu sessizce kapatmak, kullanicinin
  #    yapilandirmasini gorusu alinmadan degistirmek olurdu.
  #
  #    Flooding riski dedup ile kapatiliyor: 'backup.basarili' anahtari
  #    ALARM_DEDUP_DK (360 dk) penceresinde bir kez mail atar. Gece yedegi
  #    bildirimini alir; her yayinlamada calisan 'backup.sh --yerel'
  #    bildirimleri ise bastirilir (log'a yine yazilir).
  SEBEP="$(posta_gonder)"
  if [ "$SEBEP" = "OK" ]; then
    POSTA_SONUC="gonderildi"
  else
    POSTA_SONUC="BASARISIZ:$SEBEP"
    # 🔴 IKINCIL MEKANIZMA: mail gidemediyse olay AYRI bir dosyaya da yazilir.
    #    Boylece "alarmin kendisi calismiyor" durumu da gorunur olur ve
    #    durum sayfasi bu dosyayi okuyup uyarabilir.
    printf '%s|%s|%s|%s|sebep=%s\n' \
      "$ZAMAN" "$SEVIYE" "$ANAHTAR" "$BASLIK" "$SEBEP" >>"$GONDERILEMEDI" 2>/dev/null || true
  fi
fi

# --- Dedup durumunu guncelle (mail gitmese de olay gorulmus sayilir) ---------
if [ "$SEVIYE" != "COZULDU" ] && [ "$BASTIRILDI" = "0" ]; then
  printf '%s|%s|%s\n' "$SAAT_EPOCH" "$SEVIYE" "$BASLIK" >"$DURUM_DOSYA" 2>/dev/null || true
fi

# 🔴 HICBIR SEYI COZMEYEN "COZULDU" GUNLUGE YAZILMAZ.
#
# Cagiranlar (saglik.sh, ticari-kontrol.sh, backup.sh, hazirlik-gunluk.sh,
# durum-uret.sh) kontrol SUCCESS oldugunda KOSULSUZ 'alarm COZULDU' cagirir.
# Acik alarm yoksa bu bir islemsizdir: mail gitmez, durum dosyasi zaten
# yoktur, temizlenecek bir sey yoktur. Yine de her calistirmada bir satir
# yaziliyordu.
#
# 22.09.2026 olcumu: 3323 satirlik alarm.log'un 1347'si (%40,5) tam olarak
# bu islemsiz satirdi - 628'i yalniz sys.disk. 15 dakikada bir, gunde 3
# anahtardan ~288 satir. Log 6000 satirda kirpiliyor; bu hizla gercek
# olaylar (toplam 140 satir) geri donulemez bicimde disari itilecekti.
#
# Olay kaybi YOK: gercekten acik bir alarmi kapatan COZULDU'de GONDER=1
# olur ve satir normal sekilde yazilir.
if [ "$SEVIYE" = "COZULDU" ] && [ "$GONDER" = "0" ]; then
  : # islemsiz - gunluge yazma
else
  yaz_log "$POSTA_SONUC"
fi

# Log doyasi sinirsiz buyumesin - son 5000 satir yeter
if [ -f "$ALARM_LOG" ]; then
  SATIR="$(wc -l <"$ALARM_LOG" 2>/dev/null || echo 0)"
  if [ "$SATIR" -gt 6000 ] 2>/dev/null; then
    tail -n 5000 "$ALARM_LOG" >"$ALARM_LOG.tmp" 2>/dev/null && mv "$ALARM_LOG.tmp" "$ALARM_LOG" 2>/dev/null || true
  fi
fi

# 🔴 Cagiran betigi asla dusurme.
exit 0
