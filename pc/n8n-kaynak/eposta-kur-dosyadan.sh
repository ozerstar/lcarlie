#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - ARIZA BILDIRIMI E-POSTA KURULUMU  (INTERAKTIF OLMAYAN)
#
# CR-002 · 15.09.2026
#
# 'eposta-kur.sh' sifreyi klavyeden gizli okur ve bunun icin GERCEK bir
# terminal ister. Bazi ortamlarda (Claude Code'un '!' komutu, cron, uzaktan
# calistirma) klavye girisi iletilemiyor; betik "Secim [1]:" isteminde
# asili kaliyor. Bu surum ayni isi DOSYADAN okuyarak yapar.
#
# 🔴 SIFRE KOMUT SATIRINA YAZILMAZ.
#    Arguman olarak verilirse 'ps' ciktisinda, shell gecmisinde ve
#    surec listesinde gorunur. Bu yuzden yalnizca DOSYADAN okunur.
#
# 🔴 SIFRE DOSYASI ISI BITINCE SILINIR (mumkunse 'shred' ile uzerine yazilarak).
#
# Kullanim:
#   1) Yerelde sifreyi bir dosyaya yaz (tek satir, baska hicbir sey)
#   2) scp <dosya> lcarlie:/root/.eposta-sifre
#   3) ssh lcarlie "/opt/lcarlie/eposta-kur-dosyadan.sh \
#        --gonderen info@lcarlie.com.tr --alici moy.ozeryildiz@gmail.com"
#
# Secenekler:
#   --gonderen <adres>     ZORUNLU - parolanin ait oldugu hesap
#   --alici <adres>        ZORUNLU - alarmlarin gidecegi adres (TEK adres)
#   --saglayici yandex|gmail   varsayilan: yandex
#   --sifre-dosya <yol>    varsayilan: /root/.eposta-sifre
#   --sifreyi-sakla        dosyayi silme (yalnizca sorun giderme icin)
# =============================================================================
set -uo pipefail

MSMTP=/root/.msmtprc
CONF=/opt/lcarlie/backup/backup.conf
SIFRE_DOSYA=/root/.eposta-sifre
SAGLAYICI=yandex
GONDEREN=""
ALICI=""
SAKLA=0

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --gonderen)     GONDEREN="${2:-}"; shift 2 ;;
    --alici)        ALICI="${2:-}"; shift 2 ;;
    --saglayici)    SAGLAYICI="${2:-}"; shift 2 ;;
    --sifre-dosya)  SIFRE_DOSYA="${2:-}"; shift 2 ;;
    --sifreyi-sakla) SAKLA=1; shift ;;
    *) kirmizi "Bilinmeyen secenek: $1"; exit 1 ;;
  esac
done

[ -n "$GONDEREN" ] || { kirmizi "--gonderen zorunlu"; exit 1; }
[ -n "$ALICI" ]    || { kirmizi "--alici zorunlu"; exit 1; }

# 🔴 TEK ALICI. Bosluklu birden fazla adres verilirse msmtp onu TEK bir
#    adres sanar ve gonderim sessizce basarisiz olur.
case "$ALICI" in
  *" "*|*,*) kirmizi "--alici yalnizca TEK adres alir (bosluk/virgul yok): $ALICI"; exit 1 ;;
esac
case "$GONDEREN" in *@*) : ;; *) kirmizi "--gonderen gecerli bir adres degil: $GONDEREN"; exit 1 ;; esac
case "$ALICI"    in *@*) : ;; *) kirmizi "--alici gecerli bir adres degil: $ALICI"; exit 1 ;; esac

case "$SAGLAYICI" in
  gmail)  SUNUCU="smtp.gmail.com";  SPORT=587; STARTTLS="on" ;;
  yandex) SUNUCU="smtp.yandex.com"; SPORT=465; STARTTLS="off" ;;
  *) kirmizi "--saglayici yandex veya gmail olmali (verilen: $SAGLAYICI)"; exit 1 ;;
esac

# --- Sifreyi oku -------------------------------------------------------------
[ -f "$SIFRE_DOSYA" ] || {
  kirmizi "Sifre dosyasi bulunamadi: $SIFRE_DOSYA"
  sari "Once yerelden gonderin:  scp <dosya> lcarlie:$SIFRE_DOSYA"
  exit 1
}
# İlk satir alinir; CR, bosluk ve sekmeler temizlenir.
# 🔴 Gmail uygulama sifreleri ekranda "abcd efgh ijkl mnop" gibi BOSLUKLU
#    gosterilir ama bosluksuz girilmelidir. Yandex'te de kopyalarken bosluk
#    bulasabiliyor. Sessizce "sifre yanlis" hatasi almamak icin temizliyoruz.
SIFRE="$(head -n1 "$SIFRE_DOSYA" | tr -d ' \t\r\n')"

if [ -z "$SIFRE" ]; then
  kirmizi "Sifre dosyasi BOS: $SIFRE_DOSYA"
  exit 1
fi
case "$SIFRE" in
  BURAYA_*) kirmizi "Sifre dosyasinda yer tutucu metin var, gercek parola degil."; exit 1 ;;
esac
# Uzunluk kontrolu - bariz yanlis yapistirmayi erken yakala
UZUNLUK="${#SIFRE}"
if [ "$UZUNLUK" -lt 8 ]; then
  kirmizi "Sifre cok kisa ($UZUNLUK karakter) - yanlis dosya olabilir."
  exit 1
fi

echo "=============================================="
echo " L'CARLIE - e-posta bildirimi kurulumu"
echo "=============================================="
echo "  saglayici : $SAGLAYICI ($SUNUCU:$SPORT starttls=$STARTTLS)"
echo "  gonderen  : $GONDEREN"
echo "  alici     : $ALICI"
echo "  sifre     : okundu ($UZUNLUK karakter, gosterilmiyor)"
echo ""

# --- Yedek al ----------------------------------------------------------------
[ -f "$MSMTP" ] && cp "$MSMTP" "/root/.msmtprc.yedek-$(date +%Y%m%d-%H%M%S)"
[ -f "$CONF" ]  && cp "$CONF"  "/root/backup.conf.yedek-$(date +%Y%m%d-%H%M%S)"

# --- msmtprc yaz -------------------------------------------------------------
umask 077
cat > "$MSMTP" <<MSM
# L'CARLIE ariza bildirimi - eposta-kur-dosyadan.sh tarafindan yazildi
# $(date -Is)
defaults
auth           on
tls            on
tls_starttls   $STARTTLS
tls_trust_file /etc/ssl/certs/ca-certificates.crt
logfile        /opt/lcarlie/backup/log/msmtp.log

account        lcarlie
host           $SUNUCU
port           $SPORT
from           $GONDEREN
user           $GONDEREN
password       $SIFRE

account default : lcarlie
MSM
chmod 600 "$MSMTP"
yesil "  /root/.msmtprc yazildi (izin 600)"

# --- NOTIFY ayarlari ---------------------------------------------------------
if grep -q '^NOTIFY_EMAIL=' "$CONF"; then
  sed -i "s|^NOTIFY_EMAIL=.*|NOTIFY_EMAIL=\"$ALICI\"|" "$CONF"
else
  echo "NOTIFY_EMAIL=\"$ALICI\"" >> "$CONF"
fi
# Her basarili yedekte e-posta ISTEMIYORUZ - yalnizca arizada.
# Gunde bir "her sey yolunda" postasi kisa surede okunmamaya baslar ve
# gercek ariza postasi onun arasinda kaybolur.
if grep -q '^NOTIFY_ON_SUCCESS=' "$CONF"; then
  sed -i "s|^NOTIFY_ON_SUCCESS=.*|NOTIFY_ON_SUCCESS=0|" "$CONF"
else
  echo "NOTIFY_ON_SUCCESS=0" >> "$CONF"
fi
yesil "  NOTIFY_EMAIL=$ALICI  ·  yalnizca ARIZADA e-posta gidecek"

# --- Sifre dosyasini sil -----------------------------------------------------
sifreyi_sil() {
  [ "$SAKLA" = "1" ] && { sari "  UYARI: sifre dosyasi BIRAKILDI: $SIFRE_DOSYA"; return; }
  if command -v shred >/dev/null 2>&1; then
    shred -u -n 3 "$SIFRE_DOSYA" 2>/dev/null && yesil "  Sifre dosyasi guvenli silindi (shred)" && return
  fi
  rm -f "$SIFRE_DOSYA" && yesil "  Sifre dosyasi silindi"
}

# --- Deneme postasi ----------------------------------------------------------
echo ""
echo "Deneme postasi gonderiliyor..."
# 🔴 'From:' basligi SART ve '--read-envelope-from' KULLANILMAZ (CR-002).
#    Basliksiz kullanimda msmtp hic baglanti kurmadan
#    "envelope-from address is missing" deyip 78 ile cikiyor; dogru parola
#    girilmis olsa bile kurulum "basarisiz" gorunuyordu.
GONDERIM_CIKTI=$(printf 'From: %s\nTo: %s\nSubject: [LCARLIE] E-posta bildirimi calisiyor\nContent-Type: text/plain; charset=UTF-8\n\nBu bir denemedir - kurulum basarili.\n\nArtik su durumlarda buraya e-posta gelecek:\n- Gece yedegi basarisiz olursa\n- Drive aktarimi yapilamazsa\n- Aylik geri yukleme testi coker ise\n- Aktif bir workflow beklenmedik sekilde durur veya acilirsa\n- Bir kanalda hata kaydi olusursa\n- Disk, sertifika veya veritabani sorun verirse\n\nAlarm gecmisi: /opt/lcarlie/alarm.log\nDurum sayfasi : gizli adres (.env icinde DURUM_TOKEN)\n\nSunucu: n8n.lcarlie.shop\nZaman : %s\n' \
  "$GONDEREN" "$ALICI" "$(date -Iseconds)" | timeout 40 msmtp "$ALICI" 2>&1)
RC=$?
unset SIFRE

if [ "$RC" -eq 0 ]; then
  yesil "  GONDERILDI - gelen kutunuzu kontrol edin ($ALICI)"
  sari  "  Ilk gonderimde SPAM klasorune de bakin."
  sifreyi_sil
  echo ""
  yesil "Kurulum tamam."
  exit 0
fi

kirmizi "  GONDERILEMEDI (cikis kodu $RC)"
echo ""
echo "Hata (sifre gosterilmez):"
printf '%s\n' "$GONDERIM_CIKTI" | sed 's/password.*/password <GIZLENDI>/' | sed 's/^/    /'
echo ""
sari "En sik sebepler:"
sari "  1. Normal hesap sifresi girildi - UYGULAMA PAROLASI gerekiyor."
sari "  2. Yandex'te SMTP erisimi kapali (Ayarlar -> E-posta istemcileri)."
sari "  3. Gonderen adres, parolanin ait oldugu hesaptan farkli."
sari "  4. 'timed out' yaziyorsa aga cikis engelli (40 sn zaman asimi)."
echo ""
# 🔴 KISMEN BASARILI DURUM ACIKCA SOYLENIR - "hicbir sey olmadi" izlenimi yanlis olur.
sari "NOT: /root/.msmtprc ve NOTIFY_EMAIL YAZILDI - ayarlar duruyor."
sari "     Alarm olaylari her halukarda /opt/lcarlie/alarm.log'a kaydediliyor."
sari "     Yalnizca TESLIM basarisiz."
# Sifre dosyasi BIRAKILIR: kullanici duzeltip tekrar denesin diye.
sari "     Sifre dosyasi silinmedi ($SIFRE_DOSYA) - duzeltip tekrar calistirin."
sari "     Vazgecerseniz elle silin:  shred -u $SIFRE_DOSYA"
exit 1
