-- SAHA KONUM TAKİBİ
--
-- Sahip kararı 24.09.2026: saha elemanının konumu, panel açıkken periyodik
-- olarak kaydedilsin; yönetici "rotada mı" görebilsin.
--
-- 🔴 BU VERİ ÇALIŞANIN KİŞİSEL VERİSİDİR. Şirket adres listesi tutmakla aynı
-- şey değil. Sistemin kendisi üç şeyi zorunlu kılar, çünkü sonradan eklenen
-- koruma eklenmez:
--
--   1. SAKLAMA SÜRESİ. Kayıtlar `SAKLAMA_GUN` sonra silinir. Süresiz saklanan
--      konum geçmişi, ev adresini ve mesai dışı alışkanlıkları da anlatır --
--      toplanma amacıyla ilgisi olmayan bir bilgi.
--   2. KİŞİ KENDİ VERİSİNİ GÖREBİLİR. Takip edilenin göremediği bir kayıt,
--      denetlenemeyen bir kayıttır.
--   3. AÇIKÇA GÖRÜNÜR. Panel, konum paylaşımı açıkken bunu yazar. Sessiz
--      takip, kazara değil TASARIMLA önlenir.
--
-- Bunlar teknik tercih değil, bu veriyi tutmanın koşuludur.

BEGIN;

CREATE TABLE IF NOT EXISTS core.saha_konum (
  konum_id    bigserial PRIMARY KEY,
  kullanici   text NOT NULL,
  ts          timestamptz NOT NULL DEFAULT now(),
  enlem       double precision NOT NULL,
  boylam      double precision NOT NULL,
  dogruluk_m  numeric,
  hiz_m_s     numeric,
  -- TARAYICI: panelden gelir, telefon kilitlenince durur.
  -- OWNTRACKS: ayrı uygulama, arka planda da gönderir.
  kaynak      text NOT NULL DEFAULT 'TARAYICI'
              CHECK (kaynak IN ('TARAYICI', 'OWNTRACKS')),
  -- Hangi rota sırasında alındığı; "rotada mı" sorusu buna dayanır.
  rota_id     bigint REFERENCES core.saha_rota(rota_id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS saha_konum_kullanici_idx
  ON core.saha_konum (kullanici, ts DESC);
CREATE INDEX IF NOT EXISTS saha_konum_ts_idx ON core.saha_konum (ts);

COMMENT ON TABLE core.saha_konum IS
  'Saha elemani konum gecmisi. Calisanin KISISEL VERISI: saklama suresi sinirli, kisi kendi verisini gorebilir, panel takibi acikca gosterir.';

-- Son bilinen konum + o an rotada mı. Yönetici görünümü buradan okur.
CREATE OR REPLACE VIEW mart.saha_son_konum AS
 SELECT DISTINCT ON (k.kullanici)
        k.kullanici, k.ts, k.enlem, k.boylam, k.dogruluk_m, k.kaynak, k.rota_id,
        round(EXTRACT(epoch FROM now() - k.ts))::bigint AS kac_saniye_once,
        -- 🔴 "Bayat" ile "hareketsiz" AYNI DEĞİL. Telefon kilitlendiğinde
        -- tarayıcı konum göndermeyi durdurur; bu, kişinin durduğu anlamına
        -- GELMEZ. Panel de tam olarak bunu yazar.
        CASE WHEN now() - k.ts > interval '10 minutes' THEN 'BAYAT'
             ELSE 'TAZE' END AS tazelik
   FROM core.saha_konum k
  ORDER BY k.kullanici, k.ts DESC;

COMMIT;
