#!/usr/bin/env bash
# L'CARLIE AUTONOMOUS COMPANY RUNTIME
# 17.09.2026 · closed-loop runtime · MEVCUT SEMA KULLANILIR
#
# F0 ACTION FIREWALL — bu betikte DIS EYLEM KODU YOKTUR.
#   Reklam yayini, butce, fiyat, musteri mesaji, site yayini, odeme, silme:
#   bu dosyada HICBIR kod yolu yok. Dis eylem YALNIZ core.karar PROPOSED
#   satiri olarak onerilir; uygulamasi insana aittir.
#   firewall-test modu bunu her calistirmada KANITLAR.
set -euo pipefail

PG=(docker exec -i lcarlie-postgres psql -U n8n -d n8n -v ON_ERROR_STOP=1)
SQL() { "${PG[@]}" -At -c "$1"; }
SQLF() { "${PG[@]}" -f -; }
LOG="/opt/lcarlie/runtime/runtime.log"
mkdir -p /opt/lcarlie/runtime
say() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"; }

# ─────────────────────────────────────────────────────────────
# F0 · ACTION FIREWALL
# ─────────────────────────────────────────────────────────────
firewall_test() {
  say "F0 ACTION FIREWALL testi"
  local kirli=0
  # Bu betikte dis eylem cagrisi olmamali.
  local yasak='meta-aktar|graph\.facebook|business\.facebook|/api/v[0-9]|wix\.com/_api|curl -X (POST|PUT|DELETE|PATCH)|DROP TABLE|TRUNCATE|DELETE FROM'
  if grep -nE "$yasak" "$0" | grep -v '^\s*#' | grep -v 'yasak=' | grep -v 'firewall'; then
    say "  ✗ IHLAL: dis eylem/destructive kod yolu bulundu"; kirli=1
  else
    say "  ✓ dis eylem kod yolu YOK (reklam/butce/fiyat/mesaj/odeme/silme)"
  fi
  # Runtime yalnizca su tablolara YAZAR:
  say "  ✓ yazma kapsami: core.ic_mesaj · core.acik_soru · core.buyume_bulgu ·"
  say "                   core.karar(PROPOSED) · core.karar_red_team · core.inanc_catismasi"
  say "  ✓ dis eylem yolu: core.karar PROPOSED -> INSAN ONAYI -> insan uygular"
  [ "$kirli" -eq 0 ] && say "F0 SONUC: PASS" || { say "F0 SONUC: FAIL"; return 1; }
}

# ─────────────────────────────────────────────────────────────
# F5 · EVENT ENGINE — gercek veriden olay turet (tablo eklemeden)
#      Olaylar core.ic_mesaj'a ALERT olarak yazilir, ureten departman ile.
# ─────────────────────────────────────────────────────────────
event_scan() {
  say "F5 EVENT SCAN"
  SQLF <<'EOSQL'
WITH
-- 28.09.2026 DUZELTME (olculdu). Uc alarmin ucu de yanlis konusuyordu:
--   1) SALE_DROP yalniz mart.siparis'e bakiyordu; Wix DISI (kapida odemeli,
--      elle) satislari hic gormuyordu. 13-14.09'da tahsil edilip bakiyeye
--      aktarilmis 4 adet 1.200 TL'lik satis bu yuzden "satis yok" sayildi.
--   2) "Harcama devam ederken" SIMDIKI ZAMAN iddiasidir; dayanagi ise son
--      satistan beri biriken KUMULATIF sayiydi. Harcama 24.09'dan beri
--      sifirken alarm uc gun ust uste ayni 6559 TL'yi "devam eden" diye
--      gosterdi ve "butceyi acilen durdur" olu tavsiyesini uretti.
--   3) DATA_STALE 24 saatlik tazelik bekliyordu; oysa core.kanit_anlik'i
--      ureten buyume-brief.sh CR-015 ile bilerek HAFTALIGA alindi (Pazartesi
--      08:45). Haftalik bir tablo dogal olarak 168 saate kadar eskir; alarm
--      her hafta bos yere yandi (gundem #100/#109/#112/#114/#116 hep budur).
-- SON SATIS = Wix siparisi VEYA tahsil edilmis elle satis; hangisi gec ise o.
ss AS (
  SELECT max(an) AS an FROM (
    SELECT max(olusturma) AS an FROM mart.siparis
    UNION ALL
    SELECT max(olusturma) FROM mart.gonderi
     WHERE sinif = 'ELLE_SATIS' AND cod_durum = 'TRANSFERRED'
  ) k
),
sd AS (SELECT (current_date - (SELECT an FROM ss)::date) AS gun_gecti),
-- GECMIS: son satistan bu yana biriken toplam
hd AS (
  SELECT round(coalesce(sum(harcama),0)) AS harcama FROM raw.meta_harcama
  WHERE gun > (SELECT an FROM ss)::date
),
-- SIMDI: harcama HALA suruyor mu. Olcut SON HARCAMA YAPILAN GUN'dur,
-- 7 gunluk pencere degil: pencere, 5 gun once bitmis bir harcamayi da
-- "suruyor" gibi gosterir. Pencere toplami ayrica yazilir ama hukum vermez.
hd7 AS (
  SELECT round(coalesce(sum(harcama),0)) AS harcama,
         max(gun) FILTER (WHERE harcama > 0) AS son_gun
    FROM raw.meta_harcama WHERE gun >= current_date-7
),
-- META_SPEND_ANOMALY: son 7 gun harcama var, siparis yok/az
msa AS (
  SELECT round(coalesce(sum(harcama),0)) h FROM raw.meta_harcama WHERE gun >= current_date-7
),
-- siparis sayaci da iki kaynagi birden sayar (ayni kusur burada da vardi)
ms AS (
  SELECT (SELECT count(*) FROM mart.siparis WHERE olusturma >= current_date-7)
       + (SELECT count(*) FROM mart.gonderi
           WHERE sinif = 'ELLE_SATIS' AND cod_durum = 'TRANSFERRED'
             AND olusturma >= current_date-7) AS n
),
-- DATA_STALE: en son anlik goruntu yasi (uretim HAFTALIK -> esik 192 saat)
ds AS (SELECT round(extract(epoch from (now()-max(alindi)))/3600) saat FROM core.kanit_anlik)
INSERT INTO core.ic_mesaj (kimden, kime, tip, konu, icerik, durum)
SELECT * FROM (
  SELECT 'ECOM'::text, 'EXEC'::text, 'ALERT'::text,
         'SALE_DROP · '||sd.gun_gecti||' gundur satis yok',
         'Son satistan (Wix siparisi veya tahsil edilmis elle satis) bu yana '||
         sd.gun_gecti||' gun gecti. O tarihten beri biriken Meta harcamasi '||
         hd.harcama||' TL (kumulatif, gecmis). '||
         CASE WHEN hd7.son_gun IS NULL
              THEN 'Harcama DURMUS: son 7 gunde hic harcama yok; '||
                   'butce durdurma tavsiyesi gecersiz.'
              WHEN hd7.son_gun >= current_date-1
              THEN 'Harcama SURUYOR: son harcama gunu '||hd7.son_gun||
                   ', son 7 gun toplami '||hd7.harcama||' TL.'
              ELSE 'Harcama DURMUS: en son '||hd7.son_gun||' tarihinde harcandi ('||
                   (current_date - hd7.son_gun)||' gun once). Son 7 gun toplami '||
                   hd7.harcama||' TL; butce durdurma tavsiyesi gecersiz.'
         END,
         'OPEN'
  FROM sd, hd, hd7 WHERE sd.gun_gecti >= 3
  UNION ALL
  SELECT 'META_MEDIA','FINANCE','ALERT',
         'META_SPEND_ANOMALY · 7 gunde '||msa.h||' TL / '||ms.n||' siparis',
         'Son 7 gunde '||msa.h||' TL harcandi, '||ms.n||' siparis olustu. '||
         CASE WHEN ms.n=0 THEN 'Siparis basina maliyet TANIMSIZ (payda 0).'
              ELSE 'Siparis basina '||round(msa.h::numeric/ms.n)||' TL.' END,
         'OPEN'
  FROM msa, ms WHERE msa.h > 1000 AND ms.n <= 2
  UNION ALL
  SELECT 'AI_OPS','EXEC','ALERT',
         'DATA_STALE · anlik goruntu '||ds.saat||' saatlik',
         'core.kanit_anlik en son '||ds.saat||' saat once uretildi. Uretim HAFTALIK '||
         '(buyume-brief.sh, Pazartesi 08:45), esik 192 saat. Bu yastaki bir goruntu '||
         'haftalik uretimin de disinda kalmis demektir.',
         'OPEN'
  FROM ds WHERE ds.saat > 192
) e(kimden,kime,tip,konu,icerik,durum)
-- IDEMPOTENCY: ayni konu son 20 saatte acilmissa tekrar acma
WHERE NOT EXISTS (
  SELECT 1 FROM core.ic_mesaj m
  WHERE m.konu = e.konu AND m.zaman > now() - interval '20 hours'
);
EOSQL
  local n; n=$(SQL "SELECT count(*) FROM core.ic_mesaj WHERE tip='ALERT' AND zaman > now()-interval '5 minutes';")
  say "  yeni event: $n"
}

# ─────────────────────────────────────────────────────────────
# F1 · BUS CONSUMER + F2 TASK DISPATCHER + F3 CAPABILITY ROUTING
#      OPEN mesajlari tuketir, departman/capability secer, gorev acar.
# ─────────────────────────────────────────────────────────────
bus_consume() {
  say "F1/F2/F3 BUS CONSUMER + DISPATCHER"
  SQLF <<'EOSQL'
-- 1) OPEN mesajlari IN_PROGRESS'e al (claim)
UPDATE core.ic_mesaj SET durum='IN_PROGRESS'
WHERE durum='OPEN' AND tip IN ('ALERT','RISK','FINDING','OPPORTUNITY','BLOCKER','CHALLENGE','QUESTION','REQUEST');

-- 2) DECISION MEMORY KONTROLU + GOREV URET (dedupe'li)
--    Capability routing: mesaj tipi + hedef departman -> gereken capability'ler
INSERT INTO core.acik_soru
 (hedef, soru, neden_onemli, beklenen_bilgi_degeri, kaynak_plani, ureten,
  oncelik, is_etkisi, gereken_departmanlar, onay_gereksinimi, tahmini_compute, proje)
SELECT
  'SIRKET',
  'Bus#'||m.mesaj_id||' · '||m.konu||' — aciklayici hipotezler ve karsi kanit',
  m.icerik,
  CASE WHEN m.tip IN ('ALERT','RISK','BLOCKER') THEN 'YUKSEK' ELSE 'ORTA' END,
  CASE m.kimden
    WHEN 'ECOM'        THEN 'mart.siparis + mart.gonderi + lcarlie.konusma'
    WHEN 'META_MEDIA'  THEN 'raw.meta_harcama + mart.reklam_performans'
    WHEN 'AI_OPS'      THEN 'core.kanit_anlik + saglik.sh'
    WHEN 'FINANCE'     THEN 'mart.ekonomi_gunluk + mart.siparis_ekonomi'
    WHEN 'REGULATORY'  THEN 'urun belgeleri + core.anayasa'
    ELSE 'core.buyume_bulgu + mart.inanc_durumu' END,
  'ORCHESTRATOR',
  CASE WHEN m.tip IN ('ALERT','RISK','BLOCKER') THEN 'P1' ELSE 'P3' END,
  m.tip,
  CASE m.tip
    WHEN 'ALERT'       THEN ARRAY['EXEC','FINANCE','RED_TEAM']
    WHEN 'RISK'        THEN ARRAY['EXEC','FINANCE','RED_TEAM']
    WHEN 'BLOCKER'     THEN ARRAY['REGULATORY','EXEC']
    WHEN 'OPPORTUNITY' THEN ARRAY['CREATIVE_STRAT','CUSTOMER_INT','REGULATORY']
    ELSE ARRAY['DATA_BI','RED_TEAM'] END,
  'L3',
  'LIGHT',
  'CLOSED_LOOP_'||to_char(current_date,'YYYYMMDD')
FROM core.ic_mesaj m
WHERE m.durum='IN_PROGRESS' AND m.bagli_soru IS NULL
  -- DEDUPE / TEKRAR KESIF KORUMASI
  AND NOT EXISTS (
    SELECT 1 FROM core.acik_soru s
    WHERE s.soru LIKE 'Bus#'||m.mesaj_id||' ·%'
  )
  AND NOT EXISTS (
    SELECT 1 FROM core.acik_soru s
    WHERE s.durum IN ('OPEN','IN_PROGRESS') AND s.neden_onemli = m.icerik
  );

-- 3) Mesaj <-> gorev bagini kur
UPDATE core.ic_mesaj m SET bagli_soru = s.soru_id
FROM core.acik_soru s
WHERE m.bagli_soru IS NULL AND s.soru LIKE 'Bus#'||m.mesaj_id||' ·%';

-- ─────────────────────────────────────────────────────────────
-- 4) YETIM TIPLER: TASK · HANDOFF · RESULT   (20.09.2026 eklendi)
--
-- 🔴 BULUNAN HAL: yukaridaki claim listesi yalnizca SINYAL tiplerini
--    (ALERT/RISK/FINDING/...) tuketiyordu. TASK, HANDOFF ve RESULT hicbir
--    adimda gecmiyordu. Olculdu: 45 ic mesajin 32'si (%71) bu tiplerdeydi
--    ve 29 TASK'in TAMAMI 'OPEN' kalmisti. Yani veri yolu departmanlara
--    gorev dagitiyor, gorevi alan hicbir surec yok.
--
-- 🔴 TASK'i YENI SORUYA CEVIRMEK YANLIS OLURDU: bu gorevler zaten bir
--    sorudan turuyor ("AI veri acigi sorusu #86"). Soru -> gorev -> yeni
--    soru zinciri kendi kuyrugunu yiyen bir dongu olurdu. Dogru islem
--    gorevi KAYNAGINA baglamak ve kaynagi kapandiginda kapatmaktir.

-- 4a) Bagi kur. Uretici bagli_soru'yu doldurmamis; referans yalnizca konu
--     metninde duruyor ("Karar olcum plani #61").
-- 🔴 'Bus#' ile BASLAYAN konu haric tutulur: oradaki numara bir MESAJ
--    kimligidir, soru kimligi degil. Ayirmazsak RESULT 'Bus#22' mesaji
--    alakasiz 22 numarali soruya baglanirdi.
UPDATE core.ic_mesaj m
   SET bagli_soru = (substring(m.konu from '#([0-9]+)'))::bigint
 WHERE m.tip IN ('TASK','HANDOFF','RESULT')
   AND m.bagli_soru IS NULL
   AND m.konu ~ '#[0-9]+'
   AND m.konu !~ '^Bus#'
   AND EXISTS (SELECT 1 FROM core.acik_soru s
                WHERE s.soru_id = (substring(m.konu from '#([0-9]+)'))::bigint);

-- 4b) Kaynak sorusu KAPANMIS gorev kapanir. Uydurma kapanis degil:
--     gorevin varlik sebebi o soruydu ve soru karara baglandi.
UPDATE core.ic_mesaj m
-- 🔴 yanit_veren, core.departman(kod)'a FK'lidir: uydurma bir ad ('RUNTIME')
--    reddedilir. Sema, yanitin GERCEK bir departmandan gelmesini sart kosuyor.
--    Gorevleri dagitan da kapatan da AI_OPS (Automation / AI Ops).
   SET durum='COMPLETE', kapanma=clock_timestamp(), yanit_veren='AI_OPS',
       yanit='Kaynak soru #'||m.bagli_soru||' durumu '||s.durum||' — gorev kendiliginden kapandi.'
  FROM core.acik_soru s
 WHERE s.soru_id = m.bagli_soru
   AND m.tip IN ('TASK','HANDOFF','RESULT')
   AND m.durum <> 'COMPLETE'
   AND s.durum IN ('ANSWERED','DROPPED_LOW_VALUE');

-- 4c) Kaynak sorusu ACIK olan gorev izlemeye alinir ama KAPATILMAZ --
--     is hala yapilmadi, kapatmak yalan olurdu.
UPDATE core.ic_mesaj m SET durum='IN_PROGRESS'
  FROM core.acik_soru s
 WHERE s.soru_id = m.bagli_soru
   AND m.tip IN ('TASK','HANDOFF','RESULT')
   AND m.durum='OPEN'
   AND s.durum IN ('OPEN','IN_PROGRESS','BLOCKED_NEEDS_HUMAN','BLOCKED_NO_ACCESS');
EOSQL
  say "  acik gorev: $(SQL "SELECT count(*) FROM core.acik_soru WHERE durum IN ('OPEN','IN_PROGRESS');")"
  # 🔴 KAPANAMAYAN YETIM SAYISI GIZLENMEZ. Kaynagi bulunamayan TASK/HANDOFF/
  #    RESULT mesajlari kapatilmaz -- onlari sessizce COMPLETE yapmak
  #    "is bitti" yalani olurdu. Sayisi her calistirmada yazilir.
  say "  baglanamayan yetim mesaj: $(SQL "SELECT count(*) FROM core.ic_mesaj WHERE tip IN ('TASK','HANDOFF','RESULT') AND bagli_soru IS NULL AND durum <> 'COMPLETE';")"
}

# ─────────────────────────────────────────────────────────────
# F6 · OTOMATIK RED TEAM — onemli sonuca kendiliginden saldirir
# ─────────────────────────────────────────────────────────────
redteam_auto() {
  say "F6 OTOMATIK RED TEAM"
  SQLF <<'EOSQL'
-- Son 24 saatte yazilmis, red team gormemis HYPOTHESIS icin gorev ac
INSERT INTO core.acik_soru
 (hedef, soru, neden_onemli, beklenen_bilgi_degeri, kaynak_plani, ureten,
  oncelik, is_etkisi, gereken_departmanlar, onay_gereksinimi, proje)
SELECT 'SIRKET',
  'RED TEAM · bulgu#'||b.bulgu_id||' neden yanlis olabilir?',
  'Otomatik tetik: '||b.baslik||' (guven '||coalesce(b.guven::text,'?')||
  '). Kontrol: selection bias · sample size · measurement error · alternative '||
  'explanation · reverse causality · stale data · commercial reality · compliance.',
  'YUKSEK',
  'core.buyume_bulgu + core.karar_red_team + mart.inanc_durumu',
  'RED_TEAM','P1','CHALLENGE',ARRAY['RED_TEAM'],'L3',
  'CLOSED_LOOP_'||to_char(current_date,'YYYYMMDD')
FROM core.buyume_bulgu b
WHERE b.seviye='HYPOTHESIS'
  AND b.olusturma > now() - interval '24 hours'
  AND coalesce(b.inanc_durumu,'ACTIVE')='ACTIVE'
  AND b.guven IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM core.acik_soru s WHERE s.soru LIKE 'RED TEAM · bulgu#'||b.bulgu_id||'%'
  );
EOSQL
  say "  red team gorevi: $(SQL "SELECT count(*) FROM core.acik_soru WHERE ureten='RED_TEAM' AND durum IN ('OPEN','IN_PROGRESS');")"
}

# ─────────────────────────────────────────────────────────────
# F4 · MANAGING DIRECTOR CYCLE — durumu okur, gundem uretir
# ─────────────────────────────────────────────────────────────
md_cycle() {
  say "F4 MANAGING DIRECTOR CYCLE"
  "${PG[@]}" <<'EOSQL'
\pset pager off
\echo '--- SIRKET DURUMU ---'
SELECT
 (SELECT count(*) FROM core.ic_mesaj WHERE durum IN ('OPEN','IN_PROGRESS')) AS acik_mesaj,
 (SELECT count(*) FROM core.acik_soru WHERE durum IN ('OPEN','IN_PROGRESS')) AS acik_gorev,
 (SELECT count(*) FROM core.inanc_catismasi WHERE durum='OPEN') AS acik_celiski,
 (SELECT count(*) FROM core.karar WHERE durum='PROPOSED') AS onay_bekleyen,
 (SELECT count(*) FROM core.karar WHERE durum IN ('MEASURING','EXECUTED')) AS kapanmayi_bekleyen,
 (SELECT pencere_30->>'nakit_durum' FROM core.kanit_anlik ORDER BY anlik_id DESC LIMIT 1) AS nakit;
\echo '--- GUNDEM (oncelik sirasi) ---'
SELECT oncelik, beklenen_bilgi_degeri AS deger, ureten, left(soru,78) AS gorev
FROM mart.sirket_gundemi LIMIT 12;
EOSQL
}

# ─────────────────────────────────────────────────────────────
# F7 · EXECUTIVE BRIEF
# ─────────────────────────────────────────────────────────────
brief() {
  say "F7 EXECUTIVE BRIEF"
  "${PG[@]}" <<'EOSQL'
\pset pager off
\echo '=========== L CARLIE EXECUTIVE BRIEF ==========='
\echo '--- NE DEGISTI (son 24s event) ---'
SELECT kimden||' -> '||coalesce(kime,'*') AS yol, tip, left(konu,70) AS konu, durum
FROM core.ic_mesaj WHERE zaman > now()-interval '24 hours' ORDER BY mesaj_id;
\echo '--- OTONOM CALISMA ---'
SELECT ureten, durum, count(*) FROM core.acik_soru GROUP BY 1,2 ORDER BY 1,2;
\echo '--- ONAY BEKLEYEN ---'
SELECT karar_id, karar_tipi, left(oneri,66) AS oneri, kanit_kalitesi
FROM core.karar WHERE durum='PROPOSED' ORDER BY karar_id;
\echo '--- ACIK CELISKI ---'
SELECT catisma_id, durum, left(aciklama,90) FROM core.inanc_catismasi WHERE durum='OPEN';
\echo '--- YAPILMAMIS GOREV (kaynagi hala acik) ---'
SELECT m.mesaj_id, m.kimden||' -> '||coalesce(m.kime,'*') AS yol, m.tip,
       left(m.konu,60) AS konu, m.bagli_soru AS kaynak_soru
  FROM core.ic_mesaj m
 WHERE m.tip IN ('TASK','HANDOFF','RESULT') AND m.durum <> 'COMPLETE'
   AND m.bagli_soru IS NOT NULL
 ORDER BY m.mesaj_id;
\echo '--- KAYNAGI BULUNAMAYAN MESAJ (kimse tuketemiyor) ---'
-- 🔴 Bu liste BOS OLMALI. Dolu ise bir uretici, tuketicisi olmayan mesaj
--    yaziyor demektir; sayiyi gizlemek isi bitmis gostermek olurdu.
SELECT m.mesaj_id, m.kimden||' -> '||coalesce(m.kime,'*') AS yol, m.tip,
       left(m.konu,60) AS konu
  FROM core.ic_mesaj m
 WHERE m.tip IN ('TASK','HANDOFF','RESULT') AND m.durum <> 'COMPLETE'
   AND m.bagli_soru IS NULL
 ORDER BY m.mesaj_id;
EOSQL
}

# ─────────────────────────────────────────────────────────────
case "${1:-gun}" in
  firewall-test) firewall_test ;;
  event)         event_scan ;;
  bus)           bus_consume ;;
  redteam)       redteam_auto ;;
  md)            md_cycle ;;
  brief)         brief ;;
  gun)           firewall_test && event_scan && bus_consume && redteam_auto && md_cycle && brief ;;
  *) echo "kullanim: $0 {firewall-test|event|bus|redteam|md|brief|gun}"; exit 2 ;;
esac

