-- =============================================================================
-- L'CARLIE - CR-016 KAPANIS YAMASI  (Chief Architect review'i)
--
-- Uc kanit duzeltmesi + ilk gercek insan karari. Yeni mimari YOK.
-- =============================================================================

BEGIN;

-- ===========================================================================
-- 1) SHIPMENT METRIGI - IKI TARAF AYRI PAYDA
-- ===========================================================================
-- 🔴 RAPORDAKI HATA: "12/37 matched · 5 ambiguous · 32 unmatched" yazdim.
--    12, 5 ve 32 UCU DE GONDERI tarafi sayimi (12+5+32+1 iade = 50);
--    37 ise SIPARIS sayisi. Iki farkli paydayi ayni cumleye koymak
--    matematiksel olarak yanlis ve okuyani yaniltir.
--    Bu, projenin defalarca duzelttigi "birbirinden turemis iki sayiyi
--    yan yana koymadan once ayni sey mi diye sor" hatasinin ayni turu.
DROP VIEW IF EXISTS mart.eslestirme_ozet CASCADE;
CREATE VIEW mart.eslestirme_ozet AS
WITH gon AS (
  SELECT sinif, count(*) AS adet FROM mart.gonderi_eslestirme GROUP BY 1
), gon_t AS (SELECT count(*) AS toplam FROM raw.bk_shipment),
sip AS (
  SELECT
    count(*) AS toplam,
    count(*) FILTER (WHERE EXISTS (
      SELECT 1 FROM mart.gonderi_eslestirme e
       WHERE e.siparis_id = w.siparis_id AND e.sinif='MATCHED'))       AS eslesen,
    -- 🔴 Bir siparis, belirsiz bir gonderinin ADAYI olabilir; bu siparis
    --    "eslesmedi" degil "belirsiz"dir. Ayri sayilir.
    count(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM mart.gonderi_eslestirme e
         WHERE e.siparis_id = w.siparis_id AND e.sinif='MATCHED')
      AND EXISTS (
        SELECT 1 FROM raw.bk_shipment b
         WHERE round(b.siparis_tutari,2)=round(w.toplam,2)
            OR round(b.cod_tutar,2)=round(w.toplam,2)))                 AS belirsiz
    FROM raw.wix_order w
)
SELECT 'ORDER SIDE'::text AS taraf,
       sip.toplam                                             AS toplam,
       sip.eslesen                                            AS matched,
       sip.belirsiz                                           AS ambiguous,
       sip.toplam - sip.eslesen - sip.belirsiz                AS unmatched,
       round(100.0*sip.eslesen/nullif(sip.toplam,0),1)        AS match_rate_yuzde
  FROM sip
UNION ALL
SELECT 'SHIPMENT SIDE',
       gon_t.toplam,
       coalesce((SELECT adet FROM gon WHERE sinif='MATCHED'),0),
       coalesce((SELECT adet FROM gon WHERE sinif='AMBIGUOUS'),0),
       coalesce((SELECT adet FROM gon WHERE sinif='UNMATCHED'),0),
       round(100.0*coalesce((SELECT adet FROM gon WHERE sinif='MATCHED'),0)
             /nullif(gon_t.toplam,0),1)
  FROM gon_t;

COMMENT ON VIEW mart.eslestirme_ozet IS
  'Eslestirme HER TARAF KENDI PAYDASIYLA. Order-side ve shipment-side sayimlari '
  'ASLA ayni cumlede karistirilmaz (CR-016 review bulgusu).';

-- ===========================================================================
-- 2) META RISK CUMLESI - KOSULLU HALE GETIR
-- ===========================================================================
-- 🔴 "Okunamayan 2 hesapta harcama varsa zarar YALNIZ BUYUR" fazla kesindi:
--    olculmeyen gelir (WhatsApp/telefon satisi, Wix disi COD) ihtimalini
--    yok sayiyordu. Kosullu ifade tek yonlu kesinlik iddia etmez.
UPDATE core.source_authority SET
  gap = 'ad/creative seviyesi ERISILEMIYOR: ads_read izni verilmemis '
        '(OAuthException #200, sonda 16.09.2026). Kampanya seviyesi calisiyor. '
        'KAPSAMA 1/3. '
        'KOSULLU RISK: erisilemeyen Meta hesaplarinda EK HARCAMA varsa VE '
        'olculen gelir tabani DEGISMIYORSA, gozlenen paid-media ekonomisi '
        'daha kotu gorunur. Ancak olculmeyen gelir de mevcut (Wix disi '
        'kapida odeme, WhatsApp/telefon satisi) - bu yon aksi yonde calisir. '
        'Iki bilinmezlik ayni anda acik; tek yonlu kesinlik IDDIA EDILMEZ.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-016: level=ad ve act_/ads sondalandi (reddedildi); '
                      'risk ifadesi kosullu hale getirildi (review)'
WHERE alan='ad_spend';

-- 3) SHIPMENT: P0 CLOSED DEGIL, PARTIAL
UPDATE core.source_authority SET
  current_connection = 'PARTIAL',
  gap = 'Eslestirme CR-016''da IYILESTIRILDI ama KAPANMADI (PARTIAL). '
        'Gonderi tarafi: 12 MATCHED / 5 AMBIGUOUS / 32 UNMATCHED / 1 iade (toplam 50). '
        'Siparis tarafi ayri paydayla olculur - mart.eslestirme_ozet. '
        'AMBIGUOUS gonderiler ZORLA BIRLESTIRILMEDI. '
        'PII alinmadigi icin telefon/ad ile eslestirme YAPILAMAZ; kalan '
        'eslesmezligin cogu bu tasarim kararinin bedelidir.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-016 review: iki taraf ayri paydayla raporlandi, durum PARTIAL'
WHERE alan='shipment';

-- ===========================================================================
-- 3) PAZAR ARASTIRMASI - ADJACENT_CATEGORY_REFERENCE
-- ===========================================================================
-- 🔴 Genital temizleyici ile VIREON AYNI KATEGORI DEGIL. "direct competitor
--    benchmark" olarak kullanmak yanlis olurdu. Etiket degistirildi ve
--    hipotez KANITLANMIS NEDEN gibi yazilmadi.
DROP VIEW IF EXISTS mart.pazar_arastirma CASCADE;
CREATE VIEW mart.pazar_arastirma AS
SELECT * FROM (VALUES
  ('ADJACENT_CATEGORY_REFERENCE', 'FACT',
   'Komsu kategori "genital bolge temizleyici (erkek)": 45,00 TL''den basliyor, 59 urun listeleniyor',
   'cimri.com fiyat karsilastirma', '16.09.2026',
   'DIRECT COMPETITOR BENCHMARK DEGILDIR. Temizleyici ile bakim kremi ayri kategori; '
   'yalniz KOMSU KATEGORI REFERANSI olarak kullanilir.'),
  ('ADJACENT_CATEGORY_REFERENCE', 'INTERPRETATION',
   'VIREON 2.400 TL (indirimli 1.200) komsu kategori tabanindan belirgin sekilde yuksek - '
   'musteride PREMIUM FIYAT ALGISI olusabilir',
   'ic veri (raw.wix_urun) + cimri.com', '16.09.2026',
   'Yorumdur, olcum degildir. Musterinin bu karsilastirmayi yaptigi DOGRULANMADI.'),
  ('ADJACENT_CATEGORY_REFERENCE', 'HYPOTHESIS',
   'Fiyat sorularinin BIR KISMI premium fiyat farkindan kaynaklaniyor OLABILIR',
   'mart.soru_konu FIYAT=143/259 + komsu kategori tabani', '16.09.2026',
   'KANITLANMIS NEDEN DEGILDIR. Dogrulamak icin musteriye "neyle karsilastirdiniz" '
   'sorulmali; bugun bu veri YOK. Karar kaniti olarak kullanilamaz.'),
  ('RAKIP_IZLEME', 'NOT_CONNECTED',
   'Yapisal rakip reklam/fiyat izleme kaynagi bagli degil - tekil arama yapildi, surekli akis YOK',
   'MANUAL_RESEARCH_REQUIRED', '16.09.2026',
   'Tek seferlik arama trend gostermez.'),
  ('ARAMA_TALEBI', 'NOT_CONNECTED',
   'Arama hacmi / SEO veri kaynagi bagli degil',
   'MANUAL_RESEARCH_REQUIRED', '16.09.2026',
   'Kategori talebinin buyuyup buyumedigi BILINMIYOR.')
) AS t(kod, seviye, bulgu, kaynak, tarih, yorum);

COMMENT ON VIEW mart.pazar_arastirma IS
  'ADJACENT_CATEGORY_REFERENCE - direct competitor benchmark DEGIL. '
  'FACT/INTERPRETATION/HYPOTHESIS ayri; hipotez kanitlanmis neden gibi yazilmaz. '
  'Kaynak ve tarih her satirda zorunlu.';

COMMIT;
