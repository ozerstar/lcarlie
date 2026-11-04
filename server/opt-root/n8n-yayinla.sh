#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - n8n YAYINLAMA HATTI
#
# Tek komut: kaynak -> test -> yedek -> uret -> aktar -> yayinla -> dogrula
#
# 🔴 TESTLER GECMEZSE HICBIR SEY YAYINLANMAZ.
# 🔴 Aktarim ile yayinlama ARASINDA olursek EXIT tuzagi hepsini yayina geri alir.
#
# ⚠️ DOGRULAMA BASARISIZSA OTOMATIK GERI DONMEZ - komutu yazar, karar sizindir.
#    (Onceki basliкta "otomatik geri doner" yaziyordu; DOGRU DEGILDI.
#     Yanlis vaat, operatoru sistemin kendini toparladigina inandiriyordu.)
#
# Bu betik, elle yapilirken tekrar tekrar yasanan uc hatayi onler:
#   1. import:workflow workflow'u yayindan DUSURUR - tekrar yayinlamayi unutmak
#   2. Testi calistirmadan yayinlamak (bugun kritik kontrol 91->90'a dustu)
#   3. Yedek almadan degisiklik yapmak
#
# Kullanim:
#   n8n-yayinla.sh              -> tum workflow'lari yayinla
#   n8n-yayinla.sh --test-only  -> sadece testleri calistir, yayinlama
#   n8n-yayinla.sh --atla-yedek -> yedegi atla (sadece acil durumda)
# =============================================================================
set -uo pipefail
# 🔴 DOCKER_API_VERSION SABITLENMEZ (20.09.2026'da kaldirildi).
# Buraya 'export DOCKER_API_VERSION=1.43' yaziliydi. Docker yukseltilince
# daemon minimum API 1.44 istemeye basladi ve HER docker cagrisi
# "client version 1.43 is too old" ile patladi. Cagrilar 2>/dev/null ile
# susturuldugu icin hata gorunmedi: on kontrol "konteyner calismiyor" dedi,
# oysa konteyner ayaktaydi. Istemci surumu kendi pazarlar; SABITLEME.

KAYNAK=/root
KAP=lcarlie-n8n
DB=lcarlie-postgres
GERI_DONUS=/opt/lcarlie/geri-donus
mkdir -p "$GERI_DONUS"

SADECE_TEST=0
ATLA_YEDEK=0
for a in "$@"; do
  [ "$a" = "--test-only" ] && SADECE_TEST=1
  [ "$a" = "--atla-yedek" ] && ATLA_YEDEK=1
done

kirmizi() { printf '\033[31m%s\033[0m\n' "$1"; }
yesil()   { printf '\033[32m%s\033[0m\n' "$1"; }
sari()    { printf '\033[33m%s\033[0m\n' "$1"; }
baslik()  { echo ""; echo "=============================================================="; echo " $1"; echo "=============================================================="; }

# -----------------------------------------------------------------------------
# 🔴 GUVENLIK AGI
# import:workflow workflow'u YAYINDAN DUSURUR. Betik aktarim ile yayinlama
# ARASINDA herhangi bir sebeple olurse workflow'lar KAPALI kalir ve sistem
# calismaz hale gelir. (Bu tam olarak 13.09.2026'da basima geldi.)
# Bu tuzak, betik nasil sonlanirsa sonlansin her seyi tekrar yayina alir.
# -----------------------------------------------------------------------------
AKTARIM_BASLADI=0
# 🔴 Tuzak, dizi doldurulmadan once de tetiklenebilir. 'set -u' altinda
#    tanimsiz diziye dokunmak tuzagin KENDISINI dusururdu - yani kurtarma
#    mekanizmasi tam ihtiyac duyuldugu anda calismazdi. Onceden bosalt.
AKTIF_EDILECEKLER=()
guvenlik_agi() {
  local kod=$?
  if [ "$AKTARIM_BASLADI" -eq 1 ] && [ "$kod" -ne 0 ]; then
    echo ""
    sari "  !!! Yayinlama yarida kesildi - workflow'lar yayina geri aliniyor..."
    # 🔴 YALNIZCA 'aktif_olmali=evet' OLANLAR GERI ACILIR.
    #    Onceki hali istisnasiz HEPSINI aktif ediyordu; bilerek kapatilmis
    #    bir workflow (web sohbeti) kurtarma sirasinda sessizce geri acilirdi.
    for w in "${AKTIF_EDILECEKLER[@]}"; do
      docker exec "$KAP" n8n update:workflow --id="$w" --active=true >/dev/null 2>&1
    done
    docker restart "$KAP" >/dev/null 2>&1
    sleep 25
    sari "  Workflow'lar yayina alindi. Sistem calisir durumda olmali."
    sari "  Onceki surume donmek icin: /opt/lcarlie/n8n-geri-don.sh"
  fi
}
trap guvenlik_agi EXIT

# -----------------------------------------------------------------------------
# WORKFLOW TANIMLARI - TEK KAYNAK  (CR-002 madde 4)
#
# 🔴 LISTE ARTIK BU DOSYADA DEGIL: /opt/lcarlie/uretim-workflowlari.conf
#
# 🔴 COZULEN SESSIZ HATA: Onceki hali aktarimdan sonra istisnasiz butun
#    workflow'lari 'update:workflow --active=true' ile yayina aliyordu.
#    lcarlieSohbet01 15.09.2026'da BILEREK yayindan dusurulmustu (site
#    widget'i kaldirildi). Bir sonraki yayinlama onu SESSIZCE GERI ACACAKTI
#    ve dogrulama adimi da "YAYINDA" diye yesil gosterecegi icin kimse fark
#    etmeyecekti - yani hatta, kendi dogrulamasini da kandiriyordu.
#    Artik hangi workflow'un aktif olacagi yapilandirmadaki 7. alandan gelir.
# -----------------------------------------------------------------------------
URETIM_CONF=/opt/lcarlie/uretim-workflowlari.conf
if [ ! -r "$URETIM_CONF" ]; then
  kirmizi "  Yapilandirma bulunamadi: $URETIM_CONF"
  kirmizi "  Workflow listesi olmadan yayinlama yapilmaz."
  exit 1
fi
# shellcheck disable=SC1090
. "$URETIM_CONF"
if [ "${#WORKFLOWLAR_TANIM[@]}" -eq 0 ]; then
  kirmizi "  Yapilandirmada workflow tanimi yok: $URETIM_CONF"
  exit 1
fi

WORKFLOWLAR=()          # ID|build|json   (uretim + aktarim icin)
AKTIF_EDILECEKLER=()    # aktif_olmali=evet olanlarin ID'leri
PASIF_KALACAKLAR=()     # aktif_olmali=hayir olanlarin ID'leri
for t in "${WORKFLOWLAR_TANIM[@]}"; do
  IFS='|' read -r t_id t_ad t_kanal t_rol t_build t_json t_aktif t_trafik t_sessiz <<<"$t"
  WORKFLOWLAR+=("$t_id|$t_build|$t_json")
  if [ "$t_aktif" = "evet" ]; then
    AKTIF_EDILECEKLER+=("$t_id")
  else
    PASIF_KALACAKLAR+=("$t_id")
  fi
done

# Yayinlamadan once gecmesi ZORUNLU testler
TESTLER=(
  "test-filtre.js|Mevzuat filtresi"
  "test-turkce.js|Turkce karakter"
  "test-akis.js|Senaryo + kritik kontrol"
  "kirmizi-takim.js|Kirmizi takim"
  "test-eskalasyon.js|Eskalasyon dogrulugu"
  "test-sablon.js|Meta sablonlari"
  "test-hiz-siniri.js|Hiz siniri (kotuye kullanim)"
  # CR-002: aktif kanallarda hata yolu, kimlik korunmasi ve PII yasagi.
  "test-hata-yolu.js|Hata yolu + PII yasagi"
  # 🔴 Bu test URETIMDEN ONCE kosar; JSON yoksa ureticiyi kendi calistirir.
  "test-messenger.js|Messenger giris kapisi (echo/pencere/tekrar)"
  # CR-002.5: test/uretim ayrimi - 'test-' oneki zorunlulugunu tutan kapi.
  "test-kimlik-standardi.js|Test kimlik standardi"
)

# -----------------------------------------------------------------------------
baslik "1/7  ON KONTROL"
for c in "$KAP" "$DB" lcarlie-caddy; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" != "true" ]; then
    kirmizi "  HATA: $c calismiyor. Yayinlama durduruldu."
    exit 1
  fi
  echo "  ok  $c"
done

# -----------------------------------------------------------------------------
baslik "2/7  KAYNAK DOSYALARI KAPSAYICIYA KOPYALA"
KOPYALANAN=0
# 🔴 .conf DOSYALARI DA KOPYALANIR (CR-002.5).
#    Onceki hali yalnizca *.js aliyordu. test-kimlik-standardi.js,
#    yayinlama duman testi kimliginin 'test-' onekli oldugunu
#    uretim-workflowlari.conf'tan DOGRULUYOR; dosya kapsayicida olmayinca
#    test ENOENT ile coktu. Testin okumasi gereken her sey iceride olmali.
for f in "$KAYNAK"/*.js "$KAYNAK"/*.conf; do
  [ -e "$f" ] || continue
  docker cp "$f" "$KAP:/tmp/" >/dev/null 2>&1 && KOPYALANAN=$((KOPYALANAN+1))
done
# 🔴 'docker cp' KAYNAK DOSYANIN IZINLERINI TASIR ve dosyayi ROOT sahipli
#    birakir. n8n 'node' (uid 1000) olarak calisiyor; kaynak dosya 700 ise
#    testler dosyayi OKUYAMAZ ve "Permission denied" ile coker - hem de
#    hata mesaji test icerigiyle ilgisiz oldugu icin yanlis yere bakilir.
#    (Ayni sinif tuzak 14.09'da geri-donus dosyalarinda yasandi.)
#    Testlerin okumasi gereken dosyalari acikca okunabilir yap.
docker exec -u 0 "$KAP" sh -c 'chmod 644 /tmp/*.js /tmp/*.conf 2>/dev/null' >/dev/null 2>&1
echo "  $KOPYALANAN dosya kopyalandi"

# -----------------------------------------------------------------------------
baslik "3/7  TESTLER"
BASARISIZ=0
for t in "${TESTLER[@]}"; do
  DOSYA="${t%%|*}"; AD="${t##*|}"
  # 🔴 EKSIK TEST = BASARISIZ TEST.
  # Once "ATLANDI" deyip devam ediyordu: scp yarim kalsa veya dosya adi
  # degisse 6 testin 6'si atlanir, sayac 0 kalir ve "testler gecti" denip
  # YAYINLANIRDI. Testin yoklugu, testin gecmesi anlamina gelmez.
  if ! docker exec "$KAP" test -f "/tmp/$DOSYA"; then
    kirmizi "  EKSIK    $AD  (/tmp/$DOSYA yok - test calistirilamadi)"
    BASARISIZ=$((BASARISIZ+1))
    continue
  fi
  CIKTI=$(docker exec "$KAP" node "/tmp/$DOSYA" 2>&1)
  KOD=$?
  # Ozet satirlarini yakala
  OZET=$(echo "$CIKTI" | grep -E "Basarili:|Basarisiz:|Turkce test:|Senaryolar|Kritik kontrol|Eskale edilen|Kacirilan|ESKALE dogru|SATIS dogru|KARMA dogru" | tr -s ' ' | paste -sd' · ' -)
  # Basarisizlik isaretleri
  if [ $KOD -ne 0 ] \
     || echo "$CIKTI" | grep -qE "Basarisiz: [1-9]" \
     || echo "$CIKTI" | grep -qE "Kacirilan *: *[1-9]" \
     || echo "$CIKTI" | grep -qE "kacan riskli mesaj: [1-9]" \
     || echo "$CIKTI" | grep -qE "bosuna insana giden satis sorusu: [1-9]"; then
    kirmizi "  BASARISIZ  $AD"
    echo "$CIKTI" | grep -iE "HATA|BASARISIZ|KACTI" | head -8 | sed 's/^/      /'
    BASARISIZ=$((BASARISIZ+1))
  else
    yesil "  GECTI      $AD"
    [ -n "$OZET" ] && echo "      $OZET"
  fi
done

if [ "$BASARISIZ" -gt 0 ]; then
  echo ""
  kirmizi "  $BASARISIZ test basarisiz. HICBIR SEY YAYINLANMADI."
  kirmizi "  Once testleri duzeltin, sonra tekrar calistirin."
  exit 1
fi

if [ "$SADECE_TEST" -eq 1 ]; then
  echo ""
  yesil "  Tum testler gecti. (--test-only: yayinlama yapilmadi)"
  exit 0
fi

# -----------------------------------------------------------------------------
baslik "4/7  YEDEK VE GERI DONUS NOKTASI"
if [ "$ATLA_YEDEK" -eq 0 ]; then
  /opt/lcarlie/backup/backup.sh --yerel >/dev/null 2>&1 && echo "  ok  yerel yedek alindi (Drive gece yuklenir)" \
    || sari "  UYARI: yedek alinamadi, devam ediliyor"
else
  sari "  yedek atlandi (--atla-yedek)"
fi

# 🔴 GERI DONUS NOKTASI: ONCE URET, SONRA TAKAS ET.
#
# Onceki hali once `rm -f "$GERI_DONUS"/*.json` yapip sonra disa aktariyordu.
# Export basarisiz olursa elde HIC geri donus noktasi kalmiyordu - hem de
# tam yayin yapmak uzereyken. Ustelik tek nesil tutuluyordu: arka arkaya iki
# yayindan sonra "geri donus noktasi" zaten bozuk surum oluyordu.
#
# Simdi gecici klasore uretilir, HEPSI basariliysa takas edilir ve
# son 5 nesil zaman damgasiyla saklanir.
GECICI="$GERI_DONUS/.yeni"
rm -rf "$GECICI"; mkdir -p "$GECICI"
EXPORT_TAMAM=1
for w in "${WORKFLOWLAR[@]}"; do
  ID="${w%%|*}"
  # 🔴 Hedefi ONCE root olarak sil.
  # /tmp'de root sahipli eski bir dosya kalmissa (sticky bit yuzunden)
  # n8n'in 'node' kullanicisi uzerine YAZAMAZ ve export sessizce
  # 'EACCES' ile duser. Bu, yedeksiz yayinlamaya yol aciyordu.
  docker exec -u 0 "$KAP" rm -f "/tmp/onceki-$ID.json" >/dev/null 2>&1
  HATA=$(docker exec "$KAP" n8n export:workflow --id="$ID" --output="/tmp/onceki-$ID.json" 2>&1)
  if [ $? -eq 0 ] && docker cp "$KAP:/tmp/onceki-$ID.json" "$GECICI/" >/dev/null 2>&1; then
    echo "  ok  $ID disa aktarildi"
  else
    sari "  UYARI: $ID disa aktarilamadi"
    echo "$HATA" | grep -iE "error|eacces|denied" | head -2 | sed 's/^/        /'
    EXPORT_TAMAM=0
  fi
done

if [ "$EXPORT_TAMAM" -eq 1 ] && [ -n "$(ls -A "$GECICI" 2>/dev/null)" ]; then
  NESIL="$GERI_DONUS/$(date +%Y%m%d-%H%M%S)"
  mv "$GECICI" "$NESIL"
  # Guncel geri donus noktasi her zaman ayni yerde dursun
  rm -f "$GERI_DONUS"/*.json 2>/dev/null
  cp "$NESIL"/*.json "$GERI_DONUS/" 2>/dev/null
  echo "  ok  geri donus noktasi: $(basename "$NESIL")"
  # Son 5 nesli tut
  ls -1dt "$GERI_DONUS"/2* 2>/dev/null | tail -n +6 | xargs -r rm -rf
else
  rm -rf "$GECICI"
  kirmizi "  DIKKAT: yeni geri donus noktasi URETILEMEDI."
  sari   "          Onceki nokta korundu, ama o ESKI bir surum."
  sari   "          Geri donmek gerekirse bugunku degisiklikler kaybolur."
fi

# -----------------------------------------------------------------------------
baslik "5/7  URET VE DOGRULA  (henuz aktarim YOK)"
# 🔴 Once HEPSI uretilir ve dogrulanir, sonra aktarilir.
# Boylece uretim/anahtar hatasi canli sisteme HIC dokunmadan yakalanir -
# yarida kesilip workflow'lari yayindan dusurme riski ortadan kalkar.
# -----------------------------------------------------------------------------
# 🔴 URETIM ANINDA GOMULEN SIRLAR
#
# n8n'de `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` -- Code dugumu ortam degiskeni
# OKUYAMAZ. Meta webhook dogrulama anahtari bu yuzden calisma aninda
# alinamiyor ve URETIM aninda gomulmek zorunda.
#
# 🔴 NEDEN ZORUNLU: 26.09.2026'da olculdu, canli WhatsApp workflow'unda bu
#    deger HALA 'BURAYA_META_DOGRULAMA_ANAHTARI' placeholder'iydi. Yani o
#    kanalin Meta dogrulamasi hicbir zaman tamamlanamazdi ve kanal "aktif"
#    gorunurken ise yaramaz durumdaydi. Ureticiler artik anahtar
#    verilmezse PATLIYOR; sessizce bozuk workflow uretmiyor.
#
# Anahtar KAYNAKTA DURMAZ, yalniz .env'de. Buradan tek satir okunur ve
# ureticiye ortam degiskeni olarak gecirilir.
URETIM_SIRLARI=()
# Her sir: ureticinin bekledigi degisken adi. Eksikse UYARI verilir ve
# ilgili uretici zaten patlar -- sessizce bozuk workflow uretilmez.
for _ad in MESSENGER_VERIFY_TOKEN WHATSAPP_VERIFY_TOKEN MESSENGER_PANEL_TOKEN; do
  _deg=$(awk -F= -v a="^${_ad}=" '$0 ~ a {print substr($0, index($0,"=")+1); exit}' /opt/lcarlie/n8n/.env 2>/dev/null || true)
  if [ -n "${_deg:-}" ]; then
    URETIM_SIRLARI+=(-e "${_ad}=${_deg}")
  else
    sari "  UYARI: $_ad .env'de yok - o kanalin ureticisi patlayacak"
  fi
done
unset _ad _deg

HAZIR=()
for w in "${WORKFLOWLAR[@]}"; do
  ID="${w%%|*}"; ARA="${w#*|}"; BUILD="${ARA%%|*}"; JSON="${ARA##*|}"

  # 🔴 EKSIK URETICI = BASARISIZ YAYINLAMA.
  # Once "ATLANDI" deyip devam ediyordu ve hicbir sayac artmiyordu.
  # O workflow yeniden uretilmiyor, aktarilmiyor - ama 7. adim yalnizca
  # veritabanindaki 'active' bayragina baktigi icin onceki yayindan kalma
  # AKTIF degerini gorup YESIL yaziyor, SORUN 0 kaliyor ve hat
  # "YAYINLAMA BASARILI" deyip 0 ile cikiyordu.
  # Yani build-sohbet-workflow.js gonderilemese bile satis ajani gunlerce
  # eski mantikla calisir, herkes yayinin gectigini sanirdi.
  # Testler icin ayni kural zaten var: testin yoklugu gecmesi demek degil.
  if ! docker exec "$KAP" test -f "/tmp/$BUILD"; then
    kirmizi "  HATA: $BUILD kapsayicida yok - hicbir sey aktarilmadi"
    kirmizi "  (kaynak dosya gonderilememis olabilir)"
    exit 1
  fi

  if ! docker exec ${URETIM_SIRLARI[@]+"${URETIM_SIRLARI[@]}"} "$KAP" node "/tmp/$BUILD" >/dev/null 2>&1; then
    kirmizi "  HATA: $BUILD calistirilamadi - hicbir sey aktarilmadi"
    exit 1
  fi

  # Panel anahtari - yer tutucu varsa yerine konur (deger EKRANA BASILMAZ)
  if docker exec "$KAP" grep -q "BURAYA_PILOT_ANAHTARI" "/tmp/$JSON" 2>/dev/null; then
    # 🔴 BOS ANAHTAR SESSIZCE YERLESTIRILIYORDU.
    # grep bir sey bulamazsa TOK="" olur; sed yer tutucuyu BOS DIZE ile
    # degistirir, "kalan yer tutucu" kontrolu 0 doner ve hat
    # "anahtar yerlestirildi" yazip devam ederdi. Panel ya herkese acik
    # kalir ya hic kimseyi iceri almaz - iki durumda da yayin basarili gorunur.
    # Ayrica 'cut -d= -f2' ilk '=' isaretinde keser: icinde '=' gecen bir
    # anahtar (base64/JWT) sessizce kirpilirdi. sed ile tamami alinir.
    TOK=$(sed -n 's/^PILOT_TOKEN=//p' /opt/lcarlie/n8n/.env | head -n1)
    if [ -z "$TOK" ]; then
      kirmizi "  HATA: PILOT_TOKEN .env icinde bos veya bulunamadi"
      kirmizi "  Bos anahtarla yayinlamak paneli korumasiz birakir - durduruldu."
      exit 1
    fi
    # 🔴 /g SART: yer tutucu hem aciklamada hem sabitte geciyor olabilir
    docker exec -e TOK="$TOK" "$KAP" sh -c "sed -i \"s|BURAYA_PILOT_ANAHTARI|\$TOK|g\" /tmp/$JSON"
    # 🔴 'grep -c ... || echo 0' KULLANMA: eslesme yoksa grep 1 doner ve
    #    ciktiya IKINCI bir 0 eklenir ("0\n0"), sahte hata uretir. Bu tuzaga dustum.
    KALAN=$(docker exec "$KAP" grep -o "BURAYA_PILOT_ANAHTARI" "/tmp/$JSON" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$KALAN" != "0" ]; then
      kirmizi "  HATA: $JSON icinde $KALAN yer tutucu kaldi - hicbir sey aktarilmadi"
      exit 1
    fi
    echo "  ok  $ID  uretildi + anahtar yerlestirildi"
  else
    echo "  ok  $ID  uretildi"
  fi

  HAZIR+=("$ID|$JSON")
done

if [ "${#HAZIR[@]}" -eq 0 ]; then
  kirmizi "  Aktarilacak workflow yok."
  exit 1
fi

# -----------------------------------------------------------------------------
baslik "6/7  AKTAR, YAYINLA VE YENIDEN BASLAT"
# Buradan itibaren canli sisteme dokunuluyor - guvenlik agi devrede.
AKTARIM_BASLADI=1
for h in "${HAZIR[@]}"; do
  ID="${h%%|*}"; JSON="${h##*|}"
  docker exec "$KAP" n8n import:workflow --input="/tmp/$JSON" >/dev/null 2>&1 \
    && echo "  ok  $ID  aktarildi" \
    || { kirmizi "  HATA: $ID aktarilamadi"; exit 1; }
done

# 🔴 import:workflow workflow'u YAYINDAN DUSURUR - burasi atlanamaz
# 🔴 AMA YALNIZCA 'aktif_olmali=evet' OLANLAR YAYINA ALINIR (CR-002).
for h in "${HAZIR[@]}"; do
  ID="${h%%|*}"
  ISTENEN="hayir"
  for a in "${AKTIF_EDILECEKLER[@]}"; do [ "$a" = "$ID" ] && ISTENEN="evet" && break; done
  if [ "$ISTENEN" = "evet" ]; then
    docker exec "$KAP" n8n update:workflow --id="$ID" --active=true >/dev/null 2>&1 \
      && echo "  ok  $ID  yayina alindi" \
      || sari "  UYARI: $ID yayina alinamadi"
  else
    # import zaten pasif birakir; yine de acikca pasiflestirip DOGRULUYORUZ -
    # "herhalde pasiftir" varsayimi tam da bu CR'nin kapatmaya calistigi sey.
    docker exec "$KAP" n8n update:workflow --id="$ID" --active=false >/dev/null 2>&1
    echo "  --  $ID  BILEREK yayina alinmadi (yapilandirma: aktif_olmali=hayir)"
  fi
done

echo "  n8n yeniden baslatiliyor..."
docker restart "$KAP" >/dev/null
# 🔴 SABIT 'sleep 28' YERINE HAZIR OLANA KADAR BEKLE.
# Sistemdeki diger butun betikler (geri-don, geri-yukle, hiz-sifirla)
# 45x2sn yoklama kullaniyor; en kritik olan yayinlama hatti sabit
# bekliyordu. n8n 2.38.7 acilista goc (migration) calistiriyor; yogun
# bir makinede 28 saniye yetmeyebilir. Yetmedigi anda dogrulama 502
# alir, SORUN artar, betik exit 1 verir, EXIT tuzagi devreye girip
# n8n'i BIR KEZ DAHA yeniden baslatir ve operatore "yayinlama yarida
# kesildi" denir - oysa her sey dogru aktarilmistir. Operator saglam
# bir yayini geri almaya yonlendirilir.
HAZIR=0
for _ in $(seq 1 45); do
  sleep 2
  if [ "$(curl -s --max-time 10 --connect-timeout 5 -o /dev/null -w '%{http_code}' https://n8n.lcarlie.shop/ 2>/dev/null)" = "200" ]; then
    HAZIR=1; break
  fi
done
if [ "$HAZIR" -eq 1 ]; then
  echo "  ok  n8n yanit veriyor"
else
  sari "  UYARI: n8n 90 sn icinde yanit vermedi - dogrulama yine de denenecek"
fi

# -----------------------------------------------------------------------------
baslik "7/7  DOGRULAMA"
SORUN=0

echo "  --- Yayin durumu (veritabanindan) ---"
DURUM=$(docker exec "$DB" psql -U n8n -d n8n -tAc \
  "SELECT id || '|' || active FROM workflow_entity;" 2>/dev/null)
# 🔴 DOGRULAMA ARTIK "BEKLENEN DURUM"A GORE YAPILIR.
#    Onceki hali her workflow'un YAYINDA olmasini bekliyordu; bilerek
#    kapatilmis bir workflow "YAYINDA DEGIL" diye kirmizi sayilirdi ve
#    operatoru saglam bir yayini geri almaya yonlendirirdi. Ayni sekilde,
#    pasif kalmasi gereken bir workflow yanlislikla acilirsa bu da ARIZADIR.
for w in "${WORKFLOWLAR[@]}"; do
  ID="${w%%|*}"
  ISTENEN="hayir"
  for a in "${AKTIF_EDILECEKLER[@]}"; do [ "$a" = "$ID" ] && ISTENEN="evet" && break; done
  SATIR=$(echo "$DURUM" | grep "^$ID|" || true)
  if [ -z "$SATIR" ]; then
    kirmizi "      $ID  BULUNAMADI"
    SORUN=$((SORUN+1))
  elif echo "$SATIR" | grep -qE "\|(t|true)$"; then
    GERCEK="evet"
  else
    GERCEK="hayir"
  fi
  if [ -n "$SATIR" ]; then
    if [ "$GERCEK" = "$ISTENEN" ]; then
      if [ "$ISTENEN" = "evet" ]; then yesil "      $ID  YAYINDA (beklenen)"
      else                             yesil "      $ID  PASIF (beklenen)"; fi
    else
      kirmizi "      $ID  BEKLENEN=$ISTENEN GERCEK=$GERCEK"
      SORUN=$((SORUN+1))
    fi
  fi
done

echo "  --- Uc noktalar ---"
# 🔴 YENIDEN DENEME SART - YARIS KOSULU VAR.
#    n8n yeniden baslatildiktan sonra HTTP 200 dondugu anda webhook
#    kayitlari HENUZ TAMAMLANMAMIS olabiliyor. 15.09.2026'da tam bu oldu:
#    /webhook/whatsapp dogrulama adiminda 404 dondu, birkac saniye sonra
#    elle bakildiginda 200 veriyordu. Yani SAGLAM bir yayin "basarisiz"
#    isaretlendi ve EXIT tuzagi devreye girdi. Tek seferlik olcum,
#    yeniden baslayan bir servis icin yeterli degildir.
uc_nokta_dene() {   # uc_nokta_dene <adres>  -> son HTTP kodunu basar
  local adres="$1" kod="" i
  for i in 1 2 3 4 5 6; do
    kod=$(curl -s --max-time 20 --connect-timeout 5 -o /dev/null -w "%{http_code}" "$adres")
    [ "$kod" = "200" ] && break
    sleep 5
  done
  printf '%s' "$kod"
}
for u in "https://n8n.lcarlie.shop/|panel" \
         "https://n8n.lcarlie.shop/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=x&hub.challenge=1|whatsapp"; do
  ADRES="${u%%|*}"; AD="${u##*|}"
  KOD=$(uc_nokta_dene "$ADRES")
  if [ "$KOD" = "200" ]; then yesil "      $AD  HTTP $KOD"; else kirmizi "      $AD  HTTP $KOD"; SORUN=$((SORUN+1)); fi
done

echo "  --- Duman testi (dagitilmis ajan) ---"
# 🔴 HEDEF KANAL YAPILANDIRMADAN GELIR, SABIT DEGIL.
#    Onceki hali /webhook/sohbet'e sabitlenmisti. O kanal 15.09'da bilerek
#    devre disi birakilinca her yayinlama "AJAN GERCEK CEVAP URETMIYOR"
#    diyerek basarisiz oldu ve operatoru SAGLAM bir yayini geri almaya
#    yonlendirdi. Sabit ID'ler bu projede ucuncu kez ayni sinif hatayi
#    uretti (durum sayfasi, yayinlama, duman testi).
DUMAN_AKTIF=0
for a in "${AKTIF_EDILECEKLER[@]}"; do [ "$a" = "${DUMAN_WORKFLOW:-}" ] && DUMAN_AKTIF=1 && break; done
if [ "$DUMAN_AKTIF" -eq 0 ]; then
  # 🔴 ATLANAN KONTROL BASARILI SAYILMAZ (CR-002 madde 9) - ama saglam bir
  #    yayini da dusurmez. Acikca yazilir ki kimse "test gecti" sanmasin.
  sari "      ATLANDI - duman testi kanali (${DUMAN_WORKFLOW:-tanimsiz}) aktif degil"
  sari "      DIKKAT: dagitilmis ajan bu yayinlamada DOGRULANMADI."
else
# 🔴 "cevap" anahtarini aramak YETMEZ.
# Ajan tamamen olse bile workflow VARSAYILAN metni yine "cevap" alaninda
# donuyordu; test gecer, durum sayfasi yesil kalir ve satis kanali
# GUNLERCE sessizce olu kalabilirdi. Bu yuzden GERCEK bir urun cevabi
# isteniyor: bilinen bir urunun adi ve fiyati donmeli, otomatik olmali.
duman_gonder() {
  curl -s --max-time 30 --connect-timeout 5 -X POST "https://n8n.lcarlie.shop${DUMAN_YOL}" \
    -H "Content-Type: application/json" \
    -d "{\"mesaj\":\"${DUMAN_MESAJ}\",\"musteriId\":\"${DUMAN_KIMLIK}\"}" 2>/dev/null
}
CEVAP=$(duman_gonder)

# 🔴 DUMAN TESTI KENDI HIZ SINIRIMIZA TAKILABILIR.
# Duman testi sunucunun KENDI IP'sinden gidiyor; yuk testi, izleme veya
# arka arkaya yayinlama o IP kovasini doldurmus olabilir. O zaman ajan
# gayet saglam calisirken yayinlama "AJAN GERCEK CEVAP URETMIYOR" deyip
# basarisiz olur ve operator saglam bir yayini geri almaya yonlendirilir.
# (14.09.2026'da tam bu oldu: 100 istekli paralel test kovayi doldurdu.)
# Sinira takildiysak SADECE IP kovalarini temizleyip BIR KEZ tekrar dene.
if echo "$CEVAP" | grep -q "Çok sayıda mesaj"; then
  sari "      duman testi hiz sinirina takildi - kovalar temizlenip tekrar denenecek"
  # 🔴 Yalnizca HIZ kovalari temizlenir; kayitlar/eskalasyonlar ASLA silinmez.
  #    Hedef workflow yapilandirmadan gelir, sabit ID yok.
  docker exec "$DB" psql -U n8n -d n8n -c \
    "UPDATE workflow_entity
        SET \"staticData\" = jsonb_set(
              jsonb_set(\"staticData\"::jsonb, '{global,hiz}',   '{}'::jsonb, true),
              '{global,ipHiz}', '{}'::jsonb, true)::text::json
      WHERE id='${DUMAN_WORKFLOW}';" >/dev/null 2>&1
  sleep 3
  CEVAP=$(duman_gonder)
fi

# 🔴 FIYATI SABIT KODLAMA - ajanin KENDI kaynagindan oku.
# Onceki hali '900' ariyordu. LIPVORA'nin fiyati degistigi gun -ki bu
# sizin ticari kararinizdir, bu dosyayi kimse acmaz- HER YAYIN dogrulamayi
# gecemez, EXIT tuzagi devreye girer ve operatore "yayinlama yarida
# kesildi, geri donmek ister misiniz" denir. Sebebi de hicbir yerde yazmaz.
# (SUNACNEA fiyatini 990'dan 1.200'e cekerken bu tuzagin kiyisindan donduk.)
BEKLENEN_FIYAT=$(docker exec "$KAP" node -e "
try {
  const u = require('/tmp/urunler.js');
  const t = (u.URUNLER || u)['${DUMAN_URUN}'];
  process.stdout.write(String((t && t.fiyat ? t.fiyat : '').replace(/[^0-9]/g,'')));
} catch (e) { process.stdout.write(''); }
" 2>/dev/null)
if [ -z "$BEKLENEN_FIYAT" ]; then
  sari "      urunler.js'den ${DUMAN_URUN} fiyati okunamadi - yalniz urun adi aranacak"
fi

if echo "$CEVAP" | grep -q '"otomatik":true' && echo "$CEVAP" | grep -q "$DUMAN_URUN" \
   && { [ -z "$BEKLENEN_FIYAT" ] || echo "$CEVAP" | grep -q "$BEKLENEN_FIYAT"; }; then
  yesil "      ${DUMAN_WORKFLOW}  gercek urun cevabi dondu (${DUMAN_URUN} ${BEKLENEN_FIYAT:-?} TL)"
else
  kirmizi "      ${DUMAN_WORKFLOW}  AJAN GERCEK CEVAP URETMIYOR"
  echo "        donen: $(echo "$CEVAP" | head -c 140)"
  SORUN=$((SORUN+1))
fi
fi   # <- duman testi kanali aktif mi blogunun sonu

# -----------------------------------------------------------------------------
echo ""
if [ "$SORUN" -eq 0 ]; then
  yesil "=============================================================="
  yesil " YAYINLAMA BASARILI"
  yesil "=============================================================="
  /opt/lcarlie/durum-uret.sh >/dev/null 2>&1 || true
  exit 0
fi

kirmizi "=============================================================="
kirmizi " DOGRULAMA BASARISIZ - $SORUN sorun"
kirmizi "=============================================================="
echo ""
sari " Geri donmek icin:"
sari "   /opt/lcarlie/n8n-geri-don.sh"
echo ""
sari " Geri donus dosyalari: $GERI_DONUS"
exit 1
