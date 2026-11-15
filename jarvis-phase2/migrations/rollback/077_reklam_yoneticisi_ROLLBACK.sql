-- 077 geri al: yalniz bu gocun nesneleri. Oneri gecmisi silinir; onay
-- kuyruguna dusmus oneriler (core.ai_action_proposal) yerinde kalir.
BEGIN;
DROP TABLE IF EXISTS core.reklam_oneri;
DROP TABLE IF EXISTS core.reklam_oneri_kosu;
DROP VIEW IF EXISTS mart.reklam_urun_ekonomi;
DROP VIEW IF EXISTS mart.reklam_defter_tazelik;
DROP VIEW IF EXISTS mart.reklam_defter_gunluk;
DROP VIEW IF EXISTS mart.reklam_defter_satis;
DROP VIEW IF EXISTS mart.reklam_kreatif;
COMMIT;
