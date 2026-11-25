-- BLOG HATTI kuyruğu (25.11.2026). scripts/blog-hatti.py yazar (n8n/root),
-- panel (jarvis_web) ve Company Memory (ai_reader) yalnız okur.
BEGIN;

CREATE TABLE IF NOT EXISTS core.blog_kuyruk (
  id            bigserial PRIMARY KEY,
  slug          text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]{3,90}$'),
  kaynak        text NOT NULL CHECK (kaynak IN ('HAZIR','PLAN','GSC')),
  plan_no       text,
  oncelik       integer NOT NULL DEFAULT 500,
  konu          text NOT NULL,
  tur           text NOT NULL DEFAULT 'NEW' CHECK (tur IN ('NEW','REFRESH')),
  mevcut_slug   text,                       -- REFRESH: korunacak canlı adres
  kategori_id   text,
  durum         text NOT NULL DEFAULT 'BEKLIYOR' CHECK (durum IN
                ('BEKLIYOR','YAZILDI','GORSEL_BEKLIYOR','GORSEL_HAZIR','YAYINLANDI','INSANA','HATA')),
  deneme        integer NOT NULL DEFAULT 0,
  gorsel_deneme integer NOT NULL DEFAULT 0,
  hata          text,
  bekleme_sebebi text,                      -- INSANA / bekleme gerekçesi (sahibe giden cümle)
  kaynak_dosya  text,
  kaynak_sha    text,
  icerik        jsonb NOT NULL DEFAULT '{}',  -- tr: baslik, seo_baslik, meta, html, faq_jsonld, gorsel brifi, kesitler
  ceviriler     jsonb NOT NULL DEFAULT '{}',  -- {en:{baslik,seo_baslik,meta,slug,html,faq_jsonld,kapak_metni}, ...}
  gorsel        jsonb NOT NULL DEFAULT '{}',  -- tarayici is_id, sahne yolu, kapak/ic dosyaları, wix medya id'leri
  wix           jsonb NOT NULL DEFAULT '{}',  -- {tr:{post_id,url,slug}, en:{...}, yedek, yonlendirme}
  kapilar       jsonb NOT NULL DEFAULT '{}',  -- kapı sonuçları (kelime, yapı, iddia, kaynak, canlı denetim)
  gecmis        jsonb NOT NULL DEFAULT '{}',  -- zaman damgalı olay defteri
  olusturuldu   timestamptz NOT NULL DEFAULT now(),
  guncellendi   timestamptz NOT NULL DEFAULT now(),
  yayinlandi    timestamptz
);

CREATE INDEX IF NOT EXISTS blog_kuyruk_durum_ix ON core.blog_kuyruk (durum, oncelik, id);

GRANT SELECT ON core.blog_kuyruk TO jarvis_web;
GRANT SELECT ON core.blog_kuyruk TO ai_reader;

-- Panel/ekip için içerik gövdesi olmadan özet görünüm.
CREATE OR REPLACE VIEW mart.blog_hatti_ozet AS
SELECT slug, kaynak, plan_no, oncelik, konu, tur, durum, deneme, gorsel_deneme,
       left(coalesce(hata, bekleme_sebebi, ''), 300) AS sebep,
       (wix -> 'tr' ->> 'url') AS tr_url,
       (SELECT count(*) FROM jsonb_object_keys(wix) k WHERE k IN ('tr','en','de','ru','ar')
          AND wix -> k ->> 'url' IS NOT NULL) AS yayinli_dil,
       guncellendi, yayinlandi
  FROM core.blog_kuyruk;

GRANT SELECT ON mart.blog_hatti_ozet TO jarvis_web;
GRANT SELECT ON mart.blog_hatti_ozet TO ai_reader;

COMMIT;
