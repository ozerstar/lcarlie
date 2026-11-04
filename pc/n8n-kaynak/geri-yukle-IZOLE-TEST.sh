#!/usr/bin/env bash
# =============================================================================
# L'CARLIE - YEDEK GERI YUKLEME TESTI  (IZOLE KONTEYNER)
#
# 🔴 NEDEN YENI DOSYA - geri-yukle-TEST.sh NESI EKSIKTI:
#    Eski test, yedegi URETIM POSTGRES KONTEYNERININ ICINDE `n8n_test`
#    adli bir veritabanina yukluyordu. Yani:
#      - ayni postgres sureci, ayni disk, ayni bellek
#      - CREATE/DROP DATABASE uretim sunucusunda calisiyor
#      - veritabani adindaki tek harflik bir hata uretimi vurabilir
#      - 27M'lik restore uretim I/O'sunu tuketiyor
#    "Canli veritabanina dokunulmadi" dogruydu ama "izole" degildi.
#
#    Ayrica eski test YALNIZ n8n'in kendi tablolarina bakiyordu
#    (workflow_entity, credentials_entity). Ticari aynanin sema ve
#    satirlari - core/raw/mart - hic dogrulanmiyordu. Yani ticari verinin
#    geri gelip gelmedigi test edilmemis oluyordu; oysa 1 Ekim'den sonra
#    kurtarilmasi gereken sey tam olarak odur.
#
# 🔴 BU BETIK URETIME YAZMAZ.  Uretim yalnizca OKUNUR ve test oncesi/sonrasi
#    parmak izi karsilastirilir. Parmak izi degisirse test BASARISIZ sayilir.
#
# Cikis kodu: 0 = BASARILI · 1 = BASARISIZ
# =============================================================================
set -uo pipefail

STACK=/opt/lcarlie/n8n
BK=/opt/lcarlie/backup
KAP_URETIM=lcarlie-postgres
KAP_TEST=lcarlie-yedek-testi
# 🔴 IMAJ SABITLENMEZ, URETIMDEN TURETILIR. Duz postgres:17'de pgvector
#    yok; 01.10.2026'da pg_restore'un 14 hatasinin tamami bundan cikti
#    (vector eklentisi -> mem0.hatira ve ai_semantic.memory_embedding).
IMAJ=$(docker inspect lcarlie-postgres --format '{{.Config.Image}}' 2>/dev/null)
[ -n "$IMAJ" ] || IMAJ=lcarlie/postgres-pgvector:17.11-0.8.6-alpine

set -a; . "$STACK/.env"; set +a

# 🔴 SONUC DOSYASI YALNIZ KANONIK KOSUDA YAZILIR.
#    Elle bir arsiv verildiginde (hata ayiklama, tek seferlik sinama)
#    son-test.txt'e DOKUNULMAZ: ad-hoc bir deneme, gunluk saglik
#    sinyalini kirletmemeli.
ARSIV="${1:-}"
KANONIK=0
if [ -z "$ARSIV" ]; then
  KANONIK=1
  ARSIV=$(ls -1t "$BK"/archive/lcarlie-n8n-*.tgz.enc 2>/dev/null | head -n1)
fi
[ -n "$ARSIV" ] && [ -f "$ARSIV" ] || { echo "HATA: yedek dosyasi bulunamadi"; exit 1; }

# 🔴 BASARISIZ ILE BASLAR.  Betik hangi noktada kesilirse kesilsin
#    (sifre cozulemedi, konteyner kalkmadi, operator Ctrl-C yapti)
#    sonuc BASARISIZ yazilir. Onceki halinde erken `exit 1` dallari
#    son-test.txt'e hic dokunmuyordu; yani BASARISIZ bir test, dunku
#    BASARILI kaydini oldugu gibi birakiyor ve saglik sinyali
#    "yedek geri yuklenebiliyor" demeye devam ediyordu. Bu, CR'nin
#    yasakladigi seyin ta kendisi: basarisiz yedek, eski basariyi
#    bugunun basarisi gibi gostermemeli.
SONUC=BASARISIZ
NEDEN=""

W=$(mktemp -d)
temizle() {
  # 🔴 Temizlik HER cikista calisir - hata da olsa, kesilse de. Yoksa
  #    28M'lik bir konteyner ve cozulmus DUZ METIN dump diskte kalir.
  #    Cozulmus dump sifresizdir; birakmak, sifrelemeyi anlamsiz kilar.
  docker rm -f "$KAP_TEST" >/dev/null 2>&1
  rm -rf "$W"
  if [ "$KANONIK" -eq 1 ]; then
    printf '%s|%s|izole|%s\n' "$(date -Iseconds)" "$SONUC" "${NEDEN:--}" > "$BK/son-test.txt"
    chmod 600 "$BK/son-test.txt"
  fi
}
trap temizle EXIT

echo "=== YEDEK GERI YUKLEME TESTI (IZOLE) ==="
echo "Arsiv: $(basename "$ARSIV")  ($(du -h "$ARSIV" | cut -f1))"
echo

# --- 0) URETIM PARMAK IZI (ONCE) ---------------------------------------------
# 🔴 "Uretime dokunmadim" bir NIYET beyanidir; parmak izi bunu OLCUYE cevirir.
parmak_izi() {
  docker exec -i "$KAP_URETIM" psql -U n8n -d n8n -tA 2>/dev/null <<'SQL'
SELECT string_agg(x, '|' ORDER BY x) FROM (
  SELECT 'db=' || string_agg(datname, ',' ORDER BY datname) AS x FROM pg_database
  UNION ALL SELECT 'wix=' || count(*)::text FROM raw.wix_order
  UNION ALL SELECT 'bk='  || count(*)::text FROM raw.bk_shipment
  UNION ALL SELECT 'cus=' || count(*)::text FROM core.customer
  UNION ALL SELECT 'tbl=' || count(*)::text FROM information_schema.tables
             WHERE table_schema IN ('core','raw','mart')
) t;
SQL
}
IZ_ONCE=$(parmak_izi)
[ -z "$IZ_ONCE" ] && { echo "HATA: uretim parmak izi okunamadi - test yapilmaz."; exit 1; }
echo "-- 0/6 uretim parmak izi alindi"

# --- 1) COZ ------------------------------------------------------------------
echo "-- 1/6 sifre cozuluyor"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in "$ARSIV" -out "$W/b.tgz" -pass "env:BACKUP_ENC_KEY" 2>/dev/null \
  || { NEDEN="sifre cozulemedi"; echo "   BASARISIZ: $NEDEN"; exit 1; }

echo "-- 2/6 arsiv aciliyor"
tar -xzf "$W/b.tgz" -C "$W" 2>/dev/null || { NEDEN="arsiv bozuk"; echo "   BASARISIZ: $NEDEN"; exit 1; }
DUMP="$W/n8n-db.dump"
[ -f "$DUMP" ] || { NEDEN="n8n-db.dump arsivde yok"; echo "   BASARISIZ: $NEDEN"; exit 1; }

# --- 3) IZOLE KONTEYNER ------------------------------------------------------
# 🔴 PORT YAYINLANMAZ (-p yok): test veritabani disariya hic acilmaz.
# 🔴 tmpfs: veri diske hic inmez, konteyner olunce kaybolur.
# 🔴 Rastgele parola: disari acilmadigi icin yalnizca konteyner icinde gecerli
#    ve hicbir yere yazilmaz.
echo "-- 3/6 izole test konteyneri baslatiliyor ($KAP_TEST)"
docker rm -f "$KAP_TEST" >/dev/null 2>&1
docker run -d --name "$KAP_TEST" \
  --network none \
  -e POSTGRES_PASSWORD="$(head -c 18 /dev/urandom | base64)" \
  -e POSTGRES_USER=n8n -e POSTGRES_DB=postgres \
  --tmpfs /var/lib/postgresql/data:rw,size=2g \
  "$IMAJ" >/dev/null 2>&1 || { NEDEN="test konteyneri baslatilamadi"; echo "   BASARISIZ: $NEDEN"; exit 1; }

# Hazir olana kadar bekle (en fazla 150 sn)
for i in $(seq 1 60); do
  docker exec "$KAP_TEST" pg_isready -U n8n -q 2>/dev/null && break
  sleep 1
done
docker exec "$KAP_TEST" pg_isready -U n8n -q 2>/dev/null \
  || { NEDEN="test postgres 150 sn icinde hazir olmadi"; echo "   BASARISIZ: $NEDEN"; exit 1; }

# --- 4) GERI YUKLE -----------------------------------------------------------
echo "-- 4/6 yedek izole veritabanina yukleniyor"
docker cp "$DUMP" "$KAP_TEST":/tmp/test.dump >/dev/null 2>&1
docker exec "$KAP_TEST" psql -U n8n -d postgres -q -c "CREATE DATABASE n8n_geri OWNER n8n;" 2>/dev/null

# 🔴 pg_restore ROL UYARILARI verir (uretimdeki roller test konteynerinde yok).
#    Bunlar veri kaybi DEGILDIR; basarisizlik olcusu asagidaki SEMA ve
#    SATIR kontrolleridir, pg_restore'un cikis kodu tek basina degil.
docker exec "$KAP_TEST" pg_restore -U n8n -d n8n_geri --no-owner --no-acl \
  /tmp/test.dump >/dev/null 2>"$W/restore.err"
# 🔴 `grep -c ... || echo 0` KULLANILMAZ: grep -c eslesme yokken hem "0"
#    yazar hem 1 ile cikar, yani || dali da calisir ve degisken "0\n0"
#    olur. Sonra `[ "$HATA_SAY" -eq 0 ]` "integer expression expected"
#    verir, test de HATALI sekilde BASARISIZ sayilir - nitekim oldu.
HATA_SAY=$(grep -c "^pg_restore: error" "$W/restore.err" 2>/dev/null) || true
HATA_SAY=${HATA_SAY:-0}

# --- 5) DOGRULA --------------------------------------------------------------
echo "-- 5/6 geri yuklenen veri dogrulaniyor"
SONUC_SQL=$(docker exec -i "$KAP_TEST" psql -U n8n -d n8n_geri -tA -F'|' 2>/dev/null <<'SQL'
SELECT
  (SELECT count(*) FROM information_schema.schemata WHERE schema_name='core'),
  (SELECT count(*) FROM information_schema.schemata WHERE schema_name='raw'),
  (SELECT count(*) FROM information_schema.schemata WHERE schema_name='mart'),
  (SELECT count(*) FROM raw.wix_order),
  (SELECT count(*) FROM raw.bk_shipment),
  (SELECT count(*) FROM core.customer),
  (SELECT count(*) FROM workflow_entity),
  (SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('core','raw','mart'));
SQL
)
IFS='|' read -r S_CORE S_RAW S_MART R_WIX R_BK R_CUS R_WF R_TBL <<< "$SONUC_SQL"

# Uretimdeki guncel sayilar - KARSILASTIRMA icin, esitlik BEKLENMEZ:
# yedek 03:30/04:53'te alindi, o saatten sonra ETL calisti.
URETIM=$(docker exec -i "$KAP_URETIM" psql -U n8n -d n8n -tA -F'|' 2>/dev/null <<'SQL'
SELECT (SELECT count(*) FROM raw.wix_order), (SELECT count(*) FROM raw.bk_shipment),
       (SELECT count(*) FROM core.customer);
SQL
)
IFS='|' read -r U_WIX U_BK U_CUS <<< "$URETIM"

echo
printf '   %-28s %10s %10s\n' "kontrol" "yedekte" "uretimde"
printf '   %-28s %10s %10s\n' "core semasi"    "${S_CORE:-0}" "-"
printf '   %-28s %10s %10s\n' "raw semasi"     "${S_RAW:-0}"  "-"
printf '   %-28s %10s %10s\n' "mart semasi"    "${S_MART:-0}" "-"
printf '   %-28s %10s %10s\n' "core/raw/mart tablo" "${R_TBL:-0}" "-"
printf '   %-28s %10s %10s\n' "raw.wix_order"  "${R_WIX:-0}"  "${U_WIX:-?}"
printf '   %-28s %10s %10s\n' "raw.bk_shipment" "${R_BK:-0}"  "${U_BK:-?}"
printf '   %-28s %10s %10s\n' "core.customer"  "${R_CUS:-0}"  "${U_CUS:-?}"
printf '   %-28s %10s %10s\n' "workflow_entity" "${R_WF:-0}"  "-"
echo

ekle() { NEDEN="${NEDEN:+$NEDEN · }$1"; SONUC=BASARISIZ; }

# 🔴 BURAYA KADAR GELMEK, BASARI DEMEK DEGIL - yalnizca "olculebilir hale
#    geldik" demek. Sonuc burada iyimser baslatilir ve asagidaki her
#    kontrol onu geri alabilir. Betik buradan ONCE kesilirse SONUC
#    BASARISIZ kalir (basta oyle tanimlandi) ve trap onu yazar.
SONUC=BASARILI

[ "${S_CORE:-0}" -eq 1 ] || ekle "core semasi yok"
[ "${S_RAW:-0}"  -eq 1 ] || ekle "raw semasi yok"
[ "${S_MART:-0}" -eq 1 ] || ekle "mart semasi yok"
[ "${R_TBL:-0}"  -ge 20 ] || ekle "core/raw/mart tablo sayisi dusuk (${R_TBL:-0})"
# 🔴 Satir sayisi sanity: yedekteki sayi uretimin %50'sinden az olmamali.
#    Esitlik aranmaz - yedek alindiktan sonra ETL calisti, fark NORMAL.
#    Aranan sey "veri geldi mi", "birebir ayni mi" degil.
for p in "wix:${R_WIX:-0}:${U_WIX:-0}" "bk:${R_BK:-0}:${U_BK:-0}" "cus:${R_CUS:-0}:${U_CUS:-0}"; do
  ad=${p%%:*}; rest=${p#*:}; y=${rest%%:*}; u=${rest#*:}
  [ "${y:-0}" -gt 0 ] || ekle "$ad: yedekte 0 satir"
  [ "${u:-0}" -gt 0 ] && [ $((y * 2)) -lt "$u" ] && ekle "$ad: yedek uretimin yarisindan az ($y < $u)"
done
if [ "${HATA_SAY:-0}" -ne 0 ]; then
  ekle "pg_restore $HATA_SAY hata satiri"
  # 🔴 KANITI SAKLA. restore.err gecici dizinde ve trap onu siliyor;
  #    eskiden alarm "yedek geri yuklenemiyor" diyor ama hangi hata
  #    oldugu sorulunca cevap yoktu. Kanitsiz alarm alarmdan sayilmaz.
  KANIT=/opt/lcarlie/backup/log/son-restore-hatalari.log
  {
    echo "=== $(date -Is) · arsiv: $(basename "$ARSIV") · $HATA_SAY hata ==="
    grep "^pg_restore: error" "$W/restore.err" 2>/dev/null | head -60
  } > "$KANIT" 2>/dev/null || true
  echo "   hata ayrintisi: $KANIT"
fi

# --- 6) URETIM DEGISMEDI MI --------------------------------------------------
IZ_SONRA=$(parmak_izi)
if [ "$IZ_ONCE" = "$IZ_SONRA" ]; then
  echo "   URETIM DEGISMEDI: parmak izi ayni (once=sonra)"
else
  echo "   🔴 URETIM PARMAK IZI DEGISTI"
  echo "      once : $IZ_ONCE"
  echo "      sonra: $IZ_SONRA"
  ekle "URETIM PARMAK IZI DEGISTI"
fi
echo "-- 6/6 test konteyneri siliniyor"

echo
echo "======================================================"
echo " YEDEK GERI YUKLEME TESTI: $SONUC"
[ -n "$NEDEN" ] && echo " Neden: $NEDEN"
echo " Izole konteyner kullanildi - uretim postgres'ine YAZILMADI."
echo "======================================================"

# 🔴 son-test.txt BURADA YAZILMAZ - temizle() trap'i yazar.
#    Sebep: buraya ulasamayan her kosu (sifre cozulemedi, konteyner
#    kalkmadi, Ctrl-C) sessizce eski kaydi birakirdi.

[ "$SONUC" = BASARILI ]
