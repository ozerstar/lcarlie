-- 076 META REKLAM IZLEME (15.11.2026)
--
-- Sahip 15.11: "Jarvis'in Meta reklam API'sine erisimi var, surekli kontrol
-- etsin." Gunluk ETL (raw.meta_reklam, 08:30) bir gun gecikmeli ve yerlesim
-- kirilimi yok. Bu tablolar SAATLIK izleyicinin (scripts/meta-reklam-izle.py)
-- yazdigi yerdir.
--
-- 🔴 YALNIZ OKUMA. Izleyici Meta'da hicbir ayari degistirmez; bu tablolar da
--    yalniz olculeni tutar.
-- 🔴 Okunamayan kaynak SIFIR yazilmaz: kosu satirinda durum=HATA/KISMI kalir,
--    reklam satiri hic olusmaz.
-- 🔴 reach/frekans toplanamaz (ayni kisi iki gunde/iki yerlesimde sayilir).
--    Gorunumler bu iki alani TOPLAMAZ; gunluk satirda oldugu gibi verir.
--
-- Geri alma: migrations/rollback/076_meta_izleme_ROLLBACK.sql

BEGIN;

-- 1) Reklam x gun. Her kosu bugunu + onceki iki gunu yeniden yazar (Meta gec
--    gelen donusumleri geriye dogru isler).
CREATE TABLE IF NOT EXISTS raw.meta_izleme_reklam (
    gun              date        NOT NULL,
    ad_id            text        NOT NULL,
    hesap_id         text        NOT NULL,
    kampanya_id      text,
    kampanya_adi     text,
    kampanya_amaci   text,          -- objective (OUTCOME_SALES, OUTCOME_TRAFFIC...)
    adset_id         text,
    adset_adi        text,
    optimizasyon     text,          -- optimization_goal
    ad_adi           text,
    durum            text,          -- reklamin effective_status (olcum anindaki)
    adset_durum      text,
    kampanya_durum   text,
    gunluk_butce     numeric(14,2), -- reklam setinin gunluk butcesi (TL), yoksa NULL
    harcama          numeric(14,2) NOT NULL DEFAULT 0,
    gosterim         bigint        NOT NULL DEFAULT 0,
    erisim           bigint,
    frekans          numeric(10,4),
    tiklama          bigint        NOT NULL DEFAULT 0,  -- tum tiklamalar
    link_tiklama     bigint        NOT NULL DEFAULT 0,  -- inline_link_clicks
    ctr              numeric(10,4),                     -- baglanti CTR %
    tbm              numeric(14,4),                     -- baglanti tiklama basi maliyet TL
    cpm              numeric(14,4),
    sepete_ekle      integer       NOT NULL DEFAULT 0,
    odeme_baslat     integer       NOT NULL DEFAULT 0,
    satin_alma       integer       NOT NULL DEFAULT 0,
    satin_alma_degeri numeric(14,2) NOT NULL DEFAULT 0, -- Meta'nin IDDIASI, defter degil
    mesaj_baslat     integer       NOT NULL DEFAULT 0,  -- messaging_conversation_started_7d
    sayfa_goruntule  integer       NOT NULL DEFAULT 0,  -- landing_page_view
    eylemler         jsonb         NOT NULL DEFAULT '[]'::jsonb,
    eylem_degerleri  jsonb         NOT NULL DEFAULT '[]'::jsonb,
    olcum_at         timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (gun, ad_id)
);
CREATE INDEX IF NOT EXISTS meta_izleme_reklam_adset ON raw.meta_izleme_reklam (adset_id, gun);
CREATE INDEX IF NOT EXISTS meta_izleme_reklam_kampanya ON raw.meta_izleme_reklam (kampanya_id, gun);

-- 2) Reklam x gun x yerlesim (publisher_platform + platform_position).
CREATE TABLE IF NOT EXISTS raw.meta_izleme_yerlesim (
    gun          date   NOT NULL,
    ad_id        text   NOT NULL,
    yayinci      text   NOT NULL,   -- facebook / instagram / audience_network / messenger / threads
    konum        text   NOT NULL,   -- feed / instagram_stories / instagram_reels / an_classic ...
    hesap_id     text   NOT NULL,
    kampanya_id  text,
    adset_id     text,
    harcama      numeric(14,2) NOT NULL DEFAULT 0,
    gosterim     bigint        NOT NULL DEFAULT 0,
    tiklama      bigint        NOT NULL DEFAULT 0,
    link_tiklama bigint        NOT NULL DEFAULT 0,
    sepete_ekle  integer       NOT NULL DEFAULT 0,
    satin_alma   integer       NOT NULL DEFAULT 0,
    olcum_at     timestamptz   NOT NULL DEFAULT now(),
    PRIMARY KEY (gun, ad_id, yayinci, konum)
);
CREATE INDEX IF NOT EXISTS meta_izleme_yerlesim_yayinci ON raw.meta_izleme_yerlesim (yayinci, gun);

-- 3) Her kosu bir satir: "veri yok" ile "soramadim" burada ayrilir.
CREATE TABLE IF NOT EXISTS raw.meta_izleme_kosu (
    id             bigserial PRIMARY KEY,
    bas_at         timestamptz NOT NULL DEFAULT now(),
    bit_at         timestamptz,
    durum          text NOT NULL CHECK (durum IN ('SURUYOR','TAMAM','KISMI','HATA')),
    aralik_bas     date,
    aralik_bit     date,
    reklam_satir   integer,
    yerlesim_satir integer,
    uyari_sayisi   integer,
    yeni_uyari     integer,
    bildirim       text,          -- hangi yollar ulasti (push,eposta) ya da neden ulasmadi
    hata           text
);

-- 4) Uyari defteri: ayni uyari iki kez bildirilmez.
CREATE TABLE IF NOT EXISTS raw.meta_izleme_uyari (
    anahtar       text PRIMARY KEY,
    kural         text NOT NULL,   -- AN_HARCAMA / HARCAMA_SATIS / SET_SONUCSUZ / OKUNAMADI
    seviye        text NOT NULL CHECK (seviye IN ('KRITIK','UYARI','BILGI')),
    metin         text NOT NULL,
    oneri         text,            -- yalniz ONERI; hicbir ayar otomatik degismez
    veri          jsonb NOT NULL DEFAULT '{}'::jsonb,
    ilk_at        timestamptz NOT NULL DEFAULT now(),
    son_at        timestamptz NOT NULL DEFAULT now(),
    bildirildi_at timestamptz,
    kanallar      text
);

-- 5) Reklam (kreatif) sayfasinin okuyacagi gorunum: gunluk performans +
--    kreatif ustverisi (raw.meta_kreatif, gunluk ETL) tek satirda.
CREATE OR REPLACE VIEW mart.meta_kreatif_gunluk AS
SELECT r.gun, r.hesap_id, r.kampanya_id, r.kampanya_adi, r.kampanya_amaci,
       r.adset_id, r.adset_adi, r.optimizasyon, r.ad_id, r.ad_adi,
       r.durum, r.adset_durum, r.kampanya_durum, r.gunluk_butce,
       r.harcama, r.gosterim, r.erisim, r.frekans, r.tiklama, r.link_tiklama,
       r.ctr, r.tbm, r.cpm, r.sepete_ekle, r.odeme_baslat, r.satin_alma,
       r.satin_alma_degeri, r.mesaj_baslat, r.sayfa_goruntule,
       COALESCE(y.an_harcama, 0) AS an_harcama,
       k.kreatif_id, k.kreatif_adi, k.baslik, k.govde, k.cta, k.nesne_tipi,
       k.kucuk_gorsel, k.video_id, k.hedef_url,
       r.olcum_at
FROM raw.meta_izleme_reklam r
LEFT JOIN raw.meta_kreatif k ON k.ad_id = r.ad_id
LEFT JOIN (SELECT gun, ad_id, sum(harcama) AS an_harcama
           FROM raw.meta_izleme_yerlesim
           WHERE yayinci = 'audience_network'
           GROUP BY gun, ad_id) y ON y.gun = r.gun AND y.ad_id = r.ad_id;

-- 6) Kreatif ozeti: son 7 ve 30 gun, reklam basina. reach/frekans YOK
--    (toplanamaz).
CREATE OR REPLACE VIEW mart.meta_kreatif_ozet AS
SELECT ad_id,
       max(ad_adi) AS ad_adi, max(adset_adi) AS adset_adi, max(kampanya_adi) AS kampanya_adi,
       (array_agg(durum ORDER BY gun DESC))[1] AS son_durum,
       max(gun) AS son_gun,
       sum(harcama)     FILTER (WHERE gun > current_date - 7)  AS harcama_7g,
       sum(gosterim)    FILTER (WHERE gun > current_date - 7)  AS gosterim_7g,
       sum(link_tiklama) FILTER (WHERE gun > current_date - 7) AS link_tiklama_7g,
       sum(sepete_ekle) FILTER (WHERE gun > current_date - 7)  AS sepete_ekle_7g,
       sum(satin_alma)  FILTER (WHERE gun > current_date - 7)  AS satin_alma_7g,
       sum(an_harcama)  FILTER (WHERE gun > current_date - 7)  AS an_harcama_7g,
       sum(harcama)     FILTER (WHERE gun > current_date - 30) AS harcama_30g,
       sum(gosterim)    FILTER (WHERE gun > current_date - 30) AS gosterim_30g,
       sum(link_tiklama) FILTER (WHERE gun > current_date - 30) AS link_tiklama_30g,
       sum(sepete_ekle) FILTER (WHERE gun > current_date - 30) AS sepete_ekle_30g,
       sum(satin_alma)  FILTER (WHERE gun > current_date - 30) AS satin_alma_30g,
       round(100.0 * sum(link_tiklama) FILTER (WHERE gun > current_date - 7)
             / NULLIF(sum(gosterim) FILTER (WHERE gun > current_date - 7), 0), 3) AS ctr_7g,
       round(sum(harcama) FILTER (WHERE gun > current_date - 7)
             / NULLIF(sum(link_tiklama) FILTER (WHERE gun > current_date - 7), 0), 3) AS tbm_7g,
       max(kucuk_gorsel) AS kucuk_gorsel, max(baslik) AS baslik, max(govde) AS govde,
       max(cta) AS cta, max(hedef_url) AS hedef_url, max(olcum_at) AS olcum_at
FROM mart.meta_kreatif_gunluk
GROUP BY ad_id;

-- 7) Yerlesim ozeti (gun x yayinci x konum).
CREATE OR REPLACE VIEW mart.meta_yerlesim_gunluk AS
SELECT gun, yayinci, konum, count(DISTINCT ad_id) AS reklam,
       sum(harcama) AS harcama, sum(gosterim) AS gosterim,
       sum(link_tiklama) AS link_tiklama, sum(sepete_ekle) AS sepete_ekle,
       sum(satin_alma) AS satin_alma
FROM raw.meta_izleme_yerlesim
GROUP BY gun, yayinci, konum;

-- Panel (jarvis_web) ve okuyucu (ai_reader) yalniz okur.
GRANT USAGE ON SCHEMA raw, mart TO jarvis_web, ai_reader;
GRANT SELECT ON raw.meta_izleme_reklam, raw.meta_izleme_yerlesim,
                raw.meta_izleme_kosu, raw.meta_izleme_uyari,
                mart.meta_kreatif_gunluk, mart.meta_kreatif_ozet,
                mart.meta_yerlesim_gunluk
             TO jarvis_web, ai_reader;
-- Gorunum raw.meta_kreatif'i de okur; gorunum sahibinin yetkisiyle calisir,
-- ek GRANT gerekmez.

COMMIT;
