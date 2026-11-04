-- =============================================================================
-- L'CARLIE - MIMARI DERSLER  (Decision Memory learning katmani)
--
-- 🔴 NEDEN core.karar DEGIL:
--    core.karar bir DURUM MAKINESIDIR (PROPOSED -> APPROVED -> EXECUTED ->
--    MEASURING -> CONCLUDED) ve karar_tipi listesi buyume kararlarina kapali
--    bir kume (PRODUCT_PRIORITY, MEDIA_BUDGET, ...). Bir mimari ders
--    "onaylanmaz", "yurutulmez", "sonuclandirilmaz" - GECERLIDIR ya da
--    yeni kanitla degisir. Karar tablosuna sokulsaydi:
--      - mart.karar_oncelik kuyrugunu kirletirdi (insan onayi bekliyormus gibi)
--      - karar_gecis_kontrol trigger'i anlamsiz bir gecis zorlardi
--      - "6 acik karar" sayisi gercegi yansitmazdi
--
-- 🔴 EKLEME-ONLY: UPDATE yolu YOK. Bir ders yanlislanirsa SILINMEZ;
--    yerine yenisi yazilir ve eskisi `gecersiz_kilan` ile isaretlenir.
--    Audit trail'in anlami "bir zamanlar bunu ogrenmistik" bilgisini
--    korumaktir.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS core.mimari_ders (
  ders_id        bigserial PRIMARY KEY,
  kod            text NOT NULL UNIQUE,      -- kararli slug; idempotent ekleme anahtari
  baslik         text NOT NULL,
  ders           text NOT NULL,             -- dersin kendisi (genel kural)
  tetikleyen     text NOT NULL,             -- bu dersi DOGURAN olculmus olay
  kanit          text NOT NULL,             -- olgunun sayisal dayanagi
  sonuc          text NOT NULL,             -- sistemde ne degismeli
  kaydeden       text NOT NULL,
  olusturma      timestamptz NOT NULL DEFAULT clock_timestamp(),
  -- 🔴 Ders GECERSIZ kilinabilir ama SILINEMEZ.
  gecersiz_kilan bigint REFERENCES core.mimari_ders(ders_id),
  gecersizlik_nedeni text
);

COMMENT ON TABLE core.mimari_ders IS
  'Mimari dersler. core.karar DEGIL: ders onaylanmaz/yurutulmez, gecerlidir ya da yeni kanitla degisir. Ekleme-only.';

-- ---------------------------------------------------------------------------
-- DERS 1: OLCUM TAMLIGI, TICARI TAMLIK DEGILDIR
-- ---------------------------------------------------------------------------
-- 🔴 Bu ders bir "model hatasi" kaydi DEGIL, bir SISTEM TASARIM dersidir.
--    Chief Architect tespiti (16.09.2026): "Sistem cok iyi olcum altyapisi
--    kurup yine de en temel ekonomik soruyu gec sorabiliyorsa, olcum
--    mimarisinin kendi BASARI KRITERINDE eksik var demektir."
INSERT INTO core.mimari_ders (kod, baslik, ders, tetikleyen, kanit, sonuc, kaydeden) VALUES
('MEASUREMENT_COMPLETENESS_IS_NOT_COMMERCIAL_COMPLETENESS',
 'Olcum tamligi, ticari tamlik degildir',

 'Bir sistem su kapilarin HEPSINDEN gecebilir: '
 'ingestion · reconciliation · attribution · data quality · readiness — '
 've yine de su soruya cevap veremeyebilir: "Para kazaniyor muyuz, kaybediyor muyuz?" '
 'Bu yuzden TICARI YASAYABILIRLIK, hazirligin birinci sinif ve ACIK bir boyutu olmalidir. '
 'Hicbir buyume/olcekleme onerisi, katki marji gorunurlugu olmadan '
 'EKONOMIK OLARAK DOGRULANMIS sayilamaz.',

 'CR-004''ten CR-012''ye kadar olcum altyapisi kuruldu (ham ayna, kimlik omurgasi, '
 'mutabakat testleri, KDV duzeltmesi, atif olcumu, hazirlik kapilari) ve bu boyunca '
 'panel TEK BIR ticari rakam gostermedi - cunku her gorunum 1 Ekim kesim tarihine '
 'bagliydi. O sirada reklam harcamasi olculebilen ciroyu asiyordu ve bu hicbir '
 'ekranda GORUNMEDI. Aciklik ancak CR-013 (Commercial Cash Guardrail) ile kapandi; '
 'o da ayri bir talimatla acildi, sistemin kendi uyarisiyla degil.',

 'Olculdu (16.09.2026, son 30 gun): net ciro 16.182,09 TL · bilinen COGS 5.200,00 TL · '
 'satis kargosu 1.193,29 TL · Meta harcamasi 29.509,99 TL · reklam sonrasi katki '
 '-20.796,36 TL (CRITICAL). 30 gunun 18''inde harcama VAR, siparis YOK. '
 'Reklam harcamasi 06.08.2026''da basladi; nakit korkulugu 16.09.2026''da kuruldu - '
 'yani yaklasik ALTI HAFTA boyunca kayip gorunmedi.',

 'TICARI YASAYABILIRLIK ACIK BIR HAZIRLIK BOYUTU OLACAK. '
 'Bunun on kosulu birim ekonomisinin kurulmasidir (COGS Truth Layer): '
 'urun maliyeti · paketleme · odeme komisyonu · kargo · kapida odeme maliyeti · '
 'kanal komisyonu · indirim maliyeti · numune maliyeti · iade ekonomik etkisi · '
 'degisken katki. Bu katman kurulmadan hicbir scale onerisi "ekonomik olarak '
 'dogrulanmis" etiketi alamaz. '
 '🔴 BU DERS BIR CR DEGILDIR ve tek basina hicbir uretim davranisini degistirmez; '
 'uygulamasi COGS Truth Layer tasarimina aittir.',

 'Chief Architect (16.09.2026)')
-- 🔴 Ekleme-only + idempotent: ayni ders ikinci kez YAZILMAZ, cogaltilmaz.
--    (Bu projede tadil metinlerinin 7 kez cogalmasi tam da bu korumanin
--     yoklugundan olmustu.)
ON CONFLICT (kod) DO NOTHING;

-- ---------------------------------------------------------------------------
-- GORUNUR OLSUN - kayitli ama okunmayan ders, ders degildir
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.mimari_ders CASCADE;

CREATE VIEW mart.mimari_ders AS
SELECT d.ders_id, d.kod, d.baslik, d.ders, d.tetikleyen, d.kanit, d.sonuc,
       d.kaydeden, d.olusturma,
       (d.gecersiz_kilan IS NULL) AS gecerli,
       d.gecersizlik_nedeni
  FROM core.mimari_ders d
 ORDER BY (d.gecersiz_kilan IS NULL) DESC, d.ders_id;

COMMENT ON VIEW mart.mimari_ders IS
  'Mimari dersler, gecerli olanlar ustte. Gecersiz kilinanlar SILINMEZ - audit trail.';

COMMIT;
