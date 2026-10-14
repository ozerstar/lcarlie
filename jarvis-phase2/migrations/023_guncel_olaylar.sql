-- 023 — Güncel Olaylar departmanı: her gün dış dünyadan önemli haberler
--
-- NEDEN VAR
-- Sahip Türkiye genel haber analizi istemişti ve HİÇ ÜRETİLMEMİŞTİ. Sebep
-- ölçüldü (20.09.2026): araştırma katmanı sessizce ölüydü -- tek arama arka
-- ucu DuckDuckGo'nun anahtarsız HTML ucuydu ve bu sunucunun IP'sinden
-- HTTP 202 + bot-engelleme sayfası dönüyordu, 0 sonuç. Yani "araştır"
-- denince sistem çalışıyor görünüp boş dönüyordu. Gemini grounding'e
-- geçilince gerçek kaynaklar gelmeye başladı; bu tablo o çıktının yeri.
--
-- 🔴 KAYNAKSIZ CÜMLE YAZILMAZ
-- Her madde en az bir URL taşır. Model yorum yapabilir ama olguyu
-- kaynaktan alır; kaynağı olmayan madde kaydedilmez. Bülten "dolu görünsün"
-- diye uydurulmuş bir haber, hiç bülten olmamasından kötüdür.
--
-- 🔴 "HABER YOK" AYRI BİR DURUMDUR
-- Araştırma boş dönerse `durum='KAYNAK_YOK'` yazılır ve bülten boş gösterilir.
-- Satırın hiç olmaması "o gün çalışmadı" demektir; ikisi karıştırılmamalı --
-- bu projede bir cron'un iki gün ölü kalması tam bu yüzden fark edilmemişti.

\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS core.guncel_olay (
  id          bigserial PRIMARY KEY,
  gun         date        NOT NULL,
  aci         text        NOT NULL,        -- ekonomi | sektor | duzenleme ...
  baslik      text        NOT NULL,
  ozet        text        NOT NULL,
  neden_onemli text,                       -- BİZE etkisi; model yorumu
  kaynak_url  text        NOT NULL,        -- 🔴 zorunlu: kaynaksız madde yok
  kaynak_adi  text,
  yayin_tarihi text,
  onem        text        NOT NULL DEFAULT 'BILGI'
              CHECK (onem IN ('KRITIK','DIKKAT','BILGI')),
  olusturma   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT guncel_olay_tekil UNIQUE (gun, kaynak_url)
);

CREATE TABLE IF NOT EXISTS core.guncel_olay_kosu (
  gun         date PRIMARY KEY,
  durum       text        NOT NULL CHECK (durum IN ('URETILDI','KAYNAK_YOK','HATA')),
  aci_sayisi  integer     NOT NULL DEFAULT 0,
  kaynak_sayisi integer   NOT NULL DEFAULT 0,
  madde_sayisi  integer   NOT NULL DEFAULT 0,
  model       text,
  sure_sn     numeric,
  not_metni   text,
  olusturma   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.guncel_olay_kosu IS
  'Günün koşu kaydı. Satır YOKSA o gün hiç çalışmadı; durum=KAYNAK_YOK ise '
  'çalıştı ama kaynak bulamadı. İkisi ayrı şeydir.';

CREATE OR REPLACE VIEW mart.guncel_olaylar AS
SELECT o.gun, o.aci, o.onem, o.baslik, o.ozet, o.neden_onemli,
       o.kaynak_url, o.kaynak_adi, o.yayin_tarihi, o.olusturma,
       k.durum AS gun_durumu, k.model, k.kaynak_sayisi
FROM core.guncel_olay o
LEFT JOIN core.guncel_olay_kosu k ON k.gun = o.gun
ORDER BY o.gun DESC,
         CASE o.onem WHEN 'KRITIK' THEN 0 WHEN 'DIKKAT' THEN 1 ELSE 2 END,
         o.aci;

COMMENT ON VIEW mart.guncel_olaylar IS
  'Güncel Olaylar departmanının günlük bülteni. Her madde kaynak URL taşır.';

GRANT SELECT ON mart.guncel_olaylar TO ai_reader;
GRANT SELECT ON core.guncel_olay_kosu TO ai_reader;

COMMIT;
