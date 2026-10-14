-- =============================================================================
-- L'CARLIE — INSTAGRAM ORGANIK ICERIK (20.09.2026)
--
-- NEDEN: CONTENT, SOCIAL, INSTAGRAM ve ART departmanlarinin veri kaynagi YOKTU
-- ve bu yuzden dordu de 'YOK' durumundaydi. Reklam tarafi olculuyordu, organik
-- taraf hic okunmuyordu. Hesapta 120 gonderi duruyor (06.05.2026'dan beri).
--
-- 🔴 NE ALINAMIYOR, ACIKCA: erisim/gosterim/kaydetme (insights) ve etiketlenme
--    (/tags) uclari "(#10) Application does not have permission" ile reddediliyor
--    -- instagram_manage_insights izni App Review ister. Bu yuzden:
--      * ETKILESIM = begeni + yorum. Bu ORAN DEGIL, SAYIDIR; erisim bilinmeden
--        "etkilesim orani" hesaplanamaz ve hesaplanmis gibi gosterilmez.
--      * UGC departmani bu veriyle ACILMAZ; /tags kapali oldugu icin baskasinin
--        bizi etiketledigi icerik gorunmuyor.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.ig_medya (
  medya_id     text PRIMARY KEY,
  ig_user_id   text NOT NULL,
  tur          text,               -- IMAGE | VIDEO | CAROUSEL_ALBUM
  urun_tipi    text,               -- FEED | REELS | STORY
  metin        text,               -- caption (kendi metnimiz)
  zaman        timestamptz,
  begeni       bigint,
  yorum        bigint,
  baglanti     text,
  kucuk_gorsel text,
  ham          jsonb NOT NULL DEFAULT '{}'::jsonb,
  cekim_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ig_medya_zaman_idx ON raw.ig_medya (zaman DESC);
CREATE INDEX IF NOT EXISTS ig_medya_tur_idx   ON raw.ig_medya (urun_tipi, zaman DESC);

-- ---------------------------------------------------------------------------
-- ICERIK PERFORMANSI
-- 🔴 "En iyi gonderi" ILAN EDILMEZ. Erisim bilinmedigi icin yuksek begeni,
--    iyi icerik mi yoksa o gun daha cok kisiye mi gosterildi ayirt edilemez.
--    Gorunum bunu her satirda tasir.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS mart.icerik_performans CASCADE;
CREATE VIEW mart.icerik_performans AS
SELECT
  m.medya_id,
  m.zaman,
  (m.zaman AT TIME ZONE 'Europe/Istanbul')::date          AS gun,
  coalesce(m.urun_tipi, m.tur)                            AS bicim,
  m.tur,
  left(coalesce(m.metin,''), 120)                         AS icerik_basi,
  length(coalesce(m.metin,''))                            AS icerik_uzunluk,
  -- Hashtag sayimi: '#' ile baslayan kelimeler.
  (SELECT count(*) FROM regexp_matches(coalesce(m.metin,''), '#[[:alnum:]_]+', 'g')) AS etiket_sayisi,
  -- 🔴 Mevzuat izi: "reklam"/"tanitim" ibaresi ve YZ beyani var mi. Reklam
  --    iceren gonderide ibare zorunlulugu var; bu alan denetimi kolaylastirir.
  (coalesce(m.metin,'') ~* '#?(reklam|tanitim|tanıtım|isbirligi|işbirliği)')      AS reklam_ibaresi,
  (coalesce(m.metin,'') ~* 'yapay zek')                                          AS yz_beyani,
  coalesce(m.begeni,0)                                    AS begeni,
  coalesce(m.yorum,0)                                     AS yorum,
  coalesce(m.begeni,0) + coalesce(m.yorum,0)              AS etkilesim,
  m.baglanti,
  -- Her satirda tasinan durus: sayidir, oran degildir.
  'ERISIM_YOK_ORAN_HESAPLANAMAZ'::text                    AS olcum_sinirI
FROM raw.ig_medya m;

GRANT SELECT ON mart.icerik_performans TO ai_reader;
