#!/usr/bin/env bash
# L'CARLIE gece yedeklemesi. Ciktilar SIFRELIDIR (AES-256).
set -uo pipefail

# --yerel : Google Drive aktarimini atla.
# Yayinlama hatti her calistiginda Drive'a yuklemek KOTA doldurur
# (13.09.2026: 15+ yayinlama -> Google 'Request a higher quota limit' dedi).
# Geri donus noktasi zaten YEREL dosya; Drive'a gece yedegi yukler.
YEREL_SADECE=0
for a in "$@"; do [ "$a" = "--yerel" ] && YEREL_SADECE=1; done


BASE="/opt/lcarlie"
STACK="$BASE/n8n"
BK="$BASE/backup"
TS="$(date +%Y-%m-%d_%H%M)"
LOG="$BK/log/backup-$(date +%Y-%m).log"
STATUS="BASARILI"
DETAY=""

mkdir -p "$BK/log" "$BK/archive"
exec 3>&1
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG" >&3; }
fail() { STATUS="BASARISIZ"; DETAY="${DETAY}
- $*"; say "HATA: $*"; }

say "===== Yedekleme basladi ($TS) ====="

# ayarlar + gizli anahtarlar
# shellcheck disable=SC1090
. "$BK/backup.conf"
set -a; . "$STACK/.env"; set +a

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- 1) PostgreSQL ---
if docker exec lcarlie-postgres pg_dump -U n8n -d n8n -Fc -f /tmp/n8n.dump 2>>"$LOG" \
   && docker cp lcarlie-postgres:/tmp/n8n.dump "$WORK/n8n-db.dump" 2>>"$LOG"; then
  docker exec lcarlie-postgres rm -f /tmp/n8n.dump 2>/dev/null
  say "PostgreSQL dump alindi ($(du -h "$WORK/n8n-db.dump" | cut -f1))"
else
  fail "PostgreSQL dump alinamadi"
fi

# --- 2) n8n workflow disa aktarimi (kimlik bilgileri DAHIL DEGIL) ---
if docker exec lcarlie-n8n n8n export:workflow --all --output=/tmp/workflows.json >>"$LOG" 2>&1 \
   && docker cp lcarlie-n8n:/tmp/workflows.json "$WORK/workflows.json" 2>>"$LOG"; then
  docker exec lcarlie-n8n rm -f /tmp/workflows.json 2>/dev/null
  say "Workflow'lar disa aktarildi"
else
  say "NOT: workflow disa aktarimi atlandi (henuz workflow yok olabilir)"
  echo '[]' > "$WORK/workflows.json"
fi

# --- 3) Yapilandirma (gizli .env HARIC) ---
# 🔴 EKSIK BIR YAN DOSYA YUZUNDEN VERITABANI DOKUMU CÖPE GITMESIN.
# Onceki hali 'cp ... 2>/dev/null' ile hatayi gizliyor, sonra tar bu
# dosya adlarini ACIKCA listeliyordu. Caddyfile yeniden adlandirilmis
# olsa tar "Cannot stat" ile cikis 2 verir ve saniyeler once BASARIYLA
# alinmis 13 MB'lik PostgreSQL dokumu paketlenmeden atilirdi -
# o gece HIC yedek olusmazdi. Ustelik hata mesaji "Sifreleme/paketleme
# basarisiz" diyerek operatoru BACKUP_ENC_KEY'e yonlendirirdi.
for Y in docker-compose.yml Caddyfile; do
  if ! cp "$STACK/$Y" "$WORK/" 2>>"$LOG"; then
    say "UYARI: $Y kopyalanamadi - yedege dahil edilmeyecek (veritabani dokumu korunuyor)"
  fi
done
echo "n8n_image=${N8N_IMAGE_TAG:-latest}" > "$WORK/SURUM.txt"

# --- 4) Paketle ve SIFRELE ---
OUT="$BK/archive/lcarlie-n8n-$TS.tgz.enc"
# Veritabani dokumu ZORUNLU; yan dosyalar varsa eklenir.
if [ ! -s "$WORK/n8n-db.dump" ]; then
  fail "Veritabani dokumu yok veya bos - yedek olusturulmadi"
fi
PAKET="n8n-db.dump workflows.json SURUM.txt"
for Y in docker-compose.yml Caddyfile; do
  [ -f "$WORK/$Y" ] && PAKET="$PAKET $Y"
done
if tar -czf "$WORK/bundle.tgz" -C "$WORK" $PAKET 2>>"$LOG" \
   && openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
        -in "$WORK/bundle.tgz" -out "$OUT" -pass "env:BACKUP_ENC_KEY" 2>>"$LOG"; then
  chmod 600 "$OUT"
  say "Sifreli yedek olusturuldu: $(basename "$OUT") ($(du -h "$OUT" | cut -f1))"
else
  fail "Sifreleme/paketleme basarisiz"
fi

# --- 5) Harici depolamaya aktar ---
RCONF=/root/.config/rclone/rclone.conf
UZAK_TAMAM=0          # bu gecenin dosyasi off-site'ta DOGRULANDI mi
AKTARIM_HATASI=""     # asil aktarim hatasi; telafi tutarsa GERI ALINIR

# 🔴 DIS YENIDEN DENEME SART - rclone'un --retries'i BU HATAYI KAPSAMIYOR.
#    Gozlenen hata (16.09.2026):
#      Failed to create file system for "gdrive:...": couldn't find root
#      directory ID: 403 Quota exceeded ... consumer project_number:202264815644
#    Bu hata BAGLANTI KURULURKEN olusuyor, aktarim sirasinda degil; yani
#    --retries/--low-level-retries hic devreye girmiyor. Ustelik kota
#    rclone'un PAYLASILAN API projesine ait - dunyadaki tum rclone
#    kullanicilariyla ayni havuz. Kota dalgalaniyor: elle deneme calisirken
#    betikten calismiyordu. Kalici cozum kendi client_id'miz (YAPILACAKLAR 6c);
#    bu dongu o yapilana kadar belirtiyi hafifletir.
rclone_dene() {   # $1=kaynak  $2=aciklama  [$3...=ek secenekler]
  local kaynak="$1" ad="$2"; shift 2
  local i bekle=0
  for i in 1 2 3; do
    if [ "$bekle" -gt 0 ]; then
      say "UYARI: $ad ${bekle}s sonra yeniden denenecek"
      sleep "$bekle"
    fi
    if timeout 600 rclone copy "$kaynak" "$RCLONE_REMOTE/" \
         --config "$RCONF" --timeout 120s --contimeout 30s \
         --retries 2 --low-level-retries 3 "$@" >>"$LOG" 2>&1; then
      [ "$i" -gt 1 ] && say "$ad: $i. denemede basarili"
      return 0
    fi
    bekle=$(( i * 60 ))
  done
  return 1
}

# 🔴 "rclone copy basarili dondu" ILE "dosya orada" AYNI SEY DEGILDIR.
#    Cikis kodu 0 olsa bile dosyanin gercekten gittigi ve BOYUTUNUN
#    tuttugu dogrulanir. Aksi halde yarim giden bir yedek "tamam"
#    sayilir - ve bu, geri donus gereken gun anlasilir.
uzak_dogrula() {  # $1=yerel dosya yolu
  local ad boy uzak
  ad="$(basename "$1")"
  boy="$(stat -c%s "$1" 2>/dev/null)"
  [ -z "$boy" ] && return 1
  uzak="$(timeout 120 rclone lsl "$RCLONE_REMOTE/" --config "$RCONF" \
            --include "$ad" 2>/dev/null | awk 'NR==1{print $1}')"
  [ -n "$uzak" ] && [ "$uzak" = "$boy" ]
}

if [ -z "${RCLONE_REMOTE:-}" ]; then
  say "NOT: RCLONE_REMOTE bos - yedek sunucuda kaldi. Harici hedef tanimlanmali."
elif [ "${YEREL_SADECE:-0}" = "1" ]; then
  say "Harici aktarim atlandi (--yerel)"
else
  if rclone_dene "$OUT" "asil aktarim"; then
    if uzak_dogrula "$OUT"; then
      UZAK_TAMAM=1
      say "Harici depolamaya aktarildi ve DOGRULANDI: $RCLONE_REMOTE"
    else
      # HENUZ fail DEGIL: asagidaki telafi turu bu dosyayi aktarabilir.
      AKTARIM_HATASI="Aktarim basarili dondu ama dosya uzakta dogrulanamadi ($(basename "$OUT"))"
      say "UYARI: $AKTARIM_HATASI - telafi turu denenecek"
    fi
  else
    AKTARIM_HATASI="Harici depolamaya aktarim basarisiz - 3 deneme ($RCLONE_REMOTE)"
    say "UYARI: $AKTARIM_HATASI - telafi turu denenecek"
  fi

  # 🔴 TELAFI, ASIL AKTARIM BASARISIZ OLSA DA DENENIR.
  #    Onceki hali telafiyi yalnizca asil aktarim BASARILI oldugunda
  #    caliştiriyordu. Oysa telafiye en cok ihtiyac duyulan an, asil
  #    aktarimin basarisiz oldugu gecedir: o gece eksikler birikir ve
  #    bir daha denenmez. Kota dalgalandigi icin ikinci deneme tutabilir.
  # 🔴 TELAFI PENCERESI, SILME ESIGINDEN BUYUK OLMALI (ikinci tur denetimi).
  #    Onceki hali --max-age 72h idi, silme esigi ise -mtime +7 (7 gun).
  #    Arada OLU BIR BOLGE kaliyordu: 3 gunu asip da off-site'a gidememis
  #    bir dosya bir daha ASLA denenmiyor, 7. gunde "korunan" listesine
  #    dusuyor ve oradan hic cikamiyordu -> her gece kalici BASARISIZ +
  #    kalici alarm + sinirsiz disk buyumesi. Pencere artik silme esiginden
  #    2 gun GENIS.
  TELAFI_GUN=$(( ${RETENTION_DAYS:-7} + 2 ))
  if timeout 900 rclone copy "$BK/archive" "$RCLONE_REMOTE/" \
       --config "$RCONF" --include 'lcarlie-n8n-*.tgz.enc' --max-age "${TELAFI_GUN}d" \
       --timeout 120s --contimeout 30s --retries 2 \
       --transfers 1 --tpslimit 2 >>"$LOG" 2>&1; then
    say "Eksik yedek telafisi tamamlandi (son ${TELAFI_GUN} gun)"
    # Asil aktarim dusmustu ama telafi gecmis olabilir - yeniden dogrula.
    if [ "$UZAK_TAMAM" -eq 0 ] && uzak_dogrula "$OUT"; then
      UZAK_TAMAM=1
      say "Telafi sirasinda bu gecenin yedegi de aktarildi"
    fi
  else
    say "UYARI: eksik yedek telafisi yapilamadi"
  fi

  # 🔴 KARAR NOKTASI: telafi turu bittikten SONRA verilir.
  #    Asil aktarim dusup telafi tuttuysa sonuc BASARILIDIR - o dosya
  #    off-site'ta ve dogrulandi. Hatayi burada geri almazsak, calisan
  #    bir yedekleme her gece "BASARISIZ" diye alarm uretir (21.09.2026'da
  #    birebir bu oldu, 15 dakikada bir posta gitti).
  if [ -n "$AKTARIM_HATASI" ]; then
    if [ "$UZAK_TAMAM" -eq 1 ]; then
      say "NOT: asil aktarim basarisizdi ama telafi tuttu - sonuc BASARILI sayiliyor"
    else
      fail "$AKTARIM_HATASI"
    fi
  fi

  # Uzaktaki eskileri temizle - YALNIZ bu gece off-site dogrulandiysa.
  # Aktarim calismiyorken uzaktan silmek, elimizdeki tek kopyayi azaltir.
  if [ "$UZAK_TAMAM" -eq 1 ]; then
    timeout 300 rclone delete "$RCLONE_REMOTE/" --min-age "${REMOTE_RETENTION_DAYS:-30}d" \
      --config "$RCONF" --timeout 120s --retries 2 >>"$LOG" 2>&1 || true
  else
    say "Uzak temizlik ATLANDI (off-site kopya dogrulanamadi)"
  fi
fi

# --- 6) Eski yedekleri temizle ---
#
# 🔴 BURADA GERCEK BIR VERI KAYBI YOLU VARDI (16.09.2026'da bulundu).
#    fail() cikis YAPMIYOR - yalnizca STATUS'u isaretleyip devam ediyor.
#    Yani aktarim basarisiz olsa bile bu satir calisiyordu ve 7 gunden
#    eski yerel yedekleri SILIYORDU. Aktarim ust uste 7 gun basarisiz
#    olsaydi (kota sorunu 13.09'dan beri arali arali suruyor), o yedekler
#    hem yerelden silinmis hem uzaga hic gitmemis olurdu: HICBIR YERDE
#    kalmazlardi. Ustelik panel "91 yedek var" diye guven verirdi.
#
#    Yeni kural: OFF-SITE KOPYASI DOGRULANMAYAN DOSYA, ESKI OLSA DA SILINMEZ.
if [ -n "${RCLONE_REMOTE:-}" ] && [ "${YEREL_SADECE:-0}" != "1" ]; then
  UZAK_LISTE="$(timeout 180 rclone lsf "$RCLONE_REMOTE/" --config "$RCONF" 2>/dev/null)"
  UZAK_KOD=$?
else
  UZAK_LISTE=""; UZAK_KOD=1
fi

KORUNAN=0
if [ "$UZAK_KOD" -eq 0 ] && [ -n "$UZAK_LISTE" ]; then
  while IFS= read -r -d '' D; do
    if printf '%s\n' "$UZAK_LISTE" | grep -qxF "$(basename "$D")"; then
      rm -f "$D" 2>>"$LOG"
    else
      KORUNAN=$(( KORUNAN + 1 ))
    fi
  done < <(find "$BK/archive" -name 'lcarlie-n8n-*.tgz.enc' \
             -mtime "+${RETENTION_DAYS:-7}" -print0 2>>"$LOG")
  if [ "$KORUNAN" -gt 0 ]; then
    # 🔴 BU 'fail' DEGIL (ikinci tur denetimi).  Onceki hali burada fail()
    #    cagiriyordu; sonucta off-site aktarimi BASARIYLA dogrulanmis bir
    #    calisma bile "BASARISIZ" bitiyordu ve mesaj olgusal olarak yanlisti
    #    ("harici aktarim calismiyor" derken 7 saniye once aktarim yapilmisti).
    #    "Bu gecenin yedegi alinamadi" ile "gecmisten artik var" AYRI
    #    arizalardir; ikincisi calismayi dusurmez, ayri bir uyari uretir.
    #    Her gece kirmizi yanan alarm, bakilmayan alarmdir.
    say "UYARI: $KORUNAN eski yedek off-site kopyasi olmadigi icin silinmedi"
    "$BASE/alarm.sh" DEGRADED backup.offsite.eksik \
      "$KORUNAN eski yedegin off-site kopyasi yok" \
      "Bu dosyalar yerelde tutuluyor (silinmedi), veri kaybi YOK. Telafi penceresi ${TELAFI_GUN:-9} gun." 2>/dev/null || true
  fi
else
  # Uzak liste alinamadiysa HICBIR SEY SILINMEZ. "Bilmiyorum" durumunda
  # silmek, en kotu varsayimla hareket etmektir.
  ESKI=$(find "$BK/archive" -name 'lcarlie-n8n-*.tgz.enc' -mtime "+${RETENTION_DAYS:-7}" | wc -l)
  [ "$ESKI" -gt 0 ] && say "UYARI: uzak liste alinamadi - $ESKI eski yedek silinmedi (guvenli taraf)"
fi

ADET=$(find "$BK/archive" -name 'lcarlie-n8n-*.tgz.enc' | wc -l)
say "Sunucuda tutulan yedek adedi: $ADET (hedef: son ${RETENTION_DAYS:-7} gun)"

# --- 7) Bildirim ---
#
# 🔴 CR-002'DE BULUNAN SESSIZ HATA:
#    Onceki hali 'msmtp --read-envelope-from "$NOTIFY_EMAIL"' kullaniyordu
#    ama urettigi mailde "From:" BASLIGI HIC YOKTU. --read-envelope-from
#    zarf gondericisini From basligindan okur; baslik olmayinca msmtp
#    "envelope-from address is missing" deyip EX_NOPERM (78) ile cikiyordu.
#    Yani NOTIFY_EMAIL doldurulmus olsa bile TEK BIR BILDIRIM GITMEZDI ve
#    betik yalnizca "NOT: e-posta gonderilemedi" diye log'a yazip devam
#    ederdi - kimse fark etmezdi. 15.09.2026'da canlida birebir dogrulandi.
#
# 🔴 BILDIRIM ARTIK ALARM MERKEZINDEN GECER (/opt/lcarlie/alarm.sh):
#    - olay ONCE diske yazilir (e-posta calismasa bile kaybolmaz)
#    - ayni ariza tekrar tekrar mail atmaz (dedup)
#    - mail gonderilemezse bu da ayrica kaydedilir ve durum sayfasinda gorunur
#    alarm.sh cikis kodu her zaman 0'dir; bildirim yedeklemeyi dusuremez.
ALARM_BETIK=/opt/lcarlie/alarm.sh
if [ -x "$ALARM_BETIK" ]; then
  BILDIRIM_DETAY="$(
    echo "Durum   : $STATUS"
    echo "Tarih   : $TS"
    echo "Dosya   : $(basename "$OUT")"
    echo "Boyut   : $(du -h "$OUT" 2>/dev/null | cut -f1)"
    echo "Sunucuda: $ADET yedek"
    echo "Harici  : ${RCLONE_REMOTE:-tanimli degil}"
    [ -n "$DETAY" ] && { echo; echo "Sorunlar:$DETAY"; }
    echo
    echo "Log: $LOG"
  )"
  if [ "$STATUS" = "BASARISIZ" ]; then
    "$ALARM_BETIK" FAILED "backup.calisma" "Yedekleme BASARISIZ - $TS" "$BILDIRIM_DETAY" >/dev/null 2>&1
    say "Alarm uretildi (backup.calisma / FAILED)"
  else
    # Basarili yedekte once "duzeldi" bilgisi verilir (acik alarm varsa kapanir).
    "$ALARM_BETIK" COZULDU "backup.calisma" "Yedekleme tekrar basarili - $TS" "$BILDIRIM_DETAY" >/dev/null 2>&1
    if [ "${NOTIFY_ON_SUCCESS:-1}" = "1" ]; then
      "$ALARM_BETIK" BILGI "backup.basarili" "Yedekleme basarili - $TS" "$BILDIRIM_DETAY" >/dev/null 2>&1
    fi
    say "Alarm merkezine bildirildi (backup.calisma / BASARILI)"
  fi
else
  # 🔴 Alarm betigi yoksa bu sessizce gecilmez - log'a acikca yazilir.
  say "UYARI: alarm betigi bulunamadi ($ALARM_BETIK) - bildirim URETILEMEDI"
fi

# 🔴 CALISMA TURU LOGA YAZILIR (CR-002).
#    Onceki hali her calismayi ayni cumleyle bitiriyordu: "Yedekleme bitti:
#    BASARILI". Oysa iki farkli sey var:
#      tam   : gece yedegi - Drive'a da yukler, GERCEK yedekleme budur
#      yerel : her yayinlamada calisan '--yerel' - Drive'a BILEREK yuklemez
#    Ikisi ayirt edilemedigi icin, 03:30'da BASARISIZ biten gece yedeginin
#    ustune gun icinde bir yayinlama yapilinca log'un son satiri "BASARILI"
#    oluyor ve gosterge gece arizasini GIZLIYORDU. 15.09.2026'da birebir
#    bu oldu: 03:30 BASARISIZ, 22:49 (yerel) BASARILI, panel sakin.
MOD_ETIKET=$([ "${YEREL_SADECE:-0}" = "1" ] && echo "yerel" || echo "tam")
say "===== Yedekleme bitti: $STATUS ($MOD_ETIKET) ====="
[ "$STATUS" = "BASARILI" ] || exit 1
exit 0
