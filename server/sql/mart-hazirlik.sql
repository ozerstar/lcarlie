-- =============================================================================
-- L'CARLIE - MART: OLCUM HAZIRLIK KAPISI + MALIYET KALITESI  (CR-012)
--
-- 🔴 NEDEN VAR - bagimsiz denetimin en sert cumlesi (16.09.2026):
--      "PARTIAL yazsa bile insan ekranda 4,8 gordugunde 4,8'i HATIRLAR."
--
--    Panel bugune kadar ROAS sayisini gosterip yanina "eksik olabilir" notu
--    koyuyordu. Bu yeterli degil. 3 Meta hesabinin 1'i bagli; eksik harcama
--    ROAS'i OLDUGUNDAN YUKSEK gosterir. Yanlis sayinin sik gorunmesi,
--    sayinin hic olmamasindan tehlikelidir.
--
--    Bu dosya kapiyi kurar: KOSULLAR SAGLANMADIKCA SAYI URETILMEZ.
--    Uretilmeyen sayi yerine EKSIGIN ADI yazilir.
--
-- 🔴 KAPSAMA ile KALITE AYRI SEYDIR:
--      cost_coverage = kac kalemde maliyet VAR
--      cost_quality  = kaci GERCEKTEN OLCULMUS maliyet
--    36 urunun 36'sinda maliyet var (kapsama %96,2 ciro agirlikli) ama
--    hepsi ayni 400 TL sahip TAHMINI. Kapsama yuksek, kalite sifir.
--    SKU bazinda reklam karari bu ayrim olmadan verilirse YANLIS URUN secilir.
-- =============================================================================

BEGIN;

DROP VIEW IF EXISTS mart.hazirlik_ozet   CASCADE;
DROP VIEW IF EXISTS mart.hazirlik        CASCADE;
DROP VIEW IF EXISTS mart.maliyet_kalite  CASCADE;

-- ---------------------------------------------------------------------------
-- MALIYET KALITESI
-- ---------------------------------------------------------------------------
-- 🔴 Kalite SIRALI: OLCULMUS > TEDARIKCI > TAHMIN.  Sahip beyani "ortalama
--    400 TL" bir TAHMINDIR ve oyle etiketlenir - kaydin kendi gerekce
--    metninde de boyle yaziyor ("GERCEK URUN MALIYETI DEGIL").
CREATE VIEW mart.maliyet_kalite AS
SELECT m.urun_id,
       u.ad AS urun_adi,
       u.fiyat,
       m.maliyet,
       m.kaynak,
       m.gerekce,
       -- 🔴 MALIYETIN KDV TABANI ACIK SORU (CR-012).
       --    Beyan edilen 400 TL'nin KDV dahil mi haric mi oldugu sahibe
       --    sorulmadi. Marj hesabi KDV HARIC varsayar (COGS'un standart
       --    tutulusu). Varsayim GIZLENMEZ: ayar girilene kadar her satir
       --    TEYIT_EDILMEDI der. Bu veri setinde etkisi 3.733 TL.
       coalesce((SELECT deger FROM core.ayar WHERE anahtar='maliyet_kdv_tabani'),
                'TEYIT_EDILMEDI')                   AS kdv_tabani,
       CASE
         -- Wix'ten gelen deger, sahibin urun kartina girdigi gercek maliyettir
         WHEN m.kaynak = 'WIX'                                THEN 'OLCULMUS'
         -- Elle girilmis ama gerekcesinde "ORTALAMA"/"DEGIL" geciyorsa tahmin
         WHEN m.gerekce ILIKE '%ORTALAMA%'
           OR m.gerekce ILIKE '%GERCEK URUN MALIYETI DEGIL%'  THEN 'TAHMIN'
         WHEN m.kaynak = 'ELLE'                               THEN 'ELLE_BEYAN'
         ELSE 'BILINMIYOR'
       END AS kalite
  FROM core.urun_maliyet m
  LEFT JOIN raw.wix_urun u ON u.urun_id = m.urun_id
 WHERE m.gecerli_bitis IS NULL;

COMMENT ON VIEW mart.maliyet_kalite IS
  'Aktif maliyet kayitlarinin KALITESI. OLCULMUS=gercek, TAHMIN=sahip ortalamasi.';

-- ---------------------------------------------------------------------------
-- HAZIRLIK KOSULLARI  - her kosul AYRI SATIR
-- ---------------------------------------------------------------------------
-- 🔴 Tek bir "hazir mi" boolean'i yetmez: hazir DEGILSE panel NEYIN eksik
--    oldugunu yazmak zorunda. Satir bazli olunca eksigin adi da geliyor.
CREATE VIEW mart.hazirlik AS

-- 1) Olcum penceresi acildi mi?
SELECT 'OLCUM_BASLADI'                                        AS kosul,
       (now() >= mart.kesim())                                AS saglandi,
       format('olcum baslangici %s',
              to_char(mart.kesim() AT TIME ZONE 'Europe/Istanbul','DD.MM.YYYY')) AS detay,
       'Kesim tarihi core.ayar.olcum_baslangici icinde'        AS nereden

UNION ALL
-- 2) Reklam harcamasinin TAMAMI bagli mi?
-- 🔴 EN KRITIK KOSUL. Eksik harcama ROAS'i yukari sisirir.
SELECT 'REKLAM_HARCAMASI_TAM',
       NOT EXISTS (SELECT 1 FROM core.source_authority
                    WHERE alan='ad_spend' AND current_connection <> 'CONNECTED'),
       coalesce((SELECT current_connection FROM core.source_authority WHERE alan='ad_spend'),
                '(kayit yok)'),
       'core.source_authority.ad_spend'

UNION ALL
-- 3) Siparis kaydi tam mi? (WhatsApp/telefon siparisleri Wix'e giriliyor mu)
-- 🔴 Wix'te kaydi olmayan kapida odemeli gonderi varsa, o ciro Wix aynasinda
--    YOK demektir; ROAS'in PAYI eksik kalir ve olcu OLDUGUNDAN KOTU cikar.
--    Yani bu kosul ile (2) ters yonlerde saptirir - ikisi de kapali olmali.
SELECT 'SIPARIS_KAYDI_TAM',
       NOT EXISTS (SELECT 1 FROM mart.gonderi
                    WHERE olcumde AND sinif = 'ELLE_SATIS'),
       format('%s gonderi Wix kaydi olmadan kapida odemeli',
              (SELECT count(*) FROM mart.gonderi WHERE olcumde AND sinif='ELLE_SATIS')),
       'mart.gonderi sinif=ELLE_SATIS'

UNION ALL
-- 4) Ciro tanimi gecerli mi? (KDV okunabiliyor mu)
-- 🔴 KDV NULL ise net ciro da NULL olur; marj ve ROAS hesaplanamaz.
SELECT 'CIRO_TANIMI_GECERLI',
       NOT EXISTS (SELECT 1 FROM mart.siparis
                    WHERE olcumde AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
                      AND kdv IS NULL),
       format('%s sayilan siparişte KDV okunamadi',
              (SELECT count(*) FROM mart.siparis
                WHERE olcumde AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')
                  AND kdv IS NULL)),
       'raw.wix_order.kdv (totals.tax)'

UNION ALL
-- 5) Siniflandirilamayan gonderi kaldi mi?
SELECT 'GONDERI_SINIFLANDI',
       NOT EXISTS (SELECT 1 FROM mart.gonderi WHERE olcumde AND alarm),
       format('%s gonderinin yonu bilinmiyor',
              (SELECT count(*) FROM mart.gonderi WHERE olcumde AND alarm)),
       'mart.gonderi alarm=true';

COMMENT ON VIEW mart.hazirlik IS
  'ROAS/marj gosterilebilmesi icin saglanmasi gereken kosullar. Her satir ayri kapi.';

-- ---------------------------------------------------------------------------
-- TEK SATIRLIK OZET  - panel bunu okur
-- ---------------------------------------------------------------------------
CREATE VIEW mart.hazirlik_ozet AS
SELECT bool_and(saglandi)                                        AS karar_hazir,
       count(*) FILTER (WHERE NOT saglandi)                      AS eksik_sayisi,
       coalesce(string_agg(kosul, ', ' ORDER BY kosul)
                FILTER (WHERE NOT saglandi), '')                 AS eksikler,
       coalesce(string_agg(format('%s (%s)', kosul, detay), ' · ' ORDER BY kosul)
                FILTER (WHERE NOT saglandi), '')                 AS eksik_detay
  FROM mart.hazirlik;

COMMENT ON VIEW mart.hazirlik_ozet IS
  'karar_hazir=false ise panel ROAS SAYISI GOSTERMEZ, eksigin adini yazar.';

COMMIT;
