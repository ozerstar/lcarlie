-- Eczane WhatsApp kampanyası: gönderim defteri (13.11.2026).
-- Sahip: "Ankara'daki tüm eczanelere WhatsApp, banlanmayacak düzenle",
-- "sabah 10 akşam 6'ya kadar dakikada 1", "geri dönüşleri de not et".
BEGIN;
CREATE TABLE IF NOT EXISTS core.eczane_gonderim (
  id           bigserial PRIMARY KEY,
  hedef_id     bigint NOT NULL REFERENCES core.eczane_hedef(id),
  kanal        text NOT NULL DEFAULT 'whatsapp',
  telefon      text NOT NULL,                 -- 90XXXXXXXXXX
  sablon       text,
  wamid        text UNIQUE,
  durum        text NOT NULL CHECK (durum IN ('GONDERILDI','SENT','DELIVERED','READ','FAILED','REDDEDILDI')),
  hata_kodu    text,
  hata         text,
  gonderildi   timestamptz NOT NULL DEFAULT now(),
  guncellendi  timestamptz NOT NULL DEFAULT now()
);
-- Aynı numaraya kampanya başına TEK mesaj (iki hedef aynı numarayı paylaşabilir).
CREATE UNIQUE INDEX IF NOT EXISTS eczane_gonderim_tek_numara
  ON core.eczane_gonderim (kanal, telefon, sablon) WHERE durum <> 'REDDEDILDI';
CREATE INDEX IF NOT EXISTS eczane_gonderim_gun ON core.eczane_gonderim (gonderildi);
COMMIT;
