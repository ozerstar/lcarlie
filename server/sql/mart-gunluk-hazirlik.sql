-- =============================================================================
-- L'CARLIE - 1 EKIM'E KADAR GUNLUK HAZIRLIK KONTROLU
--
-- Chief Architect talimati (16.09.2026):
--   "Son hafta gunluk su readiness kontrolunu calistir:
--    manual_order_capture_complete, sample_classification_explicit,
--    basitkargo_marker_readable, meta_spend_coverage, cost_quality_p0,
--    unanswered_messages, backup_health.
--    Bunlardan ILK UCU gecmiyorsa 1 Ekim geldi diye ROAS'i karar metrigi yapma."
--
-- 🔴 BU VIEW mart.hazirlik'IN YERINE GECMEZ.
--    mart.hazirlik tek bir soruyu cevaplar: "panel ROAS SAYISI gosterebilir mi".
--    Bu view baska bir soruyu cevaplar: "1 Ekim'de olcmeye BASLAYABILIR miyiz".
--    Ikisi ayri kapidir; ortak olan satirlar burada YENIDEN TANIMLANMAZ,
--    mart.hazirlik'tan OKUNUR - ayni olgunun iki tanimi olursa biri
--    sessizce eskir (proje bunu mart.acik_isler'de uc kez yasadi).
--
-- 🔴 ILK UC SATIR "P0" KAPISIDIR ve digerlerinden farkli bir is yapar:
--    ucu birden gecmeden ROAS bir KARAR METRIGI olamaz. Sebebi aritmetik:
--      - manual_order_capture eksikse  -> ROAS'in PAYI eksik  -> olcu KOTU cikar
--      - sample_classification eksikse -> gider yanlis yere yazilir -> her iki yone
--      - basitkargo_marker okunamiyorsa -> ikinci satiri duzeltmenin YOLU yok
--    Yani P0 kapisi kapaliyken cikan ROAS, yanlis olmakla kalmaz; hangi
--    yone yanlis oldugu da bilinmez. Yorumlanamayan sayi karar veremez.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.roas_kapisi        CASCADE;
DROP VIEW IF EXISTS mart.gunluk_hazirlik    CASCADE;
DROP VIEW IF EXISTS mart.p0_urun            CASCADE;

-- ---------------------------------------------------------------------------
-- P0 URUN LISTESI  - sahip karari, yoksa olculmus vekil
-- ---------------------------------------------------------------------------
-- 🔴 SIRA ONEMLI: gunluk_hazirlik bu view'i okur, o yuzden ONCE kurulur.
CREATE VIEW mart.p0_urun AS
WITH sahip AS (
  -- core.ayar.p0_urunler = virgulle ayrilmis urun_id listesi
  SELECT btrim(x) AS urun_id
    FROM core.ayar a, unnest(string_to_array(a.deger, ',')) AS x
   WHERE a.anahtar = 'p0_urunler' AND btrim(coalesce(a.deger,'')) <> ''
), vekil AS (
  -- 🔴 VEKIL, SAHIP KARARININ YERINE GECMEZ - eksikligini gorunur kilar.
  --    "Hangi urune reklam verecegiz" ileriye donuk bir secimdir; gecmis
  --    ciro onu TAHMIN eder, TANIMLAMAZ. Detay metni hangisinin
  --    kullanildigini her zaman yazar.
  SELECT k.urun_id
    FROM mart.siparis_kalem k
    JOIN raw.wix_order w ON w.siparis_id = k.siparis_id
   WHERE k.ciro_sinifi <> 'IPTAL'
     AND w.olusturma >= clock_timestamp() - interval '90 days'
   GROUP BY k.urun_id
   ORDER BY sum(k.satir_ciro_net) DESC NULLS LAST
   LIMIT 5
)
SELECT urun_id, 'SAHIP_KARARI'::text AS kaynak FROM sahip
UNION ALL
SELECT urun_id, 'VEKIL_SON_90_GUN_CIRO'::text FROM vekil
 WHERE NOT EXISTS (SELECT 1 FROM sahip);

COMMENT ON VIEW mart.p0_urun IS
  'Reklam verilecek oncelikli urunler. core.ayar.p0_urunler yazilmadiysa son 90 gun cirosu VEKIL olarak kullanilir.';

-- ---------------------------------------------------------------------------
-- 7 MADDELIK GUNLUK KONTROL
-- ---------------------------------------------------------------------------
CREATE VIEW mart.gunluk_hazirlik AS

-- 1 ---------------------------------------------------------------------------
-- P0 · WhatsApp/telefon siparisleri sisteme giriliyor mu?
-- 🔴 mart.hazirlik'taki SIPARIS_KAYDI_TAM ile AYNI OLGU - yeniden
--    tanimlanmiyor, oradan okunuyor.
SELECT 1                                   AS sira,
       'manual_order_capture_complete'     AS anahtar,
       'P0'                                AS kapi,
       h.saglandi                          AS gecti,
       h.detay                             AS detay,
       'mart.hazirlik / SIPARIS_KAYDI_TAM' AS nereden,
       'Kapida odemeli ama Wix kaydi olmayan gonderi = cirosu gorunmeyen satis. '
       'WhatsApp/telefon siparis giris SOP''unu isletir.'  AS neden_onemli
  FROM mart.hazirlik h WHERE h.kosul = 'SIPARIS_KAYDI_TAM'

-- 2 ---------------------------------------------------------------------------
-- P0 · Numune ACIKCA isaretli mi? (varsayimla degil)
-- 🔴 16.09.2026 duzeltmesi: "kapida odeme yok + Wix kaydi yok => numune"
--    kurali KALDIRILDI. Isaret yoksa sinif UNKNOWN'dur. Bu satir, kac
--    gonderinin hala insan karari bekledigini soyler.
UNION ALL
SELECT 2, 'sample_classification_explicit', 'P0',
       NOT EXISTS (SELECT 1 FROM mart.gonderi WHERE sinif = 'UNKNOWN'),
       format('%s gonderinin sinifi BILINMIYOR (%s TL kargo)',
              (SELECT count(*) FROM mart.gonderi WHERE sinif='UNKNOWN'),
              (SELECT to_char(coalesce(sum(kargo_ucreti),0),'FM999999990.00')
                 FROM mart.gonderi WHERE sinif='UNKNOWN')),
       'mart.gonderi sinif=UNKNOWN',
       'Isaretlenmemis gonderi ne satis ne pazarlama gideri sayilabilir. '
       'Varsayimla numune saymak, bir SATISI gider diye okumaktir.'

-- 3 ---------------------------------------------------------------------------
-- P0 · EK BILGI alani API'de GERCEKTEN okunabiliyor mu?
-- 🔴🔴 BU SATIR BILEREK SERT. Bugune kadar 50/50 gonderide ek_bilgi BOS.
--    Yani `NUMUNE-<tarih>` standardi, degeri HIC GORULMEMIS bir alanin
--    uzerine kuruluydu. `ek_bilgi` su an content.name'den cikariliyor ve
--    bunun BasitKargo panelindeki "EK BILGI" kutusu oldugu DOGRULANMADI.
--    Dogrulanmadan 2. satirin (sample_classification) duzeltilmesi mumkun
--    degil: isaretleme yapilir ama sisteme hic ulasmaz, kimse fark etmez.
--
--    GECMESI ICIN IKISI BIRDEN GEREKIR:
--      a) Gercek bir test gonderisiyle alan kanitlanmis ve
--         core.ayar.basitkargo_ek_bilgi_alani'na hangi JSON yoluna
--         dustugu YAZILMIS olmali,
--      b) veride o alanin dolu oldugu EN AZ BIR gonderi bulunmali.
--    (a) tek basina yetmez: yol elle yazilip veri gelmiyor olabilir.
--    (b) tek basina yetmez: dolan alan baska bir sey olabilir.
UNION ALL
-- 🔴 01.10.2026 DEGISTI, SAHIP KARARIYLA. Eski ad: basitkargo_marker_readable.
--    Kapi, gonderiye konacak NUMUNE isaretinin API'de okunabildiginin
--    kanitlanmasini bekliyordu. Sahip 29.09'da "numune isaretine gerek yok"
--    dedi; kapi boylece ARTIK HIC YAPILMAYACAK bir seyi beklemeye basladi ve
--    ROAS karar metrigini sonsuza kadar kilitliyordu.
--
--    Kapinin amaci isaret degildi: numune ile satisin birbirine karismamasi.
--    Olculdu 01.10.2026: 51 gonderinin 51'inde sinif biliniyor
--    (NUMUNE 32 · ELLE_SATIS 9 · SATIS 9 · IADE 1), sinifsiz 0. Ayrim zaten
--    baska yoldan kuruluyor. Yeni kosul dogrudan AMACI olcer.
--
--    📌 Ayrica 29.09'da olculdu: BasitKargo API'sinde ayri bir "EK BILGI"
--    alani YOK -- contentName, content.items[].name olarak donuyor; reference
--    sessizce kayboluyor. Kapi kanitlanamaz bir sey bekliyordu.
SELECT 3, 'gonderi_sinifi_biliniyor', 'P0',
       NOT EXISTS (SELECT 1 FROM mart.gonderi
                    WHERE sinif IS NULL OR sinif = 'BILINMIYOR'),
       format('%s/%s gonderinin sinifi biliniyor · %s',
              (SELECT count(*) FROM mart.gonderi
                WHERE sinif IS NOT NULL AND sinif <> 'BILINMIYOR'),
              (SELECT count(*) FROM mart.gonderi),
              coalesce((SELECT string_agg(d.sinif || ' ' || d.n, ' · ' ORDER BY d.n DESC)
                          FROM (SELECT sinif, count(*) AS n FROM mart.gonderi
                                 WHERE sinif IS NOT NULL GROUP BY sinif) d),
                       'kayit yok')),
       'mart.gonderi.sinif',
       'Numune ile satis ayrilamazsa ciro da maliyet de birbirine karisir: '
       'bedelsiz gonderi satis sayilir, kargo gideri yanlis siparise yazilir.'

-- 4 ---------------------------------------------------------------------------
-- Meta harcamasinin TAMAMI okunuyor mu? (3 hesabin 3'u)
-- 🔴 Eksik hesap harcamayi yalniz DUSUK gosterir, yani ROAS'i yalniz
--    YUKSEK gosterir. Tek yonlu sapma - bu yuzden "iyimser" degil "yanlis".
UNION ALL
SELECT 4, 'meta_spend_coverage', 'DESTEK',
       (SELECT aktif_tam FROM mart.meta_kapsama),
       -- 🔴 Ciplak yuzde yazilmaz; mart.meta_kapsama.etiket zaten neyin yuzdesi
       --    oldugunu tasir (Chief Architect terminoloji kilidi).
       (SELECT format('%s · bilinen envanter %s · kapsam disi %s (INACTIVE_EXCLUDED)',
                      etiket, bilinen_kapsama, kapsam_disi) FROM mart.meta_kapsama),
       'mart.meta_kapsama (core.meta_hesap_kayit + raw.meta_hesap)',
       'Okunmayan hesap harcamayi dusuk gosterir, ROAS''i oldugundan iyi gosterir.'

-- 5 ---------------------------------------------------------------------------
-- En cok reklam verilecek urunlerin GERCEK maliyeti girildi mi?
-- 🔴 P0 urun listesi SAHIBIN kararidir (hangi urune reklam verilecegi
--    ileriye donuk bir secim, gecmis ciro degil). Liste core.ayar'a
--    yazilabilir; yazilmadiysa son 90 gunun en cok ciro yapan 5 urunu
--    VEKIL olarak kullanilir ve detay bunu ACIKCA yazar.
UNION ALL
SELECT 5, 'cost_quality_p0', 'DESTEK',
       NOT EXISTS (
         SELECT 1 FROM mart.p0_urun p
         LEFT JOIN mart.maliyet_kalite mk ON mk.urun_id = p.urun_id
          WHERE coalesce(mk.kalite,'YOK') <> 'OLCULMUS'),
       format('%s P0 urununun %s''inde gercek maliyet var (liste: %s)',
              (SELECT count(*) FROM mart.p0_urun),
              (SELECT count(*) FROM mart.p0_urun p
                 JOIN mart.maliyet_kalite mk ON mk.urun_id = p.urun_id
                WHERE mk.kalite='OLCULMUS'),
              (SELECT max(kaynak) FROM mart.p0_urun)),
       'mart.p0_urun + mart.maliyet_kalite',
       'Maliyet tahminse marj da tahmindir; tahmini marjla reklam butcesi buyutulmez.'

-- 6 ---------------------------------------------------------------------------
-- Cevapsiz musteri mesaji kaldi mi?
-- 🔴 Atif kurulamadi ama BU olculebiliyor: cevapsiz mesaj = kacan satis.
UNION ALL
SELECT 6, 'unanswered_messages', 'DESTEK',
       NOT EXISTS (SELECT 1 FROM mart.konusma_cevapsiz WHERE bekleme_saat > 24),
       format('%s mesaj 24 saati gecti (en eskisi %s gun)',
              (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat > 24),
              (SELECT coalesce(round(max(bekleme_saat)/24.0,1),0) FROM mart.konusma_cevapsiz)),
       'mart.konusma_cevapsiz',
       'Cevaplanmamis mesaj, reklamla satin alinmis ve sonra birakilmis taleptir.'

-- 7 ---------------------------------------------------------------------------
-- Veritabaninin YEDEGI saglikli mi?
-- 🔴 Bu satiri betik doldurur: yedek dosya sisteminde ve uzak diskte
--    yasar, PostgreSQL icinden gorunmez. hazirlik-gunluk.sh once olcer,
--    core.ayar'a yazar, sonra bu view okur.
--
-- 🔴 DURUM DORT DEGERLI ve yalniz HEALTHY 'gecti' sayilir:
--      HEALTHY  = planli yerel yedek TAZE + SIFRELI uzak kopya TAZE
--                 + geri yukleme testi guncel ve basarili
--      DEGRADED = yerel var ama uzak kopya eksik/bayat/dogrulanamadi
--      FAILED   = yerel yedek yok/bayat/bos ya da geri yukleme testi basarisiz
--      UNKNOWN  = olcum hic yapilamadi
--    DEGRADED ve UNKNOWN 'gecti' DEGILDIR. "Yedek dosyasi duruyor" ile
--    "felakette geri donebiliriz" ayni cumle degil; bu satir ikincisini
--    olcer.
--
-- 🔴 ELLE ALINMIS CR DUMP'I HICBIR ZAMAN HEALTHY URETMEZ - betik yalniz
--    archive/lcarlie-n8n-*.tgz.enc desenini planli yedek sayar.
UNION ALL
SELECT 7, 'backup_health', 'DESTEK',
       coalesce((SELECT nullif(btrim(deger),'') FROM core.ayar
                  WHERE anahtar='son_yedek_durum'), 'UNKNOWN') = 'HEALTHY',
       -- 🔴 BURADA coalesce(format(...), 'yedek yok') KULLANILAMAZ.
       --    format() NULL argumanlari bos dizeye cevirir ve SONUC NULL DEGILDIR:
       --    kayit hic yokken ekrana "son yedek:  ( saat once)" yaziyordu -
       --    yani yoklugu, bos bir OLCUM gibi gosteriyordu. Yokluk ile bos
       --    deger ayni sey degil; ayrimi CASE yapar.
       CASE
         WHEN (SELECT nullif(btrim(deger),'') FROM core.ayar
                WHERE anahtar='son_yedek_notu') IS NULL
           THEN 'UNKNOWN - hazirlik-gunluk.sh hic calismadi, yedek OLCULMEDI'
         ELSE (SELECT btrim(deger) FROM core.ayar WHERE anahtar='son_yedek_notu')
       END,
       'core.ayar.son_yedek_durum + son_yedek_notu (hazirlik-gunluk.sh yazar)',
       '1 Ekim''den sonra bu veritabani ticari kaydin kendisidir; '
       'geri yuklenemeyen yedek, yedek degildir.'

-- 8 ---------------------------------------------------------------------------
-- TICARI YASAYABILIRLIK  -  architecture lesson'in hazirliga yansimasi
-- 🔴 core.mimari_ders / MEASUREMENT_COMPLETENESS_IS_NOT_COMMERCIAL_COMPLETENESS:
--    "Bir sistem ingestion · reconciliation · attribution · data quality ·
--     readiness kapilarinin HEPSINDEN gecip yine de 'para kazaniyor muyuz'
--     sorusuna cevap veremeyebilir."
--    Bu satir tam olarak o eksigi hazirligin ACIK bir boyutu yapar.
--
-- 🔴 DESTEK degil, KENDI BASINA bir boyut - ama P0 DEGIL: P0 kapisi olcum
--    TEMELIYLE ilgilidir (siniflandirma, isaret okunabilirligi, manuel giris).
--    Ticari yasayabilirlik onlarin USTUNE kurulur. P0'a eklenseydi mevcut
--    ROAS kapisinin anlamini degistirirdi - ona DOKUNULMADI.
UNION ALL
SELECT 8, 'commercial_viability', 'TICARI',
       (SELECT olculebiliyor FROM mart.ticari_yasayabilirlik),
       (SELECT left(ifade, 220) FROM mart.ticari_yasayabilirlik),
       'mart.ticari_yasayabilirlik (mart.ekonomi_ozet(30))',
       'Olcum tamligi ticari tamlik DEGILDIR. Ekonomik olarak dogrulanmamis '
       'katki uzerinden SCALE/butce artisi onerilemez.'

-- 9 ---------------------------------------------------------------------------
-- DAVRANIS / FUNNEL GORUNURLUGU  (CR-017)
-- 🔴 READY icin asgari sartlar, sahip beyanina degil OLCUME baglidir:
--      landing gozlemi · view_item · add_to_cart · checkout gorunurlugu ·
--      purchase/Wix mutabakati · source/medium · tazelik
--    Bunlarin HEPSI olculmeden READY YAZILMAZ. Bugun hicbiri ambara akmiyor.
-- 🔴 KAPI ADI 'DAVRANIS': P0'a DA, DESTEK'e DE karistirilmaz. P0 olcum
--    temelidir (siniflandirma/isaret/manuel giris); davranis gorunurlugu
--    onun USTUNE gelir ve ROAS kapisinin anlamini DEGISTIRMEZ.
UNION ALL
SELECT 9, 'behavioral_funnel_visibility', 'DAVRANIS',
       (SELECT bool_and(gozlem_durumu = 'OBSERVED') FROM mart.funnel_saglik
         WHERE adim_kod IN ('LANDING','PRODUCT_VIEW','ADD_TO_CART','BEGIN_CHECKOUT','PURCHASE')),
       (SELECT format('%s/%s funnel adimi gozleniyor · enstrumantasyon: %s · GA4 Data API: %s',
              count(*) FILTER (WHERE gozlem_durumu='OBSERVED'), count(*),
              string_agg(DISTINCT enstrumantasyon, '/'),
              CASE WHEN EXISTS (SELECT 1 FROM raw.ga4_event) THEN 'akiyor' ELSE 'BAGLI DEGIL' END)
          FROM mart.funnel_saglik),
       'mart.funnel_saglik (core.funnel_adim + raw.ga4_event)',
       'Davranis verisi olmadan huni tikanikligi OLCULEMEZ. NOT_MEASURED asla 0 sayilmaz.';

COMMENT ON VIEW mart.gunluk_hazirlik IS
  '1 Ekim oncesi gunluk hazirlik kontrolu. Ilk 3 satir (P0) gecmeden ROAS karar metrigi OLAMAZ.';

-- ---------------------------------------------------------------------------
-- ROAS KAPISI  - tek satir, tek cevap
-- ---------------------------------------------------------------------------
-- 🔴 Bu view'in TEK isi su cumleyi uretmek: "ROAS bugun karar metrigi
--    olabilir mi". Panel ve ajan bunu okur; kendi kararlarini vermezler.
CREATE VIEW mart.roas_kapisi AS
SELECT
  bool_and(gecti) FILTER (WHERE kapi = 'P0')                     AS p0_gecti,
  bool_and(gecti)                                                AS hepsi_gecti,
  count(*) FILTER (WHERE NOT gecti AND kapi = 'P0')              AS p0_eksik,
  count(*) FILTER (WHERE NOT gecti)                              AS toplam_eksik,
  coalesce(string_agg(anahtar, ', ' ORDER BY sira)
           FILTER (WHERE NOT gecti AND kapi='P0'), '')           AS p0_eksikler,
  -- 🔴 TICARI kapi DESTEK'e KARISTIRILMAZ. "Cevapsiz mesaj var" ile
  --    "para kazanip kazanmadigimizi olcemiyoruz" ayni agirlikta degil;
  --    ayni listeye konursa ikincisi birincinin yaninda kaybolur.
  coalesce(string_agg(anahtar, ', ' ORDER BY sira)
           FILTER (WHERE NOT gecti AND kapi = 'DESTEK'), '')     AS destek_eksikler,
  coalesce(string_agg(anahtar, ', ' ORDER BY sira)
           FILTER (WHERE NOT gecti AND kapi = 'TICARI'), '')     AS ticari_eksikler,
  -- 🔴 DAVRANIS kapisi da AYRI bucket: "huni gormuyoruz" ile "cevapsiz mesaj var"
  --    ayni listeye konursa ilki ikincinin yaninda kaybolur.
  coalesce(string_agg(anahtar, ', ' ORDER BY sira)
           FILTER (WHERE NOT gecti AND kapi = 'DAVRANIS'), '')   AS davranis_eksikler,
  coalesce(bool_and(gecti) FILTER (WHERE kapi = 'TICARI'), false) AS ticari_gecti,
  -- 🔴 SCALE KAPISI, ROAS KAPISINDAN AYRIDIR ve EK bir kosuldur.
  --    ROAS "yorumlanabilir mi" der; bu "butce buyutulebilir mi" der.
  --    Ikisi de acik olmadan scale onerilemez.
  (coalesce(bool_and(gecti) FILTER (WHERE kapi = 'P0'), false)
   AND coalesce((SELECT scale_konusulabilir FROM mart.ticari_yasayabilirlik), false))
                                                                 AS scale_konusulabilir,
  -- 🔴 Karar cumlesi burada uretilir ki panel, ajan ve rapor AYNI cumleyi
  --    okusun. Uc yerde uc esik = uc farkli gercek.
  CASE
    WHEN bool_and(gecti) FILTER (WHERE kapi = 'P0')
      THEN 'ROAS_KARAR_METRIGI_OLABILIR'
    ELSE 'ROAS_KARAR_METRIGI_OLAMAZ'
  END                                                            AS karar,
  CASE
    WHEN bool_and(gecti) FILTER (WHERE kapi = 'P0')
      THEN 'P0 kapisi acik. ROAS yorumlanabilir; yine de eksik hesap/maliyet varsa yon bellidir.'
    ELSE 'P0 kapisi KAPALI. 1 Ekim gelse bile ROAS karar metrigi yapilmaz: '
         'cikan sayinin hangi yone yanlis oldugu bilinemez.'
  END                                                            AS gerekce
FROM mart.gunluk_hazirlik;

COMMENT ON VIEW mart.roas_kapisi IS
  'Tek cevap: ROAS bugun karar metrigi olabilir mi. Panel, ajan ve rapor AYNI cumleyi bundan okur.';

COMMIT;
