-- 024 — JARVİS KENDİ ÖNERİLERİNİN SONUCUNU OKUYABİLSİN (sahip kararı, 21.09.2026)
--
-- SORUN
-- DERSLER paneli `core.karar` (şirket karar defteri) üzerinden öğreniyor.
-- Jarvis'in KENDİ önerilerinin sonucu -- onaylandı mı, reddedildi mi --
-- öğrenme döngüsüne HİÇ girmiyordu, çünkü `core.ai_action_proposal`
-- ai_reader'a kapalı. `jarvis/memory.py` bunu kendi yorumunda yazıyor:
--   "Jarvis'in KENDI onerileri (core.ai_action_proposal) hala kapali --
--    ogrenme dongusunun o yarisi ayri bir izin isi."
-- Sahip o izni istedi.
--
-- 🔴 TABLO AÇILMIYOR, DAR BİR GÖRÜNÜM AÇILIYOR
-- `core.ai_action_proposal` kapalı KALIR. Yalnız sonucu öğrenmek için
-- gereken alanlar bir görünümde açılır. Dışarıda bırakılanlar ve sebepleri:
--
--   payload          İŞ İÇERİĞİ. Müşteri metni, fiyat, reklam kopyası
--                    burada. Öğrenme "hangi tip onaylanıyor" sorusuna
--                    bakar; içeriği okumasına gerek YOK. Kapalı kalır.
--   payload_hash     İçeriğe dolaylı köprü; gereksiz.
--   decision_reason  Sahibin ELİYLE yazdığı serbest metin. Ne yazacağı
--                    önceden bilinemez; öğrenmenin ona ihtiyacı yok.
--   proposed_by /
--   decided_by       Kimlik alanları. Tek kişilik işletmede ayrıca
--                    bilgi taşımıyor, açmanın karşılığı yok.
--   idempotency_key  Slug taşıyor, dolaylı olarak konuyu ele verir.
--
-- Açılanlar yalnız: eylem tipi, risk sınıfı, durum ve zaman damgaları.
--
-- 🔴 SALT OKUNUR. Yalnız SELECT verilir. Jarvis kendi önerisinin sonucunu
-- OKUYABİLİR, DEĞİŞTİREMEZ -- yoksa kendi karnesini kendi yazardı.
--
-- Geri alma: migrations/rollback/024_oneri_sonuc_ROLLBACK.sql

BEGIN;

CREATE OR REPLACE VIEW mart.ai_oneri_sonuc AS
SELECT
    p.action_id,
    p.task_id,
    p.action_type,
    p.risk_class,
    p.state,
    -- Öğrenme modülünün beklediği sözlüğe çevrilir (jarvis/learning.py:
    -- DECIDED / POSITIVE / PENDING kümeleri). Ham `state` de taşınır ki
    -- eşleme değişirse kaynağa dönülebilsin.
    CASE p.state
        WHEN 'PROPOSED'  THEN 'PROPOSED'
        WHEN 'APPROVED'  THEN 'APPROVED'
        WHEN 'EXECUTED'  THEN 'CONCLUDED'
        WHEN 'REJECTED'  THEN 'REJECTED'
        WHEN 'EXPIRED'   THEN 'CANCELLED'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        ELSE p.state
    END AS durum,
    p.proposed_at,
    p.decided_at,
    p.expires_at,
    -- Kaç saatte karara bağlandı. "Bekleyen öneri birikiyor mu" sorusunun
    -- cevabı; serbest metin taşımaz.
    CASE WHEN p.decided_at IS NULL THEN NULL
         ELSE round(EXTRACT(EPOCH FROM (p.decided_at - p.proposed_at)) / 3600.0, 2)
    END AS karar_saati
FROM core.ai_action_proposal p;

COMMENT ON VIEW mart.ai_oneri_sonuc IS
 'Jarvis''in kendi önerilerinin SONUCU. payload/decision_reason/kimlik '
 'alanları bilerek dışarıda. Salt okunur; öğrenme döngüsü içindir.';

GRANT SELECT ON mart.ai_oneri_sonuc TO ai_reader;

COMMIT;

