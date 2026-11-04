-- =============================================================================
-- FUNNEL ETIKET DUZELTMESI  ·  25.09.2026
--
-- NEDEN. core.funnel_adim.enstrumantasyon ELLE tutulan bir etikettir ve
-- 17.09.2026'da, GA4 Data API ambara BAGLANMADAN once, tarayici ag trafigi
-- izlenerek yazilmisti. API baglandiktan sonra hic guncellenmedi. Sonuc:
-- mart.funnel_saglik iki adim icin kendi kendisiyle celisiyordu --
-- "enstrumantasyon YOK" diyen etiketin yanindaki sutun "OBSERVED" diyordu.
-- mutabakat.sql'in 23. kontrolu bunu dogru yakaladi ve 22-24 Eylul'de
-- her gun FAILED verip e-posta gonderdi. Kusur kontrolde degil, etiketteydi.
--
-- OLCUM (25.09.2026, raw.ga4_event -> ham->>'eventCount' toplami):
--   begin_checkout   29 gun, 70 olay, son 21.09
--   purchase          9 gun, 10 olay, son 11.09
--   view_cart         0 satir            <- etiketi DOGRU, dokunulmuyor
--
-- NEDEN "MEASURED" DEGIL "PARTIAL". Iki adim da olculuyor ama EKSIK sayiyor:
--   * purchase: 01.08'den beri Wix 14 siparis yazdi, GA4 8'ini yakaladi (%57).
--     Alti siparis GA4'te YOK. "MEASURED" demek bu farki gorunmez kilardi.
--   * begin_checkout: 70 olay gozlendi, ama 17.09'daki ag trafigi olcumu
--     /checkout sayfasinda bu olayi GORMEDI. Ikisi birden dogru olabilir
--     (olay bazi yollarda atiyor, hepsinde degil) -> kapsama eksik.
--
-- 🔴 BU BIR ETIKET DUZELTMESIDIR, OLCUM DEGISIKLIGI DEGIL. Tek bir olay
--    satiri eklenmedi/silinmedi. Gozlem_durumu zaten veriden hesaplaniyordu;
--    degisen, o veriyi "yok" sayan elle yazilmis not.
-- =============================================================================

BEGIN;

-- Guvenlik: beklenen mevcut durumu gormezsek DURDUR. Baskasi bu arada
-- etiketi degistirmisse ustune yazmayalim.
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM core.funnel_adim
   WHERE (adim_kod='BEGIN_CHECKOUT' AND enstrumantasyon='NOT_INSTRUMENTED')
      OR (adim_kod='PURCHASE'       AND enstrumantasyon='NOT_TESTED');
  IF n <> 2 THEN
    RAISE EXCEPTION 'Beklenen baslangic durumu yok (bulunan: %). Etiketler baskasi tarafindan degismis olabilir; elle bak.', n;
  END IF;
END $$;

UPDATE core.funnel_adim SET
  enstrumantasyon = 'PARTIAL',
  olcum_yontemi   = 'GA4 Data API toplu raporu (raw.ga4_event, ham->>eventCount)',
  olcum_zamani    = clock_timestamp(),
  olcum_kaniti    = '25.09.2026 olculdu: 29 gunde 70 begin_checkout olayi, son 21.09.2026. '
                 || 'Olay ATILIYOR. 17.09.2026''deki ag trafigi olcumu /checkout sayfasinda '
                 || 'bu olayi gormemisti; ikisi birden dogru olabilir -- olay bazi yollarda '
                 || 'atip hepsinde atmiyor olabilir. Bu yuzden MEASURED degil PARTIAL.',
  notlar          = 'Etiket 17.09''de "NOT_INSTRUMENTED" yazilmisti; o tarihte GA4 Data API '
                 || 'ambara bagli DEGILDI. Baglandiktan sonra etiket guncellenmedi ve '
                 || 'mart.funnel_saglik kendi kendisiyle celisti (etiket "yok", durum '
                 || '"OBSERVED"). 25.09.2026''da veriye bakilarak duzeltildi. '
                 || 'Kapsama olculmedi: kac oturumun checkout''a girip olay atmadigi bilinmiyor.'
WHERE adim_kod = 'BEGIN_CHECKOUT';

UPDATE core.funnel_adim SET
  enstrumantasyon = 'PARTIAL',
  olcum_yontemi   = 'GA4 Data API + mart.siparis capraz mutabakati',
  olcum_zamani    = clock_timestamp(),
  olcum_kaniti    = '25.09.2026 olculdu: 9 gunde 10 purchase olayi, son 11.09.2026. '
                 || 'Capraz mutabakat (01.08.2026''dan itibaren): Wix 14 siparis, GA4 8 '
                 || 'purchase -> GA4 siparislerin %57''sini yakaliyor, 6''si GA4''te YOK. '
                 || 'Yani olay calisiyor ama EKSIK sayiyor.',
  notlar          = 'Etiket "NOT_TESTED" idi ve gerekcesi "dogrulamak gercek siparis '
                 || 'gerektirir, bu para harcamaktir" seklindeydi. O gerekce artik '
                 || 'gecersiz: gercek siparisler ZATEN verildi ve purchase olayi uretimde '
                 || 'gozlendi -- test siparisi vermeye gerek yok, veri elimizde. '
                 || '🔴 GA4 hala TICARI OTORITE DEGILDIR: ciro Wix tarafindan okunur, '
                 || 'bu satir yalnizca olcum katmaninin sagligini anlatir.'
WHERE adim_kod = 'PURCHASE';

-- Duzeltmenin ISE YARADIGINI ayni islem icinde dogrula: 23. mutabakat
-- kontrolunun kovaladigi celiski sifirlanmali. Sifirlanmazsa geri al.
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM mart.funnel_saglik
   WHERE enstrumantasyon IN ('NOT_INSTRUMENTED','NOT_TESTED') AND gozlem_durumu='OBSERVED';
  IF n <> 0 THEN
    RAISE EXCEPTION 'Celiski surduruyor (% satir). Degisiklik geri alindi.', n;
  END IF;
END $$;

COMMIT;
