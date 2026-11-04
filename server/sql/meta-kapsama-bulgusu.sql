-- =============================================================================
-- L'CARLIE - META KAPSAMA BULGUSU  (16.09.2026, Business Manager'dan olculdu)
--
-- 🔴 SONUC: "1/3 hesap" KAPSAMA ACIGI KOZMETIKTIR, MADDI DEGIL.
--    Erisilemeyen iki hesabin IKISI DE BOS - Business Manager ve Reklam
--    Yoneticisi arayuzunden dogrudan goruldu:
--
--      act_1601342818221781 ("lcarliee", Lcarlie isletmesi)
--        -> 1 Tem 2026 - 16 Eyl 2026 harcama 0,00 TL
--
--      act_560782561026922
--        -> 16 Agu 2023 - 15 Eyl 2026 (3 YIL) HIC KAMPANYA YOK
--           yalniz 4 yayinlanmamis taslak var
--
--    Yani ölçülen 30.128,04 TL harcama TOPLAM harcamadir; eksik hesaplarda
--    saklanan ek harcama YOKTUR. -20.709,70 TL'lik nakit tablosu EKSIK DEGIL.
--
-- 🔴 BU BULGU OLCULDU, VARSAYILMADI. Onceki metin "erisilemeyen hesaplarda
--    ek harcama VARSA" diye kosullu yazilmisti; artik kosul COZULDU.
--
-- 🔴 ATAMA YAPILAMADI ve ARTIK GEREKLI DEGIL:
--    - AdsReader, SAGLIKLI YASAM REHBERI isletmesinde;
--      act_1601342818221781 ise Lcarlie isletmesinde -> capraz isletme
--      atamasi dogrudan yapilamaz.
--    - act_560782561026922 hicbir Business Manager'da DEGIL (kisisel hesap).
--    - Ikisi de bos oldugu icin baglanmalarinin OLCUME KATKISI SIFIR.
-- =============================================================================

BEGIN;

UPDATE core.source_authority SET
  gap = 'KAPSAMA 1/3 HESAP - ama bu acik KOZMETIK, maddi degil (16.09.2026 olculdu). '
        'Erisilemeyen iki hesabin IKISI DE BOS: act_1601342818221781 -> 1 Tem-16 Eyl '
        '2026 harcama 0,00 TL; act_560782561026922 -> 16 Agu 2023-15 Eyl 2026 (3 yil) '
        'HIC KAMPANYA YOK (yalniz 4 yayinlanmamis taslak). '
        'Dolayisiyla olculen harcama TOPLAM harcamadir; nakit tablosu EKSIK DEGIL. '
        'ads_read IZNI VAR - ad/adset/creative seviyesi calisiyor (CR-016''da '
        '"ads_read yok" denmisti, o test YANLIS JETONLA yapilmisti ve GECERSIZDIR). '
        'business_management YOK: hesap kesfi (me/adaccounts) calismaz. '
        'ATAMA ENGELI: AdsReader SAGLIKLI YASAM REHBERI isletmesinde, bos hesaplar '
        'baska isletmede/hicbir isletmede - capraz atama gerekir ama GEREKSIZ.',
  dogrulama_zamani = now(),
  dogrulama_yontemi = 'CR-016 corrective: Business Manager + Reklam Yoneticisi '
                      'arayuzunden iki bos hesap dogrudan goruldu (0 TL / 0 kampanya)'
WHERE alan='ad_spend';

-- 🔴 KARARIN YANLISLAMA KOSULU GUNCELLENIR: (1) numarali kosul COZULDU.
--    Karar SILINMEZ; kosul listesi gercege gore duzeltilir.
UPDATE core.karar
   SET yanlislama_kosulu =
       'Su UCU birlikte saglanirsa karar yeniden degerlendirilir: '
    || '(1) gercek COGS girilir (bugun olculmus 0/36), '
    || '(2) payment authority kurulur (PayTR/muhasebe), '
    || '(3) orneklem >=10 siparise ulasir. '
    || 'Bunlar saglandiktan SONRA paid media ekonomisi POZITIF ve TEKRARLANABILIR '
    || 'gorunurse karar yanlislanmis olur. '
    || E'\nCOZULEN KOSULLAR: '
    || '"ads_read yok" -> GECERSIZ (izin zaten vardi, yanlis jetonla test edilmisti). '
    || '"diger 2 Meta hesabinin gorunurlugu" -> COZULDU: ikisi de BOS oldugu '
    || 'olculdu (0 TL / 3 yilda 0 kampanya), baglanmalarinin olcume katkisi SIFIR.'
 WHERE NOT fixture AND karar_tipi='MEDIA_BUDGET';

-- 🔴 IDEMPOTENT OLMAK ZORUNDA - bkz. cr016-meta-duzeltme.sql'deki ayni not.
--    Bu dosya da her raw-uygula.sh kosusunda calisiyor ve korumasiz `||`
--    ekleme TADIL 2 metnini defalarca cogaltmisti.
UPDATE core.karar_insan
   SET karar_notu = karar_notu || E'\n\n--- TADIL 2 (16.09.2026) ---\n'
     || 'Business Manager''dan olculdu: erisilemeyen iki reklam hesabi BOS. '
     || 'act_1601342818221781 harcama 0,00 TL (1 Tem-16 Eyl 2026); '
     || 'act_560782561026922 uc yilda hic kampanya yok. '
     || 'SONUC: "1/3 kapsama" acigi KOZMETIK. Olculen 30.128,04 TL TOPLAM '
     || 'harcamadir ve -20.709,70 TL''lik nakit tablosu EKSIK DEGILDIR. '
     || 'Kararin dayandigi ekonomi ZAYIFLAMADI, AKSINE DOGRULANDI. '
     || 'Atama manuel aksiyonu ONCELIKSIZ hale geldi (yapilsa da rakam degismez).'
 WHERE karar_id IN (SELECT karar_id FROM core.karar
                     WHERE NOT fixture AND karar_tipi='MEDIA_BUDGET')
   AND karar_notu NOT LIKE '%--- TADIL 2%';

COMMIT;
