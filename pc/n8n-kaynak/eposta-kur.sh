#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - ARIZA BILDIRIMI E-POSTA KURULUMU
#
# Su an sunucuda bir arıza olursa KIMSEYE haber gitmiyor: gece yedegi
# basarisiz olsa, Drive aktarimi kessе, geri yukleme testi coksе kimse
# fark etmiyor. Bu betik o bosluğu kapatir.
#
# 🔴 SIFRE BU BETIGE YAZILMAZ, EKRANA BASILMAZ, KAYDA GECMEZ.
#    Betik sizden ister, gizli okur (ekranda gorunmez) ve dogrudan
#    /root/.msmtprc icine yazar (izin 600, yalniz root okur).
#
# Kullanim (kendi terminalinizden):
#   ssh -t lcarlie "/opt/lcarlie/eposta-kur.sh"
# =============================================================================
set -uo pipefail

MSMTP=/root/.msmtprc
CONF=/opt/lcarlie/backup/backup.conf

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }

if [ ! -t 0 ]; then
  kirmizi "Bu betik sizinle konusmasi gerekiyor (sifre soracak)."
  kirmizi "Soyle calistirin:  ssh -t lcarlie \"/opt/lcarlie/eposta-kur.sh\""
  exit 1
fi

echo "=============================================="
echo " L'CARLIE - ariza bildirimi e-posta kurulumu"
echo "=============================================="
echo ""
echo "Saglayici secin:"
echo "  1) Yandex  (kurumsal - lcarlie.com.tr)   [varsayilan]"
echo "  2) Gmail"
read -r -p "Secim [1]: " SEC
SEC="${SEC:-1}"

case "$SEC" in
  2)
    SUNUCU="smtp.gmail.com"; SPORT=587; STARTTLS="on"
    echo ""
    echo "Gmail'de NORMAL sifreniz CALISMAZ. 'Uygulama Sifresi' gerekir:"
    echo "  myaccount.google.com/security -> 2 Adimli Dogrulama acik olmali"
    echo "  -> 'Uygulama sifreleri' -> yeni olustur -> 16 haneli kod"
    VARSAYILAN_ADRES=""
    ;;
  *)
    # 🔴 Yandex 465 numarali kapiyi ve dogrudan SSL'i tercih ediyor;
    #    STARTTLS (587) da calisir ama 465 daha az sorun cikariyor.
    SUNUCU="smtp.yandex.com"; SPORT=465; STARTTLS="off"
    echo ""
    echo "Yandex'te NORMAL sifreniz genelde CALISMAZ."
    echo "Uygulama parolasi gerekir:"
    echo "  id.yandex.com -> Guvenlik -> 'Uygulama parolalari'"
    echo "  -> tur olarak 'E-posta' secin -> olusan parolayi kopyalayin"
    echo ""
    echo "Ayrica Yandex Mail ayarlarinda SMTP acik olmali:"
    echo "  mail.yandex.com -> Ayarlar -> 'Tum ayarlar' -> E-posta istemcileri"
    echo "  -> 'SMTP ile parola ile' secenegi isaretli olmali"
    VARSAYILAN_ADRES="info@lcarlie.com.tr"
    ;;
esac

echo ""
if [ -n "$VARSAYILAN_ADRES" ]; then
  read -r -p "Gonderen adres [$VARSAYILAN_ADRES]: " GONDEREN
  GONDEREN="${GONDEREN:-$VARSAYILAN_ADRES}"
else
  read -r -p "Gonderen adres               : " GONDEREN
fi
[ -n "$GONDEREN" ] || { kirmizi "Bos birakilamaz."; exit 1; }

# 🔴 -s : yazilan karakterler EKRANDA GORUNMEZ
read -r -s -p "Uygulama sifresi (gorunmez)  : " SIFRE; echo ""
[ -n "$SIFRE" ] || { kirmizi "Bos birakilamaz."; exit 1; }

read -r -p "Bildirim gidecek adres [$GONDEREN]: " ALICI
ALICI="${ALICI:-$GONDEREN}"

echo ""
echo "Ozet:"
echo "  sunucu   : $SUNUCU:$SPORT (starttls=$STARTTLS)"
echo "  gonderen : $GONDEREN"
echo "  alici    : $ALICI"
echo "  sifre    : (girildi, gosterilmiyor)"
read -r -p "Devam edilsin mi? (EVET yazin): " ONAY
[ "$ONAY" = "EVET" ] || { sari "Iptal edildi. Hicbir sey degismedi."; exit 1; }

# --- Yedek al -----------------------------------------------------------
[ -f "$MSMTP" ] && cp "$MSMTP" "/root/.msmtprc.yedek-$(date +%Y%m%d-%H%M%S)"
[ -f "$CONF" ]  && cp "$CONF"  "/root/backup.conf.yedek-$(date +%Y%m%d-%H%M%S)"

# --- msmtprc yaz --------------------------------------------------------
umask 077
cat > "$MSMTP" <<MSM
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
unset SIFRE
yesil "  /root/.msmtprc yazildi (izin 600)"

# --- NOTIFY_EMAIL ayarla ------------------------------------------------
if grep -q '^NOTIFY_EMAIL=' "$CONF"; then
  sed -i "s|^NOTIFY_EMAIL=.*|NOTIFY_EMAIL=\"$ALICI\"|" "$CONF"
else
  echo "NOTIFY_EMAIL=\"$ALICI\"" >> "$CONF"
fi
# Her basarili yedekte e-posta ISTEMIYORUZ - yalnizca arizada.
# (Gunde bir "her sey yolunda" postasi, kisa surede okunmamaya baslar
#  ve gercek ariza postasi da onun arasinda kaybolur.)
if grep -q '^NOTIFY_ON_SUCCESS=' "$CONF"; then
  sed -i "s|^NOTIFY_ON_SUCCESS=.*|NOTIFY_ON_SUCCESS=0|" "$CONF"
else
  echo "NOTIFY_ON_SUCCESS=0" >> "$CONF"
fi
yesil "  NOTIFY_EMAIL ayarlandi, yalnizca ARIZADA e-posta gidecek"

# --- Deneme postasi -----------------------------------------------------
echo ""
echo "Deneme postasi gonderiliyor..."
# 🔴 'From:' BASLIGI OLMADAN '--read-envelope-from' KULLANILMAZ (CR-002).
#
# Onceki hali tam da bunu yapiyordu: uretilen mesajda From: basligi YOKTU
# ama msmtp'ye "zarf gondericisini From basligindan oku" deniyordu. msmtp
# bu durumda hicbir SMTP baglantisi bile kurmadan
#     "envelope-from address is missing"
# deyip EX_NOPERM (78) ile cikiyor.
#
# Sonuc: kullanici DOGRU uygulama parolasini girse bile betik
# "GONDERILEMEDI" deyip asagida "normal sifre girdiniz / SMTP kapali /
# gonderen adres farkli" diye UC YANLIS SEBEP siralardi. Kullanici
# calisan bir kurulumu bozuk sanip tekrar tekrar denerdi.
#
# Ayni hata backup.sh'te de vardi ve orada da hic bildirim gitmiyordu.
#
# Duzeltme: From: basligi acikca yaziliyor ve zarf gondericisi msmtp'nin
# kendi hesap ayarindan ('from' alani) geliyor - bayrak gereksiz.
# 🔴 Ayrica zaman asimi: agi asili birakan bir SMTP sunucusu kurulum
#    betigini sonsuza kadar bekletmesin.
if printf 'From: %s\nTo: %s\nSubject: [L%sCARLIE] E-posta bildirimi calisiyor\nContent-Type: text/plain; charset=UTF-8\n\nBu bir denemedir.\n\nArtik su durumlarda buraya e-posta gelecek:\n- Gece yedegi basarisiz olursa\n- Drive aktarimi yapilamazsa\n- Aylik geri yukleme testi coker ise\n- Aktif bir workflow beklenmedik sekilde durursa\n- Kanal hata kaydi olusursa\n\nSunucu: n8n.lcarlie.shop\nZaman : %s\n' \
     "$GONDEREN" "$ALICI" "'" "$(date -Iseconds)" | timeout 30 msmtp "$ALICI" 2>/tmp/msmtp-hata.txt; then
  yesil "  GONDERILDI - gelen kutunuzu kontrol edin ($ALICI)"
  echo ""
  yesil "Kurulum tamam."
  rm -f /tmp/msmtp-hata.txt
  exit 0
fi

kirmizi "  GONDERILEMEDI"
echo ""
echo "Hata (sifre gosterilmez):"
sed 's/password.*/password <GIZLENDI>/' /tmp/msmtp-hata.txt | sed 's/^/    /'
rm -f /tmp/msmtp-hata.txt
echo ""
sari "En sik sebepler:"
sari "  1. Normal hesap sifresi girildi - UYGULAMA PAROLASI gerekiyor."
sari "  2. Yandex'te SMTP erisimi kapali (Ayarlar -> E-posta istemcileri)."
sari "  3. Gonderen adres, parolanin ait oldugu hesaptan farkli."
sari "  4. 'timed out' yaziyorsa: aga cikis engelli (30 sn zaman asimi)."
echo ""
# 🔴 KISMEN BASARILI DURUM ACIKCA SOYLENIR.
#    .msmtprc ve NOTIFY_EMAIL bu noktada ZATEN YAZILDI. Yalnizca deneme
#    postasi gonderilemedi. Kullaniciya "hicbir sey olmadi" izlenimi
#    vermek yanlis olur - ayar duruyor, alarm hatti kaydi tutmaya devam
#    ediyor, eksik olan tek sey teslim.
sari "NOT: /root/.msmtprc ve NOTIFY_EMAIL YAZILDI - ayarlar duruyor."
sari "     Alarm olaylari her halukarda /opt/lcarlie/alarm.log'a kaydediliyor."
sari "     Yalnizca TESLIM basarisiz. Duzeltip ayni komutu tekrar calistirin."
exit 1
