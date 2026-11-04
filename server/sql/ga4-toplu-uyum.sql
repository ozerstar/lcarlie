-- ---------------------------------------------------------------------
-- raw.ga4_event: TOPLU (aggregate) satirlari kabul et
-- 20.09.2026
--
-- NEDEN
-- Tablo OLAY DUZEYI veri icin kurulmustu (event_timestamp, user_pseudo_id,
-- session_id -> BigQuery aktarimi sekli). Ama bugun baglanan kaynak GA4
-- DATA API ve o yalnizca TOPLU rapor verir: tarih + olay adi + sayi.
-- Toplu satirda olay zamani YOKTUR.
--
-- ga4-yukle.py bu tabloya karsi HIC CALISTIRILMAMIS; ilk gercek calismada
-- iki hata birden cikti (olculdu):
--   1) event_timestamp NOT NULL ihlali
--   2) kanit_durumu = 'GA4_AGGREGATE' CHECK ihlali
--      (izinli: OBSERVED / CONSENT_LIMITED / SAMPLED / SUSPECT)
--
-- KARAR
-- Zaman damgasini "gece yarisi" gibi bir degerle DOLDURMUYORUZ - bu
-- uydurma olurdu ve bu projede tam olarak bundan kaciniyoruz. Kaynakta
-- yoksa kolonda da yok: NULL.
--
-- Toplu satirin olay duzeyi satirdan ayirt edilebilmesi icin ayri bir
-- kolon: granulerlik. kanit_durumu'nu bu is icin kullanmak yanlis olurdu --
-- o kolon verinin KALITESINI anlatir (gozlendi mi, orneklendi mi), veri
-- tanesinin BUYUKLUGUNU degil. Ikisini ayri tutmak, "sayiyi kim uretti"
-- sorusunu sonra da cevaplanabilir kilar.
-- ---------------------------------------------------------------------

BEGIN;

-- 1) Toplu satirda olay zamani yok.
ALTER TABLE raw.ga4_event ALTER COLUMN event_timestamp DROP NOT NULL;

-- 2) Tane buyuklugu ayri kolonda. Varsayilan EVENT: mevcut satirlarin
--    (ve ileride gelebilecek BigQuery aktariminin) anlami degismez.
ALTER TABLE raw.ga4_event
  ADD COLUMN IF NOT EXISTS granulerlik text NOT NULL DEFAULT 'EVENT';

ALTER TABLE raw.ga4_event DROP CONSTRAINT IF EXISTS ga4_event_granulerlik_check;
ALTER TABLE raw.ga4_event
  ADD CONSTRAINT ga4_event_granulerlik_check
  CHECK (granulerlik IN ('EVENT', 'GUNLUK_TOPLAM'));

-- 3) Gunluk tekrar calisma COGALTMAMALI.
--    Mevcut ga4_event_tekil indeksi event_timestamp iceriyor; NULL'lar
--    btree'de birbirinden farkli sayildigi icin toplu satirlari
--    tekillestirmez. Bu yuzden toplu satirlara kendi indeksi:
--    satin almalar transaction_id tasidigi icin disarida (onlari
--    ga4_purchase_tekil zaten tekillestiriyor).
CREATE UNIQUE INDEX IF NOT EXISTS ga4_event_toplu_tekil
  ON raw.ga4_event (event_name, event_date)
  WHERE granulerlik = 'GUNLUK_TOPLAM' AND transaction_id IS NULL;

COMMIT;
