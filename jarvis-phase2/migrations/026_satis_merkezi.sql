-- 026 — SATIŞ MERKEZİ: elle gönderi notu + elle stok sayımı (21.09.2026)
--
-- Sahip: *"fiyatı olmayan gönderilerin yanına veya kararsız kalınan
-- bilgileri elle yazmam için kutu koy ki dataların eksik olmasın… hangi
-- üründen kaç tane dağıtıldı orada yazılsın… stok takibi için panel aç,
-- ben güncel stok bilgilerini elle gireyim."*
--
-- ÖLÇÜLEN DURUM
-- `mart.siparis` 37 kayıt, HEPSİ kanal='WEB' (Wix). `odeme_durumu` PAID 32 /
-- NOT_PAID 5, `ciro_sinifi` DOGRULANMIS 21 / BEYAN_EDILMIS 11 / IPTAL 5.
-- Yani "para gelmemiş gönderi" görünüyor ama NEDEN gelmediği (UGC mi,
-- influencer mı, numune mi) hiçbir yerde yazmıyor. Bu ayrım olmadan
-- "kaç tane dağıtıldı" sorusu cevaplanamıyor.
--
-- 🔴 İKİ TABLO DA İNSAN BEYANIDIR -> human_approver yazar, ai_writer YAZAMAZ.
-- Sebep `core.pazar_bulgu` ile aynı: makinenin kendi çıkarımını insanın
-- beyanı gibi kaydetmesi, sistemin kendi iddiasını kendi kanıtına
-- çevirmesi olur. Stok sayımı ve "bu bir influencer gönderisiydi" bilgisi
-- ölçülemez, yalnız BEYAN edilir.
--
-- Geri alma: migrations/rollback/026_satis_merkezi_ROLLBACK.sql

BEGIN;

-- ---------------------------------------------------------------- gönderi notu
CREATE TABLE IF NOT EXISTS core.gonderi_notu (
    not_id       bigserial PRIMARY KEY,
    siparis_ref  text,                     -- mart.siparis.entity_id; elle
                                           -- girilen gönderide NULL olabilir
    tur          text        NOT NULL,
    alici        text,                     -- kime gitti
    urun_adi     text,
    adet         numeric,
    elle_fiyat   numeric,                  -- fiyatsız gönderide beyan edilen değer
    not_metni    text,
    giren        text        NOT NULL,
    girildi      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT gonderi_notu_tur CHECK (tur IN
        ('SATIS', 'UGC', 'INFLUENCER', 'NUMUNE', 'HEDIYE', 'IADE', 'DEGISIM', 'BILINMIYOR')),
    -- 🔴 Adet ve fiyat NEGATİF olamaz; iade için ayrı tür var, eksi sayı değil.
    CONSTRAINT gonderi_notu_adet CHECK (adet IS NULL OR adet >= 0),
    CONSTRAINT gonderi_notu_fiyat CHECK (elle_fiyat IS NULL OR elle_fiyat >= 0)
);

COMMENT ON TABLE core.gonderi_notu IS
 'Gönderinin NE OLDUĞU: satış mı, UGC mi, numune mi. İnsan beyanıdır; '
 'ölçüm değildir. Fiyatsız gönderide değeri buraya elle yazılır.';

CREATE INDEX IF NOT EXISTS gonderi_notu_ref ON core.gonderi_notu (siparis_ref);
CREATE INDEX IF NOT EXISTS gonderi_notu_urun ON core.gonderi_notu (urun_adi);

-- ---------------------------------------------------------------- stok sayımı
CREATE TABLE IF NOT EXISTS core.stok_sayim (
    sayim_id     bigserial PRIMARY KEY,
    urun_adi     text        NOT NULL,
    adet         integer     NOT NULL,
    nerede       text        NOT NULL DEFAULT 'DEPO',
    giren        text        NOT NULL,
    sayim_zamani timestamptz NOT NULL DEFAULT now(),
    not_metni    text,
    CONSTRAINT stok_sayim_adet CHECK (adet >= 0)
);

COMMENT ON TABLE core.stok_sayim IS
 'Elle girilen stok sayımı. Wix/Trendyol stok alanı ayrı bir şeydir '
 '(platformun kendi sayısı); bu, fiziksel sayımın beyanıdır.';

-- ---------------------------------------------------------------- görünümler
-- Her ürünün EN SON sayımı. Tarihçe tabloda kalır, panel sonuncuyu gösterir.
CREATE OR REPLACE VIEW mart.stok_guncel AS
SELECT DISTINCT ON (urun_adi)
       urun_adi, adet, nerede, giren, sayim_zamani, not_metni,
       EXTRACT(DAY FROM (now() - sayim_zamani))::int AS gun_gecti
  FROM core.stok_sayim
 ORDER BY urun_adi, sayim_zamani DESC;

-- Ürün başına DAĞITIM: satılan + bedelsiz giden, ayrı ayrı.
-- 🔴 İkisi TOPLANMAZ. "20 adet çıktı" demek, 15 satış + 5 numuneyi aynı
-- kefeye koymaktır ve ciro hesabını bozar.
CREATE OR REPLACE VIEW mart.urun_dagitim AS
WITH satilan AS (
    SELECT urun_adi, sum(adet)::numeric AS adet, count(*)::int AS satir
      FROM mart.siparis_kalem
     GROUP BY urun_adi
), bedelsiz AS (
    SELECT urun_adi,
           sum(COALESCE(adet, 0))::numeric AS adet,
           count(*)::int AS satir
      FROM core.gonderi_notu
     WHERE tur IN ('UGC', 'INFLUENCER', 'NUMUNE', 'HEDIYE')
     GROUP BY urun_adi
)
SELECT COALESCE(s.urun_adi, b.urun_adi) AS urun_adi,
       COALESCE(s.adet, 0)   AS satilan_adet,
       COALESCE(s.satir, 0)  AS satis_satiri,
       COALESCE(b.adet, 0)   AS bedelsiz_adet,
       COALESCE(b.satir, 0)  AS bedelsiz_satiri,
       COALESCE(s.adet, 0) + COALESCE(b.adet, 0) AS toplam_cikan
  FROM satilan s
  FULL OUTER JOIN bedelsiz b ON b.urun_adi = s.urun_adi;

-- ---------------------------------------------------------------- yetkiler
GRANT SELECT ON core.gonderi_notu, core.stok_sayim,
                mart.stok_guncel, mart.urun_dagitim TO ai_reader;
-- 🔴 ai_writer'a YAZMA VERİLMEZ: ikisi de insan beyanı.
GRANT SELECT, INSERT, UPDATE, DELETE ON core.gonderi_notu, core.stok_sayim
    TO human_approver;
GRANT USAGE ON SEQUENCE core.gonderi_notu_not_id_seq,
                        core.stok_sayim_sayim_id_seq TO human_approver;

COMMIT;

