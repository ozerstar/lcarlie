-- 080 · Reklam yorumu "gizlendi" işareti (25.11.2026)
-- Sahip 25.11'de 7 yorumu Instagram'da gizledi; panel bunları hâlâ "cevapsız"
-- sayıyordu. Toplayıcı (jarvis/meta_reklam_detay.py, yalnız GET) Instagram
-- yorumunun `hidden` alanını okur ve buraya yazar.
--   gizli = true   Instagram'da gizlendi -> panelde soluk, cevapsız sayısına girmez
--   gizli = false  görünür
--   gizli = NULL   bilinmiyor (Facebook yorumu ya da alan gelmedi)
-- Kişisel veri sınıfı değişmez: yalnız jarvis_web (panel) okur, ai_reader YOK.
BEGIN;
ALTER TABLE raw.meta_reklam_yorum ADD COLUMN IF NOT EXISTS gizli boolean;
COMMENT ON COLUMN raw.meta_reklam_yorum.gizli IS
  'Instagram hidden alani (true=gizlendi). NULL=bilinmiyor. 080.';
-- Tablo düzeyindeki SELECT yeni sütunu da kapsar; açık yazılır ki 079'dan
-- bağımsız kurulumda da panel okuyabilsin.
GRANT SELECT (gizli) ON raw.meta_reklam_yorum TO jarvis_web;
COMMIT;
