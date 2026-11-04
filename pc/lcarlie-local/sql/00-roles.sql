-- lcarlie YEREL: rolleri olustur (uretimden alinan schema-only dump --no-acl ile alindigi icin
-- roller ve yetkiler dump'ta YOK). Rol adlari f4/f5/f6 betiklerinden, DB_CONTRACT.md'den,
-- F1.md'den ve dump'taki nesne sahiplerinden (n8n, function_owner, mem0_writer) alinmistir.
-- LOGIN parolalari psql degiskeni olarak verilir (.env.local), dosyada parola yoktur.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['n8n','function_owner','mem0_writer','ai_reader','ai_writer','human_approver','action_executor'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', r);
    END IF;
  END LOOP;
END $$;

-- F1: worker LOGIN'i NOINHERIT; yalnizca ai_reader / ai_writer'a SET ROLE yapabilir.
SELECT format('CREATE ROLE ai_orchestrator_worker LOGIN NOINHERIT PASSWORD %L', :'worker_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_orchestrator_worker') \gexec
GRANT ai_reader, ai_writer TO ai_orchestrator_worker;

-- Yerel test icin bir insan onaylayici (human_approver uyesi, INHERIT).
SELECT format('CREATE ROLE local_approver_1 LOGIN PASSWORD %L', :'approver_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='local_approver_1') \gexec
GRANT human_approver TO local_approver_1;
