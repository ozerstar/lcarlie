-- 074 · Görsel onayları (sahip isteği 05.11.2026)
-- Sahip üretilen görselleri sağa (beğendi) / sola (beğenmedi) kaydırır.
-- Beğenmeme nedenleri kalıcıdır: jarvis/gorsel_tercih.py bunları okuyup
-- yeni görsel istemine "kaçınılacaklar" olarak ekler.
BEGIN;

CREATE TABLE IF NOT EXISTS core.gorsel_onay (
    onay_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kaynak       text NOT NULL CHECK (kaynak IN ('tarayici', 'kreatif', 'ig')),
    anahtar      text NOT NULL UNIQUE,          -- panel yolu: tarayici/…, kreatif/…, gonderi-gorsel/…
    baslik       text NOT NULL DEFAULT '',
    karar        text NOT NULL CHECK (karar IN ('BEGENDI', 'BEGENMEDI')),
    nedenler     text[] NOT NULL DEFAULT '{}',
    yorum        text NOT NULL DEFAULT '' CHECK (length(yorum) <= 1000),
    karar_veren  text NOT NULL,
    karar_zamani timestamptz NOT NULL DEFAULT clock_timestamp(),
    -- Beğenilmeyen görselin nedeni olmadan kaydı anlamsızdır: öğrenilecek bir şey kalmaz.
    CONSTRAINT gorsel_onay_neden CHECK (karar = 'BEGENDI' OR cardinality(nedenler) > 0 OR length(btrim(yorum)) >= 3)
);
CREATE INDEX IF NOT EXISTS gorsel_onay_karar_idx ON core.gorsel_onay (karar, karar_zamani DESC);

GRANT SELECT, INSERT, UPDATE ON core.gorsel_onay TO jarvis_web;
GRANT USAGE ON SEQUENCE core.gorsel_onay_onay_id_seq TO jarvis_web;
GRANT SELECT ON core.gorsel_onay TO ai_reader;

COMMIT;
