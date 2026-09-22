-- 032 GERİ ALMA. Hatırlatıcı tablosunu düşürür.
-- 🔴 Veri kaybı: sahibin yazdığı tüm hatırlatıcılar silinir.
BEGIN;
DROP VIEW IF EXISTS mart.hatirlatici_guncel;
DROP TABLE IF EXISTS core.hatirlatici;
COMMIT;
