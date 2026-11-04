#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - 1 EKIM'E KADAR GUNLUK HAZIRLIK KONTROLU
#
# Chief Architect talimati (16.09.2026):
#   "Son hafta gunluk su readiness kontrolunu calistir: 7 madde.
#    Bunlardan ilk ucu gecmiyorsa 1 Ekim geldi diye ROAS'i karar metrigi yapma."
#
# 🔴 BETIK OLCER, VIEW KARAR VERIR.  Yedek dosya sisteminde yasar,
#    PostgreSQL icinden gorunmez. O yuzden burada olculur, core.ayar'a
#    yazilir ve mart.gunluk_hazirlik oradan okur. Esik degeri iki yerde
#    tutulmaz: "taze mi" sorusunu yalniz view cevaplar.
#
# 🔴 HICBIR SEY DUZELTMEZ.  Bu betik yalniz olcer ve yazar. Eksigi kapatmak
#    insanin isi; kapatiyormus gibi yapan bir kontrol, kontrol degildir.
#
# Cikis kodu:  0 = 7/7 gecti · 1 = P0 kapisi KAPALI · 3 = P0 acik, destek eksik
#
# Kullanim: /opt/lcarlie/hazirlik-gunluk.sh
# =============================================================================
set -uo pipefail

KAP=lcarlie-postgres
VT="${LCARLIE_VT:-n8n}"

sorgu() { docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -F'|' -v ON_ERROR_STOP=1 2>&1; }

# --- 1) YEDEK OLCUMU ----------------------------------------------------------
# 🔴🔴 ONCEKI SURUM YANLIS YERE BAKIYORDU - ve bu, olcumun kendisinden
#    daha buyuk bir hataydi. `/opt/lcarlie/yedek` diye bir dizin hic
#    olmadi; gercek yedek sistemi `/opt/lcarlie/backup` altinda,
#    zamanlamasi da `crontab -l` de degil `/etc/cron.d/lcarlie-backup`
#    icinde. Ben yalniz `crontab -l` ye bakip "planli yedek YOK" dedim.
#    YANLISTI: gunluk 03:30 yedegi, sifreleme, uzak kopya, aylik geri
#    yukleme testi - hepsi kurulu ve calisiyordu. Bir seyi bulamamak,
#    onun olmadigini kanitlamaz.
#
# 🔴 DURUM DORT DEGERLI, iki degil:
#      HEALTHY  = planli yerel yedek TAZE + sifreli uzak kopya TAZE
#      DEGRADED = yerel taze ama guvenli uzak kopya eksik/bayat
#      FAILED   = yerel yedek yok/bayat ya da geri yukleme testi basarisiz
#      UNKNOWN  = olcum yapilamiyor (dizin okunamiyor, rclone cevap vermiyor)
#    UNKNOWN, FAILED DEGILDIR ve HEALTHY hic degildir: "bilmiyoruz" kendi
#    basina bir cevaptir ve bastirilmamalidir.
#
# 🔴 ELLE ALINMIS CR DUMP'I HICBIR ZAMAN HEALTHY URETMEZ.  Yalniz
#    `archive/lcarlie-n8n-*.tgz.enc` deseni planli yedek sayilir.
BK=/opt/lcarlie/backup
ARSIV_DIZIN="$BK/archive"
TAZE_SAAT=${LCARLIE_YEDEK_TAZE_SAAT:-36}
UZAK_HEDEF=$(grep -E '^RCLONE_REMOTE=' "$BK/backup.conf" 2>/dev/null | cut -d= -f2- | tr -d '"')

YEDEK_DURUM=UNKNOWN
YEDEK_ZAMAN=""
YEDEK_NOT=""
not_ekle() { YEDEK_NOT="${YEDEK_NOT:+$YEDEK_NOT · }$1"; }

# (a) YEREL PLANLI YEDEK
SON_ARSIV=$(ls -t "$ARSIV_DIZIN"/lcarlie-n8n-*.tgz.enc 2>/dev/null | head -1)
if [ -z "$SON_ARSIV" ]; then
  YEDEK_DURUM=FAILED
  not_ekle "planli yedek arsivi YOK ($ARSIV_DIZIN)"
else
  YEREL_ZAMAN=$(date -Iseconds -r "$SON_ARSIV" 2>/dev/null)
  YEREL_YAS_SAAT=$(( ( $(date +%s) - $(stat -c %Y "$SON_ARSIV") ) / 3600 ))
  ADET=$(ls "$ARSIV_DIZIN"/lcarlie-n8n-*.tgz.enc 2>/dev/null | wc -l)
  # 🔴 Boyut sifir olan bir arsiv "var" sayilmaz.
  BOY=$(stat -c %s "$SON_ARSIV" 2>/dev/null || echo 0)
  if [ "${BOY:-0}" -le 0 ]; then
    YEDEK_DURUM=FAILED; not_ekle "son arsiv 0 bayt"
  elif [ "$YEREL_YAS_SAAT" -gt "$TAZE_SAAT" ]; then
    YEDEK_DURUM=FAILED
    not_ekle "yerel yedek BAYAT (${YEREL_YAS_SAAT} saat, esik ${TAZE_SAAT})"
  else
    YEDEK_ZAMAN="$YEREL_ZAMAN"
    not_ekle "yerel: $(basename "$SON_ARSIV") (${YEREL_YAS_SAAT} saat, ${ADET} arsiv)"
    YEDEK_DURUM=DEGRADED   # uzak kopya dogrulanana kadar en fazla DEGRADED
  fi
fi

# (b) GUVENLI UZAK KOPYA
# 🔴 Uzak hedef rclone crypt DEGIL (type=drive). Sifreleme UYGULAMA
#    KATMANINDA: arsiv yuklenmeden ONCE openssl aes-256-cbc/pbkdf2 ile
#    sifreleniyor, yani uzaga giden dosya zaten sifreli. Bunu VARSAYMIYORUZ,
#    her kosuda 'Salted__' imzasiyla DOGRULUYORUZ - sifresiz bir arsiv
#    uzaga gidiyorsa PII disari cikiyor demektir ve bu HEALTHY olamaz.
if [ "$YEDEK_DURUM" = DEGRADED ] && [ -n "${UZAK_HEDEF:-}" ]; then
  if [ "$(head -c 8 "$SON_ARSIV" 2>/dev/null)" != "Salted__" ]; then
    YEDEK_DURUM=FAILED
    not_ekle "🔴 ARSIV SIFRELI DEGIL - uzaga gonderilmemeli"
  else
    UZAK_SON=$(timeout 120 rclone lsl "$UZAK_HEDEF/" \
                 --config /root/.config/rclone/rclone.conf \
                 --include 'lcarlie-n8n-*.tgz.enc' 2>/dev/null \
               | sort -k2 | tail -1)
    if [ -z "$UZAK_SON" ]; then
      # 🔴 rclone cevap vermediginde "uzak kopya yok" DENMEZ - bilinmiyor.
      #    Google Drive kotasi bu projede bilinen, aralikli bir sorun.
      not_ekle "uzak kopya DOGRULANAMADI (rclone cevap vermedi / kota)"
    else
      UZAK_TARIH=$(awk '{print $2}' <<< "$UZAK_SON")
      UZAK_YAS_SAAT=$(( ( $(date +%s) - $(date -d "$UZAK_TARIH" +%s 2>/dev/null || echo 0) ) / 3600 ))
      if [ "$UZAK_YAS_SAAT" -le "$TAZE_SAAT" ]; then
        YEDEK_DURUM=HEALTHY
        not_ekle "uzak: sifreli kopya taze (${UZAK_YAS_SAAT} saat)"
      else
        not_ekle "uzak kopya BAYAT (${UZAK_YAS_SAAT} saat)"
      fi
    fi
  fi
elif [ "$YEDEK_DURUM" = DEGRADED ]; then
  not_ekle "RCLONE_REMOTE tanimli degil - uzak kopya yok"
fi

# (c) GERI YUKLEME TESTI
# 🔴 Geri yuklenemeyen yedek, yedek degildir. Test basarisizsa durum
#    FAILED'dir - dosyalar yerinde olsa bile.
if [ -f "$BK/son-test.txt" ]; then
  TEST_SATIR=$(cat "$BK/son-test.txt" 2>/dev/null)
  TEST_SONUC=$(cut -d'|' -f2 <<< "$TEST_SATIR")
  TEST_ZAMAN=$(cut -d'|' -f1 <<< "$TEST_SATIR")
  TEST_YAS_GUN=$(( ( $(date +%s) - $(date -d "$TEST_ZAMAN" +%s 2>/dev/null || echo 0) ) / 86400 ))
  if [ "$TEST_SONUC" != "BASARILI" ]; then
    YEDEK_DURUM=FAILED
    not_ekle "geri yukleme testi BASARISIZ"
  elif [ "$TEST_YAS_GUN" -gt 35 ]; then
    [ "$YEDEK_DURUM" = HEALTHY ] && YEDEK_DURUM=DEGRADED
    not_ekle "geri yukleme testi bayat (${TEST_YAS_GUN} gun)"
  else
    not_ekle "geri yukleme testi: BASARILI (${TEST_YAS_GUN} gun once)"
  fi
else
  [ "$YEDEK_DURUM" = HEALTHY ] && YEDEK_DURUM=DEGRADED
  not_ekle "geri yukleme testi hic yapilmamis"
fi

# 🔴 HEALTHY olmayan her durumda zaman damgasi YAZILMAZ ki view
#    "taze yedek var" diyemesin. Not her halukarda yazilir.
[ "$YEDEK_DURUM" = HEALTHY ] || YEDEK_ZAMAN=""
YEDEK_NOT="[$YEDEK_DURUM] $YEDEK_NOT"

# 🔴 Olcum SONUCU ne olursa olsun yazilir - "yazmamak" ile "yedek yok"
#    ayni seye benzemesin diye. Kayit yoksa view zaten GECMEDI uretir.
#
# 🔴 DEGERLER psql DEGISKENIYLE GECIRILIR (-v ... + :'ad').
#    Ilk surumde SQL govdesine `$$${YEDEK_ZAMAN}$$` yazilmisti: tirnaksiz
#    here-document icinde `$$` KABUGUN PID'ine genisliyor, yani uretilen
#    SQL bozuluyordu ve INSERT hicbir zaman calismadi. Hata da gorunmuyordu
#    cunku ciktisi /dev/null'a gidiyordu - "olcum yapildi" sanilan bir
#    bosluk. Simdi degerler govdeye hic girmiyor ve cikti okunuyor.
YAZ=$(docker exec -i "$KAP" psql -U n8n -d "$VT" -tA -v ON_ERROR_STOP=1 \
        -v zaman="$YEDEK_ZAMAN" -v not="$YEDEK_NOT" -v durum="$YEDEK_DURUM" 2>&1 <<'SQL'
-- 🔴 core.ayar.deger NOT NULL'dur; "yedek yok" NULL ile degil BOS DIZE ile
--    yazilir ve view tarafinda nullif(deger,'') ile yokluga cevrilir.
--    Ilk denemede NULL yazilmaya calisildi, INSERT komple patladi ve
--    ONCEKI KOSUDAN KALAN TAZE DEGER YERINDE KALDI - yani kontrol, artik
--    dogru olmayan bir 'ok' gosteriyordu. Yazamamak, eski cevabi
--    dogrulamaz; o yuzden yazma her kosuda basarili olmak zorunda.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('son_yedek_zamani', :'zaman',  'hazirlik-gunluk.sh olcumu'),
  ('son_yedek_notu',   :'not',    'hazirlik-gunluk.sh olcumu'),
  ('son_yedek_durum',  :'durum',  'HEALTHY/DEGRADED/FAILED/UNKNOWN')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();
SQL
)
if grep -qi 'error' <<< "$YAZ"; then
  echo "UYARI: yedek olcumu core.ayar'a yazilamadi - 7. madde 'kayit yok' gosterecek." >&2
  echo "$YAZ" >&2
fi

# --- 1b) ALARM -----------------------------------------------------------------
# 🔴 MEVCUT ALARM MERKEZI KULLANILIR, yeni bildirim servisi KURULMAZ.
#    Arayuz: alarm.sh <SEVIYE> <kaynak> <baslik> <detay>
#    Flood/dedup davranisi alarm.sh'in kendi isi - burada TASINMAZ,
#    cunku iki yerde iki farkli susturma mantigi, susmayan bir alarm
#    ya da hic calmayan bir alarm uretir.
# 🔴 Kaynak adi backup.calisma'dan AYRI (backup.saglik): biri "gece yedegi
#    calisti mi", digeri "elimizdeki yedek geri yuklenebilir mi" sorusudur.
#    Ayni kaynak adini paylassalardi biri digerinin alarmini kapatirdi.
ALARM=/opt/lcarlie/alarm.sh
if [ -x "$ALARM" ]; then
  case "$YEDEK_DURUM" in
    FAILED)
      "$ALARM" FAILED "backup.saglik" "Yedek sagligi BASARISIZ" "$YEDEK_NOT" >/dev/null 2>&1 ;;
    DEGRADED|UNKNOWN)
      "$ALARM" DEGRADED "backup.saglik" "Yedek sagligi $YEDEK_DURUM" "$YEDEK_NOT" >/dev/null 2>&1 ;;
    HEALTHY)
      "$ALARM" COZULDU "backup.saglik" "Yedek sagligi normale dondu" "$YEDEK_NOT" >/dev/null 2>&1 ;;
  esac
else
  echo "UYARI: alarm betigi bulunamadi ($ALARM) - yedek durumu bildirilemedi." >&2
fi

# --- 2) 7 MADDE ---------------------------------------------------------------
echo "=== 1 EKIM HAZIRLIK KONTROLU  $(date '+%d.%m.%Y %H:%M') ==="
echo

SATIRLAR=$(sorgu <<'SQL'
SELECT sira, anahtar, kapi, CASE WHEN gecti THEN 'GECTI' ELSE 'KALDI' END, detay
  FROM mart.gunluk_hazirlik ORDER BY sira;
SQL
)

if [ -z "$SATIRLAR" ] || grep -q '^ERROR' <<< "$SATIRLAR"; then
  echo "HATA: hazirlik sorgusu calismadi - durum BILINMIYOR (gectiler sayilmaz)."
  echo "$SATIRLAR"
  exit 1
fi

while IFS='|' read -r sira anahtar kapi durum detay; do
  [ -z "${anahtar:-}" ] && continue
  if [ "$durum" = "GECTI" ]; then im="  ok  "; else im="  --  "; fi
  printf '%s%-2s %-32s %-7s %s\n' "$im" "$sira" "$anahtar" "[$kapi]" "$detay"
done <<< "$SATIRLAR"

# --- 3) KAPI ------------------------------------------------------------------
echo
KAPI=$(sorgu <<'SQL'
SELECT karar, p0_eksik, toplam_eksik, p0_eksikler, destek_eksikler, gerekce
  FROM mart.roas_kapisi;
SQL
)
IFS='|' read -r KARAR P0_EKSIK TOP_EKSIK P0_LISTE DESTEK_LISTE GEREKCE <<< "$KAPI"

echo "--------------------------------------------------------------"
echo "  $KARAR"
echo "  $GEREKCE"
[ -n "${P0_LISTE:-}" ]     && echo "  P0 eksikleri     : $P0_LISTE"
[ -n "${DESTEK_LISTE:-}" ] && echo "  Destek eksikleri : $DESTEK_LISTE"
echo "--------------------------------------------------------------"

if [ "${P0_EKSIK:-1}" -gt 0 ]; then
  # 🔴 Bu cumle bilerek uzun: 1 Ekim geldiginde en kolay hata, takvimi
  #    hazirlik sanmaktir. Tarih bir kapi degildir; olcum temeli kapidir.
  echo
  echo "  🔴 1 Ekim gelse bile ROAS KARAR METRIGI YAPILMAYACAK."
  echo "     Takvim hazirlik degildir. Yukaridaki P0 maddeleri kapanmadan"
  echo "     cikacak ROAS yalniz yanlis olmaz - hangi yone yanlis oldugu da"
  echo "     bilinmez, yani duzeltilemez de."
  exit 1
fi

[ "${TOP_EKSIK:-0}" -gt 0 ] && exit 3
exit 0
