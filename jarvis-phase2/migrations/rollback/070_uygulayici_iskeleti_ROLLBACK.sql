-- 070 geri alma. Uygulanmis is kayitlari (ai_action_execution) silinmez.
BEGIN;
DROP FUNCTION IF EXISTS core.ai_sistem_onerisi(text,text,text,jsonb,text);
DROP FUNCTION IF EXISTS core.ai_action_tavan_dolu(text,numeric);
DROP TABLE IF EXISTS core.ai_action_tavan;
DROP FUNCTION IF EXISTS core.ai_claim_approved_action_tipli(text,integer,text[]);
DELETE FROM core.ai_orchestrator_config WHERE config_key='uygulayici_acik';
ALTER TABLE core.ai_task DROP CONSTRAINT ai_task_source_type_check;
ALTER TABLE core.ai_task ADD CONSTRAINT ai_task_source_type_check
  CHECK (source_type = ANY (ARRAY['ACIK_SORU','BULGU','KARAR','IC_MESAJ','MANUAL']));
COMMIT;
