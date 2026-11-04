#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - SAGLIK KONTROLU TESTLERI
#
# NEDEN VAR
# 21-22.09.2026'da UC yanlis alarm ayni anda calisiyordu ve UCU DE olcum
# hatasiydi - yedek Drive'da dururken "BASARISIZ" deniyordu, dosyada
# "BASARILI" yazarken "Sonuc: izole" deniyordu. Sahip bir surü hata
# postasi aldi. Hicbiri yeni degildi; aylardir oyleydiler ve kimse fark
# etmedi cunku bu kontrollerin TESTI YOKTU.
#
# Bu dosya o uc hatayi fikstur uzerinde yeniden kurar. Regresyon olursa
# yayindan once burada patlar, sahibin gelen kutusunda degil.
#
# 🔴 HER TESTIN BIR DE TERS YONU VAR. Yalniz "yanlis alarm artik yok" demek
#    yetmez - her seyi SUCCESS sayan bir kontrol de o testi gecerdi. Gercek
#    arizanin hala yakalandigi ayrica olculur.
#
# Uretime dokunmaz: LCARLIE_KOK ile gecici bir koke baglanir, alarm.sh
# yerine cagriyi kaydeden sahte bir betik konur.
#
# Kullanim: ./saglik-test.sh
# =============================================================================
set -uo pipefail

SAGLIK="${1:-/opt/lcarlie/saglik.sh}"
# 🔴 -x DEGIL -r: yayin hattinda /root'a gonderilen kopyada calistirma
# izni YOKTUR (Windows'tan gelen dosyada exec biti olmaz). Testin
# kurulumdan ONCE kosabilmesi icin dosya bash'e verilir.
[ -r "$SAGLIK" ] || { echo "saglik.sh okunamadi: $SAGLIK" >&2; exit 2; }

GECEN=0; KALAN=0
KUTU=""

kutu_kur() {
  KUTU="$(mktemp -d)"
  mkdir -p "$KUTU/backup/log" "$KUTU/durum"
  # Yapilandirma yoksa saglik.sh bilerek durur; gercegini odunc aliyoruz.
  cp /opt/lcarlie/uretim-workflowlari.conf "$KUTU/" 2>/dev/null || echo "" > "$KUTU/uretim-workflowlari.conf"
  # Sahte alarm: gondermez, yalnizca cagrildigini yazar.
  cat > "$KUTU/alarm.sh" <<'SAHTE'
#!/bin/sh
cat >/dev/null 2>&1 || true
printf '%s|%s\n' "$1" "$2" >> "$(dirname "$0")/alarm-cagrilari.txt"
exit 0
SAHTE
  chmod +x "$KUTU/alarm.sh"
  : > "$KUTU/alarm.log"
  : > "$KUTU/alarm-cagrilari.txt"
}

kutu_yik() { [ -n "$KUTU" ] && rm -rf "$KUTU"; KUTU=""; }

kos() { LCARLIE_KOK="$KUTU" bash "$SAGLIK" --sessiz 2>/dev/null; }

# $1 aciklama  $2 beklenen desen  $3 cikti
bekle() {
  if printf '%s' "$3" | grep -qE "$2"; then
    printf '  ✓ %s\n' "$1"; GECEN=$((GECEN+1))
  else
    printf '  ✗ %s\n     beklenen desen: %s\n' "$1" "$2"; KALAN=$((KALAN+1))
  fi
}

bekleme() {
  if printf '%s' "$3" | grep -qE "$2"; then
    printf '  ✗ %s\n     OLMAMASI gereken desen bulundu: %s\n' "$1" "$2"; KALAN=$((KALAN+1))
  else
    printf '  ✓ %s\n' "$1"; GECEN=$((GECEN+1))
  fi
}

echo "=== 1) GERI YUKLEME TESTI: son-test.txt UC alanli ==="
# Gercek dosya bicimi: zaman|SONUC|mod  -- "##*|" SON alani (modu) alirsa
# "izole" sonuc sanilir ve BASARILI bir test BASARISIZ raporlanir.
kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
CIKTI="$(kos)"
bekle   "BASARILI + mod=izole -> SUCCESS" 'yedek\.geritest\|SUCCESS' "$CIKTI"
bekleme "yanlis alarm uretilmiyor"        'backup\.geritest' "$(cat "$KUTU/alarm-cagrilari.txt")"
kutu_yik

kutu_kur
printf '%s|BASARISIZ|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
CIKTI="$(kos)"
bekle "TERS YON: gercek basarisizlik hala yakalaniyor" 'yedek\.geritest\|FAILED' "$CIKTI"
kutu_yik

echo
echo "=== 2) OFF-SITE AKTARIM: telafi turu de sayilir ==="
# Aktarim IKI ayri cumleyle loglanir; yalniz birincisini aramak, telafiyle
# kurtarilan geceleri "hic aktarilmadi" gosteriyordu.
kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
{
  printf '[%s] Yedekleme basladi\n' "$(date '+%F %T')"
  printf '[%s] Telafi sirasinda bu gecenin yedegi de aktarildi\n' "$(date '+%F %T')"
  printf '[%s] ===== Yedekleme bitti: BASARILI (tam) =====\n' "$(date '+%F %T')"
} > "$KUTU/backup/log/backup-test.log"
CIKTI="$(kos)"
bekle   "yalniz telafi cumlesi varken -> SUCCESS" 'yedek\.drive\|SUCCESS' "$CIKTI"
bekleme "hic aktarilmadi denmiyor"                'yedek\.drive\|FAILED' "$CIKTI"
kutu_yik

kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
{
  printf '[%s] Yedekleme basladi\n' "$(date '+%F %T')"
  printf '[%s] ===== Yedekleme bitti: BASARILI (tam) =====\n' "$(date '+%F %T')"
} > "$KUTU/backup/log/backup-test.log"
CIKTI="$(kos)"
bekle "TERS YON: hic aktarim yoksa hala FAILED" 'yedek\.drive\|FAILED' "$CIKTI"
kutu_yik

echo
echo "=== 3) YEDEKLEME SONUCU: yalniz 'tam' calisma sayilir ==="
kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
{
  printf '[%s] ===== Yedekleme bitti: BASARISIZ (tam) =====\n' "$(date -d "-2 hours" '+%F %T')"
  printf '[%s] ===== Yedekleme bitti: BASARILI (yerel) =====\n' "$(date '+%F %T')"
} > "$KUTU/backup/log/backup-test.log"
CIKTI="$(kos)"
# Gece yedegi basarisizken, gun icindeki --yerel calisma gostergeyi
# yesile cevirmemeli. 15.09.2026'da birebir bu yasandi.
bekle "gece BASARISIZ + gunduz yerel BASARILI -> hala FAILED" 'yedek\.sonuc\|FAILED' "$CIKTI"
kutu_yik

kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
printf '[%s] ===== Yedekleme bitti: BASARILI (tam) =====\n' "$(date '+%F %T')" \
  > "$KUTU/backup/log/backup-test.log"
CIKTI="$(kos)"
bekle "TERS YON: gercekten basariliysa SUCCESS" 'yedek\.sonuc\|SUCCESS' "$CIKTI"
kutu_yik

echo
echo "=== 4) ALARM POSTASI: canlilik yoklamasi kanit sayilir ==="
# Kontrol "posta calisiyor" bilgisini yalnizca GERCEK bir gonderimden
# ogrenebiliyordu. Sistem saglikliysa yeni gonderim olmaz, son olay
# basarisizlik olarak kalir, gosterge sonsuza kadar kirmizi durur.
# 21-22.09.2026: iki gonderim zaman asimina ugradi, ertesi sabah SMTP
# 2 sn'de 250 OK veriyordu, panel hala FAILED diyordu.
kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
printf '%s|FAILED|ticari.mutabakat|Test|sebep=ZAMAN_ASIMI_25SN\n' \
  "$(date -Is -d '-8 hours')" > "$KUTU/alarm-gonderilemedi.log"
printf '%s|OK|baglanti+kimlik dogrulandi\n' "$(date -Is)" > "$KUTU/alarm-yoklama.log"
CIKTI="$(kos)"
bekle   "eski basarisizlik + TAZE yoklama -> SUCCESS" 'ALARMPOSTA\|SUCCESS' "$CIKTI"
bekleme "artik 'gonderilemiyor' denmiyor"            'Alarm e-postasi gonderilemiyor' "$CIKTI"
kutu_yik

kutu_kur
printf '%s|BASARILI|izole\n' "$(date -Is)" > "$KUTU/backup/son-test.txt"
printf '%s|FAILED|ticari.mutabakat|Test|sebep=ZAMAN_ASIMI_25SN\n' \
  "$(date -Is)" > "$KUTU/alarm-gonderilemedi.log"
printf '%s|OK|baglanti+kimlik dogrulandi\n' "$(date -Is -d '-8 hours')" > "$KUTU/alarm-yoklama.log"
CIKTI="$(kos)"
# 🔴 TERS YON: yoklama yalnizca kendisi DAHA YENIYSE kanittir. Eski bir
#    yoklama, yeni bir basarisizligi ortmemeli - yoksa "her zaman yesil"
#    bir kontrol yapmis olurduk ve ustteki test bunu yakalayamazdi.
bekle "TERS YON: yoklama ESKIYSE, yeni basarisizlik hala FAILED" 'ALARMPOSTA\|FAILED' "$CIKTI"
kutu_yik

echo
echo "=== 5) ALARM GUNLUGU: islemsiz COZULDU yazilmaz ==="
# Cagiranlar kontrol SUCCESS oldugunda kosulsuz 'alarm COZULDU' cagiriyor.
# Acik alarm yoksa bu bir islemsizdir. 22.09.2026 olcumu: 3323 satirin
# 1347'si (%40,5) tam olarak bu satirdi.
ALARM_KAYNAK="$(dirname "$SAGLIK")/alarm.sh"
[ -r "$ALARM_KAYNAK" ] || ALARM_KAYNAK=/opt/lcarlie/alarm.sh
if [ -r "$ALARM_KAYNAK" ]; then
  kutu_kur
  mkdir -p "$KUTU/alarm-durum"
  # Acik alarm YOK -> COZULDU hicbir sey cozmez -> satir yazilmamali
  LCARLIE_KOK="$KUTU" NOTIFY_EMAIL="" bash "$ALARM_KAYNAK" \
    COZULDU "sys.disk" "Disk normale dondu" "Kullanim: 40G / 89G" >/dev/null 2>&1
  bekleme "acik alarm yokken COZULDU gunluge yazilmadi" \
    'sys\.disk' "$(cat "$KUTU/alarm.log" 2>/dev/null)"

  # 🔴 TERS YON: gercek bir alarmi kapatan COZULDU YAZILMALI. Yoksa
  #    "hic yazma" diyen bir kod da ustteki testi gecerdi ve duzelme
  #    kayitlarini sessizce kaybederdik.
  LCARLIE_KOK="$KUTU" NOTIFY_EMAIL="" bash "$ALARM_KAYNAK" \
    FAILED "sys.disk" "Disk doldu" "Kullanim: 88G / 89G" >/dev/null 2>&1
  LCARLIE_KOK="$KUTU" NOTIFY_EMAIL="" bash "$ALARM_KAYNAK" \
    COZULDU "sys.disk" "Disk normale dondu" "Kullanim: 40G / 89G" >/dev/null 2>&1
  bekle "TERS YON: gercek alarmi kapatan COZULDU yazildi" \
    'COZULDU\|sys\.disk' "$(cat "$KUTU/alarm.log" 2>/dev/null)"
  kutu_yik
else
  printf '  ! alarm.sh bulunamadi, 5) atlandi\n'
fi

echo
echo "=== 6) AI SAGLAYICI TANISI: ham hata -> eyleme donusebilir sinif ==="
# gemini saglayicisi ALTI GUN boyunca 'not configured' dustu ve bu hicbir
# ekranda gorunmedi; sebep kayitliydi ama kimse okumuyordu. Siniflandirici
# veritabani gerektirmeyen --siniflandir kapisindan sinanir.
TANI="$(dirname "$SAGLIK")/ai-saglayici-tani.sh"
[ -r "$TANI" ] || TANI=/opt/lcarlie/ai-saglayici-tani.sh
if [ -r "$TANI" ]; then
  SINIF() { printf '%s\n' "$1" | bash "$TANI" --siniflandir 2>/dev/null; }

  bekle "adaptoru olmayan saglayici -> ADAPTOR_YOK" '\|ADAPTOR_YOK\|' \
    "$(SINIF 'gemini|ERROR|not configured')"
  bekle "Google 401 -> KIMLIK_401"                '\|KIMLIK_401\|' \
    "$(SINIF 'vertex|ERROR|HTTP 401 Request had invalid authentication credentials')"
  bekle "token sinirinda kesilme -> KESILDI"      '\|KESILDI\|' \
    "$(SINIF 'openai|ERROR|truncated: cevap token sinirinda kesildi')"
  bekle "kota -> KOTA_429"                        '\|KOTA_429\|' \
    "$(SINIF 'claude|ERROR|HTTP 429 rate limit exceeded')"

  # 🔴 TERS YON 1: basarili deneme sorun sayilmamali. Her seyi bir hata
  #    sinifina atayan bir siniflandirici ustteki dort testi de gecerdi.
  bekleme "basarili deneme hata sinifina atanmiyor" '(ADAPTOR_YOK|KIMLIK_401|KESILDI|KOTA_429|BILINMEYEN)' \
    "$(SINIF 'claude|SUCCESS|council opinion')"

  # 🔴 TERS YON 2: taninmayan metin sessizce 'OK' olmamali. Aksi halde
  #    yeni bir ariza turu ortaya ciktiginda sistem onu gormezden gelirdi -
  #    bu betigin var olma sebebinin ta kendisi.
  bekle "taninmayan hata BILINMEYEN olarak isaretleniyor" '\|BILINMEYEN\|' \
    "$(SINIF 'vertex|ERROR|beklenmedik yeni ariza turu xyz')"

  # 🔴 TERS YON 3: guvenlik suzgecine takilma bir saglayici arizasi DEGIL.
  bekle "guvenlik suzgeci ariza sayilmiyor" '\|GUVENLIK\|' \
    "$(SINIF 'openai|ERROR|unsafe output')"

  # 🔴 COK SATIRLI HATA GOVDESI. failover_reason cogu zaman bir JSON
  #    hata govdesi tutuyor ve satir sonu iceriyor. Ilk surumde bu
  #    satirlar ayri birer saglayici sanildi; raporda '"code": 401,'
  #    diye bir "saglayici" belirdi ve durum satiri okunamaz oldu.
  COK_SATIR="$(printf 'vertex|ERROR|HTTP 401 {\n  "error": {\n    "code": 401,\n    "message": "API keys are not supported"\n  }\n}')"
  bekle "cok satirli 401 govdesi KIMLIK_401 olarak siniflaniyor" '\|KIMLIK_401\|' \
    "$(SINIF "$COK_SATIR")"
  bekleme "hata govdesinin parcasi saglayici adi sanilmiyor" '^[^|]*(code|message|error)' \
    "$(SINIF "$COK_SATIR")"
else
  printf '  ! ai-saglayici-tani.sh bulunamadi, 6) atlandi\n'
fi

echo
echo "=== 7) YAYIN KORUMA: neyi durdurur, neyi durdurmaz ==="
# Bu betik yayini DURDURMA karari veriyor. Yanlis yonde bozulursa ya her
# yayin kilitlenir ya da sunucudaki elle duzeltmeler sessizce silinir.
KORUMA="$(dirname "$SAGLIK")/yayin-koruma.sh"
[ -r "$KORUMA" ] || KORUMA=/opt/lcarlie/yayin-koruma.sh
if [ -r "$KORUMA" ] && command -v git >/dev/null 2>&1; then
  K="$(mktemp -d)"
  mkdir -p "$K"
  printf 'birinci\n' > "$K/a.sh"
  printf 'ikinci\n'  > "$K/b.sh"
  printf 'izlenmeyen\n' > "$K/c.sh"
  printf '%s/a.sh\n%s/b.sh\n' "$K" "$K" > "$K/yayin-dosyalari.conf"
  KOS() { LCARLIE_KOK="$K" bash "$KORUMA" "$@" 2>&1; }

  CIKTI="$(KOS kontrol)"; KOD=$?
  bekle "ilk kosu taban alir ve yayini DURDURMAZ" 'ilk kurulum' "$CIKTI"

  # Izlenen bir dosya degistirildi -> yayin DURMALI
  printf 'DEGISTI\n' > "$K/a.sh"
  CIKTI="$(KOS kontrol)"; KOD=$?
  bekle   "izlenen dosya degisince yayin DURUR"      '^  - a\.sh$' "$CIKTI"
  [ "$KOD" -ne 0 ] && { printf '  ✓ %s\n' "cikis kodu 1 (yayin durdu)"; GECEN=$((GECEN+1)); } \
                   || { printf '  ✗ %s\n' "cikis kodu 0 - yayin DURMADI"; KALAN=$((KALAN+1)); }

  # 🔴 TERS YON: LISTEDE OLMAYAN dosya yayini durdurmamali. Her degisikligi
  #    ariza sayan bir kapi, her yayini kilitler ve kapatilir.
  KOS kaydet "taban" >/dev/null
  printf 'DEGISTI\n' > "$K/c.sh"
  CIKTI="$(KOS kontrol)"
  bekleme "listede OLMAYAN dosya yayini durdurmaz" '^  - c\.sh$' "$CIKTI"

  # kaydet-tek: YALNIZ adi verilen dosyayi isler
  printf 'YENI-A\n' > "$K/a.sh"
  printf 'YENI-B\n' > "$K/b.sh"
  KOS kaydet-tek "$K/a.sh" >/dev/null
  CIKTI="$(KOS kontrol)"
  bekleme "kaydet-tek a.sh'yi kapatir"              '^  - a\.sh$' "$CIKTI"
  # 🔴 TERS YON: hepsini kaydeden bir kaydet-tek ustteki testi de gecerdi
  #    ve gercek bir elle degisikligi sessizce yutardi.
  bekle   "kaydet-tek b.sh'yi HALA acik birakir"    '^  - b\.sh$' "$CIKTI"

  rm -rf "$K"
else
  printf '  ! yayin-koruma.sh ya da git yok, 7) atlandi\n'
fi

echo
echo "=== 8) POSTA YOKLAMASI: mail ATMAZ, bosuna giris yapmaz ==="
YOKLAMA="$(dirname "$SAGLIK")/posta-yoklama.sh"
[ -r "$YOKLAMA" ] || YOKLAMA=/opt/lcarlie/posta-yoklama.sh
if [ -r "$YOKLAMA" ]; then
  # 🔴 EN ONEMLI SOZLESME: bu betik POSTA GONDERMEZ. Sikayetin kendisi
  #    "bir suru hata maili" idi; test maili atan bir canlilik kontrolu
  #    hastaligin ta kendisi olurdu. Gonderim yolu KODDA OLMAMALI.
  bekleme "gonderim CAGRISI icermiyor (yapilandirma yolu sayilmaz)" \
    '(^|[^A-Za-z_.])(sendmail|msmtp)[[:space:]]|\.sendmail\(|\.send_message\(' \
    "$(grep -vE '^\s*#' "$YOKLAMA")"
  bekle "kimlik dogrulayip QUIT ediyor" 's\.login|s\.quit' "$(cat "$YOKLAMA")"

  # Kisitlama: taze bir yoklama varken tekrar kosmamali (Yandex'i saatte
  # 96 kez kimlik dogrulamaya zorlamak, postayi yavaslatan seyin kendisi).
  Y="$(mktemp -d)"
  printf '%s|OK|deneme\n' "$(date -Is)" > "$Y/alarm-yoklama.log"
  CIKTI="$(LCARLIE_KOK="$Y" MSMTPRC=/dev/null bash "$YOKLAMA" 2>&1)"; KOD=$?
  if [ -z "$CIKTI" ] && [ "$KOD" -eq 0 ]; then
    printf '  ✓ %s\n' "taze yoklama varken sessizce cikar"; GECEN=$((GECEN+1))
  else
    printf '  ✗ %s (cikti=%s kod=%s)\n' "taze yoklamada tekrar kostu" "$CIKTI" "$KOD"
    KALAN=$((KALAN+1))
  fi

  # 🔴 TERS YON: her zaman sessizce cikan bir kod ustteki testi de gecerdi.
  #    ESKI yoklamada KOSMALI -- ve yapilandirma okunamadigi icin HATA
  #    yazmali; sessiz basarisizlik yok.
  printf '%s|OK|deneme\n' "$(date -Is -d '-3 hours')" > "$Y/alarm-yoklama.log"
  CIKTI="$(LCARLIE_KOK="$Y" MSMTPRC=/dev/null bash "$YOKLAMA" 2>&1)"
  bekle "eski yoklamada KOSAR ve sonucu yazar" 'HATA|OK' "$CIKTI"
  rm -rf "$Y"
else
  printf '  ! posta-yoklama.sh bulunamadi, 8) atlandi\n'
fi

echo
echo "------------------------------------------------------------"
printf 'GECEN: %d   KALAN: %d\n' "$GECEN" "$KALAN"
[ "$KALAN" -eq 0 ] || exit 1
echo "Tum saglik kontrolu testleri gecti."
exit 0
