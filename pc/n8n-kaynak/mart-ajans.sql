-- =============================================================================
-- L'CARLIE - AJANS MODUL SINYALLERI  (CR-014)
--
-- 🔴 TURKCE METIN ESLESTIRME KURALI - TEK STANDART: core.tr_norm()
--
--    Olculdu (16.09.2026): PostgreSQL'de `~*` Turkce noktali I'yi kucuk i'ye
--    ESLEMEZ -> 'İçindekiler' ~* 'içindeki' = FALSE. Ayrica collation
--    en_US.utf8 oldugu icin NOKTASIZ ı hicbir yolla eslesmiyordu
--    ('IŞIK' ILIKE '%ışık%' = FALSE).
--
--    KURAL: Turkce metin siniflandirmasinda `~*` KULLANILMAZ.
--    Hem mesaj hem kalip core.tr_norm()'dan gecirilir:
--        core.tr_norm(m.metin) LIKE '%' || 'icindeki' || '%'
--    tr_norm: İ/I/ı->i, Ç/ç->c, Ğ/ğ->g, Ö/ö->o, Ş/ş->s, Ü/ü->u, sonra lower().
--    Orijinal mesaj ASLA degistirilmez; normalizasyon yalniz sorgu aninda.
--
--    ESKI "I harfini kaliptan disarida birak" numarasi TERK EDILDI:
--    calisiyordu ama kalibi yazan kisinin her seferinde tuzagi hatirlamasini
--    gerektiriyordu - yani ilk unutan hatayi geri getirirdi.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.soru_konu_semantik CASCADE;
DROP VIEW IF EXISTS mart.soru_konu       CASCADE;
DROP VIEW IF EXISTS mart.red_team        CASCADE;
DROP VIEW IF EXISTS mart.kreatif_hipotez CASCADE;
DROP VIEW IF EXISTS mart.pazar_sinyal    CASCADE;
DROP VIEW IF EXISTS mart.cro_sinyal      CASCADE;
DROP VIEW IF EXISTS mart.meta_sinyal     CASCADE;
DROP VIEW IF EXISTS mart.urun_sinyal     CASCADE;
DROP VIEW IF EXISTS mart.kanit_kalitesi  CASCADE;

-- ===========================================================================
-- KANIT KALITESI  -  DETERMINISTIK, MODELIN KANAATI DEGIL
-- ===========================================================================
-- 🔴 "%87 guven" YAZILMAZ. Puan alti olculebilir faktorden turer,
--    her biri 0/1/2. Toplam 0-12 -> LOW / MEDIUM / HIGH.
CREATE VIEW mart.kanit_kalitesi AS
WITH f AS (
  SELECT
    -- 1) KAPSAMA: kac kaynak gercekten bagli
    -- 🔴 OPSIYONEL MUTABAKAT ACIKLARI PAYDAYA GIRMEZ (16.09.2026).
    --    settlement_reconciliation (PayTR) operasyonu ENGELLEMEYEN bir
    --    dogrulama katmanidir; paydaya konursa "bagli olmayan kaynak" gibi
    --    sayilir ve kanit kalitesini GERCEK OLMAYAN bir eksikle asagi ceker.
    --    Ayni sebeple MANUAL_CONTROLLED_INPUT de "kopuk kaynak" degildir -
    --    ama TAMAMLANMIS da degildir, o yuzden paydada kalir ve paya girmez.
    (SELECT CASE WHEN count(*) FILTER (WHERE current_connection='CONNECTED') * 3
                      >= count(*) THEN 2
                 WHEN count(*) FILTER (WHERE current_connection='CONNECTED') > 0 THEN 1
                 ELSE 0 END
       FROM core.source_authority
      WHERE current_connection <> 'OPTIONAL_RECONCILIATION_GAP')          AS kapsama,
    -- 2) ORNEKLEM: son 30 gunde siparis adedi
    (SELECT CASE WHEN coalesce(sum(siparis),0) >= 30 THEN 2
                 WHEN coalesce(sum(siparis),0) >= 10 THEN 1 ELSE 0 END
       FROM mart.nakit_gunluk WHERE gun > current_date-30)                AS orneklem,
    -- 3) TAZELIK: ETL son 30 saat icinde calisti mi
    (SELECT CASE WHEN min(son) > now() - interval '30 hours' THEN 2
                 WHEN min(son) > now() - interval '72 hours' THEN 1 ELSE 0 END
       FROM (SELECT max(bitis) AS son FROM raw.yukleme_log GROUP BY kaynak) t) AS tazelik,
    -- 4) KAYNAK OTORITESI: siparis/odeme OPERASYONEL otoritesi kurulu mu
    -- 🔴 YENIDEN TANIMLANDI (16.09.2026, operating truth duzeltmesi).
    --    ESKI HALI: payment_online VE payment_offline'in CONNECTED olmasini
    --    ariyordu. Ikisi de degildi, puan 0 cikiyordu ve bu 0, HARD-CAP
    --    uzerinden kanit kalitesini LOW'a cakiliyordu.
    --    Ama sifirin sebebi GERCEK DEGILDI:
    --      - payment_online "bagli degil" sayiliyordu cunku PayTR API'si yok.
    --        Oysa PayTR ayri bir kanal degil, Wix checkout'unun odeme
    --        saglayicisi. Siparis ve odeme OPERASYONEL durumu Wix'ten
    --        biliniyor. Eksik olan settlement mutabakati - ayri satirda.
    --      - payment_offline "kaynak yok" sayiliyordu. Oysa kaynak belli:
    --        INSAN GIRISI. Eksik olan kaynak degil, henuz baslamamis GIRIS.
    --
    --    YENI OLCU: siparis + odeme operasyonel otoritesi bagli mi, ve
    --    manuel giris sureci FIILEN URETIYOR mu.
    -- 🔴 2 PUAN SAHIP BEYANIYLA ALINMAZ: manuel surecin var olmasi yetmez,
    --    son 30 gunde gercekten kayit girilmis olmasi gerekir. Olcum
    --    1 Ekim'de basliyor; bugun bu yuzden 1'dir, 2 degil.
    (SELECT CASE
              -- Siparis ve odeme operasyonel otoritesi bagli degilse 0.
              WHEN count(*) FILTER (WHERE alan IN ('order','payment_online')
                                      AND current_connection='CONNECTED') < 2
                THEN 0
              -- 2 puan yalnizca manuel giris sureci FIILEN ISLIYORSA:
              -- olcum baslamis VE sisteme girilmemis elle satis kalmamis.
              WHEN now() >= mart.kesim()
                   AND NOT EXISTS (SELECT 1 FROM mart.gonderi
                                    WHERE olcumde AND sinif='ELLE_SATIS')
                THEN 2
              -- Otorite bagli ama manuel giris henuz kanitlanmadi -> 1.
              ELSE 1
            END FROM core.source_authority)                               AS otorite,
    -- 5) TUTARLILIK: mutabakat gecti mi (view uzerinden dolayli: celiskili
    --    satir sayisi). Burada siparis/kalem tutarliligi ornek alinir.
    (SELECT CASE WHEN count(*) = 0 THEN 2 ELSE 0 END
       FROM (SELECT w.siparis_id FROM raw.wix_order w
               JOIN raw.wix_order_item i ON i.siparis_id=w.siparis_id
              GROUP BY w.siparis_id, w.toplam
             HAVING round(sum(i.net_toplam),2) <> round(w.toplam,2)) x)   AS tutarlilik,
    -- 6) EKSIKLIK: kac kalem MISSING
    (SELECT CASE WHEN count(*) FILTER (WHERE durum='MISSING') = 0 THEN 2
                 WHEN count(*) FILTER (WHERE durum='MISSING') <= 3 THEN 1
                 ELSE 0 END FROM mart.nakit_veri_kalitesi)                AS eksiklik
)
-- 🔴 HARD-CAP (CR-015 pre-flight bulgusu).
--    Onceki surum SADECE TOPLAMA bakiyordu: orneklem=0, otorite=0,
--    eksiklik=0 iken puan 6 cikiyor ve sinif MEDIUM yaziliyordu.
--    Yani "ornekleminiz yok, odeme otoriteniz yok, 7 kalem eksik" olan bir
--    kanit "orta kalite" diye sunuluyordu. Toplam, eksik boyutu digerlerinin
--    yuksek puaniyla GIZLIYORDU.
--
--    KRITIK BOYUTLAR: orneklem · otorite · eksiklik
--    Bunlar olmadan kanit kalitesi yukari cikamaz:
--      >=2 kritik boyut 0  -> LOW   (toplam ne olursa olsun)
--       1 kritik boyut 0   -> en fazla MEDIUM (HIGH imkansiz)
--       0 kritik boyut 0   -> normal esik (>=9 HIGH, >=5 MEDIUM)
, k AS (
  SELECT f.*,
         (CASE WHEN orneklem=0 THEN 1 ELSE 0 END
        + CASE WHEN otorite =0 THEN 1 ELSE 0 END
        + CASE WHEN eksiklik=0 THEN 1 ELSE 0 END) AS kritik_sifir,
         (kapsama+orneklem+tazelik+otorite+tutarlilik+eksiklik) AS puan
    FROM f
)
SELECT kapsama, orneklem, tazelik, otorite, tutarlilik, eksiklik, puan,
       kritik_sifir,
       CASE
         WHEN kritik_sifir >= 2 THEN 'LOW'
         WHEN kritik_sifir  = 1 THEN CASE WHEN puan >= 5 THEN 'MEDIUM' ELSE 'LOW' END
         WHEN puan >= 9        THEN 'HIGH'
         WHEN puan >= 5        THEN 'MEDIUM'
         ELSE 'LOW'
       END AS sinif,
       -- 🔴 Hard-cap uygulandiysa NEDENI YAZILIR; sessizce dusurmek,
       --    sessizce yukseltmek kadar kotu olurdu.
       CASE
         WHEN kritik_sifir >= 2 THEN
           format('HARD-CAP: %s kritik boyut sifir (%s) -> puan %s olsa da LOW',
                  kritik_sifir,
                  concat_ws(', ', CASE WHEN orneklem=0 THEN 'orneklem' END,
                                  CASE WHEN otorite =0 THEN 'kaynak_otoritesi' END,
                                  CASE WHEN eksiklik=0 THEN 'eksik_veri' END),
                  puan)
         WHEN kritik_sifir = 1 THEN
           format('HARD-CAP: %s sifir -> HIGH imkansiz',
                  concat_ws('', CASE WHEN orneklem=0 THEN 'orneklem' END,
                                CASE WHEN otorite =0 THEN 'kaynak_otoritesi' END,
                                CASE WHEN eksiklik=0 THEN 'eksik_veri' END))
         ELSE 'hard-cap yok'
       END AS hard_cap_nedeni
  FROM k;

COMMENT ON VIEW mart.kanit_kalitesi IS
  'Deterministik kanit kalitesi. 6 faktor x 0-2 puan + KRITIK BOYUT HARD-CAP. '
  'orneklem/otorite/eksiklik sifirsa toplam yuksek olsa bile sinif dusurulur.';

-- ===========================================================================
-- A) META PERFORMANCE
-- ===========================================================================
-- 🔴 KREATIF SEVIYESI VERI YOK: raw.meta_harcama yalniz kampanya
--    seviyesinde. "Su kreatif kazandi" CIKARIMI YAPILAMAZ ve yapilmaz.
CREATE VIEW mart.meta_sinyal AS
WITH p AS (
  SELECT 7  AS pencere, * FROM mart.nakit_ozet(7)
  UNION ALL
  SELECT 30 AS pencere, * FROM mart.nakit_ozet(30)
)
SELECT p.pencere,
       p.meta_harcama                          AS harcama,
       p.meta_kapsama                          AS hesap_kapsamasi,
       (SELECT sum(gosterim) FROM raw.meta_harcama
         WHERE kampanya_id<>'_HESAP' AND gun > current_date - p.pencere)  AS gosterim,
       (SELECT sum(link_tiklama) FROM raw.meta_harcama
         WHERE kampanya_id<>'_HESAP' AND gun > current_date - p.pencere)  AS link_tiklama,
       (SELECT count(DISTINCT kampanya_id) FROM raw.meta_harcama
         WHERE kampanya_id<>'_HESAP' AND gun > current_date - p.pencere)  AS kampanya,
       -- Meta'nin KENDI donusum iddiasi - bizim ciromuzla TOPLANMAZ
       (SELECT coalesce(sum(meta_donusum_degeri),0) FROM raw.meta_harcama
         WHERE kampanya_id<>'_HESAP' AND gun > current_date - p.pencere)  AS meta_iddia_gelir,
       p.net_ciro,
       p.ciro_harcama_orani,
       p.harcamali_satissiz_gun,
       p.nakit_durum,
       -- 🔴 Kreatif verisi durumu HER SATIRDA yazili - unutulmasin diye.
       'NOT_CONNECTED'                         AS kreatif_seviyesi_veri
  FROM p;

COMMENT ON VIEW mart.meta_sinyal IS
  'Meta performansi. Hesap kapsamasi 1/3 ve kreatif verisi YOK - her satirda yazili.';

-- ===========================================================================
-- B) URUN / TEKLIF STRATEJISI
-- ===========================================================================
-- 🔴 SINIFLANDIRMA SIRALI VE DETERMINISTIK.
--    En onemlisi: huni zarar ederken hicbir urun SCALE_CANDIDATE olamaz.
--    Reklam atfedilemedigi icin "bu urun reklamla kazaniyor" DENEMEZ;
--    yalnizca brut katki ve hacim konusulur.
CREATE VIEW mart.urun_sinyal AS
WITH satis AS (
  SELECT k.urun_id,
         coalesce(u.ad, k.urun_adi)                      AS urun_adi,
         sum(k.adet)                                     AS adet,
         sum(k.satir_ciro_net)                           AS ciro_net,
         sum(k.satir_maliyet)                            AS cogs,
         sum(k.brut_marj)                                AS brut_marj,
         count(DISTINCT k.siparis_id)                    AS siparis,
         max(k.gun)                                      AS son_satis
    FROM mart.siparis_kalem k
    JOIN raw.wix_order w ON w.siparis_id = k.siparis_id
    LEFT JOIN raw.wix_urun u ON u.urun_id = k.urun_id
   WHERE (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date - 30
     AND w.teslimat_durumu IS DISTINCT FROM 'CANCELED'
   GROUP BY 1,2
), genel AS (
  SELECT nakit_durum FROM mart.nakit_ozet(30)
), kal AS (
  SELECT urun_id, kalite FROM mart.maliyet_kalite
)
-- 🔴 adet numeric(12,3) geliyor ("8.000"); rapor icin tam sayiya yuvarlanir.
--    Kesirli adet satilmiyor - ondalik gosterim okuru yaniltiyor.
SELECT s.urun_id, s.urun_adi, round(s.adet)::int AS adet, s.siparis,
       round(s.ciro_net,2)  AS ciro_net,
       round(s.cogs,2)      AS cogs,
       round(s.brut_marj,2) AS brut_marj,
       round(100.0*s.brut_marj/nullif(s.ciro_net,0),1) AS brut_marj_yuzde,
       coalesce(kal.kalite,'YOK') AS maliyet_kalitesi,
       s.son_satis,
       CASE
         -- 1) Hacim yoksa hicbir sey soylenemez.
         WHEN s.adet < 3                       THEN 'INSUFFICIENT_DATA'
         -- 2) 🔴 HUNI ZARARDAYKEN SCALE YOK. Guardrail CRITICAL ise urun
         --    ne kadar iyi gorunurse gorunsun once huni duzelmeli.
         WHEN (SELECT nakit_durum FROM genel) = 'CRITICAL'
                                               THEN 'FIX_FUNNEL_FIRST'
         -- 3) Maliyet olculmemisse SCALE denemez - marj tahmine dayaniyor.
         WHEN coalesce(kal.kalite,'YOK') <> 'OLCULMUS'
                                               THEN 'TEST_SMALL'
         WHEN s.brut_marj > 0                  THEN 'SCALE_CANDIDATE'
         ELSE 'HOLD'
       END AS sinif,
       -- 🔴 Her sinifin GEREKCESI satirda durur; brief'te tekrar yazilmaz.
       CASE
         WHEN s.adet < 3 THEN format('yalniz %s adet - istatistik degil, gozlem', round(s.adet)::int)
         WHEN (SELECT nakit_durum FROM genel) = 'CRITICAL'
           THEN 'son 30 gun nakit durumu CRITICAL: reklam harcamasi net ciroyu asiyor'
         WHEN coalesce(kal.kalite,'YOK') <> 'OLCULMUS'
           THEN 'urun maliyeti olculmemis (sahip tahmini) - marj dogrulanamaz'
         ELSE 'brut katki pozitif ve maliyet olculmus'
       END AS gerekce
  FROM satis s LEFT JOIN kal ON kal.urun_id = s.urun_id
 ORDER BY s.ciro_net DESC NULLS LAST;

COMMENT ON VIEW mart.urun_sinyal IS
  'Urun/teklif sinyali. Huni CRITICAL iken hicbir urun SCALE_CANDIDATE olamaz.';

-- ===========================================================================
-- C) KREATIF ZEKA  -  HIPOTEZ, KAZANAN DEGIL
-- ===========================================================================
-- 🔴 KREATIF PERFORMANS VERISI YOK -> SIRALAMA YAPILMAZ.
--    Asagidakiler MUSTERININ KENDI MESAJLARINDAN olculmus hipotezlerdir;
--    "kazanan kreatif" degil, "test edilecek varsayim"dir.
--    Olcum (16.09.2026): 259 konusmanin 125'i icerik, 124'u fiyat soruyor.
-- ===========================================================================
-- MUSTERI SORU KONULARI  -  kategoriler VERIDEN turetildi
-- ===========================================================================
-- 🔴 KATEGORI UYDURULMADI.  Once ham dagilima bakildi (16.09.2026), sonra
--    YALNIZ gercekten gorulen konular kategori yapildi. Ornek liste
--    onerilmisti ama su konular veride HIC YOK ve kategori ACILMADI:
--      kargo · teslimat · iade · odeme · kapida odeme · gizlilik/paket
--    (hepsi 0 konusma). Var olmayan kategoriyi bos gostermek, "bu konu
--    sorulmuyor" ile "biz bakmadik"i karistirir.
--
-- 🔴 OLCUM YONTEMI: core.tr_norm iki tarafa da uygulanir (mesaj + kalip).
--    ~* KULLANILMAZ - Turkce I'yi eslemiyor (bkz. dosya basi).
--
-- 🔴 KONUSMA ve MESAJ AYRI sayilir. Bir konusmada ayni soru 2 kez gecerse
--    mesaj 2, konusma 1'dir. Kreatif kanita YALNIZ konusma sayisi girer.
--
-- 🔴 Konular ORTUSEBILIR (bir konusma hem fiyat hem icerik sorabilir);
--    yuzdeler bu yuzden toplanip 100 etmez ve oyle sunulmaz.
CREATE VIEW mart.soru_konu AS
WITH kalip AS (
  SELECT * FROM (VALUES
    ('ICERIK',     ARRAY['icindeki','icinde ne','icerik','formul'],      'Urunun icinde ne var'),
    ('FIYAT',      ARRAY['fiyat','ne kadar','kac para','ucret'],         'Fiyat'),
    ('SIPARIS_YOLU',ARRAY['siparis','nasil alin','nereden al'],          'Nasil siparis verilir'),
    ('ETKI_FAYDA', ARRAY['ne ise','fayda','etki','ise yar'],             'Ne ise yarar / faydasi'),
    ('KULLANIM',   ARRAY['nasil kullan','nereye','ne kadar sur','gunde'],'Nasil kullanilir'),
    ('GUVENLIK',   ARRAY['yan etki','alerj','zararl','guvenl'],          'Yan etki / guvenlik'),
    ('SELAMLAMA',  ARRAY['merhaba','selam','tesekkur','sagol'],          'Selamlasma / tesekkur')
  ) AS t(konu, kaliplar, aciklama)
), esles AS (
  SELECT k.konu, k.aciklama, m.konusma_id, m.metin
    FROM lcarlie.mesaj m
    JOIN kalip k ON EXISTS (
      SELECT 1 FROM unnest(k.kaliplar) p
       WHERE core.tr_norm(m.metin) LIKE '%' || p || '%')
   WHERE m.yon = 'gelen'
), toplam AS (SELECT count(*)::numeric AS konusma FROM lcarlie.konusma)
SELECT e.konu,
       max(e.aciklama)                                   AS aciklama,
       count(DISTINCT e.konusma_id)                      AS distinct_konusma,
       count(*)                                          AS eslesen_mesaj,
       round(100.0*count(DISTINCT e.konusma_id)/(SELECT konusma FROM toplam)) AS konusma_yuzde,
       -- 🔴 ORNEK MESAJ PII MASKELENEREK verilir; ham mesaj brief'e GIRMEZ.
       (array_agg(DISTINCT left(core.pii_maskele(btrim(e.metin)),56)))[1:3]   AS ornekler,
       'tr_norm + LIKE (her iki taraf normalize)'        AS olcum_yontemi,
       true                                              AS normalize_edildi,
       'v2-2026-09-16'                                   AS sorgu_surumu
  FROM esles e GROUP BY e.konu

UNION ALL
-- 🔴 SINIFLANDIRILAMAYAN KONUSMALAR GIZLENMEZ. "Diger" bos degil,
--    olculmus bir artiktir; buyukse kategoriler eksik demektir.
SELECT 'DIGER', 'Hicbir konuya girmeyen musteri mesaji',
       count(DISTINCT m.konusma_id), count(*),
       round(100.0*count(DISTINCT m.konusma_id)/(SELECT konusma FROM toplam)),
       (array_agg(DISTINCT left(core.pii_maskele(btrim(m.metin)),56)))[1:3],
       'tr_norm + LIKE (her iki taraf normalize)', true, 'v2-2026-09-16'
  FROM lcarlie.mesaj m
 WHERE m.yon='gelen' AND btrim(m.metin) <> ''
   AND NOT EXISTS (SELECT 1 FROM kalip k, unnest(k.kaliplar) p
                    WHERE core.tr_norm(m.metin) LIKE '%' || p || '%');

COMMENT ON VIEW mart.soru_konu IS
  'Musteri soru konulari. MULTI_LABEL: bir konusma birden fazla konuya girebilir. '
  'Yuzdeler toplanmaz (toplam %100''u asar). Payda = TUM konusmalar. PII maskeli.';

-- ---------------------------------------------------------------------------
-- ETIKETLEME SEMANTIGI  -  MULTI_LABEL oldugu ACIKCA yazilir
-- ---------------------------------------------------------------------------
-- 🔴 CR-015 pre-flight bulgusu: kategori sayilarinin toplami 385, tekil
--    konusma 259 -> oranlar toplami %149. Yapinin MULTI_LABEL oldugu
--    hicbir yerde YAZILI DEGILDI; okuyan yuzdeleri toplayip "%149 nasil
--    olur" diye dusunebilir ya da daha kotusu "share of classified" diye
--    yanlis bir oran turetebilirdi.
--
-- 🔴 "SHARE OF CLASSIFIED" URETILMEZ.  Etiketler ortustugu icin
--    kategori/toplam_etiket gibi bir oran anlamsizdir ve bilerek yok.
CREATE VIEW mart.soru_konu_semantik AS
WITH etiket AS (
  SELECT m.konusma_id,
         count(DISTINCT k.konu) AS etiket_sayisi
    FROM lcarlie.mesaj m
    JOIN (VALUES
      ('ICERIK',     ARRAY['icindeki','icinde ne','icerik','formul']),
      ('FIYAT',      ARRAY['fiyat','ne kadar','kac para','ucret']),
      ('SIPARIS_YOLU',ARRAY['siparis','nasil alin','nereden al']),
      ('ETKI_FAYDA', ARRAY['ne ise','fayda','etki','ise yar']),
      ('KULLANIM',   ARRAY['nasil kullan','nereye','ne kadar sur','gunde']),
      ('GUVENLIK',   ARRAY['yan etki','alerj','zararl','guvenl']),
      ('SELAMLAMA',  ARRAY['merhaba','selam','tesekkur','sagol'])
    ) AS k(konu, kaliplar)
      ON EXISTS (SELECT 1 FROM unnest(k.kaliplar) p
                  WHERE core.tr_norm(m.metin) LIKE '%'||p||'%')
   WHERE m.yon='gelen'
   GROUP BY m.konusma_id
)
SELECT 'MULTI_LABEL'::text                                   AS etiketleme,
       (SELECT count(*) FROM lcarlie.konusma)                AS payda_tum_konusma,
       (SELECT count(*) FROM etiket)                         AS etiketli_konusma,
       (SELECT count(*) FROM lcarlie.konusma)
         - (SELECT count(*) FROM etiket)                     AS etiketsiz_konusma,
       (SELECT count(*) FROM etiket WHERE etiket_sayisi >= 2) AS overlap_count,
       (SELECT round(avg(etiket_sayisi),2) FROM etiket)      AS ortalama_etiket,
       (SELECT max(etiket_sayisi) FROM etiket)               AS en_cok_etiket,
       (SELECT sum(distinct_konusma) FROM mart.soru_konu WHERE konu <> 'DIGER')
                                                             AS etiket_sayilari_toplami,
       'Yuzdeler TOPLANMAZ; payda TUM konusmalardir. share-of-classified URETILMEZ.'::text
                                                             AS uyari;

COMMENT ON VIEW mart.soru_konu_semantik IS
  'Etiketleme MULTI_LABEL. overlap_count = 2+ etiketli konusma. '
  'Yuzdelerin toplami %100''u asar ve bu bir hata DEGILDIR.';

-- 🔴 HER HIPOTEZ KENDI SAYISINI TASIR, ortak sablon YOK.
--    Ilk surumde tek bir format() ucune de AYNI argumanlari geciriyordu:
--    ucu de "%83 (216/259)" diyordu ve "konusmalarin %83'u siparis nasil
--    verilir soruyor" gibi YANLIS bir cumle uretiyordu (gercegi 28/259).
--    Kanit sayisi hipoteze ait olmali; ortak sayi paylasmak uydurma kanittir.
-- 🔴 SAYILAR ARTIK mart.soru_konu'DAN GELIR (tr_norm ile olculmus,
--    konusma seviyesinde tekil). Onceki surumde kalip "I harfini disarida
--    birak" numarasiyla yaziliydi - calisiyordu ama kirilgandi: kalibi
--    yazan kisinin her seferinde bu tuzagi hatirlamasi gerekiyordu.
CREATE VIEW mart.kreatif_hipotez AS
WITH s AS (
  SELECT (SELECT distinct_konusma FROM mart.soru_konu WHERE konu='ICERIK')       AS icerik,
         (SELECT distinct_konusma FROM mart.soru_konu WHERE konu='FIYAT')        AS fiyat,
         (SELECT distinct_konusma FROM mart.soru_konu WHERE konu='SIPARIS_YOLU') AS siparis_yolu,
         (SELECT eslesen_mesaj    FROM mart.soru_konu WHERE konu='ICERIK')       AS icerik_mesaj,
         (SELECT eslesen_mesaj    FROM mart.soru_konu WHERE konu='FIYAT')        AS fiyat_mesaj,
         (SELECT eslesen_mesaj    FROM mart.soru_konu WHERE konu='SIPARIS_YOLU') AS siparis_mesaj,
         (SELECT count(*) FROM lcarlie.konusma)                                  AS toplam
)
SELECT h.kod, h.hipotez, h.kanit, h.adet, h.mesaj, s.toplam,
       round(100.0*h.adet/nullif(s.toplam,0)) AS yuzde,
       h.kanit_kaynagi, h.beklenen_etki, h.risk, h.yanlislama,
       'tr_norm + LIKE (konusma seviyesinde tekil)' AS olcum_yontemi,
       true                                         AS normalize_edildi,
       'v2-2026-09-16'                              AS sorgu_surumu
  FROM s, LATERAL (VALUES
  ('ICERIK_SEFFAFLIGI',
   'Reklam/sayfa icerik listesini ONDE gostersin',
   'musterinin kendi sorusu: "icindekiler nelerdir" / "icinde ne var"',
   s.icerik, s.icerik_mesaj,
   'mesaj sorusu',
   'konusma hacmi duser, kalan konusmalar daha yuksek niyetli olur',
   'Konusma sayisi dusunce reklam performansi dusmus SANILABILIR - onlem: konusma degil SIPARIS olcusune bak',
   'Icerik listesi one alindiktan sonra ayni soru orani DUSMEZSE hipotez curur'),
  ('FIYAT_SEFFAFLIGI',
   'Fiyat reklamda/sayfada acikca gorunsun',
   'musterinin kendi sorusu: "fiyati nedir"',
   s.fiyat, s.fiyat_mesaj,
   'mesaj sorusu',
   'fiyat itirazi konusmadan ONCE elenir, cevapsiz mesaj yuku azalir',
   'Dusuk fiyat algisi rekabeti tetikleyebilir; ayrica 1.200 TL''ye inen fiyat birim katkiyi yariya indiriyor',
   'Fiyat gosterildikten sonra soru orani ve cevapsiz mesaj sayisi DUSMEZSE hipotez curur'),
  ('SIPARIS_YOLU',
   'Siparis adimi tek tikla ulasilir olsun',
   'musterinin kendi sorusu: "siparis nasil verilir"',
   s.siparis_yolu, s.siparis_mesaj,
   'mesaj sorusu',
   'konusmadan siparise gecis kolaylasir',
   'Mesajlasma tamamen kesilirse musteri sorusunu hic sormayip vazgecebilir',
   'Siparis yolu sadelestikten sonra bu soru surerse hipotez curur')
) AS h(kod, hipotez, kanit, adet, mesaj, kanit_kaynagi, beklenen_etki, risk, yanlislama);

COMMENT ON VIEW mart.kreatif_hipotez IS
  'Kreatif HIPOTEZLERI - musteri mesajlarindan turetilmis. Kazanan kreatif DEGIL; performans verisi YOK.';

-- ===========================================================================
-- D) CRO / LANDING PAGE
-- ===========================================================================
-- 🔴 GA4 BAGLI DEGIL -> davranis verisi YOKTUR. Asagidaki satirlar
--    OBSERVED (siparis/odeme verisinden), INFERRED (mantiksal cikarim) ve
--    HYPOTHESIS (test edilmemis) olarak ETIKETLENIR. Karistirilmaz.
CREATE VIEW mart.cro_sinyal AS
SELECT 'ODEME_TAMAMLANMAMA' AS kod, 'OBSERVED' AS seviye,
       format('%s siparis NOT_PAID durumunda (%s TL net) - odeme adimi tamamlanmiyor',
              (SELECT count(*) FROM raw.wix_order
                WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date-30
                  AND odeme_durumu='NOT_PAID' AND teslimat_durumu IS DISTINCT FROM 'CANCELED'),
              (SELECT to_char(coalesce(sum(toplam-kdv),0),'FM999990.00') FROM raw.wix_order
                WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date-30
                  AND odeme_durumu='NOT_PAID' AND teslimat_durumu IS DISTINCT FROM 'CANCELED')) AS bulgu,
       'Wix siparis kaydi' AS kaynak
UNION ALL
SELECT 'IPTAL_ORANI', 'OBSERVED',
       format('Son 30 gunde %s siparis IPTAL (%s TL net) - odenmeyen siparisler iptale donuyor',
              (SELECT count(*) FROM raw.wix_order
                WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date-30
                  AND teslimat_durumu='CANCELED'),
              (SELECT to_char(coalesce(sum(toplam-kdv),0),'FM999990.00') FROM raw.wix_order
                WHERE (olusturma AT TIME ZONE 'Europe/Istanbul')::date > current_date-30
                  AND teslimat_durumu='CANCELED')),
       'Wix siparis kaydi'
UNION ALL
-- 🔴 IFADE DUZELTILDI (16.09.2026). Eski hali "online odeme akisi tercih
--    EDILMIYOR ya da calismiyor" diyordu - bu bir OLCUM degil, iki ayri
--    NEDEN TAHMINIYDI ve OBSERVED etiketi tasiyordu. Olculen tek sey:
--    siparislerin ne kadarinin odeme yontemi PayTR (yani Wix checkout)
--    DISINDA. Bu, kapida odeme ve havale/telefon siparisi demektir;
--    "online odeme calismiyor" sonucunu vermez - PayTR ile odenen
--    siparisler sorunsuz akiyor.
SELECT 'CEVRIM_DISI_AGIRLIK', 'OBSERVED',
       format('Siparislerin %s''inin odeme yontemi Wix checkout (PayTR) DISINDA: '
              'kapida odeme / havale / telefon. Bu satislarin tahsilati sistemde '
              'insan girisiyle tamamlanir (MANUAL_CONTROLLED_INPUT). '
              'NEDEN SOYLENMEZ: tercih mi zorunluluk mu oldugu OLCULMEDI.',
              (SELECT round(100.0*count(*) FILTER (WHERE odeme_yontemi IS DISTINCT FROM 'PayTR')
                            /nullif(count(*),0))::text||'%' FROM raw.wix_order)),
       'Wix odeme yontemi (PayTR = Wix checkout saglayicisi, ayri kanal DEGIL)'
UNION ALL
SELECT 'SORU_YUKU', 'INFERRED',
       format('Konusmalarin buyuk kismi icerik/fiyat soruyor; bu bilgiler sayfada bulunsaydi konusma gerekmezdi (%s konusma)',
              (SELECT count(DISTINCT konusma_id) FROM lcarlie.mesaj
                WHERE yon='gelen' AND (metin ILIKE '%çindekiler%' OR metin ILIKE '%iyat%'))),
       'lcarlie.mesaj - dolayli cikarim'
UNION ALL
SELECT 'DAVRANIS_VERISI', 'NOT_CONNECTED',
       'GA4/GTM verisi ambara AKMIYOR - sayfa gorunumu, sepet terk orani, huni adimlari OLCULEMIYOR',
       'core.source_authority.behavior'
UNION ALL
SELECT 'SAYFA_HIZI', 'HYPOTHESIS',
       'Sayfa hizinin donusume etkisi bu sistemde olculmedi; iyilestirme onerisi kanit gerektirir',
       'test edilmemis';

COMMENT ON VIEW mart.cro_sinyal IS
  'CRO bulgulari. GA4 bagli degil - davranis verisi YOK. Her satir OBSERVED/INFERRED/HYPOTHESIS/NOT_CONNECTED.';

-- ===========================================================================
-- E) PAZAR / HEDEF KITLE / RAKIP
-- ===========================================================================
-- 🔴 DIS ARASTIRMA BAGLANTISI YOK. Uydurma pazar verisi URETILMEZ.
CREATE VIEW mart.pazar_sinyal AS
SELECT 'RAKIP_IZLEME'   AS kod, 'NOT_CONNECTED' AS seviye,
       'Rakip reklam/fiyat izleme kaynagi bagli degil' AS bulgu,
       'MANUAL_RESEARCH_REQUIRED' AS durum
UNION ALL
SELECT 'PAZAR_BUYUKLUGU','NOT_CONNECTED',
       'Kategori/pazar verisi kaynagi bagli degil','MANUAL_RESEARCH_REQUIRED'
UNION ALL
SELECT 'ARAMA_TALEBI','NOT_CONNECTED',
       'Arama hacmi / SEO veri kaynagi bagli degil','MANUAL_RESEARCH_REQUIRED'
UNION ALL
-- 🔴 IC KANIT ile DIS ARASTIRMA ayri tutulur; bu satir ICERIDEN gelir.
SELECT 'IC_TALEP_SINYALI','OBSERVED',
       format('Ic veri: %s konusma, %s tekil musteri, en sik iki soru icerik ve fiyat',
              (SELECT count(*) FROM lcarlie.konusma),
              (SELECT count(*) FROM core.customer)),
       'INTERNAL_EVIDENCE'
UNION ALL
SELECT 'KANAL_DAGILIMI','OBSERVED',
       format('Konusmalarin tamami messenger (%s/%s); Instagram ve WhatsApp ambara akmiyor',
              (SELECT count(*) FROM lcarlie.konusma WHERE kanal='messenger'),
              (SELECT count(*) FROM lcarlie.konusma)),
       'INTERNAL_EVIDENCE';

COMMENT ON VIEW mart.pazar_sinyal IS
  'Pazar/rakip: dis kaynak BAGLI DEGIL. Ic kanit ayri etiketle durur.';

-- ===========================================================================
-- F) RED TEAM  -  BAGIMSIZ ITIRAZ
-- ===========================================================================
-- 🔴 RED TEAM ANALYST'IN CIKTISINI OKUMAZ. Ayni kanit anlik goruntusune
--    bakar ve KENDI kurallarini uygular. Kazanan secmez; yalnizca
--    SUPPORT / CHALLENGE / INSUFFICIENT_EVIDENCE der.
CREATE VIEW mart.red_team AS
-- 1) ATIF ZAYIFLIGI
SELECT 'ATIF' AS baslik, 'CHALLENGE' AS hukum,
       'Hicbir urun/kampanya seviyesinde satis atfi yok (CR-011: ad eslesmesi 0/259). '
       'Reklamin hangi satisi getirdigi BILINMIYOR; urun bazli reklam karari bu veriyle verilemez.' AS gerekce,
       'core.source_authority.conversation_messenger = PARTIAL' AS kanit
UNION ALL
-- 2) VERI KAPSAMASI
-- 🔴 ITIRAZ YENIDEN CERCEVELENDI (16.09.2026). Eski hali kosulsuz CHALLENGE
--    veriyordu ve gerekcesi "1/3 hesap okunuyor" idi. Sahip dogrulamasiyla
--    okunmayan iki hesabin OPERASYON DISI oldugu belirlendi: reklam
--    yayinlamiyorlar, yani okunacak harcama YOK. Aktif kapsama tamken
--    "harcama bir tabandir" demek, olmayan bir eksigi itiraz diye sunmaktir.
--    AMA ITIRAZ TAMAMEN KALKMAZ: business_management izni olmadigi icin
--    hesap KESFI yapilamiyor - yeni acilan bir hesap sisteme KENDILIGINDEN
--    gorunmez. Bu gercek ve kalici bir sinirdir, bu yuzden hukum
--    INSUFFICIENT_EVIDENCE'a duser, SUPPORT'a degil.
SELECT 'KAPSAMA',
       CASE WHEN (SELECT aktif_tam FROM mart.meta_kapsama)
            THEN 'INSUFFICIENT_EVIDENCE' ELSE 'CHALLENGE' END,
       CASE WHEN (SELECT aktif_tam FROM mart.meta_kapsama) THEN
         format('%s Harcama bu hesaplar icin TAM sayilir. '
                'KALAN SINIR bir GROWTH BLOCKER DEGIL, bir OPS riskidir: %s - %s',
                (SELECT ifade FROM mart.meta_kapsama),
                (SELECT kesif_riski FROM mart.meta_kapsama),
                (SELECT kesif_riski_aciklama FROM mart.meta_kapsama))
       ELSE
         format('%s Harcama bir TABANDIR; gercek harcama daha yuksek olabilir, '
                'yani zarar gosterilenden BUYUK olabilir.',
                (SELECT ifade FROM mart.meta_kapsama))
       END,
       'mart.meta_kapsama + core.jeton_otorite (business_management yok)'
UNION ALL
-- 3) ORNEKLEM
SELECT 'ORNEKLEM',
       CASE WHEN (SELECT siparis FROM mart.nakit_ozet(30)) < 30 THEN 'CHALLENGE' ELSE 'SUPPORT' END,
       format('Son 30 gunde %s siparis var. Bu hacimde yuzdeler yaniltici; ham adet konusulmali. '
              'Tek bir siparis orani carpici sekilde degistirir.',
              (SELECT siparis FROM mart.nakit_ozet(30))),
       'mart.nakit_ozet(30)'
UNION ALL
-- 4) FINANSAL RISK
SELECT 'FINANSAL',
       CASE WHEN (SELECT nakit_durum FROM mart.nakit_ozet(30))='CRITICAL' THEN 'CHALLENGE' ELSE 'SUPPORT' END,
       format('Son 30 gun nakit durumu %s: harcama %s TL, net ciro %s TL. '
              'Buyume onerisi once bu farki kapatmali; olcek zarari carpar.',
              (SELECT nakit_durum FROM mart.nakit_ozet(30)),
              (SELECT to_char(meta_harcama,'FM999990.00') FROM mart.nakit_ozet(30)),
              (SELECT to_char(net_ciro,'FM999990.00') FROM mart.nakit_ozet(30))),
       'mart.nakit_ozet(30)'
UNION ALL
-- 5) OPERASYONEL KISIT
SELECT 'OPERASYON',
       CASE WHEN (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat>24) > 0
            THEN 'CHALLENGE' ELSE 'SUPPORT' END,
       format('%s cevapsiz musteri mesaji var (en eskisi %s gun). Trafigi artirmak, '
              'cevaplanamayan mesaj sayisini artirir - once kapasite.',
              (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat>24),
              (SELECT coalesce(round(max(bekleme_saat)/24.0,1),0) FROM mart.konusma_cevapsiz)),
       'mart.konusma_cevapsiz'
UNION ALL
-- 6) UYUM / MEVZUAT
SELECT 'MEVZUAT', 'CHALLENGE',
       'Kozmetik urunde tibbi/performans iddiasi yasak. Hicbir kreatif hipotezi mevzuat '
       'kapisindan gecmeden "yayina hazir" sayilamaz; MEVZUAT FILTRESI workflow''u zorunlu adimdir.',
       'n8n MEVZUAT FILTRESI (aktif)'
UNION ALL
-- 7) ALTERNATIF ACIKLAMA
SELECT 'ALTERNATIF', 'INSUFFICIENT_EVIDENCE',
       'Konusma hacmi 81/gun -> 2/gun dustu. Bu reklam performansi, kreatif yorgunlugu, hedefleme '
       'degisikligi VEYA veri toplama sorunu olabilir. Elimizdeki veri bunlari AYIRT EDEMEZ; '
       'Meta tarafindaki mesaj-baslatma sayisiyla karsilastirilmadan neden ilan edilemez.',
       'mart.konusma_gunluk + raw.meta_harcama'
UNION ALL
-- 8) MALIYET KALITESI
SELECT 'MALIYET', 'CHALLENGE',
       format('Urun maliyetinin olculmus orani %s%%. Tum marj ve urun karsilastirmalari tek bir '
              'sahip tahminine dayaniyor; urun secimi bu veriyle yapilirsa yanlis urun secilebilir.',
              (SELECT coalesce(cogs_olculmus_yuzde,0)::text FROM mart.nakit_ozet(30))),
       'mart.maliyet_kalite';

COMMENT ON VIEW mart.red_team IS
  'Bagimsiz itiraz katmani. Analyst ciktisini OKUMAZ; ayni kanittan kendi kurallarini uygular.';

-- ===========================================================================
-- BRIEF URETECI  -  kaniti DONDURUR, bulgulari YAZAR
-- ===========================================================================
-- 🔴 Once kanit dondurulur, SONRA bulgu uretilir. Ters sirada calisirsa
--    bulgu ile kanit arasinda zaman farki olusur ve "neye bakarak boyle
--    dedik" sorusu cevapsiz kalir.
CREATE OR REPLACE FUNCTION core.brief_uret(p_surum text DEFAULT 'CR-014')
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE v_id bigint; v_kal record; v_d7 record; v_d30 record;
BEGIN
  SELECT * INTO v_kal FROM mart.kanit_kalitesi;
  SELECT * INTO v_d7  FROM mart.nakit_ozet(7);
  SELECT * INTO v_d30 FROM mart.nakit_ozet(30);

  INSERT INTO core.kanit_anlik (surum, pencere_7, pencere_30, urun, kanal, konusma,
                                veri_kalitesi, eksik_kaynak, kanit_puani, kanit_sinifi)
  VALUES (
    p_surum,
    to_jsonb(v_d7), to_jsonb(v_d30),
    (SELECT coalesce(jsonb_agg(to_jsonb(u)), '[]'::jsonb) FROM mart.urun_sinyal u),
    (SELECT coalesce(jsonb_agg(to_jsonb(m)), '[]'::jsonb) FROM mart.meta_sinyal m),
    -- 🔴 OLCUM YONTEMI KANITLA BIRLIKTE SAKLANIR.  "137 konusma" tek basina
    --    bir sey ifade etmez; nasil olculdugu, normalize edilip edilmedigi
    --    ve sorgu surumu olmadan sonradan dogrulanamaz. Ayrica konusma ve
    --    mesaj sayilari AYRI durur - biri digerinin yerine kullanilamasin.
    (SELECT jsonb_build_object(
       'konusma', (SELECT count(*) FROM lcarlie.konusma),
       'cevapsiz_24s', (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat>24),
       'en_eski_gun', (SELECT coalesce(round(max(bekleme_saat)/24.0,1),0) FROM mart.konusma_cevapsiz),
       'soru_konu', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                        'konu',                  k.konu,
                        'distinct_conversations', k.distinct_konusma,
                        'matched_messages',       k.eslesen_mesaj,
                        'konusma_yuzde',          k.konusma_yuzde,
                        'sample_examples',        to_jsonb(k.ornekler),
                        'measurement_method',     k.olcum_yontemi,
                        'normalized',             k.normalize_edildi,
                        'query_version',          k.sorgu_surumu)
                        ORDER BY k.distinct_konusma DESC), '[]'::jsonb)
                      FROM mart.soru_konu k),
       -- Veride bulunmadigi icin KATEGORI ACILMAYAN konular da kayda gecer.
       'acilmayan_kategoriler', '["kargo","teslimat","iade","odeme","kapida_odeme","gizlilik_paket"]'::jsonb)),
    (SELECT coalesce(jsonb_agg(to_jsonb(v)), '[]'::jsonb) FROM mart.nakit_veri_kalitesi v),
    (SELECT coalesce(jsonb_agg(jsonb_build_object('alan',alan,'durum',current_connection)), '[]'::jsonb)
       FROM core.source_authority WHERE current_connection <> 'CONNECTED'),
    v_kal.puan, v_kal.sinif)
  RETURNING anlik_id INTO v_id;

  -- URUN bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  SELECT v_id, 'URUN', 'OBSERVED', u.sinif,
         format('%s — %s', left(u.urun_adi,40), u.sinif),
         format('%s adet · net ciro %s TL · brut katki %s TL (%s%%) · maliyet kalitesi %s',
                u.adet, to_char(u.ciro_net,'FM999990.00'), to_char(u.brut_marj,'FM999990.00'),
                u.brut_marj_yuzde, u.maliyet_kalitesi),
         u.gerekce, 'Reklam atfi YOK: bu urunun reklamla iliskisi olculemiyor',
         v_kal.sinif,
         'Olculmus urun maliyeti girildiginde brut katki degisirse bu siniflandirma gecersizdir'
    FROM mart.urun_sinyal u;

  -- META bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  SELECT v_id, 'META', 'OBSERVED', m.nakit_durum,
         format('Son %s gun · %s', m.pencere, m.nakit_durum),
         format('harcama %s TL (kapsama %s) · net ciro %s TL · oran %s · %s gun harcama var siparis yok · kreatif verisi %s',
                to_char(m.harcama,'FM999990.00'), m.hesap_kapsamasi,
                to_char(m.net_ciro,'FM999990.00'), coalesce(m.ciro_harcama_orani,0),
                m.harcamali_satissiz_gun, m.kreatif_seviyesi_veri),
         'Harcama durdurulursa nakit cikisi durur', 'Talep tamamen durabilir',
         v_kal.sinif,
         'Okunamayan 2 hesapta harcama YOKSA ve gercek ciro olculenden yuksekse sonuc degisir'
    FROM mart.meta_sinyal m;

  -- CRO bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, baslik, kanit, kanit_sinifi, yanlislama)
  SELECT v_id, 'CRO', c.seviye, c.kod, c.bulgu, v_kal.sinif,
         'GA4 baglandiginda davranis verisi bu cikarimi dogrulamaz ya da curutur'
    FROM mart.cro_sinyal c;

  -- PAZAR bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit, kanit_sinifi)
  SELECT v_id, 'PAZAR', p.seviye, p.durum, p.kod, p.bulgu, v_kal.sinif
    FROM mart.pazar_sinyal p;

  -- KREATIF hipotezleri  (HYPOTHESIS - kazanan degil)
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  -- 🔴 Kanit metni HIPOTEZIN KENDI sayisindan kurulur; ortak sayi paylasilmaz.
  -- 🔴 KONUSMA ve MESAJ ayri yazilir; olcum yontemi ve sorgu surumu kanitin
  --    parcasidir - "137" sayisi yontemi bilinmeden dogrulanamaz.
  SELECT v_id, 'KREATIF', 'HYPOTHESIS', 'TEST_SMALL', h.kod || ' — ' || h.hipotez,
         format('%s tekil konusma / %s mesaj (%s/%s konusma = %%%s) — %s · yontem: %s · surum: %s',
                h.adet, h.mesaj, h.adet, h.toplam, h.yuzde, h.kanit,
                h.olcum_yontemi, h.sorgu_surumu),
         h.beklenen_etki, h.risk, v_kal.sinif, h.yanlislama
    FROM mart.kreatif_hipotez h;

  -- RED TEAM  (bagimsiz)
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit, kanit_sinifi)
  SELECT v_id, 'RED_TEAM', 'OBSERVED', r.hukum, r.baslik, r.gerekce, v_kal.sinif
    FROM mart.red_team r;

  RETURN v_id;
END $$;

COMMENT ON FUNCTION core.brief_uret(text) IS
  'Kaniti dondurur ve bulgulari yazar. Hicbir aksiyon almaz - yalniz okur ve kaydeder.';

COMMIT;
