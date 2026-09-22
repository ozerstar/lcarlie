-- 031 — ŞABLON KÜTÜĞÜ: Template Registry
--
-- Sahip 22.09.2026, 10 şablon grubunu seçip şunu istedi: *"Her şablon için
-- Template ID, boyut, dinamik alanlar, marka kuralları, regülasyon
-- kuralları, versiyon ve onay durumu tanımlanacak."*
--
-- 030'daki kütük yalnız üretime yetiyordu (is_turu + canva_id + alan
-- haritası). Bir ŞARTNAME taşımıyordu: bu şablon kaç santim, hangi kanal
-- için, hangi marka kuralına tabi, hangi mevzuat kısıtı var.
--
-- 🔴 EN ÖNEMLİ AYRIM: TANIMLI OLMAK ≠ ÜRETİLEBİLİR OLMAK.
-- 50 şablonu kütüğe yazıp hepsini "var" saymak, Şablon Sorumlusu'na yalan
-- söyletmek olurdu: arkasında Canva tasarımı olmayan satır üretim yapamaz.
-- Bu yüzden `canva_id` artık NULL olabiliyor ve `durum` bunu ayırıyor:
--     TASLAK    -> şartnamesi yazıldı, tasarımı YOK, üretilemez
--     HAZIR     -> Canva tasarımı bağlı ve alanları işaretli, üretilebilir
--     ARSIVDE   -> kullanımdan kalktı
-- Tetikleyici bu tutarlılığı ZORLUYOR: canva_id'si olmayan satır HAZIR
-- olamaz. Sözleşmeye bırakılsa, bir gün biri elle HAZIR yazar ve üretim
-- anlaşılmaz bir hatayla düşerdi.
--
-- 🔴 MEVZUAT KURALI ŞABLONA YAZILIYOR. Bazı kısıtlar şablona özgüdür:
-- "öncesi/sonrası" formatı yalnız doğrulanabilir içerikle, fiyat kartında
-- taksit yazılamaz (kozmetikte yasak), tester kartında iddia olamaz.
-- Bunu üretim anında hatırlamak yerine şablonun kendisinde tutuyoruz.
--
-- Geri alma: migrations/rollback/031_sablon_kutugu_ROLLBACK.sql

BEGIN;

ALTER TABLE core.tasarim_sablon
    -- İnsan tarafından okunabilir benzersiz kimlik: SOCIAL_IG_POST_01
    ADD COLUMN IF NOT EXISTS sablon_kodu   text,
    ADD COLUMN IF NOT EXISTS kategori      text,
    ADD COLUMN IF NOT EXISTS platform      text,
    ADD COLUMN IF NOT EXISTS bicim         text NOT NULL DEFAULT 'PNG',
    -- Fiziksel baskıda px yanıltır; mm ve dpi ayrıca tutuluyor.
    ADD COLUMN IF NOT EXISTS en_mm         numeric(8,2),
    ADD COLUMN IF NOT EXISTS boy_mm        numeric(8,2),
    ADD COLUMN IF NOT EXISTS dpi           int,
    -- Şartname: hangi alanlar doldurulacak (tasarım olmasa da yazılır).
    ADD COLUMN IF NOT EXISTS beklenen_alanlar jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS marka_kurallari  text,
    ADD COLUMN IF NOT EXISTS mevzuat_kurallari text,
    ADD COLUMN IF NOT EXISTS surum         int  NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS durum         text NOT NULL DEFAULT 'TASLAK',
    -- Canva her şeyi yapamaz: video ve bazı baskı işleri başka motor ister.
    ADD COLUMN IF NOT EXISTS motor         text NOT NULL DEFAULT 'canva',
    ADD COLUMN IF NOT EXISTS onay_zorunlu  boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS faz           int;

-- canva_id artık zorunlu değil: şartnamesi yazılmış ama tasarımı olmayan
-- şablon kütükte durabilmeli.
ALTER TABLE core.tasarim_sablon ALTER COLUMN canva_id DROP NOT NULL;

-- Eski CHECK canva_id'yi zorunlu biçimde denetliyordu; NULL'a izin ver.
ALTER TABLE core.tasarim_sablon DROP CONSTRAINT IF EXISTS tasarim_sablon_canva_id_bicim;
ALTER TABLE core.tasarim_sablon ADD CONSTRAINT tasarim_sablon_canva_id_bicim
    CHECK (canva_id IS NULL OR canva_id ~ '^[A-Za-z0-9_-]{6,30}$');

ALTER TABLE core.tasarim_sablon DROP CONSTRAINT IF EXISTS tasarim_sablon_durum_izinli;
ALTER TABLE core.tasarim_sablon ADD CONSTRAINT tasarim_sablon_durum_izinli
    CHECK (durum IN ('TASLAK', 'HAZIR', 'ARSIVDE'));

-- 🔴 TUTARLILIK KAPISI: tasarımı olmayan şablon HAZIR olamaz.
ALTER TABLE core.tasarim_sablon DROP CONSTRAINT IF EXISTS tasarim_sablon_hazir_tasarimli;
ALTER TABLE core.tasarim_sablon ADD CONSTRAINT tasarim_sablon_hazir_tasarimli
    CHECK (durum <> 'HAZIR' OR canva_id IS NOT NULL);

CREATE UNIQUE INDEX IF NOT EXISTS tasarim_sablon_kodu_tekil
    ON core.tasarim_sablon (sablon_kodu) WHERE sablon_kodu IS NOT NULL;

-- Eski satır: elimizdeki tek gerçek şablon HAZIR'a alınır.
UPDATE core.tasarim_sablon
   SET durum = 'HAZIR', sablon_kodu = 'SOCIAL_IG_POST_01',
       kategori = 'sosyal', platform = 'instagram', dpi = 72,
       beklenen_alanlar = '["baslik","alt_baslik","slogan","marka_satiri","site","urun_gorseli"]'::jsonb,
       en = 1080, boy = 1350, faz = 1,
       marka_kurallari = 'Metropolis tipografi; marka rengi #fbcfbb; koyu zemin; logo satırı üstte',
       mevzuat_kurallari = 'Tıbbi iddia yok; süre/yüzde beyanı yok; ambalaj AI ile yeniden çizilmez'
 WHERE canva_id = 'DAHV3allkCE';

-- Panel ve kadro için: şartname + üretilebilirlik bir arada.
CREATE OR REPLACE VIEW mart.tasarim_sablon_kutuk AS
SELECT sablon_id, sablon_kodu, is_turu, ad, kategori, platform, bicim,
       en, boy, en_mm, boy_mm, dpi, beklenen_alanlar, alan_haritasi,
       marka_kurallari, mevzuat_kurallari, surum, durum, motor,
       onay_zorunlu, faz, canva_id, aktif, eklendi,
       (durum = 'HAZIR' AND canva_id IS NOT NULL) AS uretilebilir,
       CASE WHEN en IS NOT NULL AND boy IS NOT NULL AND boy > 0
            THEN round((en::numeric / boy), 3) END AS oran
  FROM core.tasarim_sablon
 ORDER BY faz NULLS LAST, kategori, sablon_kodu;

GRANT SELECT ON mart.tasarim_sablon_kutuk TO ai_reader, ai_writer;

COMMIT;
