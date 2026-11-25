-- 25.11.2026: blog hattı metin işleri (chatgpt_chat) tam yazıyı/çeviriyi istemde
-- taşır; 8.000 karakter tavanı chatgpt_chat için 60.000'e çıkarılır. Görsel
-- istemleri jarvis/tarayici.py'de 8.000'de kalır.
BEGIN;
ALTER TABLE core.tarayici_isi DROP CONSTRAINT tarayici_isi_istem_check;
ALTER TABLE core.tarayici_isi ADD CONSTRAINT tarayici_isi_istem_check
  CHECK (btrim(istem) <> '' AND length(istem) <= 60000);
COMMIT;
