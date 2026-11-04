-- =============================================================================
-- jarvis_web -> raw.wix_urun SUTUN YETKISI  (03.11.2026)
--
-- 🔴 NEDEN: gelen_kutusu._URUN_SQL urun sayfasi linki icin raw.wix_urun'a
--    LEFT JOIN yapiyor ama jarvis_web'in bu tabloda hic yetkisi yoktu.
--    Sonuc: urun gecen her konusmada musteri cevabi taslagi
--    "permission denied for table wix_urun" ile dusuyordu (03.11'de
--    WhatsApp konusmasi uzerinde kuru calistirmayla olculdu).
--
-- 🔴 YALNIZ GEREKEN UC SUTUN. Tablo yetkisi degil sutun yetkisi verilir;
--    sorgu bunlardan fazlasini okumuyor.
-- =============================================================================
GRANT USAGE ON SCHEMA raw TO jarvis_web;
GRANT SELECT (urun_id, slug, gorunur) ON raw.wix_urun TO jarvis_web;
