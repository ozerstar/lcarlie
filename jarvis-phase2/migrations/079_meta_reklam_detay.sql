-- 079 META REKLAM DETAYI (17.11.2026)
-- Sahip: "hangi reklam hangisi kapali, basarili olanlar olmayanlar, ozellikler,
-- aciklamalar ... reklam bazli gormek istiyorum; o reklamlari da gormek
-- istiyorum, yorumlari da gormek istiyorum."
-- Yazan: scripts/meta-reklam-izle.py (saatlik :12) + jarvis/meta_reklam_detay.py.
-- Yalniz Meta GET; hicbir reklam ayari degismez.
-- Tekrar guvenli (IF NOT EXISTS).
BEGIN;

CREATE TABLE IF NOT EXISTS raw.meta_reklam_envanter (
  ad_id            text PRIMARY KEY,
  hesap_id         text,
  ad_adi           text,
  durum            text,          -- effective_status
  ayar_durum       text,          -- configured_status
  adset_id         text,
  adset_adi        text,
  adset_durum      text,
  kampanya_id      text,
  kampanya_adi     text,
  kampanya_durum   text,
  kampanya_amaci   text,
  olusturma        timestamptz,
  guncelleme       timestamptz,
  onizleme         text,          -- fb.me paylasilabilir onizleme
  red_sebep        jsonb,         -- ad_review_feedback
  sorunlar         jsonb,         -- issues_info
  kampanya         jsonb,         -- butce, baslangic/bitis
  adset            jsonb,         -- butce, optimizasyon, hedef kitle ozeti, yerlesimler
  kreatif          jsonb,         -- tum metin varyasyonlari, CTA, URL, varliklar, kartlar
  fb_gonderi_id    text,
  ig_medya_id      text,
  ig_baglanti      text,
  ig_yorum_sayaci  int,           -- Meta'nin comments_count sayaci
  ig_begeni        int,
  ig_yorum_durum   text,          -- OK | OKUNAMADI | YOK_GONDERI
  ig_yorum_sebep   text,
  fb_yorum_durum   text,
  fb_yorum_sebep   text,
  yorum_olcum_at   timestamptz,
  olcum_at         timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE raw.meta_reklam_envanter IS
  'Meta hesabindaki TUM reklamlar (kapali/reddedilen dahil), saatlik. Yorum okunamadiysa durum OKUNAMADI + sebep: "yorum yok" DEMEK DEGILDIR. 079.';

CREATE TABLE IF NOT EXISTS raw.meta_reklam_yorum (
  platform      text NOT NULL,     -- instagram | facebook
  yorum_id      text NOT NULL,
  medya_id      text NOT NULL,     -- ig medya id ya da fb gonderi id
  ust_yorum_id  text,              -- yanitsa ust yorum
  zaman         timestamptz,
  metin         text,              -- KISISEL VERI: yalniz panel; modele/log'a gitmez
  kullanici     text,              -- KISISEL VERI
  begeni        int,
  yanit_sayisi  int,
  bizden        boolean,           -- markanin kendi hesabi mi yazdi
  cevaplandi    boolean,           -- ust yorumsa: marka yanit vermis mi
  olcum_at      timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (platform, yorum_id)
);
CREATE INDEX IF NOT EXISTS meta_reklam_yorum_medya_idx ON raw.meta_reklam_yorum (medya_id);
COMMENT ON TABLE raw.meta_reklam_yorum IS
  'Reklam gonderisi yorumlari (saatlik). Kisisel veri: yalniz jarvis_web (panel) okur; ai_reader YETKISIZ. 079.';

-- Panel (jarvis_web) okur. ai_reader'a (model/oneri girdisi) yorum tablosu ACILMAZ.
GRANT USAGE ON SCHEMA raw TO jarvis_web;
GRANT SELECT ON raw.meta_reklam_envanter, raw.meta_reklam_yorum TO jarvis_web;

COMMIT;
