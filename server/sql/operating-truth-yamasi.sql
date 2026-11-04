-- =============================================================================
-- L'CARLIE - OPERATING TRUTH CORRECTION PATCH  (16.09.2026)
--
-- Chief Architect + Sahip dogrulamasiyla gelen IS GERCEKLERI sisteme islenir.
-- YENI MIMARI YOK, YENI MODUL YOK - yanlis operasyonel varsayimlar duzeltilir.
--
-- 🔴 DUZELTILEN UC YANLIS VARSAYIM:
--
--  1) "Meta kapsamasi 1/3, yani eksik veri"  ->  YANLIS
--     Uc hesap BILINIYOR ama yalnizca BIRI operasyonda. Digerlerinde reklam
--     yayinlanmiyor. Bu bir VERI KALITESI ACIGI degil, KAPSAM DISI birakma
--     kararidir. Olcu ikiye ayrilir: bilinen hesap kapsamasi (1/3) ve
--     AKTIF OPERASYONEL kapsama (1/1). Karar metrigi ikincisidir.
--
--  2) "PayTR bagli degil, yani online satis bilinmiyor"  ->  YANLIS
--     PayTR ayri bir satis kanali DEGIL; Wix sitesinin odeme saglayicisi.
--     Siparis ve odeme OPERASYONEL durumu Wix'ten biliniyor. PayTR'in
--     eksikligi yalnizca SETTLEMENT MUTABAKATI acigidir - siparisi ya da
--     ciroyu UNKNOWN yapmaz.
--
--  3) "Offline odeme kaynagi bagli degil"  ->  YANLIS CERCEVE
--     Sahip karari: olcum donemi baslayinca offline odemeler INSAN
--     tarafindan girilecek. Yani bu bir entegrasyon hatasi degil, TASARLANMIS
--     bir surectir: MANUAL_CONTROLLED_INPUT. Kayit girilmediyse eksik olan
--     KAYNAK degil, GIRIS'tir.
--
-- 🔴 BU YAMA KANIT KALITESINI SAHIP BEYANIYLA YUKSELTMEZ.  Yalnizca
--    GERCEK OLMAYAN eksikleri ceza listesinden cikarir. Gercek acikliklar
--    (COGS, orneklem, atif, siniflandirma, GA4) oldugu gibi durur.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0) DURUM SOZLUGU GENISLETILIR
-- ---------------------------------------------------------------------------
-- 🔴 Mevcut CHECK yalnizca CONNECTED/PARTIAL/SOURCE_NOT_CONNECTED/NONE/UNKNOWN
--    kabul ediyordu. Iki gercek durum bu listede YOKTU ve olmadiklari icin
--    yanlis kutuya konuyorlardi:
--      - insan girisi bekleyen surec -> "SOURCE_NOT_CONNECTED" yaziliyordu
--      - istege bagli mutabakat acigi -> "SOURCE_NOT_CONNECTED" yaziliyordu
--    Ikisi de "kaynak yok" diye okunuyordu; oysa biri surec, digeri opsiyon.
ALTER TABLE core.source_authority
  DROP CONSTRAINT IF EXISTS source_authority_current_connection_check;
ALTER TABLE core.source_authority
  ADD CONSTRAINT source_authority_current_connection_check
  CHECK (current_connection IN (
    'CONNECTED','PARTIAL','SOURCE_NOT_CONNECTED','NONE','UNKNOWN',
    'MANUAL_CONTROLLED_INPUT',      -- insan girisi bekleyen TASARLANMIS surec
    'OPTIONAL_RECONCILIATION_GAP',  -- operasyonu engellemeyen mutabakat acigi
    -- 🔴 CR-017: kaynak CALISIYOR ama bize AKTARIM bloke (GA4 sitede canli,
    --    Data API credential yok). 'SOURCE_NOT_CONNECTED' bunu anlatmiyordu.
    -- 🔴 SOZLUK IKI DOSYADA TANIMLI: burada ve funnel-semantic-yamasi.sql'de.
    --    Bu dosya SONRA calistigi icin eksik birakilirsa oteki dosyanin
    --    yazdigi deger kisiti IHLAL EDER ve apply PATLAR - 17.09.2026'da oldu.
    --    Yeni bir durum eklenirse HER IKI yere de eklenmeli.
    'BLOCKED_BY_EXTERNAL_CREDENTIAL'
  ));

-- ---------------------------------------------------------------------------
-- 1-2) META HESAP KAYDI ve KAPSAMA VIEW'I --> meta-hesap-kayit.sql
-- 🔴 Bu dosyada DEGIL: nakit ve hazirlik view'lari mart.meta_kapsama'yi
--    okudugu icin o obje ERKEN kurulmali. Bu dosya ise EN SONDA calisir.

-- ---------------------------------------------------------------------------
-- 3) KAYNAK OTORITESI DUZELTMELERI
-- ---------------------------------------------------------------------------

-- 3a) REKLAM HARCAMASI: aktif kapsama tam -> CONNECTED
UPDATE core.source_authority SET
  current_connection = 'CONNECTED',
  gap = 'AKTIF OPERASYONEL KAPSAMA TAM (1/1). Bilinen 3 hesabin 2''si (560782561026922, '
        '1601342818221781) reklam YAYINLAMIYOR ve INACTIVE_EXCLUDED olarak kayitlidir - '
        'sistem kullanicisina atanmamis olmalari VERI ACIGI DEGILDIR, okunacak harcama yoktur. '
        'Onceki "1/3 kapsama" ifadesi ENVANTER olcusuydu ve karar metrigi gibi kullaniliyordu; '
        'artik mart.meta_kapsama iki olcuyu ayirir. '
        'KALAN GERCEK ACIK: business_management izni yok - hesap KESFI yapilamaz, yani yeni bir '
        'hesap acilirsa sistem bunu KENDILIGINDEN GOREMEZ; core.meta_hesap_kayit elle guncellenmelidir. '
        'ads_read VAR: ad/adset/creative seviyesi calisiyor.',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = 'Sahip beyani + Business Manager UI olcumu (16.09.2026) + Graph API act_/insights'
WHERE alan = 'ad_spend';

-- 3b) ONLINE ODEME: Wix operasyonel otoritedir, PayTR ayri bir sorudur
-- 🔴 EN ONEMLI KAVRAM DUZELTMESI. Onceki kayit "PayTR API'sine baglanti YOK"
--    diyordu ve bu, online siparisin BILINMEDIGI gibi okunuyordu. Oysa
--    PayTR ayri bir satis kanali degil, Wix checkout'unun odeme saglayicisi.
--    Siparisin varligi, tutari ve odeme durumu Wix'ten OPERASYONEL OLARAK
--    biliniyor. PayTR'in eksikligi yalnizca "banka/settlement kaydiyla
--    birebir mutabakat" acigidir.
UPDATE core.source_authority SET
  authority = 'Wix Stores (siparis + odeme operasyonel durumu)',
  current_connection = 'CONNECTED',
  gap = 'Wix, online siparisin ve odeme OPERASYONEL DURUMUNUN otoritesidir: '
        'siparis var mi, tutari ne, odendi isaretli mi - ucu de biliniyor. '
        'PayTR AYRI BIR SATIS KANALI DEGILDIR, bu Wix satislarinin odeme saglayicisidir; '
        'eksikligi settlement mutabakati acigidir ve settlement_reconciliation satirinda tutulur. '
        'ONCEKI YANLIS YORUM KALDIRILDI: "PayTR bagli degil -> online satis bilinmiyor". '
        'GERCEK SINIR: Wix''in "odendi" beyani ile bankaya GECEN para birebir eslestirilmiyor; '
        'bu bir mutabakat acigidir, siparis/ciro bilinmezligi degildir.',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = 'Sahip dogrulamasi (16.09.2026): PayTR = Wix checkout odeme saglayicisi'
WHERE alan = 'payment_online';

-- 3c) SETTLEMENT MUTABAKATI: ayri ve opsiyonel bir aciklik
INSERT INTO core.source_authority
  (alan, authority, mirror, freshness, current_connection, gap,
   dogrulama_zamani, dogrulama_yontemi, notlar)
VALUES
  ('settlement_reconciliation', 'PayTR (settlement/hesaplasma kayitlari)',
   'yok', 'yok', 'OPTIONAL_RECONCILIATION_GAP',
   'PayTR API''sine baglanti yok. Bu, siparis ya da ciro bilinmezligi DEGILDIR - '
   'siparis otoritesi Wix''tir. Aciklik sudur: Wix''in bildirdigi tahsilat ile PayTR''den '
   'bankaya GECEN tutar birebir karsilastirilmiyor (komisyon, chargeback, geciken transfer). '
   'Operasyonu ENGELLEMEZ; muhasebe kesinligi icin gerekir.',
   clock_timestamp(),
   'Kavramsal ayrim sahip tarafindan dogrulandi (16.09.2026)',
   'Baglanirsa ciro TANIMI degismez; yalnizca dogrulama katmani eklenir.')
ON CONFLICT (alan) DO UPDATE SET
  authority=EXCLUDED.authority, current_connection=EXCLUDED.current_connection,
  gap=EXCLUDED.gap, dogrulama_zamani=clock_timestamp(),
  dogrulama_yontemi=EXCLUDED.dogrulama_yontemi, notlar=EXCLUDED.notlar;

-- 3d) OFFLINE ODEME: entegrasyon hatasi degil, TASARLANMIS insan sureci
UPDATE core.source_authority SET
  authority = 'Insan girisi (kontrollu manuel kayit)',
  current_connection = 'MANUAL_CONTROLLED_INPUT',
  gap = 'Sahip karari: olcum donemi basladiginda offline/elle odemeler sisteme INSAN '
        'tarafindan girilecek. Bu bir ENTEGRASYON HATASI DEGIL, tasarlanmis bir surectir. '
        'ZORUNLU ALANLAR: siparis/referans · tarih · tutar · odeme_tipi · odeme_durumu · '
        'girildi_zamani · giren_kisi · not/kaynak. '
        'Kayit girilmediyse dogru ifade MISSING_MANUAL_ENTRY''dir - SOURCE_NOT_CONNECTED DEGIL. '
        'ONCEKI IFADE KALDIRILDI: "gercek tahsilat kaynagi tespit edilene kadar bu siparisler '
        'CIRO olarak sayilmamalidir" - kaynak bellidir (insan girisi), eksik olan GIRISTIR.',
  dogrulama_zamani = clock_timestamp(),
  dogrulama_yontemi = 'Sahip karari (16.09.2026)'
WHERE alan = 'payment_offline';

-- ---------------------------------------------------------------------------
-- 4) VIREON FIYAT MODELI
-- ---------------------------------------------------------------------------
-- 🔴 TEK SAYI YOK. "Fiyat 1200" cumlesi eksik: 1200 KAMPANYA fiyatidir,
--    kalici degildir. Sistem 1200'u PERMANENT ogrenirse kampanya bittiginde
--    musteriye yanlis fiyat soyler.
-- 🔴 TARIH UYDURULMAZ. Wix urun objesinde discount = {type, value} - BASLANGIC
--    ve BITIS ALANI YOK (16.09.2026'da olculdu). Bu yuzden kampanya suresi
--    SAHIP BEYANIDIR ve bitis tarihi BILINMIYOR.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('vireon_base_price',            '2400',
   'Normal/liste fiyati. Sahip dogrulamasi 16.09.2026.'),
  ('vireon_current_selling_price', '1200',
   'Kampanya fiyati. Wix priceData.discountedPrice ile OLCULDU 16.09.2026.'),
  ('vireon_price_state',           'CAMPAIGN',
   'CAMPAIGN | NORMAL. Kampanya bitince NORMAL olur ve fiyat 2400''e doner.'),
  ('vireon_campaign_duration',     '10 gun',
   'Sahip beyani. Wix discount objesinde sure alani YOK - olculemedi.'),
  ('vireon_campaign_source',       'OWNER_DECLARED_CAMPAIGN',
   'Wix urun objesi kampanya tarihi TASIMIYOR (discount = {type,value}); sure sahip beyanidir.'),
  ('vireon_campaign_end',          'OWNER_INPUT_REQUIRED',
   '🔴 TARIH UYDURULMADI. Sahip kesin bitis tarihi vermedi; verilene kadar BILINMIYOR.')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- 🔴 KARSILASTIRMALI FIYAT IDDIASI, BASE PRICE'TAN AYRI BIR SEYDIR.
--    Base price'in 2400 olmasi, "2400 yerine 1200" yazilabilecegi anlamina
--    GELMEZ: indirim mevzuati onceki donemin gercek fiyatinin KANITINI ister.
--    Elimizdeki fiyat logu 14.09'da basliyor ve o iki gunde liste fiyati
--    1200 gorunuyor. Yani iddia, ispat edebildigimiz donemde DESTEKLENMIYOR.
INSERT INTO core.ayar (anahtar, deger, aciklama) VALUES
  ('vireon_comparative_claim_allowed', 'HAYIR',
   'LEGAL_COMPARATIVE_PRICE_CLAIM: "2400 yerine 1200" ifadesi gecmis fiyat KANITI gerektirir. '
   'fiyat-log 14.09.2026''da basliyor ve 14-15.09''da liste fiyatini 1200 gosteriyor; '
   'ustu cizili 2400 gosterimi 16.09 04:48''de olustu. Ispat yukumlulugu karsilanana kadar '
   'musteri/reklam iletisiminde karsilastirmali fiyat KULLANILMAZ. '
   'Guvenli ifade: "Fiyati 1.200 TL." (BUSINESS_BASE_PRICE=2400 bundan BAGIMSIZDIR.)')
ON CONFLICT (anahtar) DO UPDATE
  SET deger = EXCLUDED.deger, aciklama = EXCLUDED.aciklama, guncelleme = clock_timestamp();

-- ---------------------------------------------------------------------------
-- 4b) FIYAT GERCEGI vs WIX GOZLEMI  -  IKISI AYRI KATMAN
-- ---------------------------------------------------------------------------
-- 🔴 WIX FIYAT OTORITESI DEGILDIR (Chief Architect kilidi, 16.09.2026).
--    Ilk surumde kurdugum fiyat kapisi, hazir cevap dosyasini Wix'e gore
--    "eski" ilan ediyordu. Bu, sessizce su kurali ogretiyordu:
--        "Wix ne diyorsa dogrudur, isletme gercegi ona uyar."
--    Tehlike somut: Wix'te 1.200 yanlislikla KALICI kalirsa sistem
--    "demek ki base price 2.400 degil 1.200 olmus" diye ogrenir ve
--    isletmenin normal fiyati sessizce KAYBOLUR.
--
--    DOGRU MODEL - iki katman, arada KARSILASTIRMA:
--        ISLETME FIYAT GERCEGI   (core.ayar - sahip beyani, OTORITE)
--            base_price · campaign_price · price_state · campaign_end
--                         |
--                    karsilastir
--                         |
--        WIX GOZLENEN FIYAT      (raw.wix_urun - VITRIN DURUMU, gozlem)
--                         |
--                 MATCH / PRICE_TRUTH_MISMATCH
--
--    Fark varsa sistem HICBIR TARAFI otomatik duzeltmez; MISMATCH uretir
--    ve insana sorar. Hangisinin yanlis oldugu bir OLCUM sorusu degil,
--    bir KARAR sorusudur: vitrin mi yanlis ayarlanmis, yoksa isletme
--    fiyati mi degismis de sisteme yazilmamis?
DROP VIEW IF EXISTS mart.fiyat_gercegi CASCADE;

CREATE VIEW mart.fiyat_gercegi AS
WITH isletme AS (
  SELECT (SELECT deger FROM core.ayar WHERE anahtar='vireon_base_price')::numeric   AS base_price,
         (SELECT deger FROM core.ayar WHERE anahtar='vireon_current_selling_price')::numeric AS kampanya_fiyati,
         (SELECT deger FROM core.ayar WHERE anahtar='vireon_price_state')           AS fiyat_durumu,
         (SELECT deger FROM core.ayar WHERE anahtar='vireon_campaign_end')          AS kampanya_bitisi,
         (SELECT deger FROM core.ayar WHERE anahtar='vireon_comparative_claim_allowed') AS karsilastirma_izni
), wix AS (
  SELECT (ham#>>'{priceData,price}')::numeric            AS wix_liste,
         (ham#>>'{priceData,discountedPrice}')::numeric  AS wix_satis,
         (ham#>>'{visible}')                             AS wix_yayinda
    FROM raw.wix_urun WHERE ad ILIKE '%vireon%' LIMIT 1
), h AS (
  SELECT i.*, w.*,
         -- Isletme gercegine gore BEKLENEN vitrin fiyati
         CASE WHEN i.fiyat_durumu = 'CAMPAIGN' THEN i.kampanya_fiyati
              ELSE i.base_price END AS beklenen_satis
    FROM isletme i, wix w
)
SELECT
  base_price, kampanya_fiyati, fiyat_durumu, kampanya_bitisi, karsilastirma_izni,
  wix_liste, wix_satis, wix_yayinda, beklenen_satis,

  -- 🔴 OTORITE SIRASI BURADA YAZILI: musteriye soylenecek fiyat ISLETME
  --    gercegindendir, Wix'ten degil. Wix yalniz DOGRULAMA girdisidir.
  beklenen_satis                                        AS musteriye_soylenecek_fiyat,

  (wix_satis IS NOT DISTINCT FROM beklenen_satis
   AND wix_liste IS NOT DISTINCT FROM base_price)       AS uyumlu,

  CASE
    WHEN wix_satis IS NULL OR wix_liste IS NULL         THEN 'WIX_OKUNAMADI'
    WHEN wix_satis IS DISTINCT FROM beklenen_satis
      OR wix_liste IS DISTINCT FROM base_price          THEN 'PRICE_TRUTH_MISMATCH'
    ELSE 'MATCH'
  END                                                   AS durum,

  CASE
    WHEN wix_satis IS NULL OR wix_liste IS NULL THEN
      'Wix aynasindan fiyat okunamadi. Isletme gercegi gecerlidir; vitrin durumu BILINMIYOR.'
    WHEN wix_satis IS DISTINCT FROM beklenen_satis
      OR wix_liste IS DISTINCT FROM base_price THEN
      format('🔴 PRICE_TRUTH_MISMATCH. Isletme gercegi: base %s, %s fiyati %s (beklenen vitrin: %s). '
             'Wix vitrini: liste %s, satis %s. '
             'SISTEM HICBIR TARAFI OTOMATIK DUZELTMEZ - Wix otorite DEGILDIR. '
             'Insan karari gerekir: vitrin mi yanlis ayarlandi, yoksa isletme fiyati mi '
             'degisti de core.ayar''a yazilmadi? Karar verilene kadar musteriye %s TL soylenir.',
             base_price, fiyat_durumu, kampanya_fiyati, beklenen_satis,
             wix_liste, wix_satis, beklenen_satis)
    ELSE
      format('MATCH. Isletme gercegi ile Wix vitrini ortusuyor: liste %s, satis %s (durum %s).',
             base_price, beklenen_satis, fiyat_durumu)
  END                                                   AS aciklama
FROM h;

COMMENT ON VIEW mart.fiyat_gercegi IS
  'ISLETME fiyat gercegi (core.ayar, OTORITE) ile WIX gozlenen vitrin fiyatini karsilastirir. '
  'Wix otorite DEGILDIR; fark PRICE_TRUTH_MISMATCH uretir ve insan karari bekler.';

-- ---------------------------------------------------------------------------
-- 5) KARAR HAFIZASI TADILI
-- ---------------------------------------------------------------------------
-- 🔴 ONCE TEKRARLAR TEMIZLENIR - ONCEKI YAMALAR IDEMPOTENT DEGILDI.
--    cr016-meta-duzeltme.sql ve meta-kapsama-bulgusu.sql, karar_notu'na
--    KOSULSUZ ekleme yapiyordu ve raw-uygula.sh her calistiginda yeniden
--    ekleniyordu: #25'in notunda ayni TADIL metninden 7 kopya olusmustu.
--    Tekrar bir audit trail DEGILDIR, bir hatanin izidir. Her tadilin
--    BIR kopyasi korunur; hicbir tadil icerigi silinmez.
UPDATE core.karar_insan ki
   SET karar_notu =
       -- ilk TADIL'den onceki ORIJINAL karar metni aynen korunur
       coalesce(substring(ki.karar_notu from '^(.*?)\n\n--- TADIL'), ki.karar_notu)
       || E'\n\n--- TADIL 1 (16.09.2026) ---\n'
       || 'GECERSIZ OLAN KOSUL: "Meta ads_read cozulmeden scale karari verilmeyecek". '
       || 'ads_read ZATEN VAR (META_ADS_TOKEN); onceki tespit YANLIS JETONLA yapilmisti. '
       || 'Ad/adset/creative seviyesi cekiliyor.'
       || E'\n\n--- TADIL 2 (16.09.2026) ---\n'
       || 'Business Manager''dan olculdu: erisilemeyen iki reklam hesabi BOS. '
       || 'act_1601342818221781 harcama 0,00 TL (1 Tem-16 Eyl 2026); '
       || 'act_560782561026922 uc yilda hic kampanya yok. '
       || '"1/3 kapsama" acigi KOZMETIK; nakit tablosu EKSIK DEGILDIR.'
       || E'\n\n--- TADIL 3 (16.09.2026, SAHIP DOGRULAMASI) ---\n'
       || 'GECERSIZ OLAN KOSUL: "diger 2 Meta hesabi gorunur olmadan scale karari verilmez". '
       || 'Sahip dogruladi: bu iki hesap OPERASYON DISI/OFFLINE''dir, reklam yayinlamazlar. '
       || 'Erisilememeleri aktif medya kararinda EKSIK KAPSAMA OLUSTURMAZ. '
       || 'AKTIF OPERASYONEL META KAPSAMASI ARTIK %100 (1/1).'
       || E'\nSCALE ICIN KALAN ACIKLAR (Meta disi, degismedi): '
       || 'ticari dogrulama/atif · gercek COGS (olculmus 0/36) · yeterli orneklem · '
       || 'huni/donusum kaniti.'
       || E'\nKARARIN KENDISI DEGISMEDI: paid media SCALE YOK, butce artisi YOK. '
       || 'Bu bir tadildir, karar degisikligi degildir.'
 WHERE ki.karar_id IN (SELECT karar_id FROM core.karar
                        WHERE NOT fixture AND karar_tipi = 'MEDIA_BUDGET')
   AND ki.karar_notu NOT LIKE '%TADIL 3 (16.09.2026, SAHIP DOGRULAMASI)%';

-- Yanlislama kosulu: Meta kapsamasi kosul olmaktan CIKAR
UPDATE core.karar SET
  yanlislama_kosulu =
    'Su UCU birlikte saglanirsa karar yeniden degerlendirilir: '
    || '(1) gercek COGS girilir (bugun olculmus 0/36), '
    || '(2) ticari dogrulama/atif kurulur (bugun commercial_confirmation=NOT_AVAILABLE), '
    || '(3) orneklem >=10 siparise ulasir. '
    || 'Bunlar saglandiktan SONRA paid media ekonomisi POZITIF ve TEKRARLANABILIR '
    || 'gorunurse karar yanlislanmis olur. '
    || E'\nCOZULEN/GECERSIZ KOSULLAR: '
    || '"ads_read yok" -> GECERSIZ (izin zaten vardi, yanlis jetonla test edilmisti). '
    || '"diger 2 Meta hesabinin gorunurlugu" -> KOSUL OLMAKTAN CIKTI: sahip dogrulamasiyla '
    || 'bu hesaplar OPERASYON DISI (INACTIVE_EXCLUDED); aktif operasyonel kapsama %100. '
    || '"payment authority (PayTR)" -> YENIDEN CERCEVELENDI: siparis/odeme operasyonel '
    || 'otoritesi Wix''tir ve BAGLIDIR; PayTR yalnizca settlement mutabakati acigidir.'
 WHERE NOT fixture AND karar_tipi = 'MEDIA_BUDGET';

COMMIT;
