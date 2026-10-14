-- =====================================================================
-- 027  ELLE SATIŞ CİROYA BAĞLANIYOR
--
-- 🔴 NEDEN VAR (27.09.2026 ölçümü). Satış merkezi 026'da kuruldu ve
--    `core.gonderi_notu` tablosu `tur='SATIS'` ile `elle_fiyat` alanını
--    ZATEN taşıyordu. Ama:
--
--      1. Tablo BOŞTU  — 0 satır, hiç kullanılmamış.
--      2. `mart.urun_dagitim` yalnız BEDELSİZ dalında okuyordu
--         (UGC/INFLUENCER/NUMUNE/HEDIYE). `tur='SATIS'` hiçbir dalda yok.
--      3. 🔴 `elle_fiyat` HİÇBİR görünümde geçmiyordu. Görünüm
--         tanımlarının tamamı tarandı: sıfır eşleşme.
--
--    Yani panelden elle satış girilse, adedi de fiyatı da hiçbir yere
--    ulaşmıyordu. Bu projede tanıdık desen: yazılıyor, okunmuyor.
--
--    Sonuç: 1 Ekim ölçümü tek kanaldan (Wix) besleniyor. Kapıda ödeme,
--    WhatsApp/telefon ve Trendyol satışları ciroda GÖRÜNMÜYOR.
--
-- 🔴 ELLE SATIŞ "DOĞRULANMIŞ" CİRO DEĞİLDİR. İnsan beyanıdır; Wix
--    ödemesi gibi bir ödeme kaydına dayanmaz. CR-008/CR-012'de kurulan
--    ayrım korunuyor: beyan ayrı sütunda durur, doğrulanmışa KARIŞMAZ.
--    Karıştırmak ciroyu şişirirdi -- bu projede bir kez yaşandı
--    (kalem indirimi, ciro %18,8 şişik çıkmıştı).
--
-- Geri alma: migrations/rollback/027_elle_satis_ciro_ROLLBACK.sql
-- =====================================================================
\set ON_ERROR_STOP on

BEGIN;

-- ------------------------------------------------------------- kanal
-- 🔴 KANAL ALANI YOKTU. 026'da gönderi notunun kanalı tutulmuyordu;
--    "kapıda ödeme mi WhatsApp mı" ayrımı yapılamıyordu. Ciro kanal
--    bazlı okunacaksa bu alan şart.
--    NULL serbest: eski satırlar ve kanalı bilinmeyen girişler için.
--    'BILINMIYOR' ile NULL AYRI: biri "bilmiyoruz" beyanı, diğeri
--    "sorulmadı". Yokluğun sebebini ayırmak bu projenin kuralı.
ALTER TABLE core.gonderi_notu
    ADD COLUMN IF NOT EXISTS kanal text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'gonderi_notu_kanal') THEN
        ALTER TABLE core.gonderi_notu
            ADD CONSTRAINT gonderi_notu_kanal CHECK (kanal IS NULL OR kanal IN
                ('KAPIDA', 'WHATSAPP', 'TELEFON', 'TRENDYOL', 'ELDEN', 'DIGER', 'BILINMIYOR'));
    END IF;
END $$;

COMMENT ON COLUMN core.gonderi_notu.kanal IS
 'Satışın hangi kanaldan geldiği. NULL = sorulmadı, BILINMIYOR = soruldu '
 'ama bilinmiyor. İkisi ayrı şeydir.';

-- --------------------------------------------------- ürün dağıtımı
-- Üç dal: Wix kalemleri · elle girilen SATIŞ · bedelsiz çıkış.
--
-- ⚠️ `satilan_adet` ANLAMI DEĞİŞMEDİ: hâlâ yalnız mart.siparis_kalem
--    (yani Wix). Elle satış AYRI sütunda duruyor. Eski sayıyı sessizce
--    değiştirmek, o sayıya bakan herkesi yanıltırdı.
--    `toplam_cikan` ise gerçekten "depodan çıkan" demek; elle satış
--    oraya DAHİL -- zaten eksik olan buydu.
CREATE OR REPLACE VIEW mart.urun_dagitim AS
WITH satilan AS (
    SELECT urun_adi, sum(adet)::numeric AS adet, count(*)::int AS satir
      FROM mart.siparis_kalem
     GROUP BY urun_adi
), elle AS (
    -- 🔴 `siparis_ref IS NULL` ŞART. Dolu olan, Wix siparişine iliştirilmiş
    --    bir nottur; onu ayrıca saymak çift sayım olurdu.
    SELECT urun_adi,
           sum(COALESCE(adet, 0))::numeric AS adet,
           count(*)::int AS satir,
           sum(COALESCE(elle_fiyat, 0))::numeric AS tutar
      FROM core.gonderi_notu
     WHERE tur = 'SATIS' AND siparis_ref IS NULL
     GROUP BY urun_adi
), bedelsiz AS (
    SELECT urun_adi,
           sum(COALESCE(adet, 0))::numeric AS adet,
           count(*)::int AS satir
      FROM core.gonderi_notu
     WHERE tur IN ('UGC', 'INFLUENCER', 'NUMUNE', 'HEDIYE')
     GROUP BY urun_adi
), adlar AS (
    SELECT urun_adi FROM satilan
    UNION SELECT urun_adi FROM elle
    UNION SELECT urun_adi FROM bedelsiz
)
-- 🔴 SÜTUN SIRASI DEĞİŞTİRİLEMEZ. `CREATE OR REPLACE VIEW` var olan
--    sütunların adını/sırasını değiştiremez, yalnız SONA ekleyebilir.
--    Yeni üç sütun bu yüzden en sonda; 026'nın altı sütunu aynen yerinde.
SELECT a.urun_adi,
       COALESCE(s.adet, 0)    AS satilan_adet,
       COALESCE(s.satir, 0)   AS satis_satiri,
       COALESCE(b.adet, 0)    AS bedelsiz_adet,
       COALESCE(b.satir, 0)   AS bedelsiz_satiri,
       COALESCE(s.adet, 0) + COALESCE(e.adet, 0) + COALESCE(b.adet, 0)
           AS toplam_cikan,
       COALESCE(e.adet, 0)    AS elle_satis_adet,
       COALESCE(e.satir, 0)   AS elle_satis_satiri,
       COALESCE(e.tutar, 0)   AS elle_satis_tutari
  FROM adlar a
  LEFT JOIN satilan  s ON s.urun_adi IS NOT DISTINCT FROM a.urun_adi
  LEFT JOIN elle     e ON e.urun_adi IS NOT DISTINCT FROM a.urun_adi
  LEFT JOIN bedelsiz b ON b.urun_adi IS NOT DISTINCT FROM a.urun_adi;

COMMENT ON VIEW mart.urun_dagitim IS
 'Üründen çıkan adet: Wix satışı, elle girilen satış ve bedelsiz çıkış '
 'AYRI sütunlarda. satilan_adet yalnız Wix''tir; elle satış ona karışmaz.';

-- ------------------------------------------------------- elle satış
CREATE OR REPLACE VIEW mart.elle_satis AS
SELECT n.not_id,
       n.girildi::date                         AS gun,
       COALESCE(n.kanal, 'BILINMIYOR')         AS kanal,
       n.urun_adi,
       n.adet,
       n.elle_fiyat                            AS tutar,
       -- 🔴 FİYATSIZ GİRİŞ "0 TL SATIŞ" DEĞİLDİR. Ayrı işaretlenir;
       --    toplama 0 diye girmek ciroyu sessizce eksiltirdi.
       (n.elle_fiyat IS NULL)                  AS tutar_eksik,
       n.alici,
       n.not_metni,
       n.giren,
       n.girildi
  FROM core.gonderi_notu n
 WHERE n.tur = 'SATIS' AND n.siparis_ref IS NULL;

COMMENT ON VIEW mart.elle_satis IS
 'Wix dışı satışlar (kapıda ödeme, WhatsApp, Trendyol...). İNSAN BEYANI: '
 'ödeme kaydına dayanmaz, doğrulanmış ciro değildir.';

-- -------------------------------------------------------- ciro kanal
-- Tek tabloda "ölçtüğümüz" ile "beyan edilen" yan yana. Toplamı
-- vermiyoruz: iki sayının anlamı farklı, toplamak ikisini de bozar.
CREATE OR REPLACE VIEW mart.ciro_kanal AS
SELECT s.gun,
       COALESCE(s.kanal, 'BILINMIYOR')                   AS kanal,
       'OLCULDU'::text                                   AS kaynak_tipi,
       count(*)::int                                     AS siparis,
       round(sum(COALESCE(s.ciro_dogrulanmis_net, 0)))   AS ciro_dogrulanmis,
       round(sum(COALESCE(s.ciro_beyan_edilmis_net, 0))) AS ciro_beyan,
       0::int                                            AS tutar_eksik
  FROM mart.siparis s
 GROUP BY s.gun, COALESCE(s.kanal, 'BILINMIYOR')
UNION ALL
SELECT e.gun,
       e.kanal,
       'BEYAN'::text                                     AS kaynak_tipi,
       count(*)::int                                     AS siparis,
       0                                                 AS ciro_dogrulanmis,
       round(sum(COALESCE(e.tutar, 0)))                  AS ciro_beyan,
       count(*) FILTER (WHERE e.tutar_eksik)::int        AS tutar_eksik
  FROM mart.elle_satis e
 GROUP BY e.gun, e.kanal;

COMMENT ON VIEW mart.ciro_kanal IS
 'Kanal bazlı ciro. kaynak_tipi=OLCULDU ödeme kaydına dayanır; BEYAN '
 'insan girişidir. İkisi TOPLANMAZ, yan yana okunur. tutar_eksik: '
 'fiyatı girilmemiş beyan satırı sayısı -- o satırlar 0 TL DEĞİLDİR.';

-- ---------------------------------------------------------- yetkiler
GRANT SELECT ON mart.elle_satis, mart.ciro_kanal TO ai_reader;

COMMIT;
