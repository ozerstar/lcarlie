-- =============================================================================
-- L'CARLIE - GONDERI <-> SIPARIS ESLESTIRME + MALIYET GIRIS SABLONU  (CR-016)
--
-- 🔴 BELIRSIZ ESLESME ZORLANMAZ.  CR-003'ten beri gecerli kural:
--    "uncertain match ASLA zorla birlestirilmesin". Bu dosya eslesmeyi
--    UC SINIFA ayirir ve yalniz TEK ADAYLI olani kabul eder.
--
-- 🔴 NEDEN TELEFON/AD ILE ESLESTIRMIYORUZ: BasitKargo'da alici PII'si
--    BILEREK alinmiyor (CR-004 karari). Elde kalan deterministik alanlar:
--    tutar, tarih penceresi, sehir, urun adi.
--
-- 🔴 OLCULDU (16.09.2026): 41 eslesmeyen gonderiden 3'u tek adayla
--    eslesiyor, 5'i belirsiz, 18'i hic eslesmiyor, 15'inde tutar bile yok.
--    Kazanim KUCUK ama GERCEK: 9/37 -> 12/37.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.maliyet_giris_sablonu CASCADE;
DROP VIEW IF EXISTS mart.gonderi_eslestirme    CASCADE;

CREATE VIEW mart.gonderi_eslestirme AS
WITH aday AS (
  SELECT b.gonderi_id, b.barkod, b.olusturma AS gonderi_zamani, b.sehir,
         coalesce(b.siparis_tutari, b.cod_tutar) AS gonderi_tutari,
         w.siparis_id, w.siparis_no, w.toplam
    FROM raw.bk_shipment b
    LEFT JOIN raw.wix_order w
      -- 🔴 Tutar TAM esitlik (yuvarlama 2 hane) + gonderi siparisten SONRA
      --    ve 7 gun icinde. Gevsetmek belirsizligi artirir, cozmez.
      ON round(w.toplam,2) = round(coalesce(b.siparis_tutari, b.cod_tutar),2)
     AND b.olusturma >= w.olusturma
     AND b.olusturma <= w.olusturma + interval '7 days'
     -- Zaten foreign_code ile bagli siparisler aday olamaz (cift sayim).
     AND NOT EXISTS (SELECT 1 FROM raw.bk_shipment b2 WHERE b2.foreign_code = w.siparis_id)
   WHERE (b.foreign_code IS NULL
          OR NOT EXISTS (SELECT 1 FROM raw.wix_order w2 WHERE w2.siparis_id = b.foreign_code))
     AND b.yon IS DISTINCT FROM 'INCOMING'
), sayim AS (
  SELECT gonderi_id, count(siparis_id) AS aday_sayisi FROM aday GROUP BY 1
)
-- 1) Zaten foreign_code ile bagli olanlar
SELECT b.gonderi_id, b.barkod, b.sehir,
       b.foreign_code                     AS siparis_id,
       w.siparis_no,
       'MATCHED'::text                    AS sinif,
       'foreign_code'::text               AS yontem,
       1                                  AS aday_sayisi,
       'BasitKargo kaydinda Wix siparis kimligi var'::text AS gerekce
  FROM raw.bk_shipment b
  JOIN raw.wix_order w ON w.siparis_id = b.foreign_code

UNION ALL
-- 2) Tutar+tarih ile TEK aday -> MATCHED
SELECT a.gonderi_id, a.barkod, a.sehir, a.siparis_id, a.siparis_no,
       'MATCHED', 'tutar+tarih', 1,
       format('tutar %s TL birebir, gonderi siparisten %s gun sonra',
              to_char(a.gonderi_tutari,'FM999990.00'),
              (a.gonderi_zamani::date - (SELECT olusturma::date FROM raw.wix_order w3
                                          WHERE w3.siparis_id=a.siparis_id)))
  FROM aday a JOIN sayim s USING (gonderi_id)
 WHERE s.aday_sayisi = 1 AND a.siparis_id IS NOT NULL

UNION ALL
-- 3) Birden fazla aday -> AMBIGUOUS.  🔴 BIRLESTIRILMEZ, insana birakilir.
SELECT a.gonderi_id, a.barkod, a.sehir, NULL, NULL,
       'AMBIGUOUS', 'tutar+tarih', s.aday_sayisi,
       format('%s siparis ayni tutar/pencereye uyuyor - ZORLA BIRLESTIRILMEDI', s.aday_sayisi)
  FROM (SELECT DISTINCT gonderi_id, barkod, sehir FROM aday) a
  JOIN sayim s USING (gonderi_id)
 WHERE s.aday_sayisi > 1

UNION ALL
-- 4) Hic aday yok -> UNMATCHED
SELECT a.gonderi_id, a.barkod, a.sehir, NULL, NULL,
       'UNMATCHED', 'yok', 0,
       CASE WHEN a.gonderi_tutari IS NULL
            THEN 'gonderide tutar bilgisi YOK - eslestirilecek sinyal yok'
            ELSE 'tutar/tarih penceresinde eslesen siparis yok' END
  FROM (SELECT DISTINCT ON (gonderi_id) gonderi_id, barkod, sehir, gonderi_tutari
          FROM aday ORDER BY gonderi_id) a
  JOIN sayim s USING (gonderi_id)
 WHERE s.aday_sayisi = 0;

COMMENT ON VIEW mart.gonderi_eslestirme IS
  'Gonderi<->siparis eslestirme. MATCHED yalniz TEK adayli; AMBIGUOUS asla birlestirilmez.';

-- ---------------------------------------------------------------------------
-- MALIYET GIRIS SABLONU  -  gercek COGS icin kontrollu giris
-- ---------------------------------------------------------------------------
-- 🔴 RASTGELE MALIYET TAHMIN EDILMEZ.  Bu view yalnizca "hangi urun icin
--    hangi bilgi gerekli" listesini uretir; deger SAHIP tarafindan girilir.
--    Oncelik ciroya gore: en cok satan urunun maliyeti once girilmeli.
CREATE VIEW mart.maliyet_giris_sablonu AS
SELECT u.urun_id,
       u.ad                                   AS urun_adi,
       u.sku,
       u.fiyat                                AS satis_fiyati,
       mk.maliyet                             AS mevcut_deger,
       mk.kalite                              AS mevcut_kalite,
       coalesce(s.adet, 0)                    AS son30_adet,
       coalesce(s.ciro_net, 0)                AS son30_ciro_net,
       -- 🔴 Oncelik: olculmemis VE cok satan once gelir.
       CASE WHEN mk.kalite = 'OLCULMUS' THEN 'TAMAM'
            WHEN coalesce(s.ciro_net,0) > 0  THEN 'P0 - satti, maliyeti olculmedi'
            ELSE 'P2 - satis yok' END         AS oncelik,
       'Wix > Urunler > urun > Maliyet alani' AS nereye_girilir
  FROM raw.wix_urun u
  LEFT JOIN mart.maliyet_kalite mk ON mk.urun_id = u.urun_id
  LEFT JOIN (SELECT urun_id, adet, ciro_net FROM mart.urun_sinyal) s ON s.urun_id = u.urun_id
 ORDER BY CASE WHEN mk.kalite='OLCULMUS' THEN 2 ELSE 1 END,
          coalesce(s.ciro_net,0) DESC;

COMMENT ON VIEW mart.maliyet_giris_sablonu IS
  'Gercek COGS girisi icin oncelikli liste. DEGER URETMEZ - sahip girer.';

COMMIT;
