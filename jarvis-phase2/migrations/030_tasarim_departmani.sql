-- 030 — TASARIM DEPARTMANI: şablon kütüğü + iş defteri
--
-- Sahip 22.09.2026: *"jarvise canva ile ilgili ayrı bir sekme, ayrı
-- müdürlük ve teknik personeller verelim... ama gene bizim çalışanlarla
-- entegre olsun. Ben jarvise katalog istiyorum dediğimde markanın
-- çizgisinde, markanın görselleri ürün görselleri ile birlikte
-- yapılabilsin."*
--
-- İKİ TABLO, İKİ AYRI İŞ:
--   tasarim_sablon : hangi iş türü hangi Canva tasarımıyla üretilir ve
--                    o tasarımın hangi alanları doldurulur.
--   tasarim_isi    : ne üretildi, kimin isteğiyle, ne kadara, onaylandı mı.
--
-- 🔴 ŞABLON KÜTÜĞÜ KODA GÖMÜLMEZ. Şablon eklemek yeni sürüm gerektirmemeli;
-- sahibin "bir de raf etiketi istiyorum" demesiyle bir satır eklenmesi
-- arasında dağıtım olmamalı. Kod şablonu SEÇER, tanımlamaz.
--
-- 🔴 ALAN HARİTASI ŞABLONLA BİRLİKTE DURUR. Canva'daki alan adı
-- (`baslik`) ile bizim veri adımız (`urun_adi`) aynı olmak zorunda değil;
-- eşleme şablona aittir. Kodun içine gömülürse iki şablon aynı anda
-- yaşayamaz.
--
-- 🔴 İŞ DEFTERİ ONAYSIZ YAYINI ENGELLEMEZ, GÖRÜNÜR KILAR. Yayın kararı
-- zaten EXTERNAL_ACTIONS=false ile kapalı. Buradaki `onay` alanı,
-- üretilen her tasarımın insan onayından geçip geçmediğini KAYIT altına
-- alır; onaysızı "yayınlandı" saymayı imkânsızlaştırır.
--
-- 🔴 ai_writer ONAY YAZAMAZ. Diğer insan beyanı tabloları gibi
-- (kargo_karar, kreatif_karar, stok_sayim) onay sütununu yalnız
-- human_approver değiştirebilir; tetikleyici ile zorlanır.
--
-- Geri alma: migrations/rollback/030_tasarim_departmani_ROLLBACK.sql

BEGIN;

-- ─────────────────────────────────────────────── şablon kütüğü
CREATE TABLE IF NOT EXISTS core.tasarim_sablon (
    sablon_id    bigserial   PRIMARY KEY,
    -- 'instagram_post', 'katalog_sayfa', 'afis', 'raf_etiketi', 'poster'
    is_turu      text        NOT NULL,
    ad           text        NOT NULL,
    -- Canva tasarım kimliği (alanları işaretlenmiş olan).
    canva_id     text        NOT NULL,
    -- Canva alan adı -> bizim veri adımız. {"baslik": "urun_adi", ...}
    alan_haritasi jsonb      NOT NULL DEFAULT '{}'::jsonb,
    en           int,
    boy          int,
    -- Neden bu şablon? Seçimin gerekçesi kayıtta dursun.
    gerekce      text        NOT NULL,
    aktif        boolean     NOT NULL DEFAULT true,
    ekleyen      text        NOT NULL,
    eklendi      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tasarim_sablon_gerekce_dolu CHECK (length(trim(gerekce)) >= 12),
    CONSTRAINT tasarim_sablon_canva_id_bicim CHECK (canva_id ~ '^[A-Za-z0-9_-]{6,30}$')
);

-- Aynı iş türünde aynı tasarım iki kez kütüklenmesin.
CREATE UNIQUE INDEX IF NOT EXISTS tasarim_sablon_tekil
    ON core.tasarim_sablon (is_turu, canva_id);

-- ─────────────────────────────────────────────── iş defteri
CREATE TABLE IF NOT EXISTS core.tasarim_isi (
    is_id        bigserial   PRIMARY KEY,
    is_turu      text        NOT NULL,
    sablon_id    bigint      REFERENCES core.tasarim_sablon(sablon_id),
    -- İsteği kim/ne başlattı: 'sahip', 'haftalik_kreatif', 'kampanya'
    isteyen      text        NOT NULL,
    istek        text        NOT NULL,          -- sahibin cümlesi ya da brief
    -- Şablona gönderilen veri; sonradan "ne yazmıştık" sorusuna cevap.
    veri         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    canva_tasarim text,                          -- üretilen tasarımın kimliği
    disa_aktarim text,                           -- indirme bağlantısı / yol
    durum        text        NOT NULL DEFAULT 'URETILDI',
    -- Mevzuat/marka kapısından geçti mi, geçmediyse neden.
    denetim      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    maliyet_tl   numeric(10,4) NOT NULL DEFAULT 0,
    -- 🔴 İNSAN BEYANI. Yalnız human_approver yazabilir (tetikleyici).
    onay         text,                            -- ONAYLANDI | REDDEDILDI
    onaylayan    text,
    onaylandi    timestamptz,
    red_sebebi   text,
    uretildi     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tasarim_isi_durum_izinli
        CHECK (durum IN ('URETILDI', 'BASARISIZ', 'DENETIMDE', 'ARSIVLENDI')),
    CONSTRAINT tasarim_isi_onay_izinli
        CHECK (onay IS NULL OR onay IN ('ONAYLANDI', 'REDDEDILDI')),
    -- Red edildiyse sebebi yazılmak zorunda: "neden beğenilmedi" bir
    -- sonraki üretimin girdisidir; boş bırakılırsa öğrenme kopar.
    CONSTRAINT tasarim_isi_red_sebepli
        CHECK (onay IS DISTINCT FROM 'REDDEDILDI'
               OR length(trim(coalesce(red_sebebi, ''))) >= 8)
);

CREATE INDEX IF NOT EXISTS tasarim_isi_zaman ON core.tasarim_isi (uretildi DESC);
CREATE INDEX IF NOT EXISTS tasarim_isi_onaysiz
    ON core.tasarim_isi (uretildi DESC) WHERE onay IS NULL;

-- ─────────────────────────────────────────────── onay kapısı
CREATE OR REPLACE FUNCTION core.tasarim_isi_onay_kontrol()
RETURNS trigger LANGUAGE plpgsql AS $gate$
BEGIN
    IF NEW.onay IS DISTINCT FROM OLD.onay
       AND NEW.onay IS NOT NULL
       AND current_user <> 'human_approver' THEN
        RAISE EXCEPTION
            'tasarım onayını yalnız human_approver yazabilir (deneyen: %)',
            current_user;
    END IF;
    RETURN NEW;
END;
$gate$;

DROP TRIGGER IF EXISTS tasarim_isi_onay ON core.tasarim_isi;
CREATE TRIGGER tasarim_isi_onay
    BEFORE UPDATE ON core.tasarim_isi
    FOR EACH ROW EXECUTE FUNCTION core.tasarim_isi_onay_kontrol();

-- ─────────────────────────────────────────────── panel görünümü
CREATE OR REPLACE VIEW mart.tasarim_guncel AS
SELECT i.is_id, i.is_turu, s.ad AS sablon_adi, i.isteyen, i.istek,
       i.canva_tasarim, i.disa_aktarim, i.durum, i.denetim, i.maliyet_tl,
       i.onay, i.onaylayan, i.onaylandi, i.red_sebebi, i.uretildi,
       (i.onay IS NULL AND i.durum = 'URETILDI') AS onay_bekliyor
  FROM core.tasarim_isi i
  LEFT JOIN core.tasarim_sablon s USING (sablon_id)
 ORDER BY (i.onay IS NULL) DESC, i.uretildi DESC;

GRANT SELECT ON core.tasarim_sablon, core.tasarim_isi,
                mart.tasarim_guncel TO ai_reader;
-- Makine üretir ve defterine yazar; onay sütununa tetikleyici izin vermez.
GRANT SELECT, INSERT, UPDATE ON core.tasarim_isi TO ai_writer;
GRANT SELECT ON core.tasarim_sablon TO ai_writer;
GRANT USAGE ON SEQUENCE core.tasarim_isi_is_id_seq TO ai_writer;
-- Şablon kütüğüne ve onaya sahip karar verir.
GRANT SELECT, INSERT, UPDATE ON core.tasarim_sablon, core.tasarim_isi
    TO human_approver;
GRANT USAGE ON SEQUENCE core.tasarim_sablon_sablon_id_seq,
                        core.tasarim_isi_is_id_seq TO human_approver;

COMMIT;
