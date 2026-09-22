-- 033 geri alma: Jarvis artik bulgudan is acamaz.
-- Acilmis isler SILINMEZ; yalnizca yeni is acma yetkisi kalkar.
BEGIN;
DROP FUNCTION IF EXISTS core.ai_bulgu_gorev_ac(text, text, integer);
COMMIT;
