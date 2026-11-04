-- lcarlie YEREL: core.ai_get_pending_actions() siralama testi (YALNIZCA YEREL, kalici degisiklik YAPMAZ).
-- Tum test satirlari tek bir transaction icinde eklenir ve sonda ROLLBACK edilir.
-- Fonksiyon gercek cagiran rolle (human_approver uyesi local_approver_1) cagrilir.
-- Not: identity sayaci (action_id) ROLLBACK ile geri alinmaz; yerelde zararsizdir.
-- Calistir:  docker exec -i lcarlie-pg psql -U lcarlie_admin -d lcarlie -X -v ON_ERROR_STOP=1 < sql/05-verify-pending-actions-order.sql
\pset footer off
BEGIN;

-- Test icin bir gorev: mevcut herhangi bir ai_task satiri (yoksa yerel bir MANUAL gorev eklenir; o da ROLLBACK olur).
INSERT INTO core.ai_task(source_type,task_type,idempotency_key,cutoff_version,state)
SELECT 'MANUAL','PROPOSE_ACTION','yerel-siralama-testi','yerel-test','NEEDS_REVIEW'
WHERE NOT EXISTS (SELECT 1 FROM core.ai_task);

-- Kasitli olarak dusuk riskten yuksek riske dogru eklenir (action_id artan): LOW, MEDIUM, HIGH, CRITICAL.
INSERT INTO core.ai_action_proposal(task_id,idempotency_key,action_type,payload,payload_hash,risk_class,proposed_by,expires_at)
SELECT (SELECT min(task_id) FROM core.ai_task),
       'action:yerel-siralama-testi:'||t.action_type||':'||txid_current(),
       t.action_type, jsonb_build_object('reason','YEREL SIRALAMA TESTI'), md5(t.action_type),
       t.risk_class, 'yerel-test', clock_timestamp()+interval '1 hour'
FROM (VALUES (1,'REQUEST_HUMAN_REVIEW','LOW'),
             (2,'DRAFT_CUSTOMER_REPLY','MEDIUM'),
             (3,'META_CAMPAIGN_CHANGE','HIGH'),
             (4,'PRICE_CHANGE','CRITICAL')) AS t(n,action_type,risk_class)
ORDER BY t.n;

SET LOCAL ROLE local_approver_1;
\echo '--- core.ai_get_pending_actions() ciktisi (local_approver_1 olarak) ---'
SELECT row_number() OVER () AS sira, action_id, action_type, risk_class
FROM core.ai_get_pending_actions();

\echo '--- beklenen: CRITICAL > HIGH > MEDIUM > LOW (esitlikte action_id artan) ---'
WITH r AS (
  SELECT row_number() OVER () AS sira, action_id,
         CASE risk_class WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 END AS rank
  FROM core.ai_get_pending_actions()
), k AS (
  SELECT sira, rank, action_id,
         lag(rank) OVER (ORDER BY sira) AS onceki_rank,
         lag(action_id) OVER (ORDER BY sira) AS onceki_id
  FROM r
)
SELECT count(*) AS satir,
       bool_and(onceki_rank IS NULL OR onceki_rank > rank OR (onceki_rank = rank AND onceki_id < action_id)) AS siralama_dogru
FROM k;
RESET ROLE;
ROLLBACK;
