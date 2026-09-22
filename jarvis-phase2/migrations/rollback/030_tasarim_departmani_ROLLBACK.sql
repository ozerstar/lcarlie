-- 030 GERİ ALMA. Tabloları düşürür.
-- 🔴 Veri kaybı: üretilmiş tasarımların defteri ve şablon kütüğü silinir.
-- Canva'daki tasarımlar SİLİNMEZ; yalnız bizim kaydımız gider.
BEGIN;
DROP VIEW IF EXISTS mart.tasarim_guncel;
DROP TRIGGER IF EXISTS tasarim_isi_onay ON core.tasarim_isi;
DROP FUNCTION IF EXISTS core.tasarim_isi_onay_kontrol();
DROP TABLE IF EXISTS core.tasarim_isi;
DROP TABLE IF EXISTS core.tasarim_sablon;
COMMIT;
