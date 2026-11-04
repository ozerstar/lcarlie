-- =============================================================================
-- L'CARLIE - CR-016 META BULGU DUZELTMESI + KARAR TADILI
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) YANLIS BULGUYU DUZELT
-- ---------------------------------------------------------------------------
-- 🔴 GECERSIZ SAYILAN BULGULAR:
--      "ads_read yok"                      -> YANLIS
--      "creative-level Meta data BLOCKER"  -> YANLIS
--    Sebep: test YANLIS JETONLA (META_SYSTEM_TOKEN) yapildi.
--    Dogrusu: META_ADS_TOKEN'da ads_read VAR; ad/adset/creative CALISIYOR.
--    ASIL BLOCKER: diger iki reklam hesabi sistem kullanicisina ATANMAMIS.
UPDATE core.source_authority SET
  current_connection = 'PARTIAL',
  mirror = 'raw.meta_harcama (kampanya) + raw.meta_reklam (ad, 291 satir) + '
           'raw.meta_kreatif (63 kreatif)',
  gap = 'KAPSAMA 1/3 HESAP. act_1301171572214198 erisilebilir; '
        'act_560782561026922 ve act_1601342818221781 sistem kullanicisina '
        'ATANMAMIS (#200). '
        'ads_read IZNI VAR - ad/adset/creative seviyesi CALISIYOR. '
        '(CR-016''da "ads_read yok" denmisti; o test YANLIS JETONLA '
        '(META_SYSTEM_TOKEN) yapilmisti ve bulgu GECERSIZDIR.) '
        'business_management YOK: me/adaccounts ve hesap bilgisi calismaz, '
        'yani hesap KESFI yapilamaz - yalniz ID''si bilinen hesap sorgulanir. '
        'KOSULLU RISK: erisilemeyen hesaplarda ek harcama varsa VE olculen '
        'gelir tabani degismiyorsa gozlenen paid-media ekonomisi daha kotu '
        'gorunur; ancak olculmeyen gelir de mevcut - tek yonlu kesinlik YOK.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-016 corrective: META_ADS_TOKEN debug_token (ads_read), '
                      'level=ad/adset/campaign + /ads + /adcreatives OK; '
                      'diger 2 hesap dogrudan denendi -> #200'
WHERE alan='ad_spend';

-- Kreatif otoritesi AYRI satir: artik olculuyor
INSERT INTO core.source_authority (alan, authority, current_connection, mirror,
                                   freshness, gap, dogrulama_zamani, dogrulama_yontemi)
VALUES ('creative_performance', 'Meta Ads (act_1301171572214198)', 'PARTIAL',
        'raw.meta_reklam + raw.meta_kreatif -> mart.reklam_performans',
        'meta-reklam-yukle.py, son 30 gun',
        'KAPSAMA 1/3 hesap. Ticari dogrulama YOK: atif kurulamadigi icin '
        'hangi reklamin satis getirdigi BILINMIYOR (commercial_confirmation='
        'NOT_AVAILABLE). CTR yalniz DIKKAT olcer. Meta''nin raporladigi '
        'donusum Meta''nin IDDIASIDIR, dogrulanmis satis degildir.',
        now(), 'CR-016 corrective: 291 ad-gun satiri, 51 reklam, 63 kreatif cekildi')
ON CONFLICT (alan) DO UPDATE SET
  current_connection=EXCLUDED.current_connection, mirror=EXCLUDED.mirror,
  freshness=EXCLUDED.freshness, gap=EXCLUDED.gap,
  dogrulama_zamani=EXCLUDED.dogrulama_zamani,
  dogrulama_yontemi=EXCLUDED.dogrulama_yontemi;

-- ---------------------------------------------------------------------------
-- 2) ILK INSAN KARARININ TADILI  -  SILINMEZ, EKLENIR
-- ---------------------------------------------------------------------------
-- 🔴 AUDIT TRAIL BOZULMAZ.  Orijinal karar notu SILINMIYOR; altina
--    TADIL notu ekleniyor. "Bir zamanlar bunu dusunmustuk" bilgisi korunur.
--
-- 🔴 IDEMPOTENT OLMAK ZORUNDA (16.09.2026'da bulundu).  raw-uygula.sh bu
--    dosyayi HER kosuda calistirir. Kosulsuz `||` ekleme yuzunden ayni TADIL
--    metni #25'in notuna YEDI kez eklenmisti. Tekrar bir audit trail DEGIL,
--    bir hatanin izidir ve gercek tadili okunmaz hale getirir.
--    Asagidaki NOT LIKE korumasi ikinci eklemeyi engeller.
UPDATE core.karar_insan
   SET karar_notu = karar_notu || E'\n\n--- TADIL (16.09.2026) ---\n'
     || 'GECERSIZ OLAN KOSUL: "Meta ads_read cozulmeden scale karari verilmeyecek". '
     || 'ads_read ZATEN VAR (META_ADS_TOKEN); onceki tespit YANLIS JETONLA yapilmisti. '
     || 'Ad/adset/creative seviyesi artik cekiliyor (291 satir, 51 reklam, 63 kreatif). '
     || E'\nSCALE ICIN KALAN META KOSULU: diger 2 reklam hesabinin gorunurlugu '
     || '(560782561026922, 1601342818221781 - sistem kullanicisina atanmamis). '
     || E'\nDIGER ACIK KOSULLAR DEGISMEDI: gercek COGS (olculmus 0/36) · '
     || 'payment authority (PayTR + muhasebe bagli degil) · yeterli orneklem '
     || '(son 30 gun 9 siparis, esik 10). '
     || E'\nKARARIN KENDISI DEGISMEDI: paid media SCALE YOK, butce artisi YOK.'
 WHERE karar_id IN (SELECT karar_id FROM core.karar
                     WHERE NOT fixture AND karar_tipi='MEDIA_BUDGET')
   AND karar_notu NOT LIKE '%--- TADIL%';

UPDATE core.karar
   SET yanlislama_kosulu =
       'Su dordu birlikte saglanirsa karar yeniden degerlendirilir: '
    || '(1) diger 2 Meta hesabinin gorunurlugu acilir, '
    || '(2) gercek COGS girilir (bugun olculmus 0/36), '
    || '(3) payment authority kurulur (PayTR/muhasebe), '
    || '(4) orneklem >=10 siparise ulasir. '
    || 'Bunlar saglandiktan SONRA paid media ekonomisi POZITIF ve TEKRARLANABILIR '
    || 'gorunurse karar yanlislanmis olur. '
    || 'NOT: "ads_read yok" kosulu 16.09.2026''da GECERSIZ oldu - ads_read zaten vardi.'
 WHERE NOT fixture AND karar_tipi='MEDIA_BUDGET';

COMMIT;
