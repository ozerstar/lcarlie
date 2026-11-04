-- =============================================================================
-- L'CARLIE - MART: KONUSMA HACMI  (CR-011)
--
-- 🔴🔴 BURADA **ATIF YOKTUR** VE OLAMAZ.  Bu dosya "hangi konusma hangi
--    satisi getirdi" sorusunu CEVAPLAMAZ. Olculdu ve kanitlandi
--    (16.09.2026):
--
--      Messenger'da konusan kisi              259
--      Ayni donemde Wix musterisi (20.08+)     11
--      Tam ad eslesmesi                         0
--      Telefon/e-posta gecen mesaj          1 / 1468
--      PSID'nin Wix'te karsiligi              YOK
--
--    Messenger musteriyi PSID (Page-Scoped ID) ile tanir; bu kimlik
--    Meta'ya ozeldir ve Wix'te karsiligi yoktur. Ad uzerinden
--    eslestirme denendi: TAM ad eslesmesi SIFIR, ilk ad eslesmesi 6
--    ama 37 musteride yalniz 31 tekil ilk ad var - yani ilk ad tekil
--    bir kimlik DEGIL. Boyle bir eslestirme uydurma bir atif uretirdi.
--
--    Bu dosya yalnizca HACIM ve CEVAPSIZLIK olcer. Gunluk konusma
--    sayisi, gunluk siparis ve reklam sayisiyla YAN YANA konabilir -
--    ama yan yana durmak nedensellik DEGILDIR ve oyle sunulmaz.
--
-- 🔴 GERCEK ATIF ICIN GEREKEN: ajanin musteriden telefon/e-posta almasi
--    ya da siparise referans kodu tasinmasi. Ikisi de urun karari.
--
-- 🔴 PII: musteri adi ve PSID mart'a TASINMAZ. Yalniz sayimlar.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.konusma_gunluk CASCADE;
DROP VIEW IF EXISTS mart.konusma_cevapsiz CASCADE;

-- --------------------------------------------------------------------------
-- Cevapsiz konusma  =  son mesaj MUSTERIDEN gelmis
-- --------------------------------------------------------------------------
-- 🔴 Bu, olculebilen en dogrudan is degeri: cevaplanmamis musteri
--    mesaji, kacan satis firsatidir. Atif kurmaya gerek yok.
CREATE OR REPLACE VIEW mart.konusma_cevapsiz AS
SELECT k.id                                   AS konusma_id,
       k.kanal,
       k.son_mesaj,
       (k.son_mesaj AT TIME ZONE 'Europe/Istanbul')::date AS gun,
       k.mesaj_sayisi,
       round(extract(epoch FROM (now() - k.son_mesaj))/3600.0, 1) AS bekleme_saat,
       -- PII TASINMAZ: ad yerine yalniz uzunluk/ilk harf bile verilmez.
       left(md5(k.musteri_ref), 8)            AS musteri_takma
  FROM lcarlie.konusma k
 WHERE (SELECT m.yon FROM lcarlie.mesaj m
         WHERE m.konusma_id = k.id ORDER BY m.zaman DESC LIMIT 1) = 'gelen';

COMMENT ON VIEW mart.konusma_cevapsiz IS
  'Son mesaji MUSTERIDEN gelen konusmalar - cevaplanmamis. PII tasinmaz.';

-- --------------------------------------------------------------------------
-- Gunluk konusma hacmi
-- --------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.konusma_gunluk AS
WITH yeni AS (
  SELECT (ilk_mesaj AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         kanal, count(*) AS yeni_konusma
    FROM lcarlie.konusma GROUP BY 1,2
), msj AS (
  SELECT (m.zaman AT TIME ZONE 'Europe/Istanbul')::date AS gun,
         k.kanal,
         count(*) FILTER (WHERE m.yon='gelen') AS gelen_mesaj,
         count(*) FILTER (WHERE m.yon='giden') AS giden_mesaj
    FROM lcarlie.mesaj m JOIN lcarlie.konusma k ON k.id = m.konusma_id
   GROUP BY 1,2
)
SELECT coalesce(y.gun, m.gun)            AS gun,
       coalesce(y.kanal, m.kanal)        AS kanal,
       coalesce(y.yeni_konusma, 0)       AS yeni_konusma,
       coalesce(m.gelen_mesaj, 0)        AS gelen_mesaj,
       coalesce(m.giden_mesaj, 0)        AS giden_mesaj,
       -- 🔴 TARIHSIZ KONUSMA SESSIZCE DUSMEZ.
       --    Meta'da mesaji hic olmayan bos sohbet var (olculdu: 1 adet).
       --    ilk_mesaj NULL -> gun NULL -> "gun >= kesim" NULL doner ve
       --    WHERE olcumde o satiri SESSIZCE eler: konusma sayilir ama
       --    hicbir gune yazilmaz, toplam eksik cikar. Bu, CR-008'de
       --    ciroda yasadigimiz NULL tuzaginin aynisi.
       --    Cozum: olcumde KESIN boolean olur, tarihsizlik AYRI kolonda
       --    gorunur - dusurmek yerine isaretlenir.
       coalesce(coalesce(y.gun, m.gun) >= (mart.kesim() AT TIME ZONE 'Europe/Istanbul')::date,
                false)                   AS olcumde,
       (coalesce(y.gun, m.gun) IS NULL)  AS tarih_bilinmiyor
  FROM yeni y
  FULL OUTER JOIN msj m ON m.gun = y.gun AND m.kanal = y.kanal
 ORDER BY 1 DESC NULLS LAST;

COMMENT ON VIEW mart.konusma_gunluk IS
  'Gunluk konusma hacmi. Siparis/reklam ile YAN YANA okunabilir ama bu ATIF DEGILDIR. '
  'tarih_bilinmiyor=true satiri: mesaji olmayan bos sohbet, hicbir gune yazilamaz.';

COMMIT;
