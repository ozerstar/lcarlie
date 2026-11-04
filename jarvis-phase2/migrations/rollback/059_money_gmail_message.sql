-- Yalnız şema geri alınır; silinen ikiz KMH satırları yedekten (.backup) değil, ekstre yeniden yüklenerek gelir.
BEGIN;
REVOKE UPDATE (gmail_message, line_count) ON core.jarvis_money_upload FROM jarvis_web;
DROP INDEX IF EXISTS core.jarvis_money_upload_gmail;
ALTER TABLE core.jarvis_money_upload DROP COLUMN IF EXISTS gmail_message;
COMMIT;
