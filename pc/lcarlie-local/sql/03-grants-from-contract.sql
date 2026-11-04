-- lcarlie YEREL: yetkiler. Dump --no-acl ile alindigi icin uretimdeki GRANT'lar dump'ta YOK.
-- Buradaki her GRANT su kaynaklardan birine dayanir (ek yetki uydurulmadi):
--   DB_CONTRACT.md : ai_writer -> ai_claim_task, ai_log_provider_attempt,
--                    ai_complete_task_with_proposed_decision, ai_fail_task
--                    ai_reader -> context_queries.sql icindeki statik SELECT'ler
--   f4-apply.sql   : ai_propose_action -> ai_writer; ai_decide_action, ai_get_pending_actions -> human_approver
--   f4-enqueue.sql : ai_enqueue_task -> human_approver
--   f5-apply.sql   : ai_claim_approved_action, ai_complete_action_execution -> action_executor
--                    (f5 rollback'i "REVOKE USAGE ON SCHEMA core FROM action_executor" icerir -> USAGE vardi)
--   f6-apply.sql   : ai_claim_task -> ai_writer; ai_orchestrator_health -> ai_reader
-- Dump'taki diger (f6 sonrasi) ai_* fonksiyonlarina yetki VERILMEDI: kapali-varsayilan.
BEGIN;
-- Restore edilen fonksiyonlar varsayilan olarak PUBLIC'e EXECUTE verir; SECURITY DEFINER oldugu icin kapat.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA core, mart, raw, saha, lcarlie, ai_semantic, mem0 FROM PUBLIC;
REVOKE ALL ON SCHEMA core, mart, raw, saha, lcarlie, ai_semantic, mem0 FROM PUBLIC;
-- SECURITY DEFINER OLMAYAN fonksiyonlar cagiranin yetkisiyle calisir; PG varsayilani olan PUBLIC EXECUTE'u
-- bunlara geri ver (or. mart.kesim() mart view'lari icinde kullaniliyor; yoksa ai_reader view okuyamaz).
DO $$
DECLARE f regprocedure;
BEGIN
  FOR f IN SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname IN ('core','mart','raw','saha','lcarlie','ai_semantic','mem0') AND NOT p.prosecdef AND p.prokind='f'
  LOOP EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO PUBLIC', f); END LOOP;
END $$;

-- function_owner (SECURITY DEFINER sahibi) icin asgari erisim. Dosyalarda yazili DEGIL; uretimde
-- F0-B ile verilmis olmasi gereken, sozlesme fonksiyonlarinin calismasi icin zorunlu en kucuk set:
--   core semasi USAGE + ai_complete_task_with_proposed_decision'in yazdigi core.karar (sahibi n8n).
--   + ai_log_provider_attempt'in yazdigi core.ai_calisma_log (sahibi n8n).
GRANT USAGE ON SCHEMA core TO function_owner;
GRANT SELECT, INSERT ON core.karar TO function_owner;
GRANT INSERT ON core.ai_calisma_log TO function_owner;
DO $$
DECLARE s text;
BEGIN
  FOR s IN SELECT pg_get_serial_sequence(t, a.attname)
             FROM unnest(ARRAY['core.karar','core.ai_calisma_log']) t
             JOIN pg_attribute a ON a.attrelid=t::regclass AND a.attnum>0
            WHERE pg_get_serial_sequence(t, a.attname) IS NOT NULL
  LOOP EXECUTE format('GRANT USAGE ON SEQUENCE %s TO function_owner', s); END LOOP;
END $$;

GRANT USAGE ON SCHEMA core TO ai_reader, ai_writer, human_approver, action_executor;
GRANT USAGE ON SCHEMA mart TO ai_reader;

-- ai_reader: yalnizca context_queries.sql'deki 5 iliski + health
GRANT SELECT ON core.kanit_anlik, core.source_authority, mart.sirket_gundemi, mart.karar_ozet, mart.acik_isler TO ai_reader;
GRANT EXECUTE ON FUNCTION core.ai_orchestrator_health() TO ai_reader;
-- CIKARIM (dosyalarda yok): mart view'lari cagiranin yetkisiyle calisan iki fonksiyon kullaniyor:
--   mart.kesim()      -> core.ayar okur
--   core.maliyet_bul()-> core.urun_maliyet okur
-- Bu SELECT'ler olmadan ai_reader context view'larini okuyamaz. Uretimdeki gercek ACL bilinmiyor.
GRANT SELECT ON core.ayar, core.urun_maliyet TO ai_reader;

-- ai_writer
GRANT EXECUTE ON FUNCTION core.ai_claim_task(text,integer,text) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_log_provider_attempt(bigint,text,text,integer,timestamptz,timestamptz,integer,text,boolean,boolean,text,text,text,text,text,text) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_complete_task_with_proposed_decision(bigint,uuid,text,text,text,text,text,text,text,text,text,text) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_fail_task(bigint,uuid,text,text) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_propose_action(bigint,uuid,text,text,jsonb) TO ai_writer;

-- human_approver
GRANT EXECUTE ON FUNCTION core.ai_decide_action(bigint,text,text) TO human_approver;
GRANT EXECUTE ON FUNCTION core.ai_get_pending_actions() TO human_approver;
GRANT EXECUTE ON FUNCTION core.ai_enqueue_task(text,bigint,text,text,text,integer,timestamptz,boolean,text,text) TO human_approver;

-- action_executor
GRANT EXECUTE ON FUNCTION core.ai_claim_approved_action(text,integer) TO action_executor;
GRANT EXECUTE ON FUNCTION core.ai_complete_action_execution(bigint,uuid,text,text) TO action_executor;
COMMIT;
