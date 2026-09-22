-- 027 GERİ ALMA
-- 🔴 Tablo, harcanmış paranın kaydını tutar. DROP demek, hangi gönderiye
-- kimin onay verdiğinin izini silmek demektir. Yalnız migrasyon o gün
-- yanlış uygulandıysa ve içinde gerçek karar yoksa çalıştırılır.
-- Önce bakın:  SELECT count(*) FROM core.kargo_karar;

BEGIN;

DROP VIEW IF EXISTS mart.kargo_karar_ozet;
DROP TABLE IF EXISTS core.kargo_karar;

COMMIT;
