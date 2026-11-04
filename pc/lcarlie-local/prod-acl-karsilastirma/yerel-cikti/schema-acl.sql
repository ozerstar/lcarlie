--
-- PostgreSQL database dump
--

\restrict fbh7IIr5r43sldc7ceHEx2gfcFdL1aUDeTO93PMcHMLpGywK3bqacxRNgrc86nB

-- Dumped from database version 17.11 (Debian 17.11-1.pgdg12+2)
-- Dumped by pg_dump version 17.11 (Debian 17.11-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: ai_semantic; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA ai_semantic;


ALTER SCHEMA ai_semantic OWNER TO n8n;

--
-- Name: core; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA core;


ALTER SCHEMA core OWNER TO n8n;

--
-- Name: lcarlie; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA lcarlie;


ALTER SCHEMA lcarlie OWNER TO n8n;

--
-- Name: mart; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA mart;


ALTER SCHEMA mart OWNER TO n8n;

--
-- Name: mem0; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA mem0;


ALTER SCHEMA mem0 OWNER TO n8n;

--
-- Name: raw; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA raw;


ALTER SCHEMA raw OWNER TO n8n;

--
-- Name: saha; Type: SCHEMA; Schema: -; Owner: n8n
--

CREATE SCHEMA saha;


ALTER SCHEMA saha OWNER TO n8n;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: ai_bulgu_gorev_ac(text, text, integer); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_bulgu_gorev_ac(p_slug text, p_sebep text, p_oncelik integer DEFAULT 120) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $_$
DECLARE
  c_gunluk_tavan  constant int := 6;
  c_acik_tavan    constant int := 12;
  v_sayi          int;
  v_task_id       bigint;
  v_cutoff        text;
BEGIN
  IF p_slug IS NULL OR btrim(p_slug) = '' THEN
    RAISE EXCEPTION 'slug zorunlu';
  END IF;
  -- Slug bir dosya adina donusuyor (state/agency/pending/<slug>.json):
  -- yol kacisina izin verilmez.
  IF p_slug !~ '^[a-z0-9][a-z0-9_-]{2,60}$' THEN
    RAISE EXCEPTION 'slug bicimi gecersiz: %', p_slug;
  END IF;
  IF p_sebep IS NULL OR length(btrim(p_sebep)) < 40 THEN
    RAISE EXCEPTION 'sebep en az 40 karakter olmali (ici bos oneri onay degildir)';
  END IF;

  -- Serialize quota checks and inserts across competing callers.
  PERFORM pg_advisory_xact_lock(33061014);
  IF EXISTS (SELECT 1 FROM core.ai_task
             WHERE idempotency_key = 'jarvis:HUMAN_REVIEW_REQUEST:' || p_slug) THEN
    RETURN NULL;
  END IF;

  SELECT count(*) INTO v_sayi
    FROM core.ai_task
   WHERE ai_enqueue AND source_type = 'BULGU'
     AND created_at > now() - interval '24 hours';
  IF v_sayi >= c_gunluk_tavan THEN
    RAISE EXCEPTION 'gunluk tavan doldu: son 24 saatte % bulgu isi acilmis (tavan %)',
                    v_sayi, c_gunluk_tavan;
  END IF;

  SELECT count(*) INTO v_sayi
    FROM core.ai_task
   WHERE ai_enqueue AND source_type = 'BULGU'
     AND state NOT IN ('DONE', 'FAILED_FINAL', 'SKIPPED_CUTOFF', 'DUPLICATE');
  IF v_sayi >= c_acik_tavan THEN
    RAISE EXCEPTION 'acik bulgu isi tavani doldu: % acik is var (tavan %)',
                    v_sayi, c_acik_tavan;
  END IF;

  SELECT config_value INTO v_cutoff
    FROM core.ai_orchestrator_config WHERE config_key = 'cutoff_version';

  -- source_id: imzadan turetilen kararli bir sayi. NULL birakmak
  -- ai_enqueue_task'in kendi sozlesmesine aykiri olurdu.
  INSERT INTO core.ai_task(source_type, source_id, task_type, priority,
                           eligible_after, idempotency_key, cutoff_version,
                           ai_enqueue, enqueue_reason, context_profile)
  VALUES ('BULGU',
          ('x' || substr(md5(p_slug), 1, 15))::bit(60)::bigint,
          'PROPOSE_ACTION',
          COALESCE(p_oncelik, 120),
          clock_timestamp(),
          'jarvis:HUMAN_REVIEW_REQUEST:' || p_slug,
          v_cutoff,
          true,
          left(btrim(p_sebep), 500),
          'default')
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING task_id INTO v_task_id;

  -- NULL = bu imza icin is ZATEN acilmis. Hata degil; tekrar degil.
  RETURN v_task_id;
END
$_$;


ALTER FUNCTION core.ai_bulgu_gorev_ac(p_slug text, p_sebep text, p_oncelik integer) OWNER TO function_owner;

--
-- Name: ai_claim_approved_action(text, integer); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_claim_approved_action(p_worker_id text, p_lease_seconds integer DEFAULT 300) RETURNS TABLE(execution_id bigint, action_id bigint, action_type text, payload jsonb, execution_key text, lease_token uuid, attempt_count integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_execution_id bigint; v_enabled boolean;
BEGIN
  SELECT config_value::boolean INTO v_enabled FROM core.ai_orchestrator_config WHERE config_key='action_worker_enabled';
  IF NOT COALESCE(v_enabled,false) THEN RETURN; END IF;
  IF p_worker_id IS NULL OR btrim(p_worker_id)='' THEN RAISE EXCEPTION 'worker id required'; END IF;
  IF p_lease_seconds<30 OR p_lease_seconds>900 THEN RAISE EXCEPTION 'lease seconds out of range'; END IF;
  SELECT e.execution_id INTO v_execution_id FROM core.ai_action_execution e JOIN core.ai_action_proposal a ON a.action_id=e.action_id JOIN core.ai_action_type t ON t.action_type=a.action_type WHERE e.state IN ('OPEN','FAILED_RETRYABLE') AND e.attempt_count<e.max_attempts AND a.state='APPROVED' AND t.execution_enabled ORDER BY e.execution_id FOR UPDATE OF e SKIP LOCKED LIMIT 1;
  IF v_execution_id IS NULL THEN RETURN; END IF;
  UPDATE core.ai_action_execution e SET state='LEASED',lease_owner=p_worker_id,lease_token=gen_random_uuid(),lease_until=clock_timestamp()+make_interval(secs=>p_lease_seconds),attempt_count=e.attempt_count+1 WHERE e.execution_id=v_execution_id;
  UPDATE core.ai_action_proposal a SET state='EXECUTING' FROM core.ai_action_execution e WHERE e.execution_id=v_execution_id AND a.action_id=e.action_id;
  RETURN QUERY SELECT e.execution_id,a.action_id,a.action_type,a.payload,e.execution_key,e.lease_token,e.attempt_count FROM core.ai_action_execution e JOIN core.ai_action_proposal a ON a.action_id=e.action_id WHERE e.execution_id=v_execution_id;
END $$;


ALTER FUNCTION core.ai_claim_approved_action(p_worker_id text, p_lease_seconds integer) OWNER TO function_owner;

--
-- Name: ai_claim_task(text, integer, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_claim_task(p_worker_id text, p_lease_seconds integer DEFAULT 300, p_task_type text DEFAULT NULL::text) RETURNS TABLE(task_id bigint, source_type text, source_id bigint, task_type text, idempotency_key text, context_profile text, lease_token uuid, attempt_count integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE v_enabled_after timestamptz; v_enabled boolean;
BEGIN
  SELECT config_value::boolean INTO v_enabled FROM core.ai_orchestrator_config WHERE config_key='ai_worker_enabled';
  IF NOT COALESCE(v_enabled,false) THEN RETURN; END IF;
  IF p_worker_id IS NULL OR btrim(p_worker_id)='' THEN RAISE EXCEPTION 'worker_id required'; END IF;
  IF p_lease_seconds IS NULL OR p_lease_seconds<30 OR p_lease_seconds>3600 THEN RAISE EXCEPTION 'lease_seconds out of range'; END IF;
  SELECT config_value::timestamptz INTO v_enabled_after FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after';

  RETURN QUERY
  WITH candidate AS (
    SELECT t.task_id FROM core.ai_task t
     WHERE (
             t.state IN ('OPEN','FAILED_RETRYABLE')
             -- Suresi dolmus kira yeniden aday olur: isci oldugunde is
             -- sonsuza kadar LEASED'te kalmasin. attempt_count siniri
             -- hala gecerli, yani surekli coken bir is yine de biter.
             OR (t.state='LEASED' AND t.lease_until < clock_timestamp())
           )
       AND t.eligible_after <= clock_timestamp()
       AND t.attempt_count < t.max_attempts
       AND (t.created_at >= v_enabled_after OR t.ai_enqueue)
       -- Kimse baskasinin is tipini kiralamaz.
       AND (p_task_type IS NULL OR t.task_type = p_task_type)
     ORDER BY t.priority, t.task_id
     FOR UPDATE SKIP LOCKED LIMIT 1
  ), claimed AS (
    UPDATE core.ai_task t
       SET state='LEASED', lease_owner=p_worker_id, lease_token=gen_random_uuid(),
           lease_until=clock_timestamp()+make_interval(secs=>p_lease_seconds),
           attempt_count=t.attempt_count+1, last_error=NULL
      FROM candidate c WHERE t.task_id=c.task_id
    RETURNING t.task_id,t.source_type,t.source_id,t.task_type,t.idempotency_key,
              t.context_profile,t.lease_token,t.attempt_count
  ) SELECT * FROM claimed;
END $$;


ALTER FUNCTION core.ai_claim_task(p_worker_id text, p_lease_seconds integer, p_task_type text) OWNER TO function_owner;

--
-- Name: ai_complete_action_execution(bigint, uuid, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_complete_action_execution(p_execution_id bigint, p_lease_token uuid, p_result_class text, p_result_summary text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_execution core.ai_action_execution%ROWTYPE; v_action_state text;
BEGIN
  IF p_result_class NOT IN ('EXECUTED','FAILED_RETRYABLE','FAILED_FINAL') THEN RAISE EXCEPTION 'invalid result class'; END IF;
  IF p_result_summary IS NULL OR length(p_result_summary)>1000 THEN RAISE EXCEPTION 'invalid result summary'; END IF;
  SELECT * INTO v_execution FROM core.ai_action_execution WHERE execution_id=p_execution_id FOR UPDATE;
  IF NOT FOUND OR v_execution.state<>'LEASED' OR v_execution.lease_token IS DISTINCT FROM p_lease_token OR v_execution.lease_until<clock_timestamp() THEN RAISE EXCEPTION 'invalid or expired execution lease'; END IF;
  UPDATE core.ai_action_execution SET state=p_result_class,last_result_summary=p_result_summary,lease_until=NULL,finished_at=CASE WHEN p_result_class IN ('EXECUTED','FAILED_FINAL') THEN clock_timestamp() ELSE NULL END WHERE execution_id=p_execution_id;
  v_action_state:=CASE p_result_class WHEN 'EXECUTED' THEN 'EXECUTED' WHEN 'FAILED_RETRYABLE' THEN 'APPROVED' ELSE 'EXECUTION_FAILED' END;
  UPDATE core.ai_action_proposal SET state=v_action_state WHERE action_id=v_execution.action_id;
END $$;


ALTER FUNCTION core.ai_complete_action_execution(p_execution_id bigint, p_lease_token uuid, p_result_class text, p_result_summary text) OWNER TO function_owner;

--
-- Name: ai_complete_task_with_proposed_decision(bigint, uuid, text, text, text, text, text, text, text, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_complete_task_with_proposed_decision(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_karar_tipi text, p_oneri text, p_anlik_id_text text, p_kanit_kalitesi text, p_yanlislama_kosulu text, p_urun text DEFAULT NULL::text, p_kanal text DEFAULT NULL::text, p_beklenen_etki text DEFAULT NULL::text, p_risk text DEFAULT NULL::text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $_$
DECLARE
  v_task core.ai_task%ROWTYPE;
  v_karar_id bigint;
  v_anlik_id bigint;
BEGIN
  IF p_idempotency_key IS NULL OR p_idempotency_key NOT LIKE 'ai:%' THEN
    RAISE EXCEPTION 'AI decision idempotency_key must start with ai:''';
  END IF;
  IF p_karar_tipi NOT IN ('PRODUCT_PRIORITY','MEDIA_BUDGET','OFFER_TEST','CREATIVE_TEST','CRO_CHANGE','AUDIENCE_TEST','CRM_ACTION') THEN
    RAISE EXCEPTION 'invalid karar_tipi';
  END IF;
  IF p_kanit_kalitesi NOT IN ('LOW','MEDIUM','HIGH') THEN
    RAISE EXCEPTION 'invalid kanit_kalitesi';
  END IF;
  IF p_anlik_id_text IS NULL OR p_anlik_id_text !~ '^[0-9]+$' THEN
    RAISE EXCEPTION 'anlik_id must be numeric text';
  END IF;
  v_anlik_id := p_anlik_id_text::bigint;

  SELECT * INTO v_task
  FROM core.ai_task
  WHERE task_id = p_task_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'task not found';
  END IF;
  IF v_task.lease_token IS DISTINCT FROM p_lease_token OR v_task.lease_until < clock_timestamp() THEN
    RAISE EXCEPTION 'invalid or expired lease';
  END IF;
  IF v_task.state <> 'LEASED' THEN
    RAISE EXCEPTION 'task is not leased';
  END IF;
  IF v_task.task_type <> 'PROPOSE_DECISION' THEN
    RAISE EXCEPTION 'task_type must be PROPOSE_DECISION';
  END IF;
  IF v_task.idempotency_key <> p_idempotency_key THEN
    RAISE EXCEPTION 'idempotency mismatch';
  END IF;

  INSERT INTO core.karar (
    karar_tipi, urun, kanal, oneri, anlik_id, kanit_kalitesi,
    beklenen_etki, risk, yanlislama_kosulu, durum, idempotency_key, fixture
  ) VALUES (
    p_karar_tipi, p_urun, p_kanal, p_oneri, v_anlik_id, p_kanit_kalitesi,
    p_beklenen_etki, p_risk, p_yanlislama_kosulu, 'PROPOSED', p_idempotency_key, false
  ) RETURNING karar_id INTO v_karar_id;

  UPDATE core.ai_task
     SET state = 'PROPOSED_WRITTEN',
         completed_at = clock_timestamp(),
         lease_until = NULL
   WHERE task_id = p_task_id;

  RETURN v_karar_id;
EXCEPTION WHEN unique_violation THEN
  UPDATE core.ai_task
     SET state = 'DUPLICATE',
         completed_at = clock_timestamp(),
         last_error = 'duplicate idempotency key',
         lease_until = NULL
   WHERE task_id = p_task_id;
  RAISE;
END;
$_$;


ALTER FUNCTION core.ai_complete_task_with_proposed_decision(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_karar_tipi text, p_oneri text, p_anlik_id_text text, p_kanit_kalitesi text, p_yanlislama_kosulu text, p_urun text, p_kanal text, p_beklenen_etki text, p_risk text) OWNER TO function_owner;

--
-- Name: ai_decide_action(bigint, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_decide_action(p_action_id bigint, p_decision text, p_reason text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_action core.ai_action_proposal%ROWTYPE; v_mode text; v_required integer; v_count integer; v_approvers text;
BEGIN
  IF p_decision NOT IN ('APPROVED','REJECTED') THEN RAISE EXCEPTION 'invalid decision'; END IF;
  IF p_reason IS NULL OR btrim(p_reason)='' OR length(p_reason)>2000 THEN RAISE EXCEPTION 'decision reason required'; END IF;
  IF NOT pg_has_role(session_user,'human_approver','MEMBER') THEN RAISE EXCEPTION 'human approver membership required'; END IF;
  SELECT * INTO v_action FROM core.ai_action_proposal WHERE action_id=p_action_id FOR UPDATE;
  IF NOT FOUND OR v_action.state<>'PROPOSED' THEN RAISE EXCEPTION 'action is not pending'; END IF;
  IF v_action.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'action proposal expired'; END IF;
  SELECT approval_mode INTO v_mode FROM core.ai_action_type WHERE action_type=v_action.action_type;
  INSERT INTO core.ai_action_approval(action_id,approver_identity,decision,reason) VALUES(p_action_id,session_user,p_decision,p_reason);
  IF p_decision='REJECTED' THEN
    UPDATE core.ai_action_proposal SET state='REJECTED',decided_by=session_user,decided_at=clock_timestamp(),decision_reason=p_reason WHERE action_id=p_action_id;
    RETURN;
  END IF;
  v_required:=CASE WHEN v_mode='TWO_PERSON' THEN 2 ELSE 1 END;
  SELECT count(*),string_agg(approver_identity,',' ORDER BY approver_identity) INTO v_count,v_approvers FROM core.ai_action_approval WHERE action_id=p_action_id AND decision='APPROVED';
  IF v_count>=v_required THEN
    UPDATE core.ai_action_proposal SET state='APPROVED',decided_by=v_approvers,decided_at=clock_timestamp(),decision_reason=p_reason WHERE action_id=p_action_id;
    INSERT INTO core.ai_action_execution(action_id,execution_key)
    SELECT p_action_id,'execute:'||idempotency_key FROM core.ai_action_proposal a JOIN core.ai_action_type t USING(action_type) WHERE a.action_id=p_action_id AND t.execution_enabled ON CONFLICT(action_id) DO NOTHING;
  END IF;
END $$;


ALTER FUNCTION core.ai_decide_action(p_action_id bigint, p_decision text, p_reason text) OWNER TO function_owner;

--
-- Name: ai_enqueue_task(text, bigint, text, text, text, integer, timestamp with time zone, boolean, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_enqueue_task(p_source_type text, p_source_id bigint, p_task_type text, p_idempotency_key text, p_context_profile text DEFAULT 'default'::text, p_priority integer DEFAULT 100, p_eligible_after timestamp with time zone DEFAULT clock_timestamp(), p_ai_enqueue boolean DEFAULT false, p_enqueue_reason text DEFAULT NULL::text, p_cutoff_version text DEFAULT NULL::text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE v_enabled_after timestamptz; v_cutoff_version text; v_task_id bigint;
BEGIN
  IF p_source_type NOT IN ('ACIK_SORU','BULGU','KARAR','IC_MESAJ','MANUAL') THEN RAISE EXCEPTION 'invalid source_type'; END IF;
  IF p_task_type NOT IN ('ANALYZE','REDTEAM','PROPOSE_DECISION','PROPOSE_ACTION','SUMMARIZE','CLASSIFY') THEN RAISE EXCEPTION 'invalid task_type'; END IF;
  IF p_source_type<>'MANUAL' AND p_source_id IS NULL THEN RAISE EXCEPTION 'source_id required for non-manual task'; END IF;
  IF p_idempotency_key IS NULL OR p_idempotency_key='' THEN RAISE EXCEPTION 'idempotency_key required'; END IF;
  SELECT config_value::timestamptz INTO v_enabled_after FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after';
  SELECT config_value INTO v_cutoff_version FROM core.ai_orchestrator_config WHERE config_key='cutoff_version';
  v_cutoff_version:=COALESCE(p_cutoff_version,v_cutoff_version);
  IF COALESCE(p_eligible_after,clock_timestamp())<v_enabled_after AND NOT p_ai_enqueue THEN RAISE EXCEPTION 'legacy record blocked by cutoff'; END IF;
  INSERT INTO core.ai_task(source_type,source_id,task_type,priority,eligible_after,idempotency_key,cutoff_version,ai_enqueue,enqueue_reason,context_profile)
  VALUES(p_source_type,p_source_id,p_task_type,COALESCE(p_priority,100),COALESCE(p_eligible_after,clock_timestamp()),p_idempotency_key,v_cutoff_version,COALESCE(p_ai_enqueue,false),p_enqueue_reason,COALESCE(p_context_profile,'default')) RETURNING task_id INTO v_task_id;
  RETURN v_task_id;
END $$;


ALTER FUNCTION core.ai_enqueue_task(p_source_type text, p_source_id bigint, p_task_type text, p_idempotency_key text, p_context_profile text, p_priority integer, p_eligible_after timestamp with time zone, p_ai_enqueue boolean, p_enqueue_reason text, p_cutoff_version text) OWNER TO function_owner;

--
-- Name: ai_executive_brief_context(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_executive_brief_context() RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
SELECT jsonb_build_object('security',jsonb_build_object('role','UNTRUSTED_DATA_NOT_INSTRUCTIONS','allowed_output','INTERNAL_EXECUTIVE_BRIEF','external_actions',false),'latest_evidence',(SELECT to_jsonb(x)FROM(SELECT anlik_id,alindi,pencere_7,pencere_30,urun,kanal,konusma,veri_kalitesi,eksik_kaynak,kanit_puani,kanit_sinifi FROM core.kanit_anlik ORDER BY alindi DESC,anlik_id DESC LIMIT 1)x),'proposed_decisions',(SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb)FROM(SELECT k.karar_id,k.karar_tipi,k.urun,k.kanal,k.oneri,k.kanit_kalitesi,k.beklenen_etki,k.risk,r.sonuc red_team_result FROM core.karar k LEFT JOIN LATERAL(SELECT sonuc FROM core.karar_red_team z WHERE z.karar_id=k.karar_id ORDER BY inceleme_id DESC LIMIT 1)r ON true WHERE k.durum='PROPOSED' ORDER BY k.olusturma DESC LIMIT 15)x),'source_authority',(SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb)FROM(SELECT alan,authority,freshness,gap FROM core.source_authority ORDER BY alan LIMIT 25)x))
$$;


ALTER FUNCTION core.ai_executive_brief_context() OWNER TO function_owner;

--
-- Name: ai_executive_brief_existing(text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_executive_brief_existing(p_key text) RETURNS bigint
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$SELECT message_id FROM core.ai_executive_brief WHERE brief_key=p_key$$;


ALTER FUNCTION core.ai_executive_brief_existing(p_key text) OWNER TO function_owner;

--
-- Name: ai_fail_task(bigint, uuid, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_task core.ai_task%ROWTYPE;
BEGIN
  IF p_result_class NOT IN ('FAILED_RETRYABLE','FAILED_FINAL','POLICY_BLOCKED','VALIDATION_FAILED') THEN
    RAISE EXCEPTION 'invalid failure class';
  END IF;

  SELECT * INTO v_task
  FROM core.ai_task
  WHERE task_id = p_task_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'task not found';
  END IF;
  IF v_task.lease_token IS DISTINCT FROM p_lease_token OR v_task.lease_until < clock_timestamp() THEN
    RAISE EXCEPTION 'invalid or expired lease';
  END IF;

  UPDATE core.ai_task
     SET state = CASE WHEN p_result_class = 'FAILED_RETRYABLE' AND v_task.attempt_count < v_task.max_attempts THEN 'FAILED_RETRYABLE' ELSE 'FAILED_FINAL' END,
         completed_at = CASE WHEN p_result_class = 'FAILED_RETRYABLE' AND v_task.attempt_count < v_task.max_attempts THEN NULL ELSE clock_timestamp() END,
         last_error = left(COALESCE(p_fail_reason, p_result_class), 1000),
         lease_until = NULL
   WHERE task_id = p_task_id;
END;
$$;


ALTER FUNCTION core.ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text) OWNER TO function_owner;

--
-- Name: ai_generate_company_intelligence_task(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_generate_company_intelligence_task() RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
DECLARE enabled boolean;evidence_id bigint;key text;task_id bigint;
BEGIN
 SELECT config_value::boolean INTO enabled FROM core.ai_orchestrator_config WHERE config_key='company_intelligence_enabled';
 IF enabled IS DISTINCT FROM true THEN RETURN NULL;END IF;
 SELECT anlik_id INTO evidence_id FROM core.kanit_anlik ORDER BY alindi DESC,anlik_id DESC LIMIT 1;
 IF evidence_id IS NULL THEN RETURN NULL;END IF;
 key:='ai:ci:evidence:'||evidence_id||':decision-v1';
 BEGIN task_id:=core.ai_enqueue_task('MANUAL',evidence_id,'PROPOSE_DECISION',key,'decision-v1',50,clock_timestamp(),true,'LATEST_EVIDENCE_SNAPSHOT',NULL);
 EXCEPTION WHEN unique_violation THEN SELECT t.task_id INTO task_id FROM core.ai_task t WHERE t.idempotency_key=key;END;
 RETURN task_id;
END$$;


ALTER FUNCTION core.ai_generate_company_intelligence_task() OWNER TO function_owner;

--
-- Name: ai_generate_measurement_plans(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_generate_measurement_plans() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE k record;e bigint;d bigint;n int:=0;cutoff timestamptz;body text;BEGIN
 SELECT config_value::timestamptz INTO cutoff FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after';
 FOR k IN SELECT karar_id,karar_tipi,urun,kanal,oneri,beklenen_etki,yanlislama_kosulu FROM core.karar WHERE durum='APPROVED' AND olusturma>=cutoff AND NOT EXISTS(SELECT 1 FROM core.ai_measurement_plan p WHERE p.karar_id=karar.karar_id) ORDER BY karar_id FOR UPDATE SKIP LOCKED LOOP
  body:='Karar #'||k.karar_id||E'\nÖneri: '||k.oneri||E'\nBeklenen etki: '||coalesce(k.beklenen_etki,'')||E'\nYanlışlama koşulu: '||k.yanlislama_kosulu;
  INSERT INTO core.ic_mesaj(kimden,kime,tip,konu,icerik,bagli_karar,durum)VALUES('AI_OPS','EXPERIMENT','TASK','Karar ölçüm planı #'||k.karar_id,body,k.karar_id,'OPEN')RETURNING mesaj_id INTO e;
  INSERT INTO core.ic_mesaj(kimden,kime,tip,konu,icerik,bagli_karar,durum)VALUES('AI_OPS','DATA_BI','TASK','Karar ölçüm verisi #'||k.karar_id,body,k.karar_id,'OPEN')RETURNING mesaj_id INTO d;
  INSERT INTO core.ai_measurement_plan VALUES(k.karar_id,e,d,now());n:=n+1;
 END LOOP;RETURN n;END$$;


ALTER FUNCTION core.ai_generate_measurement_plans() OWNER TO function_owner;

--
-- Name: ai_generated_question_existing(text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_generated_question_existing(text) RETURNS bigint
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $_$SELECT soru_id FROM core.ai_generated_question WHERE question_key=$1$_$;


ALTER FUNCTION core.ai_generated_question_existing(text) OWNER TO function_owner;

--
-- Name: ai_get_model_policy(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_get_model_policy() RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$ SELECT to_jsonb(p) FROM core.ai_model_policy p WHERE p.policy_name='token-economy-v2' AND p.enabled $$;


ALTER FUNCTION core.ai_get_model_policy() OWNER TO function_owner;

--
-- Name: ai_get_pending_actions(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_get_pending_actions() RETURNS TABLE(action_id bigint, task_id bigint, action_type text, payload jsonb, payload_hash text, risk_class text, policy_version text, proposed_at timestamp with time zone, expires_at timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$ SELECT a.action_id,a.task_id,a.action_type,a.payload,a.payload_hash,a.risk_class,a.policy_version,a.proposed_at,a.expires_at FROM core.ai_action_proposal a WHERE a.state='PROPOSED' AND a.expires_at>clock_timestamp() ORDER BY CASE a.risk_class WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END DESC,a.action_id ASC $$;


ALTER FUNCTION core.ai_get_pending_actions() OWNER TO function_owner;

--
-- Name: ai_jsonb_has_forbidden_key(jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_jsonb_has_forbidden_key(p_value jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
DECLARE v_key text; v_value jsonb;
BEGIN
  IF p_value IS NULL THEN RETURN false; END IF;
  IF jsonb_typeof(p_value)='object' THEN
    FOR v_key,v_value IN SELECT key,value FROM pg_catalog.jsonb_each(p_value) LOOP
      IF pg_catalog.lower(v_key)=ANY(ARRAY['command','shell','sql','url','method','headers','token','secret','password','api_key','authorization']) THEN RETURN true; END IF;
      IF core.ai_jsonb_has_forbidden_key(v_value) THEN RETURN true; END IF;
    END LOOP;
  ELSIF jsonb_typeof(p_value)='array' THEN
    FOR v_value IN SELECT value FROM pg_catalog.jsonb_array_elements(p_value) LOOP
      IF core.ai_jsonb_has_forbidden_key(v_value) THEN RETURN true; END IF;
    END LOOP;
  END IF;
  RETURN false;
END $$;


ALTER FUNCTION core.ai_jsonb_has_forbidden_key(p_value jsonb) OWNER TO function_owner;

--
-- Name: ai_load_jarvis_task_state(bigint); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_load_jarvis_task_state(p_task_id bigint) RETURNS TABLE(task_id bigint, state_json jsonb, version bigint, updated_at timestamp with time zone)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
  SELECT s.task_id, s.state_json, s.version, s.updated_at
    FROM core.jarvis_task_state s
   WHERE s.task_id = p_task_id;
$$;


ALTER FUNCTION core.ai_load_jarvis_task_state(p_task_id bigint) OWNER TO function_owner;

--
-- Name: ai_log_provider_attempt(bigint, text, text, integer, timestamp with time zone, timestamp with time zone, integer, text, boolean, boolean, text, text, text, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_log_provider_attempt(p_task_id bigint, p_provider text, p_model text, p_attempt integer, p_started_at timestamp with time zone, p_finished_at timestamp with time zone, p_latency_ms integer, p_result_class text, p_rate_limit boolean, p_timeout boolean, p_validation_result text, p_failover_reason text, p_context_profile text, p_context_version text, p_context_hash text, p_safe_summary text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_attempt_id bigint;
BEGIN
  IF p_result_class NOT IN ('SUCCESS','RATE_LIMIT','TIMEOUT','PROVIDER_ERROR','VALIDATION_FAILED','POLICY_BLOCKED','DUPLICATE','FAILED') THEN
    RAISE EXCEPTION 'invalid result_class';
  END IF;

  INSERT INTO core.ai_provider_attempt (
    task_id, provider, model, attempt, started_at, finished_at, latency_ms,
    result_class, rate_limit, timeout, validation_result, failover_reason,
    context_profile, context_version, context_hash, safe_summary
  ) VALUES (
    p_task_id, p_provider, p_model, p_attempt, p_started_at, p_finished_at, p_latency_ms,
    p_result_class, COALESCE(p_rate_limit, false), COALESCE(p_timeout, false),
    p_validation_result, p_failover_reason, p_context_profile, p_context_version,
    p_context_hash, p_safe_summary
  ) RETURNING attempt_id INTO v_attempt_id;

  INSERT INTO core.ai_calisma_log (saglayici, model, gorev, sonuc)
  VALUES (p_provider, p_model, 'task#' || COALESCE(p_task_id::text, '?'), p_result_class);

  RETURN v_attempt_id;
END;
$$;


ALTER FUNCTION core.ai_log_provider_attempt(p_task_id bigint, p_provider text, p_model text, p_attempt integer, p_started_at timestamp with time zone, p_finished_at timestamp with time zone, p_latency_ms integer, p_result_class text, p_rate_limit boolean, p_timeout boolean, p_validation_result text, p_failover_reason text, p_context_profile text, p_context_version text, p_context_hash text, p_safe_summary text) OWNER TO function_owner;

--
-- Name: ai_log_provider_usage(bigint, text, integer, integer, integer, boolean); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_log_provider_usage(p_task_id bigint, p_provider text, p_attempt integer, p_input_tokens integer, p_output_tokens integer, p_estimated boolean DEFAULT true) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
BEGIN
 IF p_input_tokens<0 OR p_output_tokens<0 OR p_input_tokens>1000000 OR p_output_tokens>100000 THEN RAISE EXCEPTION 'invalid token usage'; END IF;
 UPDATE core.ai_provider_attempt SET input_tokens=p_input_tokens,output_tokens=p_output_tokens,token_estimated=p_estimated
 WHERE attempt_id=(SELECT attempt_id FROM core.ai_provider_attempt WHERE task_id=p_task_id AND provider=p_provider AND attempt=p_attempt ORDER BY attempt_id DESC LIMIT 1);
END$$;


ALTER FUNCTION core.ai_log_provider_usage(p_task_id bigint, p_provider text, p_attempt integer, p_input_tokens integer, p_output_tokens integer, p_estimated boolean) OWNER TO function_owner;

--
-- Name: ai_orchestrator_health(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_orchestrator_health() RETURNS jsonb
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
SELECT jsonb_build_object(
  'ai_worker_enabled',(SELECT config_value::boolean FROM core.ai_orchestrator_config WHERE config_key='ai_worker_enabled'),
  'action_worker_enabled',(SELECT config_value::boolean FROM core.ai_orchestrator_config WHERE config_key='action_worker_enabled'),
  'open_tasks',(SELECT count(*) FROM core.ai_task WHERE state IN ('OPEN','FAILED_RETRYABLE')),
  'leased_tasks',(SELECT count(*) FROM core.ai_task WHERE state='LEASED'),
  'pending_actions',(SELECT count(*) FROM core.ai_action_proposal WHERE state='PROPOSED' AND expires_at>clock_timestamp()),
  'expired_actions',(SELECT count(*) FROM core.ai_action_proposal WHERE state='PROPOSED' AND expires_at<=clock_timestamp()),
  'approved_actions',(SELECT count(*) FROM core.ai_action_proposal WHERE state='APPROVED'),
  'open_executions',(SELECT count(*) FROM core.ai_action_execution WHERE state IN ('OPEN','FAILED_RETRYABLE')),
  'failed_executions',(SELECT count(*) FROM core.ai_action_execution WHERE state='FAILED_FINAL'),
  'checked_at',clock_timestamp()) $$;


ALTER FUNCTION core.ai_orchestrator_health() OWNER TO function_owner;

--
-- Name: ai_process_evidence_followups(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_process_evidence_followups() RETURNS TABLE(followup_id bigint, task_id bigint)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
DECLARE r record; latest_id bigint; k text; t bigint;
BEGIN
 SELECT max(anlik_id) INTO latest_id FROM core.kanit_anlik;
 FOR r IN SELECT f.* FROM core.ai_evidence_followup f JOIN core.acik_soru q ON q.soru_id=f.question_id WHERE f.state='WAITING' AND q.durum='ANSWERED' AND latest_id>f.baseline_evidence_id FOR UPDATE OF f SKIP LOCKED LOOP
  k:=format('ai:followup:decision:%s:evidence:%s:v1',r.decision_id,latest_id);
  SELECT a.task_id INTO t FROM core.ai_task a WHERE a.idempotency_key=k;
  IF t IS NULL THEN t:=core.ai_enqueue_task('KARAR',r.decision_id,'PROPOSE_DECISION',k,'decision-v1',90,clock_timestamp(),true,'ANSWERED_QUESTION_AND_NEW_EVIDENCE',(SELECT config_value FROM core.ai_orchestrator_config WHERE config_key='cutoff_version')); END IF;
  UPDATE core.ai_evidence_followup f SET state='ENQUEUED',enqueued_task_id=t,enqueued_at=clock_timestamp() WHERE f.followup_id=r.followup_id;
  followup_id:=r.followup_id;task_id:=t;RETURN NEXT;
 END LOOP;
END$$;


ALTER FUNCTION core.ai_process_evidence_followups() OWNER TO function_owner;

--
-- Name: ai_propose_action(bigint, uuid, text, text, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_propose_action(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_action_type text, p_payload jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_task core.ai_task%ROWTYPE; v_type core.ai_action_type%ROWTYPE; v_action_id bigint;
BEGIN
  IF p_idempotency_key IS NULL OR p_idempotency_key NOT LIKE 'action:%' THEN RAISE EXCEPTION 'action idempotency key required'; END IF;
  IF p_payload IS NULL OR jsonb_typeof(p_payload)<>'object' OR pg_column_size(p_payload)>16384 THEN RAISE EXCEPTION 'invalid action payload'; END IF;
  IF core.ai_jsonb_has_forbidden_key(p_payload) THEN RAISE EXCEPTION 'forbidden action payload key'; END IF;
  SELECT * INTO v_task FROM core.ai_task WHERE task_id=p_task_id FOR UPDATE;
  IF NOT FOUND OR v_task.state<>'LEASED' OR v_task.task_type<>'PROPOSE_ACTION' THEN RAISE EXCEPTION 'invalid action task'; END IF;
  IF v_task.lease_token IS DISTINCT FROM p_lease_token OR v_task.lease_until<clock_timestamp() THEN RAISE EXCEPTION 'invalid or expired lease'; END IF;
  SELECT * INTO v_type FROM core.ai_action_type WHERE action_type=p_action_type AND proposal_enabled FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'action type disabled'; END IF;

  CASE p_action_type
    WHEN 'REQUEST_HUMAN_REVIEW' THEN
      IF p_payload - ARRAY['subject_ref','reason'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'subject_ref')<>'string' OR jsonb_typeof(p_payload->'reason')<>'string' OR length(p_payload->>'reason')>2000 THEN RAISE EXCEPTION 'invalid review payload'; END IF;
    WHEN 'DRAFT_CUSTOMER_REPLY' THEN
      IF p_payload - ARRAY['conversation_ref','channel','draft_text'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'conversation_ref')<>'string' OR p_payload->>'channel' NOT IN ('WHATSAPP','INSTAGRAM','WEB') OR jsonb_typeof(p_payload->'draft_text')<>'string' OR length(p_payload->>'draft_text')>4000 THEN RAISE EXCEPTION 'invalid draft payload'; END IF;
    WHEN 'WHATSAPP_SEND_TEMPLATE' THEN
      IF p_payload - ARRAY['recipient_ref','template_ref','variables'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'recipient_ref')<>'string' OR jsonb_typeof(p_payload->'template_ref')<>'string' OR jsonb_typeof(p_payload->'variables')<>'object' THEN RAISE EXCEPTION 'invalid whatsapp payload'; END IF;
    WHEN 'META_CAMPAIGN_CHANGE' THEN
      IF p_payload - ARRAY['campaign_ref','operation','reason'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'campaign_ref')<>'string' OR p_payload->>'operation' NOT IN ('PAUSE','RESUME') OR jsonb_typeof(p_payload->'reason')<>'string' THEN RAISE EXCEPTION 'invalid meta payload'; END IF;
    WHEN 'WIX_PUBLISH' THEN
      IF p_payload - ARRAY['site_ref','release_ref','reason'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'site_ref')<>'string' OR jsonb_typeof(p_payload->'release_ref')<>'string' OR jsonb_typeof(p_payload->'reason')<>'string' THEN RAISE EXCEPTION 'invalid wix payload'; END IF;
    WHEN 'PRICE_CHANGE' THEN
      IF p_payload - ARRAY['product_ref','proposed_price','currency','reason'] <> '{}'::jsonb OR jsonb_typeof(p_payload->'product_ref')<>'string' OR jsonb_typeof(p_payload->'proposed_price')<>'number' OR (p_payload->>'proposed_price')::numeric<=0 OR p_payload->>'currency'<>'TRY' OR jsonb_typeof(p_payload->'reason')<>'string' THEN RAISE EXCEPTION 'invalid price payload'; END IF;
    ELSE RAISE EXCEPTION 'unsupported action type';
  END CASE;

  INSERT INTO core.ai_action_proposal(task_id,idempotency_key,action_type,payload,payload_hash,risk_class,proposed_by,expires_at)
  VALUES(p_task_id,p_idempotency_key,p_action_type,p_payload,md5(p_payload::text),v_type.risk_class,session_user,clock_timestamp()+interval '24 hours')
  RETURNING action_id INTO v_action_id;
  UPDATE core.ai_task SET state='NEEDS_REVIEW',completed_at=clock_timestamp(),lease_until=NULL WHERE task_id=p_task_id;
  RETURN v_action_id;
END $$;


ALTER FUNCTION core.ai_propose_action(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_action_type text, p_payload jsonb) OWNER TO function_owner;

--
-- Name: ai_provider_allowed(text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_provider_allowed(p text) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
WITH b AS(SELECT * FROM core.ai_provider_budget WHERE provider=p), failures AS(
 SELECT count(*) n,max(started_at) last_at FROM(
  SELECT a.started_at FROM core.ai_provider_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-make_interval(mins=>b.failure_window_minutes) AND a.result_class IN('RATE_LIMIT','TIMEOUT','PROVIDER_ERROR','ERROR')
  UNION ALL SELECT a.started_at FROM core.ai_red_team_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-make_interval(mins=>b.failure_window_minutes) AND a.result_class='ERROR')x), usage AS(
 SELECT (SELECT count(*) FROM core.ai_provider_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-interval '24 hours')+(SELECT count(*) FROM core.ai_red_team_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-interval '24 hours') attempts,
 (SELECT coalesce(sum(input_tokens+output_tokens),0) FROM core.ai_provider_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-interval '24 hours')+(SELECT coalesce(sum(input_tokens+output_tokens),0) FROM core.ai_red_team_attempt a,b WHERE a.provider=b.provider AND a.started_at>=now()-interval '24 hours') tokens)
SELECT coalesce(b.enabled AND usage.attempts<b.daily_attempt_limit AND usage.tokens<b.daily_token_limit AND NOT(failures.n>=b.failure_threshold AND failures.last_at>=now()-make_interval(mins=>b.cooldown_minutes)),false) FROM b,failures,usage$$;


ALTER FUNCTION core.ai_provider_allowed(p text) OWNER TO function_owner;

--
-- Name: ai_question_context(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_question_context() RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$SELECT jsonb_build_object('security',jsonb_build_object('content_role','UNTRUSTED_DATA','external_actions',false),'evidence',(SELECT to_jsonb(x)FROM(SELECT anlik_id,alindi,veri_kalitesi,eksik_kaynak,kanit_puani,kanit_sinifi,pencere_7,pencere_30 FROM core.kanit_anlik ORDER BY alindi DESC,anlik_id DESC LIMIT 1)x),'source_gaps',(SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb)FROM(SELECT alan,authority,freshness,gap FROM core.source_authority WHERE gap IS NOT NULL AND gap<>'' ORDER BY alan LIMIT 20)x))$$;


ALTER FUNCTION core.ai_question_context() OWNER TO function_owner;

--
-- Name: ai_route_question(bigint, text[], text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_route_question(p_soru bigint, p_departments text[], p_reason text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE d text;mid bigint;n int:=0;q core.acik_soru%ROWTYPE;BEGIN
 IF cardinality(p_departments)NOT BETWEEN 1 AND 4 OR length(coalesce(p_reason,''))NOT BETWEEN 10 AND 2000 THEN RAISE EXCEPTION'invalid route';END IF;
 SELECT * INTO q FROM core.acik_soru WHERE soru_id=p_soru AND ureten='ORCHESTRATOR' AND durum='OPEN' FOR UPDATE;IF NOT FOUND THEN RAISE EXCEPTION'question not routable';END IF;
 IF cardinality(p_departments)<>(SELECT count(DISTINCT x)FROM unnest(p_departments)x) THEN RAISE EXCEPTION'duplicate department';END IF;
 FOREACH d IN ARRAY p_departments LOOP
  IF NOT EXISTS(SELECT 1 FROM core.departman WHERE kod=d)THEN RAISE EXCEPTION'invalid department';END IF;
  IF NOT EXISTS(SELECT 1 FROM core.ai_question_route WHERE soru_id=p_soru AND departman=d)THEN
   INSERT INTO core.ic_mesaj(kimden,kime,tip,konu,icerik,bagli_soru,durum)VALUES('AI_OPS',d,'TASK','AI veri açığı sorusu #'||p_soru,q.soru||E'\n\nYönlendirme gerekçesi: '||p_reason,p_soru,'OPEN')RETURNING mesaj_id INTO mid;
   INSERT INTO core.ai_question_route VALUES(p_soru,d,mid,p_reason,now());n:=n+1;
  END IF;
 END LOOP;
 UPDATE core.acik_soru SET gereken_departmanlar=p_departments,guncelleme=clock_timestamp()WHERE soru_id=p_soru;
 RETURN n;END$$;


ALTER FUNCTION core.ai_route_question(p_soru bigint, p_departments text[], p_reason text) OWNER TO function_owner;

--
-- Name: ai_rt_claim(text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_claim(p_worker text) RETURNS TABLE(job_id bigint, lease_token uuid, karar_id bigint)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$BEGIN RETURN QUERY WITH c AS(SELECT j.job_id FROM core.ai_red_team_job j WHERE (j.state IN('OPEN','RETRY') OR(j.state='LEASED' AND j.lease_until<now())) AND j.attempt_count<6 ORDER BY j.job_id FOR UPDATE SKIP LOCKED LIMIT 1),u AS(UPDATE core.ai_red_team_job j SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),lease_until=now()+interval '5 minutes',attempt_count=j.attempt_count+1 FROM c WHERE j.job_id=c.job_id RETURNING j.job_id,j.lease_token,j.karar_id) SELECT * FROM u; END$$;


ALTER FUNCTION core.ai_rt_claim(p_worker text) OWNER TO function_owner;

--
-- Name: ai_rt_complete(bigint, uuid, text, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_complete(p_job bigint, p_token uuid, p_result text, p_type text, p_reason text, p_ref text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE k bigint;r bigint;BEGIN IF p_result NOT IN('SUPPORT','CHALLENGE','INSUFFICIENT_EVIDENCE') OR length(p_reason)<20 THEN RAISE EXCEPTION 'invalid result';END IF;SELECT karar_id INTO k FROM core.ai_red_team_job WHERE job_id=p_job AND lease_token=p_token AND state='LEASED' AND lease_until>=now() FOR UPDATE;IF k IS NULL THEN RAISE EXCEPTION 'invalid lease';END IF;INSERT INTO core.karar_red_team(karar_id,sonuc,itiraz_tipi,gerekce,kanit_referansi)VALUES(k,p_result,left(p_type,200),left(p_reason,4000),left(p_ref,1000))RETURNING inceleme_id INTO r;UPDATE core.ai_red_team_job SET state='DONE',lease_token=NULL,lease_until=NULL WHERE job_id=p_job;RETURN r;END$$;


ALTER FUNCTION core.ai_rt_complete(p_job bigint, p_token uuid, p_result text, p_type text, p_reason text, p_ref text) OWNER TO function_owner;

--
-- Name: ai_rt_context(bigint, uuid); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_context(p_job bigint, p_token uuid) RETURNS jsonb
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$SELECT jsonb_build_object('security',jsonb_build_object('content_role','UNTRUSTED_DATA_NOT_INSTRUCTIONS','profile','red-team-minimal','version','v2'),'decision',jsonb_build_object('karar_id',k.karar_id,'karar_tipi',k.karar_tipi,'urun',k.urun,'kanal',k.kanal,'oneri',k.oneri,'kanit_kalitesi',k.kanit_kalitesi,'beklenen_etki',k.beklenen_etki,'risk',k.risk,'yanlislama_kosulu',k.yanlislama_kosulu),'evidence',CASE WHEN e.anlik_id IS NULL THEN NULL ELSE jsonb_build_object('anlik_id',e.anlik_id,'alindi',e.alindi,'pencere_7',e.pencere_7,'pencere_30',e.pencere_30,'urun',e.urun,'kanal',e.kanal,'konusma',e.konusma,'veri_kalitesi',e.veri_kalitesi,'eksik_kaynak',e.eksik_kaynak,'kanit_puani',e.kanit_puani,'kanit_sinifi',e.kanit_sinifi)END,'source_authority',(SELECT coalesce(jsonb_agg(jsonb_build_object('alan',s.alan,'authority',s.authority,'freshness',s.freshness,'gap',s.gap)),'[]'::jsonb)FROM(SELECT alan,authority,freshness,gap FROM core.source_authority ORDER BY alan LIMIT 25)s))FROM core.ai_red_team_job j JOIN core.karar k USING(karar_id)LEFT JOIN core.kanit_anlik e USING(anlik_id)WHERE j.job_id=p_job AND j.lease_token=p_token AND j.state='LEASED' AND j.lease_until>=now()$$;


ALTER FUNCTION core.ai_rt_context(p_job bigint, p_token uuid) OWNER TO function_owner;

--
-- Name: ai_rt_fail(bigint, uuid, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_fail(p_job bigint, p_token uuid, p_error text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$BEGIN UPDATE core.ai_red_team_job SET state=CASE WHEN attempt_count>=6 THEN'FAILED' ELSE'RETRY' END,last_error=left(p_error,1000),lease_token=NULL,lease_until=NULL WHERE job_id=p_job AND lease_token=p_token;IF NOT FOUND THEN RAISE EXCEPTION'invalid lease';END IF;END$$;


ALTER FUNCTION core.ai_rt_fail(p_job bigint, p_token uuid, p_error text) OWNER TO function_owner;

--
-- Name: ai_rt_log(bigint, uuid, text, text, timestamp with time zone, timestamp with time zone, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_log(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE x bigint;BEGIN IF NOT EXISTS(SELECT 1 FROM core.ai_red_team_job WHERE job_id=p_job AND lease_token=p_token AND state='LEASED')THEN RAISE EXCEPTION'invalid lease';END IF;INSERT INTO core.ai_red_team_attempt(job_id,provider,model,started_at,finished_at,result_class,validation_result,failover_reason)VALUES(p_job,left(p_provider,64),left(p_model,128),p_started,p_finished,left(p_class,64),left(p_validation,64),left(p_reason,500))RETURNING attempt_id INTO x;RETURN x;END$$;


ALTER FUNCTION core.ai_rt_log(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text) OWNER TO function_owner;

--
-- Name: ai_rt_log_usage(bigint, text, integer, integer, boolean); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_log_usage(p_job bigint, p_provider text, p_input integer, p_output integer, p_estimated boolean DEFAULT true) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$BEGIN
 IF p_input<0 OR p_output<0 OR p_input>1000000 OR p_output>100000 THEN RAISE EXCEPTION'invalid token usage';END IF;
 UPDATE core.ai_red_team_attempt SET input_tokens=p_input,output_tokens=p_output,token_estimated=p_estimated WHERE attempt_id=(SELECT attempt_id FROM core.ai_red_team_attempt WHERE job_id=p_job AND provider=p_provider ORDER BY attempt_id DESC LIMIT 1);
END$$;


ALTER FUNCTION core.ai_rt_log_usage(p_job bigint, p_provider text, p_input integer, p_output integer, p_estimated boolean) OWNER TO function_owner;

--
-- Name: ai_rt_log_v2(bigint, uuid, text, text, timestamp with time zone, timestamp with time zone, text, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_log_v2(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text, p_hash text) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE x bigint;BEGIN IF NOT EXISTS(SELECT 1 FROM core.ai_red_team_job WHERE job_id=p_job AND lease_token=p_token AND state='LEASED')THEN RAISE EXCEPTION'invalid lease';END IF;INSERT INTO core.ai_red_team_attempt(job_id,provider,model,started_at,finished_at,latency_ms,result_class,rate_limit,timeout,validation_result,failover_reason,context_profile,context_version,context_hash)VALUES(p_job,left(p_provider,64),left(p_model,128),p_started,p_finished,greatest(0,extract(epoch from(p_finished-p_started))*1000)::int,left(p_class,64),p_reason~'429|rate.?limit',p_reason~'timeout|abort',left(p_validation,64),left(p_reason,500),'red-team-minimal','v2',left(p_hash,128))RETURNING attempt_id INTO x;RETURN x;END$$;


ALTER FUNCTION core.ai_rt_log_v2(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text, p_hash text) OWNER TO function_owner;

--
-- Name: ai_rt_sync(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_rt_sync() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE n int; c timestamptz; BEGIN SELECT config_value::timestamptz INTO c FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after'; IF c IS NULL THEN RAISE EXCEPTION 'cutoff missing'; END IF; INSERT INTO core.ai_red_team_job(karar_id) SELECT karar_id FROM core.karar WHERE durum='PROPOSED' AND olusturma>=c ON CONFLICT DO NOTHING; GET DIAGNOSTICS n=ROW_COUNT; RETURN n; END$$;


ALTER FUNCTION core.ai_rt_sync() OWNER TO function_owner;

--
-- Name: ai_save_jarvis_task_state(bigint, bigint, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_save_jarvis_task_state(p_task_id bigint, p_expected_version bigint, p_state jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_version bigint;
BEGIN
  IF p_task_id IS NULL OR p_expected_version IS NULL OR p_expected_version < 0 THEN
    RAISE EXCEPTION 'invalid task state request';
  END IF;
  IF p_state IS NULL OR jsonb_typeof(p_state) <> 'object' THEN
    RAISE EXCEPTION 'state must be a JSON object';
  END IF;
  IF core.ai_jsonb_has_forbidden_key(p_state) THEN
    RAISE EXCEPTION 'forbidden state payload';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM core.ai_task WHERE task_id = p_task_id) THEN
    RAISE EXCEPTION 'unknown task';
  END IF;

  IF p_expected_version = 0 THEN
    INSERT INTO core.jarvis_task_state(task_id, state_json)
    VALUES (p_task_id, p_state)
    ON CONFLICT (task_id) DO NOTHING
    RETURNING version INTO v_version;
  ELSE
    UPDATE core.jarvis_task_state
       SET state_json = p_state,
           version = version + 1,
           updated_at = clock_timestamp()
     WHERE task_id = p_task_id
       AND version = p_expected_version
    RETURNING version INTO v_version;
  END IF;

  IF v_version IS NULL THEN
    RAISE EXCEPTION 'task state version conflict';
  END IF;
  RETURN v_version;
END;
$$;


ALTER FUNCTION core.ai_save_jarvis_task_state(p_task_id bigint, p_expected_version bigint, p_state jsonb) OWNER TO function_owner;

--
-- Name: ai_write_executive_brief(text, text, text, text, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_write_executive_brief(p_key text, p_provider text, p_model text, p_hash text, p_content jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
DECLARE mid bigint;
BEGIN
 IF p_key!~'^brief:[0-9]{4}-[0-9]{2}-[0-9]{2}:' OR length(p_key)>100 THEN RAISE EXCEPTION'invalid key';END IF;
 IF jsonb_typeof(p_content)<>'object' OR p_content-ARRAY['executive_summary','priorities','risks','decisions_to_review']<>'{}'::jsonb THEN RAISE EXCEPTION'invalid schema';END IF;
 IF jsonb_typeof(p_content->'executive_summary')<>'string' OR jsonb_typeof(p_content->'priorities')<>'array' OR jsonb_typeof(p_content->'risks')<>'array' OR jsonb_typeof(p_content->'decisions_to_review')<>'array' OR pg_column_size(p_content)>16000 THEN RAISE EXCEPTION'invalid content';END IF;
 IF p_content::text~*'(https?://|curl |wget |insert into|update [a-z]|delete from|drop table|shell|command)' THEN RAISE EXCEPTION'forbidden action content';END IF;
 SELECT message_id INTO mid FROM core.ai_executive_brief WHERE brief_key=p_key;IF mid IS NOT NULL THEN RETURN mid;END IF;
 INSERT INTO core.ic_mesaj(kimden,kime,tip,konu,icerik,durum)VALUES('AI_OPS','EXEC','HANDOFF','AI Günlük Yönetici Özeti · '||split_part(p_key,':',2),p_content::text,'OPEN')RETURNING mesaj_id INTO mid;
 INSERT INTO core.ai_executive_brief(brief_key,message_id,provider,model,context_hash)VALUES(p_key,mid,left(p_provider,64),left(p_model,128),left(p_hash,128));
 RETURN mid;
END$$;


ALTER FUNCTION core.ai_write_executive_brief(p_key text, p_provider text, p_model text, p_hash text, p_content jsonb) OWNER TO function_owner;

--
-- Name: ai_write_generated_question(text, text, text, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.ai_write_generated_question(p_key text, p_provider text, p_hash text, p_data jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $_$DECLARE id bigint;BEGIN
 IF p_key!~'^question:evidence:[0-9]+:v1$' THEN RAISE EXCEPTION'invalid key';END IF;
 SELECT soru_id INTO id FROM core.ai_generated_question WHERE question_key=p_key;IF id IS NOT NULL THEN RETURN id;END IF;
 IF p_data-ARRAY['soru','neden_onemli','kaynak_plani','oncelik','beklenen_bilgi_degeri']<>'{}'::jsonb OR p_data->>'oncelik' NOT IN('P0','P1','P2','P3','P4') OR p_data->>'beklenen_bilgi_degeri' NOT IN('YUKSEK','ORTA','DUSUK') OR length(p_data->>'soru')NOT BETWEEN 10 AND 1000 OR pg_column_size(p_data)>8000 THEN RAISE EXCEPTION'invalid question';END IF;
 IF p_data::text~*'(https?://|curl |wget |insert into|update [a-z]|delete from|drop table|shell|command)' THEN RAISE EXCEPTION'forbidden content';END IF;
 INSERT INTO core.acik_soru(hedef,soru,neden_onemli,beklenen_bilgi_degeri,kaynak_plani,ureten,durum,oncelik,proje)VALUES('SIRKET',p_data->>'soru',p_data->>'neden_onemli',p_data->>'beklenen_bilgi_degeri',p_data->>'kaynak_plani','ORCHESTRATOR','OPEN',p_data->>'oncelik','AI_COMPANY_INTELLIGENCE')RETURNING soru_id INTO id;
 INSERT INTO core.ai_generated_question VALUES(p_key,id,left(p_provider,64),left(p_hash,128),now());RETURN id;END$_$;


ALTER FUNCTION core.ai_write_generated_question(p_key text, p_provider text, p_hash text, p_data jsonb) OWNER TO function_owner;

--
-- Name: anlik_yaz(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.anlik_yaz(p_surum text) RETURNS TABLE(gun date, no integer, hazir boolean)
    LANGUAGE plpgsql
    AS $$
DECLARE
  v_gun  date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
  v_no   int;
  v_haz  record;
  v_met  jsonb;
  v_kap  jsonb;
BEGIN
  SELECT coalesce(max(calisma_no), 0) + 1 INTO v_no
    FROM core.rapor_anlik WHERE rapor_gunu = v_gun;

  SELECT * INTO v_haz FROM mart.hazirlik_ozet;

  -- Kapsama: neyin ne kadari olculuyor
  SELECT jsonb_build_object(
    'maliyet_kapsama_yuzde', (SELECT round(100.0 * coalesce(sum(satir_ciro_net) FILTER (WHERE maliyeti_biliniyor),0)
                                           / nullif(sum(satir_ciro_net),0), 1)
                                FROM mart.siparis_kalem
                               WHERE ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),
    'maliyet_olculmus_urun',  (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='OLCULMUS'),
    'maliyet_tahmin_urun',    (SELECT count(*) FROM mart.maliyet_kalite WHERE kalite='TAHMIN'),
    'maliyet_kdv_tabani',     (SELECT coalesce(max(kdv_tabani),'TEYIT_EDILMEDI') FROM mart.maliyet_kalite),
    'reklam_hesap_durumu',    (SELECT current_connection FROM core.source_authority WHERE alan='ad_spend'),
    'gonderi_eslesmeyen',     (SELECT count(*) FROM mart.siparis_para WHERE NOT gonderi_kaydi_var)
  ) INTO v_kap;

  -- 🔴 Olcum penceresi ICINDEKI rakamlar. Pencere acilmadiysa hepsi 0
  --    olur - bu dogrudur ve o gun gercekten oyle gorunuyordu.
  SELECT jsonb_build_object(
    'siparis',            coalesce((SELECT count(*) FROM mart.siparis WHERE olcumde),0),
    'ciro_dogrulanmis',   coalesce((SELECT sum(ciro_dogrulanmis)     FROM mart.siparis WHERE olcumde),0),
    'ciro_beyan',         coalesce((SELECT sum(ciro_beyan_edilmis)   FROM mart.siparis WHERE olcumde),0),
    'ciro_net_dogrulanmis',coalesce((SELECT sum(ciro_dogrulanmis_net) FROM mart.siparis WHERE olcumde),0),
    'ciro_net_beyan',     coalesce((SELECT sum(ciro_beyan_edilmis_net) FROM mart.siparis WHERE olcumde),0),
    'kdv',                coalesce((SELECT sum(kdv) FROM mart.siparis WHERE olcumde
                                     AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),0),
    'teslim_net_satis',   coalesce((SELECT sum(teslim_net_satis) FROM mart.siparis_para WHERE olcumde),0),
    'cod_bekleyen',       coalesce((SELECT sum(cod_bekleyen)     FROM mart.siparis_para WHERE olcumde),0),
    'reklam_harcamasi',   coalesce((SELECT sum(reklam_harcamasi) FROM mart.gunluk_verimlilik),0),
    'brut_marj',          (SELECT sum(brut_marj) FROM mart.siparis_kalem
                            WHERE olcumde AND ciro_sinifi IN ('DOGRULANMIS','BEYAN_EDILMIS')),
    'acik_is',            coalesce((SELECT count(*) FROM mart.acik_isler),0),
    'cevapsiz_mesaj',     coalesce((SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat > 24),0)
  ) INTO v_met;

  INSERT INTO core.rapor_anlik (rapor_gunu, calisma_no, metrik_surumu,
                                karar_hazir, eksikler, kapsama_json, metrikler)
  VALUES (v_gun, v_no, p_surum, v_haz.karar_hazir, v_haz.eksikler, v_kap, v_met);

  RETURN QUERY SELECT v_gun, v_no, v_haz.karar_hazir;
END $$;


ALTER FUNCTION core.anlik_yaz(p_surum text) OWNER TO n8n;

--
-- Name: bilesen_bul(text, timestamp with time zone); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.bilesen_bul(p_bilesen text, p_tarih timestamp with time zone) RETURNS TABLE(deger numeric, uygulama text, kanit_sinifi text, kritiklik text)
    LANGUAGE sql STABLE
    AS $$
  SELECT m.deger, m.uygulama, m.kanit_sinifi, m.kritiklik
    FROM core.maliyet_bileseni m
   WHERE m.bilesen = p_bilesen
     AND m.gecerli_baslangic <= p_tarih
     AND (m.gecerli_bitis IS NULL OR m.gecerli_bitis > p_tarih)
   ORDER BY m.gecerli_baslangic DESC
   LIMIT 1;
$$;


ALTER FUNCTION core.bilesen_bul(p_bilesen text, p_tarih timestamp with time zone) OWNER TO n8n;

--
-- Name: birlestirmeleri_uygula(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.birlestirmeleri_uygula() RETURNS TABLE(kid bigint, sonuc text, aciklama text)
    LANGUAGE plpgsql
    AS $$
DECLARE k record; c_a bigint; c_b bigint; c_t bigint; n int;
BEGIN
  FOR k IN SELECT * FROM core.birlestirme_karari WHERE karar='BIRLESTIR' ORDER BY 1
  LOOP
    SELECT ci.customer_id INTO c_a FROM core.customer_identity ci
     WHERE ci.kaynak=k.kaynak AND ci.kimlik_tipi=k.kimlik_tipi
       AND ci.source_customer_id=k.source_id_a LIMIT 1;
    SELECT ci.customer_id INTO c_b FROM core.customer_identity ci
     WHERE ci.kaynak=k.kaynak AND ci.kimlik_tipi=k.kimlik_tipi
       AND ci.source_customer_id=k.source_id_b LIMIT 1;

    IF c_a IS NULL OR c_b IS NULL THEN
      -- 🔴 Karar var ama taraflardan biri veride YOK. Bu sessiz gecilmez:
      --    ya kimlik henuz yuklenmedi ya da karardaki id yanlis yazildi.
      kid := k.karar_id; sonuc := 'BEKLIYOR';
      aciklama := format('taraflar bulunamadi (a=%s b=%s)',
                         coalesce(c_a::text,'YOK'), coalesce(c_b::text,'YOK'));
      RETURN NEXT; CONTINUE;
    END IF;

    IF c_a = c_b THEN
      kid := k.karar_id; sonuc := 'ZATEN_BIRLESIK';
      aciklama := format('customer_id=%s', c_a);
      RETURN NEXT; CONTINUE;
    END IF;

    -- Kucuk customer_id hayatta kalir: kararin a/b sirasi degisse bile
    -- sonuc AYNI olur (belirlenimci birlestirme).
    IF c_a > c_b THEN c_t := c_a; c_a := c_b; c_b := c_t; END IF;

    UPDATE core.customer_identity SET customer_id = c_a, updated_at = now()
     WHERE customer_id = c_b;
    GET DIAGNOSTICS n = ROW_COUNT;

    UPDATE core.customer SET
      phone_normalized = coalesce(phone_normalized,
                                  (SELECT phone_normalized FROM core.customer WHERE customer_id=c_b)),
      email_normalized = coalesce(email_normalized,
                                  (SELECT email_normalized FROM core.customer WHERE customer_id=c_b)),
      identity_status  = 'MATCHED',
      match_method     = 'SAHIP_KARARI',
      match_confidence = 100,
      notlar = coalesce(notlar,'{}'::jsonb) || jsonb_build_object(
                 'birlestirme', jsonb_build_object(
                   'karar_id', k.karar_id, 'yutulan_customer_id', c_b,
                   'karar_veren', k.karar_veren, 'gerekce', k.gerekce,
                   'uygulandi_at', now())),
      updated_at = now()
     WHERE customer_id = c_a;

    DELETE FROM core.customer WHERE customer_id = c_b;

    -- Bu iki musteriyi kapsayan cakismalar artik gecerli degil.
    UPDATE core.identity_conflict
       SET customer_ids = array_remove(customer_ids, c_b),
           durum = 'COZULDU',
           cozum_notu = format('Sahip karari #%s ile birlestirildi (customer %s -> %s).',
                               k.karar_id, c_b, c_a),
           cozum_at = now()
     WHERE customer_ids @> ARRAY[c_a] AND customer_ids @> ARRAY[c_b];

    UPDATE core.birlestirme_karari SET uygulandi_at = now() WHERE karar_id = k.karar_id;

    kid := k.karar_id; sonuc := 'BIRLESTIRILDI';
    aciklama := format('customer %s -> %s, %s kimlik tasindi', c_b, c_a, n);
    RETURN NEXT;
  END LOOP;
END $$;


ALTER FUNCTION core.birlestirmeleri_uygula() OWNER TO n8n;

--
-- Name: brief_uret(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.brief_uret(p_surum text DEFAULT 'CR-014'::text) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE v_id bigint; v_kal record; v_d7 record; v_d30 record;
BEGIN
  SELECT * INTO v_kal FROM mart.kanit_kalitesi;
  SELECT * INTO v_d7  FROM mart.nakit_ozet(7);
  SELECT * INTO v_d30 FROM mart.nakit_ozet(30);

  INSERT INTO core.kanit_anlik (surum, pencere_7, pencere_30, urun, kanal, konusma,
                                veri_kalitesi, eksik_kaynak, kanit_puani, kanit_sinifi)
  VALUES (
    p_surum,
    to_jsonb(v_d7), to_jsonb(v_d30),
    (SELECT coalesce(jsonb_agg(to_jsonb(u)), '[]'::jsonb) FROM mart.urun_sinyal u),
    (SELECT coalesce(jsonb_agg(to_jsonb(m)), '[]'::jsonb) FROM mart.meta_sinyal m),
    -- 🔴 OLCUM YONTEMI KANITLA BIRLIKTE SAKLANIR.  "137 konusma" tek basina
    --    bir sey ifade etmez; nasil olculdugu, normalize edilip edilmedigi
    --    ve sorgu surumu olmadan sonradan dogrulanamaz. Ayrica konusma ve
    --    mesaj sayilari AYRI durur - biri digerinin yerine kullanilamasin.
    (SELECT jsonb_build_object(
       'konusma', (SELECT count(*) FROM lcarlie.konusma),
       'cevapsiz_24s', (SELECT count(*) FROM mart.konusma_cevapsiz WHERE bekleme_saat>24),
       'en_eski_gun', (SELECT coalesce(round(max(bekleme_saat)/24.0,1),0) FROM mart.konusma_cevapsiz),
       'soru_konu', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                        'konu',                  k.konu,
                        'distinct_conversations', k.distinct_konusma,
                        'matched_messages',       k.eslesen_mesaj,
                        'konusma_yuzde',          k.konusma_yuzde,
                        'sample_examples',        to_jsonb(k.ornekler),
                        'measurement_method',     k.olcum_yontemi,
                        'normalized',             k.normalize_edildi,
                        'query_version',          k.sorgu_surumu)
                        ORDER BY k.distinct_konusma DESC), '[]'::jsonb)
                      FROM mart.soru_konu k),
       -- Veride bulunmadigi icin KATEGORI ACILMAYAN konular da kayda gecer.
       'acilmayan_kategoriler', '["kargo","teslimat","iade","odeme","kapida_odeme","gizlilik_paket"]'::jsonb)),
    (SELECT coalesce(jsonb_agg(to_jsonb(v)), '[]'::jsonb) FROM mart.nakit_veri_kalitesi v),
    (SELECT coalesce(jsonb_agg(jsonb_build_object('alan',alan,'durum',current_connection)), '[]'::jsonb)
       FROM core.source_authority WHERE current_connection <> 'CONNECTED'),
    v_kal.puan, v_kal.sinif)
  RETURNING anlik_id INTO v_id;

  -- URUN bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  SELECT v_id, 'URUN', 'OBSERVED', u.sinif,
         format('%s — %s', left(u.urun_adi,40), u.sinif),
         format('%s adet · net ciro %s TL · brut katki %s TL (%s%%) · maliyet kalitesi %s',
                u.adet, to_char(u.ciro_net,'FM999990.00'), to_char(u.brut_marj,'FM999990.00'),
                u.brut_marj_yuzde, u.maliyet_kalitesi),
         u.gerekce, 'Reklam atfi YOK: bu urunun reklamla iliskisi olculemiyor',
         v_kal.sinif,
         'Olculmus urun maliyeti girildiginde brut katki degisirse bu siniflandirma gecersizdir'
    FROM mart.urun_sinyal u;

  -- META bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  SELECT v_id, 'META', 'OBSERVED', m.nakit_durum,
         format('Son %s gun · %s', m.pencere, m.nakit_durum),
         format('harcama %s TL (kapsama %s) · net ciro %s TL · oran %s · %s gun harcama var siparis yok · kreatif verisi %s',
                to_char(m.harcama,'FM999990.00'), m.hesap_kapsamasi,
                to_char(m.net_ciro,'FM999990.00'), coalesce(m.ciro_harcama_orani,0),
                m.harcamali_satissiz_gun, m.kreatif_seviyesi_veri),
         'Harcama durdurulursa nakit cikisi durur', 'Talep tamamen durabilir',
         v_kal.sinif,
         'Okunamayan 2 hesapta harcama YOKSA ve gercek ciro olculenden yuksekse sonuc degisir'
    FROM mart.meta_sinyal m;

  -- CRO bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, baslik, kanit, kanit_sinifi, yanlislama)
  SELECT v_id, 'CRO', c.seviye, c.kod, c.bulgu, v_kal.sinif,
         'GA4 baglandiginda davranis verisi bu cikarimi dogrulamaz ya da curutur'
    FROM mart.cro_sinyal c;

  -- PAZAR bulgulari
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit, kanit_sinifi)
  SELECT v_id, 'PAZAR', p.seviye, p.durum, p.kod, p.bulgu, v_kal.sinif
    FROM mart.pazar_sinyal p;

  -- KREATIF hipotezleri  (HYPOTHESIS - kazanan degil)
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit,
                                 beklenen_etki, risk, kanit_sinifi, yanlislama)
  -- 🔴 Kanit metni HIPOTEZIN KENDI sayisindan kurulur; ortak sayi paylasilmaz.
  -- 🔴 KONUSMA ve MESAJ ayri yazilir; olcum yontemi ve sorgu surumu kanitin
  --    parcasidir - "137" sayisi yontemi bilinmeden dogrulanamaz.
  SELECT v_id, 'KREATIF', 'HYPOTHESIS', 'TEST_SMALL', h.kod || ' — ' || h.hipotez,
         format('%s tekil konusma / %s mesaj (%s/%s konusma = %%%s) — %s · yontem: %s · surum: %s',
                h.adet, h.mesaj, h.adet, h.toplam, h.yuzde, h.kanit,
                h.olcum_yontemi, h.sorgu_surumu),
         h.beklenen_etki, h.risk, v_kal.sinif, h.yanlislama
    FROM mart.kreatif_hipotez h;

  -- RED TEAM  (bagimsiz)
  INSERT INTO core.buyume_bulgu (anlik_id, modul, seviye, sinif, baslik, kanit, kanit_sinifi)
  SELECT v_id, 'RED_TEAM', 'OBSERVED', r.hukum, r.baslik, r.gerekce, v_kal.sinif
    FROM mart.red_team r;

  RETURN v_id;
END $$;


ALTER FUNCTION core.brief_uret(p_surum text) OWNER TO n8n;

--
-- Name: bulgu_hipotez_kontrol(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.bulgu_hipotez_kontrol() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.seviye = 'HYPOTHESIS'
     AND (NEW.fikrimi_degistirecek IS NULL OR btrim(NEW.fikrimi_degistirecek) = '')
     AND (NEW.yanlislama IS NULL OR btrim(NEW.yanlislama) = '') THEN
    RAISE EXCEPTION
      'HYPOTHESIS kaydi yanlislama veya fikrimi_degistirecek olmadan yazilamaz (bulgu: %)',
      left(NEW.baslik, 80);
  END IF;
  NEW.guncelleme := clock_timestamp();
  RETURN NEW;
END $$;


ALTER FUNCTION core.bulgu_hipotez_kontrol() OWNER TO n8n;

--
-- Name: eposta_normal(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.eposta_normal(p_ham text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $_$
DECLARE e text;
BEGIN
  IF p_ham IS NULL THEN RETURN NULL; END IF;
  e := btrim(p_ham);
  IF e = '' THEN RETURN NULL; END IF;
  e := lower(e);
  -- en az bir '@' ve noktali alan adi
  IF e !~ '^[^@[:space:]]+@[^@[:space:]]+\.[a-z]{2,}$' THEN
    RETURN NULL;
  END IF;
  RETURN e;
END;
$_$;


ALTER FUNCTION core.eposta_normal(p_ham text) OWNER TO n8n;

--
-- Name: geo_obs_immutable(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.geo_obs_immutable() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.query_id  IS DISTINCT FROM OLD.query_id
  OR NEW.yuzey     IS DISTINCT FROM OLD.yuzey
  OR NEW.language  IS DISTINCT FROM OLD.language
  OR NEW.country   IS DISTINCT FROM OLD.country
  OR NEW.gozlem_at IS DISTINCT FROM OLD.gozlem_at
  OR NEW.ham_id    IS DISTINCT FROM OLD.ham_id
  OR NEW.cevap_hash IS DISTINCT FROM OLD.cevap_hash THEN
    RAISE EXCEPTION
      'geo_observation IMMUTABLE: yeni olcum yeni satir olmali '
      '(observation_id=%)', OLD.observation_id;
  END IF;
  RETURN NEW;
END $$;


ALTER FUNCTION core.geo_obs_immutable() OWNER TO n8n;

--
-- Name: human_conclude_decision(bigint, text, numeric, numeric, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.human_conclude_decision(p_karar bigint, p_metric text, p_baseline numeric, p_observed numeric, p_actor text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE s text;r text;BEGIN
 IF length(trim(coalesce(p_metric,'')))NOT BETWEEN 2 AND 200 OR length(trim(coalesce(p_actor,'')))NOT BETWEEN 3 AND 200 THEN RAISE EXCEPTION'invalid conclusion input';END IF;
 SELECT durum INTO s FROM core.karar WHERE karar_id=p_karar FOR UPDATE;
 IF s NOT IN('EXECUTED','MEASURING') THEN RAISE EXCEPTION'decision not measurable';END IF;
 r:=core.karar_sonuclandir(p_karar,p_metric,p_baseline,p_observed,p_actor);RETURN r;
END$$;


ALTER FUNCTION core.human_conclude_decision(p_karar bigint, p_metric text, p_baseline numeric, p_observed numeric, p_actor text) OWNER TO function_owner;

--
-- Name: human_decide_karar(bigint, text, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.human_decide_karar(p_karar bigint, p_decision text, p_note text, p_approver text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$
DECLARE current_status text;created_at timestamptz;cutoff timestamptz;new_status text;
BEGIN
 IF p_decision NOT IN('APPROVE','REJECT','DEFER','MODIFY') THEN RAISE EXCEPTION'invalid human decision';END IF;
 IF length(trim(coalesce(p_approver,''))) NOT BETWEEN 3 AND 200 THEN RAISE EXCEPTION'invalid approver';END IF;
 IF length(coalesce(p_note,''))>4000 THEN RAISE EXCEPTION'note too long';END IF;
 SELECT durum,olusturma INTO current_status,created_at FROM core.karar WHERE karar_id=p_karar FOR UPDATE;
 IF NOT FOUND OR current_status<>'PROPOSED' THEN RAISE EXCEPTION'decision is not PROPOSED';END IF;
 SELECT config_value::timestamptz INTO cutoff FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after';
 IF created_at>=cutoff AND NOT EXISTS(SELECT 1 FROM core.ai_red_team_job j JOIN core.karar_red_team r ON r.karar_id=j.karar_id WHERE j.karar_id=p_karar AND j.state='DONE') THEN RAISE EXCEPTION'red-team review required';END IF;
 INSERT INTO core.karar_insan(karar_id,karar,karar_zamani,karar_notu,onaylayan)VALUES(p_karar,p_decision,clock_timestamp(),p_note,p_approver);
 new_status:=CASE p_decision WHEN'REJECT'THEN'REJECTED' WHEN'DEFER'THEN'DEFERRED' ELSE'APPROVED' END;
 UPDATE core.karar SET durum=new_status WHERE karar_id=p_karar;
 RETURN new_status;
END$$;


ALTER FUNCTION core.human_decide_karar(p_karar bigint, p_decision text, p_note text, p_approver text) OWNER TO function_owner;

--
-- Name: human_supersede_decision(bigint, bigint, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.human_supersede_decision(p_old bigint, p_canonical bigint, p_approver text, p_reason text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core'
    AS $$DECLARE a core.karar%ROWTYPE;b core.karar%ROWTYPE;BEGIN
 IF p_old=p_canonical OR length(trim(coalesce(p_approver,'')))NOT BETWEEN 3 AND 200 OR length(trim(coalesce(p_reason,'')))NOT BETWEEN 10 AND 2000 THEN RAISE EXCEPTION'invalid supersede request';END IF;
 SELECT * INTO a FROM core.karar WHERE karar_id=p_old FOR UPDATE;SELECT * INTO b FROM core.karar WHERE karar_id=p_canonical FOR SHARE;
 IF a.durum NOT IN('PROPOSED','DEFERRED') OR b.durum<>'PROPOSED' THEN RAISE EXCEPTION'invalid decision state';END IF;
 IF (a.karar_tipi,coalesce(a.urun,''),coalesce(a.kanal,''),a.anlik_id)IS DISTINCT FROM(b.karar_tipi,coalesce(b.urun,''),coalesce(b.kanal,''),b.anlik_id)THEN RAISE EXCEPTION'decisions are not in same duplicate group';END IF;
 UPDATE core.karar SET ustunu_alan=p_canonical,gecersizlik_nedeni=p_reason,durum='CANCELLED' WHERE karar_id=p_old;
 INSERT INTO core.ai_human_supersede_audit(old_karar_id,canonical_karar_id,approver,reason)VALUES(p_old,p_canonical,p_approver,p_reason);
END$$;


ALTER FUNCTION core.human_supersede_decision(p_old bigint, p_canonical bigint, p_approver text, p_reason text) OWNER TO function_owner;

--
-- Name: jarvis_company_status(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.jarvis_company_status(p_state text) RETURNS text
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog', 'core'
    AS $$
    SELECT CASE p_state
        WHEN 'PROPOSED' THEN 'AWAITING_APPROVAL'
        WHEN 'APPROVED' THEN 'APPROVED'
        WHEN 'REJECTED' THEN 'DENIED'
        WHEN 'CANCELLED' THEN 'CANCELLED'
        WHEN 'EXECUTING' THEN 'RUNNING'
        WHEN 'EXECUTED' THEN 'COMPLETED'
        WHEN 'EXECUTION_FAILED' THEN 'FAILED'
        ELSE 'UNCERTAIN' END
$$;


ALTER FUNCTION core.jarvis_company_status(p_state text) OWNER TO n8n;

--
-- Name: jarvis_decide_company_action(bigint, text, text, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.jarvis_decide_company_action(p_action_id bigint, p_decision text, p_reason text, p_expected_hash text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_hash text;
BEGIN
    IF NOT pg_has_role(session_user,'human_approver','MEMBER') THEN
        RAISE EXCEPTION 'human approver membership required';
    END IF;
    IF p_expected_hash IS NULL OR p_expected_hash='' THEN
        RAISE EXCEPTION 'displayed action fingerprint required';
    END IF;
    SELECT payload_hash INTO v_hash FROM core.ai_action_proposal
        WHERE action_id=p_action_id AND state='PROPOSED' FOR UPDATE;
    IF NOT FOUND OR v_hash IS DISTINCT FROM p_expected_hash THEN
        RAISE EXCEPTION 'proposal changed or is no longer pending';
    END IF;
    PERFORM core.ai_decide_action(p_action_id,p_decision,p_reason);
END $$;


ALTER FUNCTION core.jarvis_decide_company_action(p_action_id bigint, p_decision text, p_reason text, p_expected_hash text) OWNER TO n8n;

--
-- Name: jarvis_record_company_vote(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.jarvis_record_company_vote() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
BEGIN
    INSERT INTO core.jarvis_action_registry_event
        (action_key,event_type,from_status,to_status,actor,note,at)
    VALUES ('company:' || NEW.action_id,'APPROVAL_VOTE',
            'AWAITING_APPROVAL','AWAITING_APPROVAL',NEW.approver_identity,
            left(NEW.decision || ': ' || NEW.reason,300),NEW.decided_at);
    RETURN NEW;
END $$;


ALTER FUNCTION core.jarvis_record_company_vote() OWNER TO n8n;

--
-- Name: jarvis_sync_company_action(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.jarvis_sync_company_action() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_before text; v_after text;
BEGIN
    v_after := core.jarvis_company_status(NEW.state);
    SELECT status INTO v_before FROM core.jarvis_action_registry
        WHERE action_key='company:' || NEW.action_id FOR UPDATE;
    INSERT INTO core.jarvis_action_registry
        (action_key,source,source_id,owner,kind,description,risk_level,
         payload_hash,status,created_at,updated_at,expires_at,payload,
         idempotency_key,approved_by,message,task_id)
    VALUES ('company:' || NEW.action_id,'company',NEW.action_id::text,'company',
            NEW.action_type,left(coalesce(NEW.payload->>'reason',NEW.action_type),2000),
            NEW.risk_class,NEW.payload_hash,v_after,NEW.proposed_at,
            coalesce(NEW.decided_at,NEW.proposed_at),NEW.expires_at,NEW.payload,
            NEW.idempotency_key,NEW.decided_by,NEW.decision_reason,NEW.task_id)
    ON CONFLICT(action_key) DO UPDATE SET
        kind=EXCLUDED.kind,description=EXCLUDED.description,
        risk_level=EXCLUDED.risk_level,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=clock_timestamp(),
        expires_at=EXCLUDED.expires_at,payload=EXCLUDED.payload,
        idempotency_key=EXCLUDED.idempotency_key,
        approved_by=EXCLUDED.approved_by,message=EXCLUDED.message,
        task_id=EXCLUDED.task_id;
    IF v_before IS NULL OR v_before IS DISTINCT FROM v_after THEN
        INSERT INTO core.jarvis_action_registry_event
            (action_key,event_type,from_status,to_status,actor,note)
        VALUES ('company:' || NEW.action_id,'STATE',v_before,v_after,
                coalesce(NEW.decided_by,NEW.proposed_by),
                left(coalesce(NEW.decision_reason,''),300));
    END IF;
    RETURN NEW;
END $$;


ALTER FUNCTION core.jarvis_sync_company_action() OWNER TO n8n;

--
-- Name: jarvis_sync_personal_action(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.jarvis_sync_personal_action() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'core', 'pg_temp'
    AS $$
DECLARE v_before text;
BEGIN
    SELECT status INTO v_before FROM core.jarvis_action_registry
        WHERE action_key='personal:' || NEW.action_id FOR UPDATE;
    INSERT INTO core.jarvis_action_registry
        (action_key,source,source_id,owner,kind,description,risk_level,
         payload_hash,status,created_at,updated_at,expires_at,payload,
         idempotency_key,approved_by,external_id,message)
    VALUES ('personal:' || NEW.action_id,'personal',NEW.action_id,NEW.owner,
            NEW.kind,left(NEW.description,2000),NEW.risk_level,
            NEW.payload_hash,NEW.status,NEW.created_at,NEW.updated_at,NEW.expires_at,
            NEW.payload,NEW.idempotency_key,NEW.approved_by,NEW.external_id,NEW.message)
    ON CONFLICT(action_key) DO UPDATE SET
        description=EXCLUDED.description,payload_hash=EXCLUDED.payload_hash,
        status=EXCLUDED.status,updated_at=EXCLUDED.updated_at,
        expires_at=EXCLUDED.expires_at,payload=EXCLUDED.payload,
        idempotency_key=EXCLUDED.idempotency_key,
        approved_by=EXCLUDED.approved_by,external_id=EXCLUDED.external_id,
        message=EXCLUDED.message;
    IF v_before IS NULL OR v_before IS DISTINCT FROM NEW.status THEN
        INSERT INTO core.jarvis_action_registry_event
            (action_key,event_type,from_status,to_status,actor,note)
        VALUES ('personal:' || NEW.action_id,'STATE',v_before,NEW.status,
                coalesce(NEW.approved_by,NEW.owner),left(coalesce(NEW.message,''),300));
    END IF;
    RETURN NEW;
END $$;


ALTER FUNCTION core.jarvis_sync_personal_action() OWNER TO n8n;

--
-- Name: karar_adaylari_uret(bigint, boolean); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.karar_adaylari_uret(p_anlik bigint DEFAULT NULL::bigint, p_fixture boolean DEFAULT false) RETURNS TABLE(yeni integer, atlanan integer)
    LANGUAGE plpgsql
    AS $$
DECLARE v_anlik bigint; v_yeni int := 0; v_atlanan int := 0; r record; v_key text;
BEGIN
  v_anlik := coalesce(p_anlik, (SELECT max(anlik_id) FROM core.kanit_anlik));
  IF v_anlik IS NULL THEN RAISE EXCEPTION 'Kanit anlik goruntusu yok - aday uretilemez'; END IF;

  -- 🔴 YALNIZ ILK 5 ONERI.  CR-016: "29 maddelik bilgi coplugu uretme".
  --    Siralama mart.karar_oncelik'ten gelir (deterministik puan).
  FOR r IN
    SELECT o.*, a.kanit_sinifi AS anlik_kalitesi, b.bulgu_id AS kaynak_bulgu
      FROM mart.karar_oncelik o
      JOIN core.buyume_bulgu b ON b.bulgu_id = o.bulgu_id
      JOIN core.kanit_anlik a  ON a.anlik_id = b.anlik_id
     WHERE b.anlik_id = v_anlik
     ORDER BY o.puan DESC, o.bulgu_id
     LIMIT 5
  LOOP
    -- 🔴 ICERIK tabanli anahtar: anlik_id YOK. Ayni oneri her hafta
    --    yeniden acilmaz; kapanmissa yeniden onerilebilir (kismi unique).
    v_key := md5(r.modul || '|' || r.baslik);
    BEGIN
      INSERT INTO core.karar (karar_tipi, urun, kanal, oneri, anlik_id, kanit_kalitesi,
                              beklenen_etki, risk, yanlislama_kosulu, idempotency_key, fixture)
      VALUES (CASE r.modul WHEN 'URUN' THEN 'PRODUCT_PRIORITY'
                           WHEN 'META' THEN 'MEDIA_BUDGET'
                           ELSE 'CREATIVE_TEST' END,
              CASE WHEN r.modul='URUN' THEN split_part(r.baslik,' — ',1) END,
              CASE WHEN r.modul='META' THEN 'meta' END,
              r.baslik, v_anlik, r.anlik_kalitesi,
              r.beklenen_etki, r.risk, r.yanlislama, v_key, p_fixture);
      v_yeni := v_yeni + 1;
      INSERT INTO core.karar_kanit (karar_id, bulgu_id)
      VALUES (currval('core.karar_karar_id_seq'), r.kaynak_bulgu);
    EXCEPTION WHEN unique_violation THEN
      v_atlanan := v_atlanan + 1;
    END;
  END LOOP;

  INSERT INTO core.karar_red_team (karar_id, sonuc, itiraz_tipi, gerekce, kanit_referansi)
  SELECT k.karar_id, rt.hukum, rt.baslik, rt.gerekce, 'mart.red_team'
    FROM core.karar k CROSS JOIN mart.red_team rt
   WHERE k.durum IN ('PROPOSED','DEFERRED') AND NOT k.fixture
     AND NOT EXISTS (SELECT 1 FROM core.karar_red_team x
                      WHERE x.karar_id=k.karar_id AND x.itiraz_tipi=rt.baslik);

  RETURN QUERY SELECT v_yeni, v_atlanan;
END $$;


ALTER FUNCTION core.karar_adaylari_uret(p_anlik bigint, p_fixture boolean) OWNER TO n8n;

--
-- Name: karar_gecis_kontrol(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.karar_gecis_kontrol() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE cutoff timestamptz;
BEGIN
 IF NEW.durum IS DISTINCT FROM OLD.durum THEN
  SELECT config_value::timestamptz INTO cutoff FROM core.ai_orchestrator_config WHERE config_key='orchestrator_enabled_after';
  IF OLD.durum='PROPOSED' AND NEW.durum IN('APPROVED','REJECTED','DEFERRED') AND NEW.olusturma>=cutoff THEN
   IF NOT EXISTS(SELECT 1 FROM core.ai_red_team_job j JOIN core.karar_red_team r ON r.karar_id=j.karar_id WHERE j.karar_id=NEW.karar_id AND j.state='DONE') THEN
    RAISE EXCEPTION 'Karar #%: AI red-team tamamlanmadan durum % olamaz',NEW.karar_id,NEW.durum;
   END IF;
  END IF;
  IF NEW.durum IN('APPROVED','REJECTED','DEFERRED') AND NOT EXISTS(SELECT 1 FROM core.karar_insan i WHERE i.karar_id=NEW.karar_id) THEN RAISE EXCEPTION 'Karar #%: insan karari kaydedilmeden durum % olamaz',NEW.karar_id,NEW.durum;END IF;
  IF NEW.durum IN('EXECUTED','MEASURING','CONCLUDED') AND NOT EXISTS(SELECT 1 FROM core.karar_insan i WHERE i.karar_id=NEW.karar_id AND i.karar IN('APPROVE','MODIFY')) THEN RAISE EXCEPTION 'Karar #%: insan ONAYI olmadan durum % olamaz',NEW.karar_id,NEW.durum;END IF;
  IF NEW.durum='EXECUTED' AND NOT EXISTS(SELECT 1 FROM core.karar_aksiyon a WHERE a.karar_id=NEW.karar_id) THEN RAISE EXCEPTION 'Karar #%: aksiyon kaydi olmadan EXECUTED olamaz',NEW.karar_id;END IF;
  IF NEW.durum='CONCLUDED' AND NOT EXISTS(SELECT 1 FROM core.karar_sonuc s WHERE s.karar_id=NEW.karar_id) THEN RAISE EXCEPTION 'Karar #%: sonuc kaydi olmadan CONCLUDED olamaz',NEW.karar_id;END IF;
 END IF;
 NEW.guncelleme:=clock_timestamp();RETURN NEW;
END$$;


ALTER FUNCTION core.karar_gecis_kontrol() OWNER TO n8n;

--
-- Name: karar_sonuclandir(bigint, text, numeric, numeric, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.karar_sonuclandir(p_karar bigint, p_metrik text, p_baz numeric, p_gozlenen numeric, p_kapatan text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE u record; v_durum text; v_kalite text; v_yanlis text; v_goreli numeric;
BEGIN
  SELECT * INTO u FROM core.sonuc_uygun_mu(p_karar);
  v_goreli := CASE WHEN p_baz IS NULL OR p_baz = 0 THEN NULL
                   ELSE round(100.0*(p_gozlenen-p_baz)/p_baz, 1) END;

  IF NOT u.uygun THEN
    -- 🔴 Uygun degilse yon BELIRTILMEZ.
    v_durum := CASE WHEN u.orneklem = 0 THEN 'NOT_MEASURABLE' ELSE 'INCONCLUSIVE' END;
    v_kalite := CASE WHEN u.orneklem = 0 THEN 'NO_DATA' ELSE 'PARTIAL' END;
    v_yanlis := 'unknown';
  ELSE
    v_durum := CASE WHEN p_gozlenen IS NULL OR p_baz IS NULL THEN 'INCONCLUSIVE'
                    WHEN p_gozlenen > p_baz THEN 'POSITIVE'
                    WHEN p_gozlenen < p_baz THEN 'NEGATIVE'
                    ELSE 'INCONCLUSIVE' END;
    v_kalite := 'SUCCESS';
    v_yanlis := CASE WHEN v_durum='NEGATIVE' THEN 'true'
                     WHEN v_durum='POSITIVE' THEN 'false' ELSE 'unknown' END;
  END IF;

  INSERT INTO core.karar_sonuc (karar_id, olcum_baslangic, olcum_bitis, ana_metrik,
         baz_deger, gozlenen_deger, goreli_degisim, veri_kalitesi, orneklem,
         sonuc_durumu, yanlislandi, uygunluk_gerekcesi, kapatan)
  VALUES (p_karar,
          (SELECT min(uygulandi)::date FROM core.karar_aksiyon WHERE karar_id=p_karar),
          clock_timestamp()::date, p_metrik, p_baz, p_gozlenen, v_goreli,
          v_kalite, u.orneklem, v_durum, v_yanlis, u.gerekce, p_kapatan)
  ON CONFLICT (karar_id) DO UPDATE SET
    gozlenen_deger=EXCLUDED.gozlenen_deger, goreli_degisim=EXCLUDED.goreli_degisim,
    veri_kalitesi=EXCLUDED.veri_kalitesi, orneklem=EXCLUDED.orneklem,
    sonuc_durumu=EXCLUDED.sonuc_durumu, yanlislandi=EXCLUDED.yanlislandi,
    uygunluk_gerekcesi=EXCLUDED.uygunluk_gerekcesi, kapanis=clock_timestamp();

  UPDATE core.karar SET durum='CONCLUDED' WHERE karar_id=p_karar;
  RETURN v_durum;
END $$;


ALTER FUNCTION core.karar_sonuclandir(p_karar bigint, p_metrik text, p_baz numeric, p_gozlenen numeric, p_kapatan text) OWNER TO n8n;

--
-- Name: karar_ustunu_al(bigint, bigint, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.karar_ustunu_al(p_eski bigint, p_yeni bigint, p_neden text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF (SELECT durum FROM core.karar WHERE karar_id=p_eski) NOT IN ('PROPOSED','DEFERRED') THEN
    RAISE EXCEPTION 'Karar #% PROPOSED/DEFERRED degil - ustu alinamaz', p_eski;
  END IF;
  UPDATE core.karar
     SET ustunu_alan = p_yeni, gecersizlik_nedeni = p_neden, durum = 'CANCELLED'
   WHERE karar_id = p_eski;
END $$;


ALTER FUNCTION core.karar_ustunu_al(p_eski bigint, p_yeni bigint, p_neden text) OWNER TO n8n;

--
-- Name: kaynak_musteri_ekle(text, text, text, text, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.kaynak_musteri_ekle(p_kaynak text, p_kaynak_kimlik_tipi text, p_source_customer_id text, p_telefon_ham text DEFAULT NULL::text, p_eposta_ham text DEFAULT NULL::text) RETURNS TABLE(customer_id bigint, telefon_sonuc text, eposta_sonuc text)
    LANGUAGE plpgsql
    AS $$
DECLARE
  v_musteri bigint;
  v_tel text := 'UNKNOWN';
  v_eps text := 'UNKNOWN';
BEGIN
  IF p_source_customer_id IS NULL OR btrim(p_source_customer_id) = '' THEN
    RAISE EXCEPTION 'source_customer_id zorunlu (kaynak=%)', p_kaynak;
  END IF;

  -- 1) Kaynak kimliginden musteriyi bul veya olustur (IDEMPOTENT) --------------
  SELECT ci.customer_id INTO v_musteri
    FROM core.customer_identity ci
   WHERE ci.kaynak = p_kaynak
     AND ci.kimlik_tipi = p_kaynak_kimlik_tipi
     AND ci.deger_ham = p_source_customer_id
   LIMIT 1;

  IF v_musteri IS NULL THEN
    INSERT INTO core.customer (identity_status, match_method, match_confidence)
    VALUES ('MATCHED', 'source_id', 100)
    RETURNING core.customer.customer_id INTO v_musteri;

    PERFORM core.kimlik_bagla(v_musteri, p_kaynak, p_kaynak_kimlik_tipi,
                              p_source_customer_id, p_source_customer_id);
  END IF;

  -- 2) E-posta ----------------------------------------------------------------
  IF p_eposta_ham IS NOT NULL AND btrim(p_eposta_ham) <> '' THEN
    v_eps := core.kimlik_bagla(v_musteri, p_kaynak, 'email', p_eposta_ham, p_source_customer_id);
  END IF;

  -- 3) Telefon ----------------------------------------------------------------
  IF p_telefon_ham IS NOT NULL AND btrim(p_telefon_ham) <> '' THEN
    v_tel := core.kimlik_bagla(v_musteri, p_kaynak, 'phone', p_telefon_ham, p_source_customer_id);
  END IF;

  RETURN QUERY SELECT v_musteri, v_tel, v_eps;
END;
$$;


ALTER FUNCTION core.kaynak_musteri_ekle(p_kaynak text, p_kaynak_kimlik_tipi text, p_source_customer_id text, p_telefon_ham text, p_eposta_ham text) OWNER TO n8n;

--
-- Name: kimlik_bagla(bigint, text, text, text, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.kimlik_bagla(p_customer_id bigint, p_kaynak text, p_kimlik_tipi text, p_deger_ham text, p_source_customer_id text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
  v_normal     text;
  v_gecerli    boolean := true;
  v_method     text;
  v_conf       smallint;
  v_digerleri  bigint[];
  v_sonuc      text;
  v_reason     text;
BEGIN
  IF p_deger_ham IS NULL OR btrim(p_deger_ham) = '' THEN
    RETURN 'UNKNOWN';
  END IF;

  CASE p_kimlik_tipi
    WHEN 'phone' THEN v_normal := core.telefon_e164(p_deger_ham);  v_method := 'phone_e164'; v_conf := 80;
    WHEN 'email' THEN v_normal := core.eposta_normal(p_deger_ham); v_method := 'email';      v_conf := 90;
    ELSE              v_normal := btrim(p_deger_ham);              v_method := 'source_id';  v_conf := 100;
  END CASE;

  IF v_normal IS NULL THEN
    -- 🔴 Normalize edilemeyen deger TAHMIN EDILMEZ. Ham hali saklanir,
    --    eslestirmede kullanilmaz.
    v_gecerli := false; v_conf := 0;
    v_sonuc := 'INVALID';
    v_reason := 'normalize edilemedi - eslestirmede kullanilmadi';
  ELSE
    -- Bu normalize deger BASKA musterilerde de var mi?
    SELECT array_agg(DISTINCT ci.customer_id)
      INTO v_digerleri
      FROM core.customer_identity ci
     WHERE ci.kimlik_tipi = p_kimlik_tipi
       AND ci.deger_normal = v_normal
       AND ci.gecerli
       AND ci.customer_id <> p_customer_id;

    IF v_digerleri IS NULL OR array_length(v_digerleri,1) IS NULL THEN
      v_sonuc := 'MATCHED';
      v_reason := format('%s ile tek musteriye bagli', v_method);
    ELSE
      -- 🔴 CAKISMA. Otomatik birlestirme YOK - iki ayri kisi olabilir ve
      --    birlestirme GERI ALINAMAZ. Insan karari beklenir.
      v_sonuc := 'CONFLICT';
      v_reason := format('%s degeri ayrica su musterilerde: %s', v_method, v_digerleri::text);
    END IF;
  END IF;

  -- Kimlik satiri (IDEMPOTENT) -------------------------------------------------
  INSERT INTO core.customer_identity (
    customer_id, kaynak, kimlik_tipi, source_customer_id,
    deger_ham, deger_normal, gecerli, match_method, match_confidence, match_reason
  ) VALUES (
    p_customer_id, p_kaynak, p_kimlik_tipi, p_source_customer_id,
    p_deger_ham, v_normal, v_gecerli, v_method, v_conf, v_reason
  )
  ON CONFLICT (kaynak, kimlik_tipi, deger_ham, COALESCE(source_customer_id,''))
  DO UPDATE SET
       deger_normal = EXCLUDED.deger_normal,
       gecerli      = EXCLUDED.gecerli,
       match_reason = EXCLUDED.match_reason,
       updated_at   = now();

  -- Cakismayi kaydet -----------------------------------------------------------
  IF v_sonuc = 'CONFLICT' THEN
    INSERT INTO core.identity_conflict (kimlik_tipi, deger_normal, customer_ids, kaynak_kayitlar)
    VALUES (
      p_kimlik_tipi, v_normal,
      (SELECT array_agg(DISTINCT x) FROM unnest(v_digerleri || p_customer_id) x),
      jsonb_build_array(jsonb_build_object(
        'kaynak', p_kaynak, 'source_customer_id', p_source_customer_id,
        'customer_id', p_customer_id))
    )
    ON CONFLICT (kimlik_tipi, deger_normal) WHERE durum = 'ACIK'
    DO UPDATE SET
      -- 🔴 Tekrar islemede cakisma KAYBOLMAZ; customer listesi genisler,
      --    ayni kaynak kaydi IKI KEZ eklenmez (idempotent).
      customer_ids    = (SELECT array_agg(DISTINCT x)
                           FROM unnest(core.identity_conflict.customer_ids || EXCLUDED.customer_ids) x),
      kaynak_kayitlar = CASE
                          WHEN core.identity_conflict.kaynak_kayitlar @> EXCLUDED.kaynak_kayitlar
                            THEN core.identity_conflict.kaynak_kayitlar
                          ELSE core.identity_conflict.kaynak_kayitlar || EXCLUDED.kaynak_kayitlar
                        END;

    -- Cakismaya taraf olan TUM musteriler isaretlenir.
    UPDATE core.customer c
       SET identity_status = 'CONFLICT', updated_at = now()
     WHERE c.customer_id = ANY(v_digerleri || p_customer_id)
       AND c.identity_status <> 'CONFLICT';
  END IF;

  -- Gosterim alanlarini tazele (TURETILMIS - otorite degil) ---------------------
  UPDATE core.customer c
     SET phone_normalized = (SELECT ci.deger_normal FROM core.customer_identity ci
                              WHERE ci.customer_id = c.customer_id
                                AND ci.kimlik_tipi='phone' AND ci.gecerli
                              ORDER BY ci.match_confidence DESC, ci.identity_id LIMIT 1),
         email_normalized = (SELECT ci.deger_normal FROM core.customer_identity ci
                              WHERE ci.customer_id = c.customer_id
                                AND ci.kimlik_tipi='email' AND ci.gecerli
                              ORDER BY ci.match_confidence DESC, ci.identity_id LIMIT 1),
         identity_status  = CASE
             WHEN c.identity_status = 'CONFLICT' THEN 'CONFLICT'   -- cakisma EZILMEZ
             WHEN v_sonuc = 'MATCHED' THEN 'MATCHED'
             WHEN v_sonuc = 'INVALID' AND c.identity_status IN ('UNKNOWN','INVALID') THEN 'INVALID'
             ELSE c.identity_status END,
         match_method     = COALESCE(c.match_method, v_method),
         match_confidence = GREATEST(COALESCE(c.match_confidence,0), v_conf),
         updated_at       = now()
   WHERE c.customer_id = p_customer_id;

  RETURN v_sonuc;
END;
$$;


ALTER FUNCTION core.kimlik_bagla(p_customer_id bigint, p_kaynak text, p_kimlik_tipi text, p_deger_ham text, p_source_customer_id text) OWNER TO n8n;

--
-- Name: kimlik_doldur(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.kimlik_doldur() RETURNS TABLE(adim text, sonuc text)
    LANGUAGE plpgsql
    AS $$
DECLARE s record; b record;
BEGIN
  SELECT * INTO s FROM core.wix_alicilari_yaz();
  adim := 'wix alicilari';
  -- Sayimlar bu calistirmanin degil, wix kaynakli TUM musterilerin
  -- GUNCEL durumudur - yanlis okunmasin diye acikca yazilir.
  sonuc := format('%s alici islendi | toplam durum: MATCHED=%s CONFLICT=%s INVALID=%s UNKNOWN=%s',
                  s.alici, s.matched, s.conflict, s.invalid, s.unknown);
  RETURN NEXT;

  FOR b IN SELECT * FROM core.birlestirmeleri_uygula() LOOP
    adim := format('birlestirme #%s', b.kid);
    sonuc := format('%s - %s', b.sonuc, b.aciklama);
    RETURN NEXT;
  END LOOP;
END $$;


ALTER FUNCTION core.kimlik_doldur() OWNER TO n8n;

--
-- Name: kreatif_itiraz_kapatma_kontrol(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.kreatif_itiraz_kapatma_kontrol() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.durum = 'KAPANDI' AND (OLD.durum IS DISTINCT FROM 'KAPANDI')
       AND current_user <> 'human_approver' THEN
        RAISE EXCEPTION
            'itirazı yalnız human_approver kapatabilir (deneyen: %)', current_user;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION core.kreatif_itiraz_kapatma_kontrol() OWNER TO n8n;

--
-- Name: lead_mesafe_m(double precision, double precision, double precision, double precision); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.lead_mesafe_m(a_enlem double precision, a_boylam double precision, b_enlem double precision, b_boylam double precision) RETURNS double precision
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$
  SELECT sqrt(
      pow((a_enlem - b_enlem) * 111320.0, 2) +
      pow((a_boylam - b_boylam) * 111320.0 * cos(radians((a_enlem + b_enlem) / 2)), 2)
  );
$$;


ALTER FUNCTION core.lead_mesafe_m(a_enlem double precision, a_boylam double precision, b_enlem double precision, b_boylam double precision) OWNER TO n8n;

--
-- Name: lead_saklama_temizligi(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.lead_saklama_temizligi() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE v_silinen integer;
BEGIN
  -- KVKK: suresi dolan kayit silinir. Ayrica Places kaynakli satirlar
  -- Google sartlari geregi daha kisa omurlu olabilir; suresi saklama_sonu
  -- ile yonetilir, kaynaga gore ayri deger yazilir.
  DELETE FROM core.lead WHERE saklama_sonu < current_date;
  GET DIAGNOSTICS v_silinen = ROW_COUNT;
  RETURN v_silinen;
END;
$$;


ALTER FUNCTION core.lead_saklama_temizligi() OWNER TO n8n;

--
-- Name: lead_zenginlestir(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.lead_zenginlestir(p_il text DEFAULT 'Ankara'::text) RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE v_sayi integer;
BEGIN
  WITH saglik AS (
      SELECT enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL
        AND segment IN ('klinik', 'muayenehane', 'tip merkezi')
  ), rakip AS (
      SELECT lead_id, enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL AND segment = 'eczane'
  ), guzellik AS (
      SELECT enlem, boylam FROM core.lead
      WHERE il = p_il AND enlem IS NOT NULL
        AND segment IN ('guzellik merkezi', 'spa masaj')
  ), hesap AS (
      SELECT l.lead_id,
             (SELECT count(*) FROM saglik s
               WHERE core.lead_mesafe_m(l.enlem, l.boylam, s.enlem, s.boylam) <= 500)   AS s500,
             (SELECT count(*) FROM rakip r
               WHERE r.lead_id <> l.lead_id
                 AND core.lead_mesafe_m(l.enlem, l.boylam, r.enlem, r.boylam) <= 200)   AS r200,
             (SELECT count(*) FROM guzellik g
               WHERE core.lead_mesafe_m(l.enlem, l.boylam, g.enlem, g.boylam) <= 1000)  AS g1k
      FROM core.lead l
      WHERE l.il = p_il AND l.enlem IS NOT NULL
  )
  UPDATE core.lead l
     SET yakin_saglik_500m  = h.s500,
         yakin_rakip_200m   = h.r200,
         yakin_guzellik_1km = h.g1k,
         zenginlestirildi   = now()
    FROM hesap h
   WHERE l.lead_id = h.lead_id;
  GET DIAGNOSTICS v_sayi = ROW_COUNT;
  RETURN v_sayi;
END;
$$;


ALTER FUNCTION core.lead_zenginlestir(p_il text) OWNER TO n8n;

--
-- Name: maliyet_bul(text, timestamp with time zone); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.maliyet_bul(p_urun_id text, p_tarih timestamp with time zone) RETURNS numeric
    LANGUAGE sql STABLE
    AS $$
  SELECT m.maliyet
    FROM core.urun_maliyet m
   WHERE m.urun_id = p_urun_id
     AND m.gecerli_baslangic <= p_tarih
     AND (m.gecerli_bitis IS NULL OR m.gecerli_bitis > p_tarih)
   ORDER BY m.gecerli_baslangic DESC
   LIMIT 1
$$;


ALTER FUNCTION core.maliyet_bul(p_urun_id text, p_tarih timestamp with time zone) OWNER TO n8n;

--
-- Name: maliyet_gecmise_don(text, numeric, timestamp with time zone, text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.maliyet_gecmise_don(p_urun_id text, p_maliyet numeric, p_baslangic timestamp with time zone, p_gerekce text) RETURNS text
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF p_gerekce IS NULL OR btrim(p_gerekce) = '' THEN
    -- Gecmisi degistiren her kayit NEDEN'ini tasimak zorundadir.
    RAISE EXCEPTION 'Gecmise donuk maliyet icin gerekce zorunludur';
  END IF;
  IF p_maliyet <= 0 THEN
    RAISE EXCEPTION 'Maliyet sifir veya negatif olamaz: %', p_maliyet;
  END IF;
  RETURN core.maliyet_guncelle(p_urun_id, p_maliyet, 'ELLE', p_gerekce, p_baslangic);
END $$;


ALTER FUNCTION core.maliyet_gecmise_don(p_urun_id text, p_maliyet numeric, p_baslangic timestamp with time zone, p_gerekce text) OWNER TO n8n;

--
-- Name: maliyet_guncelle(text, numeric, text, text, timestamp with time zone); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.maliyet_guncelle(p_urun_id text, p_maliyet numeric, p_kaynak text DEFAULT 'WIX'::text, p_gerekce text DEFAULT NULL::text, p_an timestamp with time zone DEFAULT clock_timestamp()) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_o_anki numeric; v_id bigint; v_sonraki timestamptz; v_kaynak text;
BEGIN
  IF p_urun_id IS NULL OR btrim(p_urun_id) = '' THEN
    RAISE EXCEPTION 'urun_id bos olamaz';
  END IF;

  -- Sifir/negatif/NULL = "girilmemis". Aktif kayit varsa KAPATILIR
  -- (maliyet silinmis demektir), yeni kayit acilmaz.
  --
  -- 🔴 AMA WIX, ELLE GIRILEN MALIYETI KAPATAMAZ (16.09 denetimi).
  --    raw.wix_urun_yaz her yuklemede maliyet_guncelle(...,'WIX') cagiriyor
  --    ve 36 urunun 35'inde Wix maliyeti BOS. Kaynak filtresi olmasaydi,
  --    core.maliyet_gecmise_don() ile sahip onayiyla ve gerekceli girilen
  --    bir maliyet ertesi sabah 08:30'da sessizce kapanirdi. Insan karari
  --    otomatik yuklemeye yenilmez.
  IF p_maliyet IS NULL OR p_maliyet <= 0 THEN
    UPDATE core.urun_maliyet SET gecerli_bitis = p_an
     WHERE urun_id = p_urun_id AND gecerli_bitis IS NULL
       AND (p_kaynak <> 'WIX' OR kaynak = 'WIX');
    IF FOUND THEN RETURN 'KAPATILDI'; END IF;
    -- 🔴 'YOK' ile 'reddedildi' AYNI SEY DEGIL (ikinci tur denetimi).
    --    Wix bir ELLE kaydini kapatamadiginda eski hali 'YOK' donuyordu;
    --    cagiran "kayit yoktu" ile "korundu"yu ayirt edemiyordu - sessiz
    --    reddedis.
    IF EXISTS (SELECT 1 FROM core.urun_maliyet
                WHERE urun_id = p_urun_id AND gecerli_bitis IS NULL) THEN
      RETURN 'KORUNDU_ELLE';
    END IF;
    RETURN 'YOK';
  END IF;

  -- 🔴 "Degisti mi" sorusu AKTIF kayda degil, p_an ANINDA GECERLI kayda
  --    sorulur. Aksi halde gecmise donuk bir kayit, bugunku degerle ayni
  --    oldugu icin "degismedi" sayilir ve HIC ACILMAZ - oysa o kayit
  --    BASKA BIR ZAMAN ARALIGI icindir. Test bunu da yakaladi.
  SELECT m.maliyet, m.maliyet_id, m.kaynak INTO v_o_anki, v_id, v_kaynak
    FROM core.urun_maliyet m
   WHERE m.urun_id = p_urun_id
     AND m.gecerli_baslangic <= p_an
     AND (m.gecerli_bitis IS NULL OR m.gecerli_bitis > p_an)
   ORDER BY m.gecerli_baslangic DESC LIMIT 1;

  IF v_o_anki IS NOT NULL AND v_o_anki = p_maliyet THEN
    RETURN 'DEGISMEDI';          -- idempotency buradan gelir
  END IF;

  -- 🔴 WIX, ELLE GIRILMIS AKTIF BIR KAYDI EZEMEZ (ikinci tur denetimi).
  --    Onceki hali kaynak filtresini yalniz "sifir/bos" dalina koymustu;
  --    Wix'te DEGER VARSA akis buraya duser ve sahip onayli, gerekceli
  --    girilmis bir ELLE kaydi ertesi sabah 08:30'da sessizce kapanip
  --    yerine WIX kaydi gecerdi. Yorum "insan karari otomatik yuklemeye
  --    yenilmez" diyordu, kod bunu yalniz bos-deger halinde sagliyordu:
  --    kod/yorum celiskisi.
  --
  --    Karar: ELLE kayit insan tarafindan girilmistir ve ancak insan
  --    tarafindan degistirilir. Wix'te farkli bir deger belirmesi, o
  --    degerin dogru oldugu anlamina gelmez - sahip zaten bilerek
  --    baska bir sey yazmistir. Catisma sessizce kazanilmaz, RAPORLANIR.
  IF v_o_anki IS NOT NULL THEN
    IF p_kaynak = 'WIX' AND v_kaynak = 'ELLE' THEN
      RETURN 'KORUNDU_ELLE';   -- cagiran bunu acik is olarak gosterebilir
    END IF;
    UPDATE core.urun_maliyet SET gecerli_bitis = p_an WHERE maliyet_id = v_id;
  END IF;

  -- Yeni kaydin bitisi: p_an'dan SONRAKI ilk kaydin baslangicidir.
  -- Gecmise ekleme yapilirken bu sart; yoksa yeni kayit sonraki donemi de
  -- yutar ve iki kayit ayni ani kapsar.
  SELECT min(m.gecerli_baslangic) INTO v_sonraki
    FROM core.urun_maliyet m
   WHERE m.urun_id = p_urun_id AND m.gecerli_baslangic > p_an;

  INSERT INTO core.urun_maliyet (urun_id, maliyet, gecerli_baslangic, gecerli_bitis, kaynak, gerekce)
  VALUES (p_urun_id, p_maliyet, p_an, v_sonraki, p_kaynak,
          coalesce(p_gerekce, CASE WHEN v_o_anki IS NULL THEN 'ilk kayit'
                                   ELSE format('%s -> %s', v_o_anki, p_maliyet) END))
  -- Ayni ani hedefleyen ikinci yazma: son yazan kazanir, sessizce yutulmaz.
  --
  -- 🔴 gecerli_bitis DE GUNCELLENMELI (16.09 denetiminde bulunan kusur).
  --    Eksik oldugunda su oluyordu: ayni gecerli_baslangic ile ikinci kez
  --    yazildiginda once yukaridaki UPDATE mevcut kaydi gecerli_bitis = p_an
  --    ile KAPATIYOR, sonra bu ON CONFLICT ayni satiri guncelliyor ama
  --    bitisi geri ACMIYORDU -> [t, t) sifir uzunluklu donem.
  --    core.maliyet_bul kosulu (baslangic <= t AND bitis > t) hicbir an icin
  --    saglanamaz; urunun maliyeti SONSUZA DEK "bilinmiyor" olur, marj NULL'a
  --    duser ve hicbir hata uretilmez.
  --    Tetikleyicisi siradan bir duzeltme: "1 Eylul'den 100" deyip ardindan
  --    "hayir 120'ymis" demek yeterdi.
  ON CONFLICT (urun_id, gecerli_baslangic) DO UPDATE SET
    maliyet       = EXCLUDED.maliyet,
    gecerli_bitis = EXCLUDED.gecerli_bitis,
    kaynak        = EXCLUDED.kaynak,
    gerekce       = EXCLUDED.gerekce;

  RETURN CASE WHEN v_o_anki IS NULL THEN 'ILK' ELSE 'YENI_SURUM' END;
END $$;


ALTER FUNCTION core.maliyet_guncelle(p_urun_id text, p_maliyet numeric, p_kaynak text, p_gerekce text, p_an timestamp with time zone) OWNER TO n8n;

--
-- Name: medya_istegi_dokun(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.medya_istegi_dokun() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.guncellendi := now();
    RETURN NEW;
END;
$$;


ALTER FUNCTION core.medya_istegi_dokun() OWNER TO n8n;

--
-- Name: medya_istegi_onay_kapisi(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.medya_istegi_onay_kapisi() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF (NEW.insan_onayi IS DISTINCT FROM OLD.insan_onayi
        OR NEW.onay_notu IS DISTINCT FROM OLD.onay_notu
        OR NEW.onaylayan IS DISTINCT FROM OLD.onaylayan)
       AND current_user <> 'human_approver' THEN
        RAISE EXCEPTION
            'medya cikti onayi yalniz human_approver tarafindan yazilir '
            '(deneyen: %). Otomatik cikti denetimi olculdu ve calismadi; '
            'bu alan insan gozunun kaydidir.', current_user;
    END IF;
    IF NEW.insan_onayi IS DISTINCT FROM OLD.insan_onayi
       AND NEW.insan_onayi IS NOT NULL THEN
        NEW.onaylandi := now();
        NEW.onaylayan := COALESCE(NEW.onaylayan, current_user);
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION core.medya_istegi_onay_kapisi() OWNER TO n8n;

--
-- Name: pii_maskele(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.pii_maskele(p text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$
  SELECT regexp_replace(
           regexp_replace(
             regexp_replace(coalesce(p,''),
               '[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}', '[eposta]', 'g'),
             '@[[:alnum:]._]{3,}', '[kullanici]', 'g'),
           '[0-9][0-9 ()+-]{6,}[0-9]', '[numara]', 'g');
$$;


ALTER FUNCTION core.pii_maskele(p text) OWNER TO n8n;

--
-- Name: sonuc_uygun_mu(bigint); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.sonuc_uygun_mu(p_karar bigint) RETURNS TABLE(uygun boolean, orneklem integer, gerekce text)
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE v_aksiyon timestamptz; v_gun int; v_orneklem int; v_taze boolean; v_eksik int;
BEGIN
  SELECT min(uygulandi) INTO v_aksiyon FROM core.karar_aksiyon WHERE karar_id = p_karar;
  IF v_aksiyon IS NULL THEN
    RETURN QUERY SELECT false, 0, 'aksiyon kaydi yok - olculecek bir degisiklik yok'; RETURN;
  END IF;
  v_gun := greatest(0, (clock_timestamp()::date - v_aksiyon::date));
  SELECT coalesce(sum(siparis),0)::int INTO v_orneklem
    FROM mart.nakit_gunluk WHERE gun > v_aksiyon::date;
  SELECT min(son) > now() - interval '30 hours' INTO v_taze
    FROM (SELECT max(bitis) AS son FROM raw.yukleme_log GROUP BY kaynak) t;
  SELECT count(*) INTO v_eksik FROM mart.nakit_veri_kalitesi WHERE durum='MISSING';

  IF v_gun < 7 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('olcum penceresi cok kisa (%s gun < 7)', v_gun); RETURN;
  END IF;
  IF v_orneklem < 10 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('orneklem yetersiz (%s siparis < 10) - POSITIVE/NEGATIVE uretilmez', v_orneklem); RETURN;
  END IF;
  IF NOT coalesce(v_taze,false) THEN
    RETURN QUERY SELECT false, v_orneklem, 'veri bayat (ETL 30 saatten eski)'; RETURN;
  END IF;
  IF v_eksik > 5 THEN
    RETURN QUERY SELECT false, v_orneklem,
      format('%s kritik kaynak MISSING - kapsama yetersiz', v_eksik); RETURN;
  END IF;
  RETURN QUERY SELECT true, v_orneklem, 'uygun';
END $$;


ALTER FUNCTION core.sonuc_uygun_mu(p_karar bigint) OWNER TO n8n;

--
-- Name: tarayici_isi_al(text, integer); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_al(p_worker text, p_kira_s integer DEFAULT 420) RETURNS TABLE(is_id bigint, hedef text, istem text, girdi_dosyalari jsonb, kira_jetonu uuid, deneme integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_acik boolean;
BEGIN
  SELECT config_value::boolean INTO v_acik
    FROM core.ai_orchestrator_config WHERE config_key = 'tarayici_worker_enabled';
  IF NOT COALESCE(v_acik, false) THEN
    RETURN;   -- kapali: hic is verilmez, hata da yukselmez
  END IF;
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'worker adi zorunlu';
  END IF;
  IF p_kira_s IS NULL OR p_kira_s < 60 OR p_kira_s > 1800 THEN
    RAISE EXCEPTION 'kira suresi 60-1800 sn araliginda olmali';
  END IF;

  RETURN QUERY
  WITH aday AS (
    SELECT t.is_id FROM core.tarayici_isi t
     WHERE (t.durum = 'BEKLIYOR'
            OR (t.durum = 'CALISIYOR' AND t.kira_sonu < clock_timestamp()))
       AND t.deneme < t.en_cok_deneme
     ORDER BY t.is_id
     FOR UPDATE SKIP LOCKED LIMIT 1
  ), alinan AS (
    UPDATE core.tarayici_isi t
       SET durum = 'CALISIYOR',
           kiralayan = btrim(p_worker),
           kira_zamani = clock_timestamp(),
           kira_sonu = clock_timestamp() + make_interval(secs => p_kira_s),
           kira_jetonu = gen_random_uuid(),
           deneme = t.deneme + 1,
           hata = NULL,
           guncellendi = clock_timestamp()
      FROM aday a WHERE t.is_id = a.is_id
    RETURNING t.is_id, t.hedef, t.istem, t.girdi_dosyalari, t.kira_jetonu, t.deneme
  ) SELECT * FROM alinan;
END $$;


ALTER FUNCTION core.tarayici_isi_al(p_worker text, p_kira_s integer) OWNER TO function_owner;

--
-- Name: tarayici_isi_bitir(bigint, uuid, text, jsonb, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_bitir(p_is_id bigint, p_jeton uuid, p_metin text, p_dosyalar jsonb DEFAULT '[]'::jsonb, p_ekran text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
BEGIN
  IF p_dosyalar IS NULL OR jsonb_typeof(p_dosyalar) <> 'array' THEN
    RAISE EXCEPTION 'dosyalar bir JSON dizisi olmali';
  END IF;
  -- Ne metin ne dosya varsa bu bir basari DEGILDIR. "Bos sonucu basarili
  -- sayma" kurali: ici bos bir sonuc, sahibin onuna konacak bir sey degil.
  IF (p_metin IS NULL OR btrim(p_metin) = '') AND jsonb_array_length(p_dosyalar) = 0 THEN
    RAISE EXCEPTION 'sonuc bos: ne metin ne dosya var';
  END IF;

  UPDATE core.tarayici_isi
     SET durum = 'BITTI', sonuc_metin = p_metin, sonuc_dosyalari = p_dosyalar,
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kira_jetonu = NULL, kira_sonu = NULL, guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'is bitirilemedi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
END $$;


ALTER FUNCTION core.tarayici_isi_bitir(p_is_id bigint, p_jeton uuid, p_metin text, p_dosyalar jsonb, p_ekran text) OWNER TO function_owner;

--
-- Name: tarayici_isi_ekle(text, text, text, text, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_ekle(p_isteyen text, p_hedef text, p_istem text, p_idempotency_key text, p_girdi_dosyalari jsonb DEFAULT '[]'::jsonb) RETURNS bigint
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_is_id bigint;
BEGIN
  IF p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
    RAISE EXCEPTION 'idempotency_key zorunlu';
  END IF;
  IF p_girdi_dosyalari IS NULL OR jsonb_typeof(p_girdi_dosyalari) <> 'array' THEN
    RAISE EXCEPTION 'girdi_dosyalari bir JSON dizisi olmali';
  END IF;

  -- Ayni anahtarla ikinci kez cagrilmasi HATA DEGILDIR: var olan isin
  -- kimligi doner. Boylece aglanan bir yanit ya da yeniden denenen bir
  -- cagri ikinci is acmaz.
  SELECT is_id INTO v_is_id FROM core.tarayici_isi
   WHERE idempotency_key = p_idempotency_key;
  IF v_is_id IS NOT NULL THEN
    RETURN v_is_id;
  END IF;

  INSERT INTO core.tarayici_isi (isteyen, hedef, istem, girdi_dosyalari, idempotency_key)
  VALUES (btrim(p_isteyen), p_hedef, p_istem, p_girdi_dosyalari, btrim(p_idempotency_key))
  RETURNING is_id INTO v_is_id;
  RETURN v_is_id;
END $$;


ALTER FUNCTION core.tarayici_isi_ekle(p_isteyen text, p_hedef text, p_istem text, p_idempotency_key text, p_girdi_dosyalari jsonb) OWNER TO function_owner;

--
-- Name: tarayici_isi_getir(bigint); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_getir(p_is_id bigint) RETURNS TABLE(is_id bigint, hedef text, istem text, durum text, girdi_dosyalari jsonb, slug text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
  SELECT t.is_id, t.hedef, t.istem, t.durum, t.girdi_dosyalari, t.slug
    FROM core.tarayici_isi t WHERE t.is_id = p_is_id;
$$;


ALTER FUNCTION core.tarayici_isi_getir(p_is_id bigint) OWNER TO function_owner;

--
-- Name: tarayici_isi_hata(bigint, uuid, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_hata(p_is_id bigint, p_jeton uuid, p_hata text, p_ekran text DEFAULT NULL::text) RETURNS text
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
DECLARE
  v_durum text;
BEGIN
  UPDATE core.tarayici_isi
     SET durum = CASE WHEN deneme >= en_cok_deneme THEN 'HATA' ELSE 'BEKLIYOR' END,
         hata = left(COALESCE(p_hata, 'sebep bildirilmedi'), 1000),
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kiralayan = NULL, kira_jetonu = NULL, kira_sonu = NULL,
         guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR'
  RETURNING durum INTO v_durum;
  IF v_durum IS NULL THEN
    RAISE EXCEPTION 'hata yazilamadi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
  RETURN v_durum;
END $$;


ALTER FUNCTION core.tarayici_isi_hata(p_is_id bigint, p_jeton uuid, p_hata text, p_ekran text) OWNER TO function_owner;

--
-- Name: tarayici_isi_insan(bigint, uuid, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_insan(p_is_id bigint, p_jeton uuid, p_sebep text, p_ekran text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
BEGIN
  UPDATE core.tarayici_isi
     SET durum = 'INSAN_GEREKLI',
         hata = left(COALESCE(p_sebep, 'insan mudahalesi gerekli'), 1000),
         ekran_goruntusu = COALESCE(p_ekran, ekran_goruntusu),
         kira_jetonu = NULL, kira_sonu = NULL, guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND kira_jetonu = p_jeton AND durum = 'CALISIYOR';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'insan durumu yazilamadi: kimlik/jeton/durum uyusmuyor (is_id=%)', p_is_id;
  END IF;
END $$;


ALTER FUNCTION core.tarayici_isi_insan(p_is_id bigint, p_jeton uuid, p_sebep text, p_ekran text) OWNER TO function_owner;

--
-- Name: tarayici_isi_sunuldu(bigint, text, text); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_isi_sunuldu(p_is_id bigint, p_slug text, p_uyum text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $_$
BEGIN
  IF p_slug IS NULL OR p_slug !~ '^[A-Za-z0-9_.-]{1,80}$' THEN
    RAISE EXCEPTION 'slug gecersiz';
  END IF;
  UPDATE core.tarayici_isi
     SET durum = 'SUNULDU', slug = p_slug, uyum_durumu = p_uyum,
         guncellendi = clock_timestamp()
   WHERE is_id = p_is_id AND durum IN ('BITTI','HATA','INSAN_GEREKLI');
  IF NOT FOUND THEN
    RAISE EXCEPTION 'sunuldu yazilamadi: is_id=% uygun durumda degil', p_is_id;
  END IF;
END $_$;


ALTER FUNCTION core.tarayici_isi_sunuldu(p_is_id bigint, p_slug text, p_uyum text) OWNER TO function_owner;

--
-- Name: tarayici_nabiz_oku(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_nabiz_oku() RETURNS TABLE(worker text, son_gorulme timestamp with time zone, yas_s numeric, ayrinti jsonb)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
  SELECT n.worker, n.son_gorulme,
         round(EXTRACT(EPOCH FROM (clock_timestamp() - n.son_gorulme))::numeric, 1),
         n.ayrinti
    FROM core.tarayici_nabiz n ORDER BY n.worker;
$$;


ALTER FUNCTION core.tarayici_nabiz_oku() OWNER TO function_owner;

--
-- Name: tarayici_nabiz_yaz(text, jsonb); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_nabiz_yaz(p_worker text, p_ayrinti jsonb DEFAULT '{}'::jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
BEGIN
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'worker adi zorunlu';
  END IF;
  IF p_ayrinti IS NULL OR jsonb_typeof(p_ayrinti) <> 'object' THEN
    RAISE EXCEPTION 'ayrinti bir JSON nesnesi olmali';
  END IF;
  INSERT INTO core.tarayici_nabiz (worker, son_gorulme, ayrinti)
  VALUES (btrim(p_worker), clock_timestamp(), p_ayrinti)
  ON CONFLICT (worker) DO UPDATE
    SET son_gorulme = clock_timestamp(), ayrinti = EXCLUDED.ayrinti;
END $$;


ALTER FUNCTION core.tarayici_nabiz_yaz(p_worker text, p_ayrinti jsonb) OWNER TO function_owner;

--
-- Name: tarayici_sayim(); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_sayim() RETURNS TABLE(durum text, adet bigint)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
  SELECT d.durum, COUNT(t.is_id)
    FROM (VALUES ('BEKLIYOR'),('CALISIYOR'),('BITTI'),('SUNULDU'),
                 ('HATA'),('INSAN_GEREKLI')) AS d(durum)
    LEFT JOIN core.tarayici_isi t ON t.durum = d.durum
   GROUP BY d.durum ORDER BY d.durum;
$$;


ALTER FUNCTION core.tarayici_sayim() OWNER TO function_owner;

--
-- Name: tarayici_sunulacak(integer); Type: FUNCTION; Schema: core; Owner: function_owner
--

CREATE FUNCTION core.tarayici_sunulacak(p_limit integer DEFAULT 20) RETURNS TABLE(is_id bigint, hedef text, istem text, durum text, isteyen text, sonuc_metin text, sonuc_dosyalari jsonb, ekran_goruntusu text, hata text, olusturuldu timestamp with time zone, deneme integer)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'core', 'pg_temp'
    AS $$
  SELECT t.is_id, t.hedef, t.istem, t.durum, t.isteyen, t.sonuc_metin,
         t.sonuc_dosyalari, t.ekran_goruntusu, t.hata, t.olusturuldu, t.deneme
    FROM core.tarayici_isi t
   WHERE t.durum IN ('BITTI','HATA','INSAN_GEREKLI')
   ORDER BY t.is_id
   LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 20), 100));
$$;


ALTER FUNCTION core.tarayici_sunulacak(p_limit integer) OWNER TO function_owner;

--
-- Name: tasarim_isi_onay_kontrol(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.tasarim_isi_onay_kontrol() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.onay IS DISTINCT FROM OLD.onay
       AND NEW.onay IS NOT NULL
       AND current_user <> 'human_approver' THEN
        RAISE EXCEPTION
            'tasarım onayını yalnız human_approver yazabilir (deneyen: %)',
            current_user;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION core.tasarim_isi_onay_kontrol() OWNER TO n8n;

--
-- Name: telefon_e164(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.telefon_e164(p_ham text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
  d text;
  ulusal text;
BEGIN
  IF p_ham IS NULL THEN RETURN NULL; END IF;
  d := regexp_replace(p_ham, '\D', '', 'g');
  IF d = '' THEN RETURN NULL; END IF;

  IF length(d) = 12 AND left(d,2) = '90' THEN
    ulusal := right(d,10);
  ELSIF length(d) = 11 AND left(d,1) = '0' THEN
    ulusal := right(d,10);
  ELSIF length(d) = 10 THEN
    ulusal := d;
  ELSIF length(d) = 13 AND left(d,3) = '090' THEN
    ulusal := right(d,10);
  ELSE
    -- 9 haneli, 14+ haneli, yurt disi vb. -> normalize EDILMEZ
    RETURN NULL;
  END IF;

  -- Ulusal numara 2-5 ile baslamali; 0/1/6/7/8/9 ile baslayan gecersizdir.
  IF left(ulusal,1) NOT IN ('2','3','4','5') THEN
    RETURN NULL;
  END IF;

  RETURN '+90' || ulusal;
END;
$$;


ALTER FUNCTION core.telefon_e164(p_ham text) OWNER TO n8n;

--
-- Name: tr_anahtar(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.tr_anahtar(m text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT nullif(btrim(regexp_replace(
           lower(translate(coalesce(m, ''),
                 'ÇĞİIÖŞÜÂÎÛçğıiöşüâîû',
                 'cgiiosuaiucgiiosuaiu')),
           '[^a-z0-9]+', ' ', 'g')), '');
$$;


ALTER FUNCTION core.tr_anahtar(m text) OWNER TO n8n;

--
-- Name: tr_norm(text); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.tr_norm(p text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$
  SELECT lower(translate(coalesce(p,''),
                         'İIıÇçĞğÖöŞşÜüÂâÎîÛû',
                         'iiiccggoossuuaaiiuu'));
$$;


ALTER FUNCTION core.tr_norm(p text) OWNER TO n8n;

--
-- Name: wix_alicilari_yaz(); Type: FUNCTION; Schema: core; Owner: n8n
--

CREATE FUNCTION core.wix_alicilari_yaz() RETURNS TABLE(alici integer, matched integer, conflict integer, invalid integer, unknown integer)
    LANGUAGE plpgsql
    AS $$
DECLARE r record; v_alici int := 0;
BEGIN
  FOR r IN
    SELECT DISTINCT ON (w.buyer_id)
           w.buyer_id,
           w.ham#>>'{buyerInfo,phone}' AS tel,
           w.ham#>>'{buyerInfo,email}' AS eps
      FROM raw.wix_order w
     WHERE w.buyer_id IS NOT NULL
     ORDER BY w.buyer_id, w.olusturma DESC NULLS LAST
  LOOP
    PERFORM core.kaynak_musteri_ekle('wix','wix_buyer_id', r.buyer_id, r.tel, r.eps);
    v_alici := v_alici + 1;
  END LOOP;

  RETURN QUERY
  SELECT v_alici,
         count(*) FILTER (WHERE c.identity_status='MATCHED')::int,
         count(*) FILTER (WHERE c.identity_status='CONFLICT')::int,
         count(*) FILTER (WHERE c.identity_status='INVALID')::int,
         count(*) FILTER (WHERE c.identity_status='UNKNOWN')::int
    FROM core.customer c
   WHERE EXISTS (SELECT 1 FROM core.customer_identity ci
                  WHERE ci.customer_id=c.customer_id AND ci.kaynak='wix');
END $$;


ALTER FUNCTION core.wix_alicilari_yaz() OWNER TO n8n;

--
-- Name: konusma_tazele(); Type: FUNCTION; Schema: lcarlie; Owner: n8n
--

CREATE FUNCTION lcarlie.konusma_tazele() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  UPDATE lcarlie.konusma k SET
    mesaj_sayisi = (SELECT count(*) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    ilk_mesaj    = (SELECT min(zaman) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    son_mesaj    = (SELECT max(zaman) FROM lcarlie.mesaj m WHERE m.konusma_id = k.id),
    guncelleme   = now()
  WHERE k.id = COALESCE(NEW.konusma_id, OLD.konusma_id);
  RETURN NULL;
END; $$;


ALTER FUNCTION lcarlie.konusma_tazele() OWNER TO n8n;

--
-- Name: norm(text); Type: FUNCTION; Schema: lcarlie; Owner: n8n
--

CREATE FUNCTION lcarlie.norm(t text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT btrim(regexp_replace(lower(coalesce(t,'')), '[^a-zçğıöşü0-9 ]+', ' ', 'g'));
$$;


ALTER FUNCTION lcarlie.norm(t text) OWNER TO n8n;

--
-- Name: dizi_uzunluk(jsonb); Type: FUNCTION; Schema: mart; Owner: n8n
--

CREATE FUNCTION mart.dizi_uzunluk(j jsonb) RETURNS integer
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT CASE WHEN jsonb_typeof(j) = 'array'
              THEN jsonb_array_length(j) ELSE 0 END;
$$;


ALTER FUNCTION mart.dizi_uzunluk(j jsonb) OWNER TO n8n;

--
-- Name: ekonomi_ozet(integer); Type: FUNCTION; Schema: mart; Owner: n8n
--

CREATE FUNCTION mart.ekonomi_ozet(p_gun integer) RETURNS TABLE(gun_sayisi integer, baslangic date, bitis date, siparis bigint, gerceklesmis bigint, ekonomi_tam bigint, ekonomi_kismi bigint, ekonomi_eksik bigint, net_ciro numeric, bilinen_bilesen_katkisi numeric, katki_ust_siniri numeric, dogrulanmis_katki numeric, reklam_harcamasi numeric, reklam_sonrasi_katki numeric, reklam_sonrasi_ust_sinir numeric, ekonomi_tamlik_yuzde numeric, eksik_bilesenler text, ekonomi_durumu text)
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE v_bas date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date - p_gun;
        v_bit date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
BEGIN
  RETURN QUERY
  WITH p AS (SELECT * FROM mart.ekonomi_gunluk n WHERE n.gun > v_bas AND n.gun <= v_bit),
  t AS (
    SELECT sum(p.siparis) s, sum(p.gerceklesmis_siparis) g,
           sum(p.ekonomi_tam) tam, sum(p.ekonomi_kismi) kis, sum(p.ekonomi_eksik) eks,
           sum(p.net_ciro) nc, sum(p.bilinen_bilesen_katkisi) bk,
           sum(p.katki_ust_siniri) us, sum(p.dogrulanmis_katki) dk,
           sum(p.reklam_harcamasi) rh
      FROM p
  ), e AS (
    SELECT string_agg(DISTINCT x, ', ') AS liste
      FROM mart.siparis_ekonomi se, unnest(se.eksik_bilesenler) AS x
     WHERE (se.olusturma AT TIME ZONE 'Europe/Istanbul')::date > v_bas
       AND (se.olusturma AT TIME ZONE 'Europe/Istanbul')::date <= v_bit
  )
  SELECT p_gun, v_bas + 1, v_bit,
         coalesce(t.s,0)::bigint, coalesce(t.g,0)::bigint,
         coalesce(t.tam,0)::bigint, coalesce(t.kis,0)::bigint, coalesce(t.eks,0)::bigint,
         round(coalesce(t.nc,0),2), round(coalesce(t.bk,0),2), round(coalesce(t.us,0),2),
         round(coalesce(t.dk,0),2), round(coalesce(t.rh,0),2),
         round(coalesce(t.bk,0) - coalesce(t.rh,0),2),
         round(coalesce(t.us,0) - coalesce(t.rh,0),2),
         CASE WHEN coalesce(t.s,0)=0 THEN NULL ELSE round(100.0*t.tam/t.s,1) END,
         coalesce(e.liste,'(yok)'),
         CASE
           WHEN coalesce(t.s,0)=0 AND coalesce(t.rh,0)=0 THEN 'VERI_YOK'
           WHEN coalesce(t.tam,0)=0                      THEN 'EKONOMI_OLCULEMEDI'
           WHEN t.tam < t.s                              THEN 'EKONOMI_KISMI'
           ELSE 'EKONOMI_TAM'
         END
    FROM t, e;
END $$;


ALTER FUNCTION mart.ekonomi_ozet(p_gun integer) OWNER TO n8n;

--
-- Name: kesim(); Type: FUNCTION; Schema: mart; Owner: n8n
--

CREATE FUNCTION mart.kesim() RETURNS timestamp with time zone
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE v timestamptz;
BEGIN
  SELECT deger::timestamptz INTO v FROM core.ayar WHERE anahtar='olcum_baslangici';
  IF v IS NULL THEN
    RAISE EXCEPTION 'core.ayar icinde olcum_baslangici yok veya bos - olcum penceresi belirlenemez';
  END IF;
  RETURN v;
END $$;


ALTER FUNCTION mart.kesim() OWNER TO n8n;

--
-- Name: nakit_ozet(integer); Type: FUNCTION; Schema: mart; Owner: n8n
--

CREATE FUNCTION mart.nakit_ozet(p_gun integer) RETURNS TABLE(gun_sayisi integer, baslangic date, bitis date, siparis bigint, brut_ciro numeric, net_ciro numeric, tahsil_beyan numeric, tahsil_edilmemis numeric, wixdisi_tahsil numeric, wixdisi_bekleyen numeric, bilinen_cogs numeric, cogs_olculmus_yuzde numeric, satis_kargosu numeric, numune_kargosu numeric, bilinmeyen_kargo numeric, meta_harcama numeric, meta_kapsama text, reklam_oncesi numeric, reklam_sonrasi numeric, katki_yuzde numeric, siparis_basina_harcama numeric, ciro_harcama_orani numeric, harcamali_satissiz_gun bigint, nakit_durum text)
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE v_bas date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date - p_gun;
        v_bit date := (clock_timestamp() AT TIME ZONE 'Europe/Istanbul')::date;
BEGIN
  RETURN QUERY
  WITH p AS (
    SELECT * FROM mart.nakit_gunluk n WHERE n.gun > v_bas AND n.gun <= v_bit
  ), t AS (
    SELECT sum(p.siparis)                 AS siparis,
           sum(p.brut_ciro)               AS brut_ciro,
           sum(p.net_ciro)                AS net_ciro,
           sum(p.tahsil_beyan_edilen)     AS tahsil_beyan,
           sum(p.tahsil_edilmemis)        AS tahsil_edilmemis,
           sum(p.wixdisi_tahsil_net)      AS wixdisi_tahsil,
           sum(p.wixdisi_bekleyen_net)    AS wixdisi_bekleyen,
           sum(p.bilinen_cogs)            AS cogs,
           sum(p.satis_kargosu)           AS satis_kargosu,
           sum(p.numune_kargosu)          AS numune_kargosu,
           sum(p.bilinmeyen_kargo)        AS bilinmeyen_kargo,
           sum(p.meta_harcama_gozlenen)   AS harcama,
           count(*) FILTER (WHERE p.meta_harcama_gozlenen > 0 AND p.siparis = 0) AS harcamali_satissiz
      FROM p
  )
  -- 🔴 sum(bigint) NUMERIC doner, bigint DEGIL. Acik cast olmadan
  --    "structure of query does not match function result type" hatasi verir.
  SELECT p_gun, v_bas + 1, v_bit,
         coalesce(t.siparis,0)::bigint, round(coalesce(t.brut_ciro,0),2), round(coalesce(t.net_ciro,0),2),
         round(coalesce(t.tahsil_beyan,0),2), round(coalesce(t.tahsil_edilmemis,0),2),
         round(coalesce(t.wixdisi_tahsil,0),2), round(coalesce(t.wixdisi_bekleyen,0),2),
         round(coalesce(t.cogs,0),2),
         -- 🔴 Pencere genelinde olculmus maliyet orani (ciro agirlikli)
         (SELECT round(100.0 * coalesce(sum(k.satir_ciro_net) FILTER (WHERE mk.kalite='OLCULMUS'),0)
                       / nullif(sum(k.satir_ciro_net),0), 1)
            FROM mart.siparis_kalem k
            JOIN raw.wix_order w ON w.siparis_id = k.siparis_id
            LEFT JOIN mart.maliyet_kalite mk ON mk.urun_id = k.urun_id
           WHERE (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date > v_bas
             AND (w.olusturma AT TIME ZONE 'Europe/Istanbul')::date <= v_bit
             AND k.ciro_sinifi <> 'IPTAL'),
         round(coalesce(t.satis_kargosu,0),2), round(coalesce(t.numune_kargosu,0),2),
         round(coalesce(t.bilinmeyen_kargo,0),2),
         round(coalesce(t.harcama,0),2),
         (SELECT aktif_kapsama FROM mart.meta_kapsama),
         round(coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0),2),
         round(coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0)-coalesce(t.harcama,0),2),
         round(100.0 * (coalesce(t.net_ciro,0)-coalesce(t.cogs,0)-coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
               -coalesce(t.bilinmeyen_kargo,0))
               / nullif(t.net_ciro,0), 1),
         round(coalesce(t.harcama,0) / nullif(t.siparis,0), 2),
         round(coalesce(t.net_ciro,0) / nullif(t.harcama,0), 2),
         t.harcamali_satissiz::bigint,
         CASE
           WHEN coalesce(t.harcama,0) = 0 AND coalesce(t.siparis,0) = 0 THEN 'INSUFFICIENT_DATA'
           WHEN coalesce(t.harcama,0) > coalesce(t.net_ciro,0)          THEN 'CRITICAL'
           WHEN coalesce(t.harcama,0) >= coalesce(t.net_ciro,0)-coalesce(t.cogs,0)
                                        -coalesce(t.satis_kargosu,0)-coalesce(t.numune_kargosu,0)
                                        -coalesce(t.bilinmeyen_kargo,0) THEN 'WATCH'
           ELSE 'WATCH'   -- 🔴 maliyet kalitesi olculmedigi surece HEALTHY uretilmez
         END
    FROM t;
END $$;


ALTER FUNCTION mart.nakit_ozet(p_gun integer) OWNER TO n8n;

--
-- Name: increment_workflow_version(); Type: FUNCTION; Schema: public; Owner: n8n
--

CREATE FUNCTION public.increment_workflow_version() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
			BEGIN
				IF NEW."versionCounter" IS NOT DISTINCT FROM OLD."versionCounter"
					AND (NEW."nodes"::text IS DISTINCT FROM OLD."nodes"::text
						OR NEW."settings"::text IS DISTINCT FROM OLD."settings"::text) THEN
					NEW."versionCounter" = OLD."versionCounter" + 1;
				END IF;
				RETURN NEW;
			END;
			$$;


ALTER FUNCTION public.increment_workflow_version() OWNER TO n8n;

--
-- Name: bk_pii_temizle(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.bk_pii_temizle(j jsonb) RETURNS jsonb
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT jsonb_set(
           jsonb_set(j, '{recipient}',
             jsonb_strip_nulls(jsonb_build_object(
               'city', j#>'{recipient,city}',
               'town', j#>'{recipient,town}',
               'pii_temizlendi', to_jsonb(true)))),
           '{sender}',
           jsonb_strip_nulls(jsonb_build_object('name', j#>'{sender,name}')))
$$;


ALTER FUNCTION raw.bk_pii_temizle(j jsonb) OWNER TO n8n;

--
-- Name: bk_shipment_yaz(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.bk_shipment_yaz(j_ham jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_id text; v_yeni boolean; j jsonb;
BEGIN
  v_id := raw.bos_null(j_ham->>'id');
  IF v_id IS NULL THEN
    -- 🔴 HATA MESAJINA HAM GOVDE YAZILMAZ (16.09 denetimi).
    --    Onceki hali left(j_ham::text,200) yaziyordu - yani PII TEMIZLENMEDEN
    --    ONCEKI hali. Bu metin psql stderr'ine, oradan ETL ciktisina, oradan
    --    raw.yukleme_log.mesaj'a dusuyordu. Yani "ham jsonb'de bile tutulmaz"
    --    denen alici adi/telefonu/adresi, LOG TABLOSUNA sizabiliyordu.
    --    Teshis icin PII olmayan alanlar yeterli.
    RAISE EXCEPTION 'BasitKargo gonderisinde id yok (barkod=%, tarih=%)',
      coalesce(j_ham->>'barcode','?'), coalesce(j_ham->>'createdTime','?');
  END IF;
  j := raw.bk_pii_temizle(j_ham);   -- 🔴 ham kolona da temizlenmis hali girer

  INSERT INTO raw.bk_shipment AS b (
    gonderi_id, barkod, foreign_code, icerik_kodu, ek_bilgi, yon, gonderi_no,
    durum, tasiyici, olusturma, guncelleme, kargoya_verilis, teslim, son_hareket,
    desi, kargo_ucreti, toplam_maliyet, cod_var, cod_tutar, cod_durum,
    siparis_tutari, urun_adlari, sehir, ilce, ham, cekim_at)
  VALUES (
    v_id,
    raw.bos_null(j->>'barcode'),
    raw.bos_null(j->>'foreignCode'),
    raw.bos_null(j#>>'{content,code}'),
    raw.bos_null(j#>>'{content,name}'),
    raw.bos_null(j->>'type'),
    raw.bos_null(j->>'orderNumber'),
    raw.bos_null(j->>'status'),
    raw.bos_null(j#>>'{shipmentInfo,handler,name}'),
    raw.bk_zaman(j->>'createdTime'),
    raw.bk_zaman(j->>'updatedTime'),
    raw.bk_zaman(j#>>'{shipmentInfo,shippedTime}'),
    raw.bk_zaman(j#>>'{shipmentInfo,deliveredTime}'),
    raw.bos_null(j#>>'{shipmentInfo,lastState}'),
    coalesce(raw.sayi(j#>>'{shipmentInfo,handlerDesi}'), raw.sayi(j#>>'{content,totalDesiKg}')),
    raw.sayi(j#>>'{priceInfo,shipmentFee}'),
    raw.sayi(j#>>'{priceInfo,totalCost}'),
    coalesce((j#>>'{codInfo,collectOnDelivery}')::boolean, false),
    raw.sayi(j#>>'{codInfo,amount}'),
    raw.bos_null(j#>>'{codInfo,collectionStatus}'),
    raw.sayi(j->>'orderTotal'),
    (SELECT array_agg(raw.bos_null(it->>'name') ORDER BY ord)
       FROM jsonb_array_elements(coalesce(j#>'{content,items}','[]'::jsonb))
            WITH ORDINALITY AS t(it, ord)
      WHERE raw.bos_null(it->>'name') IS NOT NULL),
    raw.bos_null(j#>>'{recipient,city}'),
    raw.bos_null(j#>>'{recipient,town}'),
    j, now())
  ON CONFLICT (gonderi_id) DO UPDATE SET
    barkod          = EXCLUDED.barkod,
    foreign_code    = EXCLUDED.foreign_code,
    icerik_kodu     = EXCLUDED.icerik_kodu,
    ek_bilgi        = EXCLUDED.ek_bilgi,
    yon             = EXCLUDED.yon,
    gonderi_no      = EXCLUDED.gonderi_no,
    durum           = EXCLUDED.durum,
    tasiyici        = EXCLUDED.tasiyici,
    olusturma       = EXCLUDED.olusturma,
    guncelleme      = EXCLUDED.guncelleme,
    kargoya_verilis = EXCLUDED.kargoya_verilis,
    teslim          = EXCLUDED.teslim,
    son_hareket     = EXCLUDED.son_hareket,
    desi            = EXCLUDED.desi,
    kargo_ucreti    = EXCLUDED.kargo_ucreti,
    toplam_maliyet  = EXCLUDED.toplam_maliyet,
    cod_var         = EXCLUDED.cod_var,
    cod_tutar       = EXCLUDED.cod_tutar,
    cod_durum       = EXCLUDED.cod_durum,
    siparis_tutari  = EXCLUDED.siparis_tutari,
    urun_adlari     = EXCLUDED.urun_adlari,
    sehir           = EXCLUDED.sehir,
    ilce            = EXCLUDED.ilce,
    ham             = EXCLUDED.ham,
    cekim_at        = EXCLUDED.cekim_at
  RETURNING (b.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;


ALTER FUNCTION raw.bk_shipment_yaz(j_ham jsonb) OWNER TO n8n;

--
-- Name: bk_zaman(text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.bk_zaman(t text) RETURNS timestamp with time zone
    LANGUAGE plpgsql STABLE
    AS $_$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  IF t ~ '(Z|[+-]\d{2}:?\d{2})$' THEN RETURN t::timestamptz; END IF;
  RETURN (t || '+03')::timestamptz;
EXCEPTION WHEN others THEN
  RETURN NULL;
END $_$;


ALTER FUNCTION raw.bk_zaman(t text) OWNER TO n8n;

--
-- Name: bos_null(text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.bos_null(t text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT nullif(btrim(coalesce(t,'')),'') $$;


ALTER FUNCTION raw.bos_null(t text) OWNER TO n8n;

--
-- Name: meta_cta(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_cta(c jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT nullif(coalesce(
    c->>'call_to_action_type',
    c->'object_story_spec'->'video_data'->'call_to_action'->>'type',
    c->'object_story_spec'->'link_data'->'call_to_action'->>'type',
    c->'asset_feed_spec'->'call_to_action_types'->>0
  ), '');
$$;


ALTER FUNCTION raw.meta_cta(c jsonb) OWNER TO n8n;

--
-- Name: meta_harcama_yaz(jsonb, text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_harcama_yaz(j jsonb, p_hesap text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_gun date; v_kmp text; v_yeni boolean;
BEGIN
  v_gun := raw.bos_null(j->>'date_start')::date;
  IF v_gun IS NULL THEN
    RAISE EXCEPTION 'Meta satirinda date_start yok: %', left(j::text,200);
  END IF;
  -- Kampanya kirilimi istenmediginde Meta campaign_id dondurmez ->
  -- hesap toplami oldugu ACIKCA isaretlenir, bos string birakilmaz.
  v_kmp := coalesce(raw.bos_null(j->>'campaign_id'), '_HESAP');

  INSERT INTO raw.meta_harcama AS m (
    gun, hesap_id, kampanya_id, kaynak, kampanya_adi, harcama, para_birimi,
    gosterim, erisim, tiklama, link_tiklama, cpm, cpc, ctr, sikligi,
    meta_donusum, meta_donusum_degeri, ham, cekim_at)
  VALUES (
    v_gun, p_hesap, v_kmp, 'META_API',
    raw.bos_null(j->>'campaign_name'),
    raw.sayi(j->>'spend'),
    raw.bos_null(j->>'account_currency'),
    raw.sayi(j->>'impressions')::bigint,
    raw.sayi(j->>'reach')::bigint,
    raw.sayi(j->>'clicks')::bigint,
    raw.sayi(j->>'inline_link_clicks')::bigint,
    raw.sayi(j->>'cpm'), raw.sayi(j->>'cpc'),
    raw.sayi(j->>'ctr'), raw.sayi(j->>'frequency'),
    -- actions / action_values dizileri: satin alma satirini bul
    (SELECT raw.sayi(a->>'value') FROM jsonb_array_elements(coalesce(j->'actions','[]'::jsonb)) a
      WHERE a->>'action_type' IN ('purchase','omni_purchase','offsite_conversion.fb_pixel_purchase')
      ORDER BY raw.sayi(a->>'value') DESC NULLS LAST LIMIT 1),
    (SELECT raw.sayi(a->>'value') FROM jsonb_array_elements(coalesce(j->'action_values','[]'::jsonb)) a
      WHERE a->>'action_type' IN ('purchase','omni_purchase','offsite_conversion.fb_pixel_purchase')
      ORDER BY raw.sayi(a->>'value') DESC NULLS LAST LIMIT 1),
    j, now())
  ON CONFLICT (gun, hesap_id, kampanya_id, kaynak) DO UPDATE SET
    kampanya_adi        = EXCLUDED.kampanya_adi,
    harcama             = EXCLUDED.harcama,
    para_birimi         = EXCLUDED.para_birimi,
    gosterim            = EXCLUDED.gosterim,
    erisim              = EXCLUDED.erisim,
    tiklama             = EXCLUDED.tiklama,
    link_tiklama        = EXCLUDED.link_tiklama,
    cpm                 = EXCLUDED.cpm,
    cpc                 = EXCLUDED.cpc,
    ctr                 = EXCLUDED.ctr,
    sikligi             = EXCLUDED.sikligi,
    meta_donusum        = EXCLUDED.meta_donusum,
    meta_donusum_degeri = EXCLUDED.meta_donusum_degeri,
    ham                 = EXCLUDED.ham,
    cekim_at            = EXCLUDED.cekim_at
  RETURNING (m.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;


ALTER FUNCTION raw.meta_harcama_yaz(j jsonb, p_hesap text) OWNER TO n8n;

--
-- Name: meta_hedef_url(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_hedef_url(c jsonb) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
  SELECT nullif(coalesce(
    c->'object_story_spec'->'video_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'link_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'link_data'->>'link',
    c->'object_story_spec'->'photo_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'template_data'->'call_to_action'->'value'->>'link',
    c->'object_story_spec'->'template_data'->>'link',
    c->'asset_feed_spec'->'link_urls'->0->>'website_url'
  ), '');
$$;


ALTER FUNCTION raw.meta_hedef_url(c jsonb) OWNER TO n8n;

--
-- Name: meta_hesap_yaz(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_hesap_yaz(j jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_id text; v_yeni boolean;
BEGIN
  -- API 'act_123' dondurur; biz her yerde oneksiz tutariz ki
  -- hafizadaki hesap kodlariyla birebir eslessin.
  v_id := regexp_replace(coalesce(j->>'id', j->>'account_id',''), '^act_', '');
  IF raw.bos_null(v_id) IS NULL THEN
    RAISE EXCEPTION 'Meta hesabinda id yok: %', left(j::text,200);
  END IF;

  INSERT INTO raw.meta_hesap AS h (hesap_id, ad, durum, para_birimi, portfolyo, ham, cekim_at)
  VALUES (v_id, raw.bos_null(j->>'name'), raw.sayi(j->>'account_status')::int,
          raw.bos_null(j->>'currency'), raw.bos_null(j#>>'{business,name}'), j, now())
  ON CONFLICT (hesap_id) DO UPDATE SET
    ad = EXCLUDED.ad, durum = EXCLUDED.durum, para_birimi = EXCLUDED.para_birimi,
    portfolyo = EXCLUDED.portfolyo, ham = EXCLUDED.ham, cekim_at = EXCLUDED.cekim_at
  RETURNING (h.xmax = 0) INTO v_yeni;

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;


ALTER FUNCTION raw.meta_hesap_yaz(j jsonb) OWNER TO n8n;

--
-- Name: meta_kreatif_yaz(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_kreatif_yaz(j jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE c jsonb;
BEGIN
  IF j->>'id' IS NULL THEN RETURN 'ATLANDI'; END IF;
  c := coalesce(j->'creative', '{}'::jsonb);
  INSERT INTO raw.meta_kreatif AS k (
    ad_id, ad_adi, ad_durumu, etkin_durum, adset_id, kampanya_id,
    kreatif_id, kreatif_adi, baslik, govde, cta, nesne_tipi,
    kucuk_gorsel, video_id, hedef_url, url_etiketleri,
    olusturma, guncelleme, ham, cekim_at)
  VALUES (
    j->>'id', j->>'name', j->>'status', j->>'effective_status',
    j->>'adset_id', j->>'campaign_id',
    c->>'id', c->>'name', c->>'title', c->>'body',
    raw.meta_cta(c), c->>'object_type',
    c->>'thumbnail_url', c->>'video_id',
    raw.meta_hedef_url(c), c->>'url_tags',
    raw.zaman(j->>'created_time'), raw.zaman(j->>'updated_time'), j, now())
  ON CONFLICT (ad_id) DO UPDATE SET
    ad_adi=EXCLUDED.ad_adi, ad_durumu=EXCLUDED.ad_durumu,
    etkin_durum=EXCLUDED.etkin_durum, adset_id=EXCLUDED.adset_id,
    kampanya_id=EXCLUDED.kampanya_id, kreatif_id=EXCLUDED.kreatif_id,
    kreatif_adi=EXCLUDED.kreatif_adi, baslik=EXCLUDED.baslik, govde=EXCLUDED.govde,
    cta=EXCLUDED.cta, nesne_tipi=EXCLUDED.nesne_tipi,
    kucuk_gorsel=EXCLUDED.kucuk_gorsel, video_id=EXCLUDED.video_id,
    hedef_url=EXCLUDED.hedef_url, url_etiketleri=EXCLUDED.url_etiketleri,
    guncelleme=EXCLUDED.guncelleme, ham=EXCLUDED.ham, cekim_at=EXCLUDED.cekim_at;
  RETURN 'OK';
END $$;


ALTER FUNCTION raw.meta_kreatif_yaz(j jsonb) OWNER TO n8n;

--
-- Name: meta_reklam_yaz(jsonb, text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.meta_reklam_yaz(j jsonb, p_hesap text) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_ad text; v_gun date;
BEGIN
  v_ad  := j->>'ad_id';
  v_gun := (j->>'date_start')::date;
  IF v_ad IS NULL OR v_gun IS NULL THEN RETURN 'ATLANDI'; END IF;

  INSERT INTO raw.meta_reklam AS m (
    hesap_id, gun, ad_id, ad_adi, adset_id, adset_adi, kampanya_id, kampanya_adi,
    harcama, gosterim, erisim, tiklama, link_tiklama, ctr, cpc, cpm, frekans,
    eylemler, eylem_degerleri, ham, cekim_at)
  VALUES (
    p_hesap, v_gun, v_ad,
    j->>'ad_name', j->>'adset_id', j->>'adset_name',
    j->>'campaign_id', j->>'campaign_name',
    raw.sayi(j->>'spend'), raw.sayi(j->>'impressions')::bigint,
    raw.sayi(j->>'reach')::bigint, raw.sayi(j->>'clicks')::bigint,
    raw.sayi(j->>'inline_link_clicks')::bigint,
    raw.sayi(j->>'ctr'), raw.sayi(j->>'cpc'), raw.sayi(j->>'cpm'),
    raw.sayi(j->>'frequency'),
    j->'actions', j->'action_values', j, now())
  ON CONFLICT (hesap_id, gun, ad_id) DO UPDATE SET
    ad_adi=EXCLUDED.ad_adi, adset_id=EXCLUDED.adset_id, adset_adi=EXCLUDED.adset_adi,
    kampanya_id=EXCLUDED.kampanya_id, kampanya_adi=EXCLUDED.kampanya_adi,
    harcama=EXCLUDED.harcama, gosterim=EXCLUDED.gosterim, erisim=EXCLUDED.erisim,
    tiklama=EXCLUDED.tiklama, link_tiklama=EXCLUDED.link_tiklama,
    ctr=EXCLUDED.ctr, cpc=EXCLUDED.cpc, cpm=EXCLUDED.cpm, frekans=EXCLUDED.frekans,
    eylemler=EXCLUDED.eylemler, eylem_degerleri=EXCLUDED.eylem_degerleri,
    ham=EXCLUDED.ham, cekim_at=EXCLUDED.cekim_at
  ;
  -- 🔴 RETURNING ile YENI/GUNCEL ayirmaya calismak (xmax hilesi) hatali ve
  --    gereksizdi; sayim ETL tarafinda yapiliyor.
  RETURN 'OK';
END $$;


ALTER FUNCTION raw.meta_reklam_yaz(j jsonb, p_hesap text) OWNER TO n8n;

--
-- Name: sayi(text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.sayi(t text) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  RETURN t::numeric;
EXCEPTION WHEN others THEN
  -- 🔴 Sessizce 0 DONDURME. Cozulemeyen sayi = NULL = "bilmiyoruz".
  RETURN NULL;
END $$;


ALTER FUNCTION raw.sayi(t text) OWNER TO n8n;

--
-- Name: wix_order_yaz(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.wix_order_yaz(j jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_id text; v_yeni boolean;
BEGIN
  v_id := raw.bos_null(j->>'id');
  IF v_id IS NULL THEN
    -- Ayni gerekce: Wix PII'si kimlik icin saklaniyor ama yukleme gunlugu
    -- AYRI bir maruziyet yuzeyidir; oraya alici bilgisi dusmemeli.
    RAISE EXCEPTION 'Wix siparisinde id yok (no=%, tarih=%)',
      coalesce(j->>'number','?'), coalesce(j->>'dateCreated','?');
  END IF;

  INSERT INTO raw.wix_order AS w (
    siparis_id, siparis_no, buyer_id, buyer_tipi, olusturma, guncelleme,
    odeme_durumu, odeme_yontemi, teslimat_durumu, toplam, para_birimi,
    kanal, arsivlendi, giren_id, giren_tipi, ic_siparis,
    ara_toplam, kdv, kargo_bedeli, siparis_indirimi, ham, cekim_at)
  VALUES (
    v_id,
    raw.sayi(j->>'number')::bigint,
    raw.bos_null(j#>>'{buyerInfo,id}'),
    raw.bos_null(j#>>'{buyerInfo,identityType}'),
    raw.zaman(j->>'dateCreated'),
    raw.zaman(j->>'lastUpdated'),
    raw.bos_null(j->>'paymentStatus'),
    raw.bos_null(j#>>'{billingInfo,paymentMethod}'),
    raw.bos_null(j->>'fulfillmentStatus'),
    raw.sayi(j#>>'{totals,total}'),
    raw.bos_null(j->>'currency'),
    raw.bos_null(j#>>'{channelInfo,type}'),
    -- 🔴 Wix bu alanlari "False"/"True" METNI olarak dondurur, boolean degil.
    lower(coalesce(j->>'archived','')) IN ('true','t'),
    raw.bos_null(j#>>'{enteredBy,id}'),
    raw.bos_null(j#>>'{enteredBy,identityType}'),
    lower(coalesce(j->>'isInternalOrderCreate','')) IN ('true','t'),
    -- 🔴 KDV AYRI OKUNUR (CR-012). totals.total KDV DAHILDIR; marj hesabi
    --    icin KDV haric taban gerekir. Alan yoksa NULL kalir - 0 YAZILMAZ,
    --    cunku "KDV yok" ile "KDV bilinmiyor" ayni sey degildir ve 0 yazmak
    --    KDV dahil tutari KDV haric gibi gosterirdi.
    -- 🔴 NET CIRO = toplam - kdv.  ara_toplam (subtotal) KULLANILMAZ:
    --    o indirim ONCESI liste tutaridir, matrah degildir.
    raw.sayi(j#>>'{totals,subtotal}'),
    raw.sayi(j#>>'{totals,tax}'),
    raw.sayi(j#>>'{totals,shipping}'),
    raw.sayi(j#>>'{totals,discount}'),
    j, now())
  ON CONFLICT (siparis_id) DO UPDATE SET
    siparis_no      = EXCLUDED.siparis_no,
    buyer_id        = EXCLUDED.buyer_id,
    buyer_tipi      = EXCLUDED.buyer_tipi,
    olusturma       = EXCLUDED.olusturma,
    guncelleme      = EXCLUDED.guncelleme,
    odeme_durumu    = EXCLUDED.odeme_durumu,
    odeme_yontemi   = EXCLUDED.odeme_yontemi,
    teslimat_durumu = EXCLUDED.teslimat_durumu,
    toplam          = EXCLUDED.toplam,
    para_birimi     = EXCLUDED.para_birimi,
    kanal           = EXCLUDED.kanal,
    arsivlendi      = EXCLUDED.arsivlendi,
    giren_id        = EXCLUDED.giren_id,
    giren_tipi      = EXCLUDED.giren_tipi,
    ic_siparis      = EXCLUDED.ic_siparis,
    ara_toplam      = EXCLUDED.ara_toplam,
    kdv             = EXCLUDED.kdv,
    kargo_bedeli    = EXCLUDED.kargo_bedeli,
    siparis_indirimi= EXCLUDED.siparis_indirimi,
    ham             = EXCLUDED.ham,
    cekim_at        = EXCLUDED.cekim_at
  RETURNING (w.xmax = 0) INTO v_yeni;

  -- Kalemler: siparisin kalem listesi kaynakta degisebilir (iptal/duzeltme).
  -- 🔴 Once sil sonra yaz - aksi halde SILINEN kalem sonsuza dek kalir.
  DELETE FROM raw.wix_order_item WHERE siparis_id = v_id;
  INSERT INTO raw.wix_order_item (siparis_id, sira, urun_id, urun_adi, sku, adet,
                                  birim_fiyat, toplam, indirim, ham)
  SELECT v_id,
         coalesce(raw.sayi(it->>'index')::int, ord::int),
         raw.bos_null(it->>'productId'),
         raw.bos_null(it->>'name'),
         raw.bos_null(it->>'sku'),
         raw.sayi(it->>'quantity'),
         raw.sayi(it->>'price'),
         raw.sayi(it->>'totalPrice'),
         -- 🔴 Kalem indirimi DUZ METINDIR: "1680.00". 'discount.amount' diye
         --    bir alt alan YOKTUR - oraya bakan kod indirimi hep 0 gorur.
         --    Bu alan okunmadigi icin ciro %18,8 sisik hesaplaniyordu.
         coalesce(raw.sayi(it->>'discount'), 0),
         it
    FROM jsonb_array_elements(coalesce(j->'lineItems','[]'::jsonb))
         WITH ORDINALITY AS t(it, ord);

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;


ALTER FUNCTION raw.wix_order_yaz(j jsonb) OWNER TO n8n;

--
-- Name: wix_urun_yaz(jsonb); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.wix_urun_yaz(j jsonb) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE v_id text; v_yeni boolean; v_maliyet numeric;
BEGIN
  v_id := raw.bos_null(j->>'id');
  IF v_id IS NULL THEN
    RAISE EXCEPTION 'Urunde id yok: %', left(j::text,200);
  END IF;
  v_maliyet := raw.sayi(j#>>'{costRange,minValue}');

  INSERT INTO raw.wix_urun AS u (
    urun_id, sku, ad, slug, fiyat, maliyet, para_birimi,
    gorunur, stok_takip, stok_adet, ham, cekim_at)
  VALUES (
    v_id,
    raw.bos_null(j->>'sku'),
    raw.bos_null(j->>'name'),
    raw.bos_null(j->>'slug'),
    raw.sayi(j#>>'{price,price}'),
    v_maliyet,
    raw.bos_null(j#>>'{price,currency}'),
    lower(coalesce(j->>'visible','')) IN ('true','t'),
    lower(coalesce(j#>>'{stock,trackInventory}','')) IN ('true','t'),
    raw.sayi(j#>>'{stock,quantity}'),
    j, now())
  ON CONFLICT (urun_id) DO UPDATE SET
    sku = EXCLUDED.sku, ad = EXCLUDED.ad, slug = EXCLUDED.slug,
    fiyat = EXCLUDED.fiyat, maliyet = EXCLUDED.maliyet,
    para_birimi = EXCLUDED.para_birimi, gorunur = EXCLUDED.gorunur,
    stok_takip = EXCLUDED.stok_takip, stok_adet = EXCLUDED.stok_adet,
    ham = EXCLUDED.ham, cekim_at = EXCLUDED.cekim_at
  RETURNING (u.xmax = 0) INTO v_yeni;

  -- Maliyet versiyonlamasi burada tetiklenir: deger degistiyse yeni surum.
  PERFORM core.maliyet_guncelle(v_id, v_maliyet, 'WIX');

  RETURN CASE WHEN v_yeni THEN 'INSERT' ELSE 'UPDATE' END;
END $$;


ALTER FUNCTION raw.wix_urun_yaz(j jsonb) OWNER TO n8n;

--
-- Name: zaman(text); Type: FUNCTION; Schema: raw; Owner: n8n
--

CREATE FUNCTION raw.zaman(t text) RETURNS timestamp with time zone
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
  IF raw.bos_null(t) IS NULL THEN RETURN NULL; END IF;
  RETURN t::timestamptz;
EXCEPTION WHEN others THEN
  RETURN NULL;
END $$;


ALTER FUNCTION raw.zaman(t text) OWNER TO n8n;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: memory_embedding; Type: TABLE; Schema: ai_semantic; Owner: n8n
--

CREATE TABLE ai_semantic.memory_embedding (
    embedding_id bigint NOT NULL,
    source_type text NOT NULL,
    source_ref text NOT NULL,
    content_hash text NOT NULL,
    model_id text NOT NULL,
    model_revision text NOT NULL,
    embedding public.vector(1024) NOT NULL,
    evidence_ref text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE ai_semantic.memory_embedding OWNER TO n8n;

--
-- Name: memory_embedding_embedding_id_seq; Type: SEQUENCE; Schema: ai_semantic; Owner: n8n
--

ALTER TABLE ai_semantic.memory_embedding ALTER COLUMN embedding_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME ai_semantic.memory_embedding_embedding_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: acik_soru; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.acik_soru (
    soru_id bigint NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    hedef text NOT NULL,
    soru text NOT NULL,
    neden_onemli text NOT NULL,
    beklenen_bilgi_degeri text NOT NULL,
    kaynak_plani text,
    ureten text DEFAULT 'ORCHESTRATOR'::text NOT NULL,
    bagli_bulgu bigint,
    durum text DEFAULT 'OPEN'::text NOT NULL,
    cevap_ozeti text,
    kapanma_nedeni text,
    oncelik text,
    is_etkisi text,
    gereken_departmanlar text[],
    bagimliliklar bigint[],
    onay_gereksinimi text,
    tahmini_compute text,
    proje text,
    CONSTRAINT acik_soru_bilgi_chk CHECK ((beklenen_bilgi_degeri = ANY (ARRAY['YUKSEK'::text, 'ORTA'::text, 'DUSUK'::text]))),
    CONSTRAINT acik_soru_durum_chk CHECK ((durum = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'ANSWERED'::text, 'DROPPED_LOW_VALUE'::text, 'BLOCKED_NEEDS_HUMAN'::text, 'BLOCKED_NO_ACCESS'::text]))),
    CONSTRAINT acik_soru_onay_chk CHECK (((onay_gereksinimi IS NULL) OR (onay_gereksinimi = ANY (ARRAY['L1'::text, 'L2'::text, 'L3'::text, 'L4'::text, 'L5'::text, 'L6'::text, 'L7'::text])))),
    CONSTRAINT acik_soru_oncelik_chk CHECK (((oncelik IS NULL) OR (oncelik = ANY (ARRAY['P0'::text, 'P1'::text, 'P2'::text, 'P3'::text, 'P4'::text])))),
    CONSTRAINT acik_soru_ureten_chk CHECK ((ureten = ANY (ARRAY['ORCHESTRATOR'::text, 'RED_TEAM'::text, 'CAPABILITY'::text, 'USER'::text])))
);


ALTER TABLE core.acik_soru OWNER TO n8n;

--
-- Name: acik_soru_soru_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.acik_soru_soru_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.acik_soru_soru_id_seq OWNER TO n8n;

--
-- Name: acik_soru_soru_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.acik_soru_soru_id_seq OWNED BY core.acik_soru.soru_id;


--
-- Name: ai_action_approval; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_action_approval (
    approval_id bigint NOT NULL,
    action_id bigint NOT NULL,
    approver_identity text NOT NULL,
    decision text NOT NULL,
    reason text NOT NULL,
    decided_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ai_action_approval_decision_check CHECK ((decision = ANY (ARRAY['APPROVED'::text, 'REJECTED'::text]))),
    CONSTRAINT ai_action_approval_reason_check CHECK (((length(reason) >= 1) AND (length(reason) <= 2000)))
);


ALTER TABLE core.ai_action_approval OWNER TO function_owner;

--
-- Name: ai_action_approval_approval_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

ALTER TABLE core.ai_action_approval ALTER COLUMN approval_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.ai_action_approval_approval_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ai_action_execution; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_action_execution (
    execution_id bigint NOT NULL,
    action_id bigint NOT NULL,
    execution_key text NOT NULL,
    state text DEFAULT 'OPEN'::text NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    last_result_summary text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ai_action_execution_attempt_count_check CHECK ((attempt_count >= 0)),
    CONSTRAINT ai_action_execution_max_attempts_check CHECK ((max_attempts > 0)),
    CONSTRAINT ai_action_execution_state_check CHECK ((state = ANY (ARRAY['OPEN'::text, 'LEASED'::text, 'EXECUTED'::text, 'FAILED_RETRYABLE'::text, 'FAILED_FINAL'::text])))
);


ALTER TABLE core.ai_action_execution OWNER TO function_owner;

--
-- Name: ai_action_execution_execution_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

ALTER TABLE core.ai_action_execution ALTER COLUMN execution_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.ai_action_execution_execution_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ai_action_proposal; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_action_proposal (
    action_id bigint NOT NULL,
    task_id bigint NOT NULL,
    idempotency_key text NOT NULL,
    action_type text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    state text DEFAULT 'PROPOSED'::text NOT NULL,
    risk_class text NOT NULL,
    policy_version text DEFAULT 'action-firewall-v1'::text NOT NULL,
    proposed_by text NOT NULL,
    proposed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    decided_by text,
    decided_at timestamp with time zone,
    decision_reason text,
    CONSTRAINT ai_action_proposal_check CHECK ((expires_at > proposed_at)),
    CONSTRAINT ai_action_proposal_check1 CHECK ((((state = 'PROPOSED'::text) AND (decided_at IS NULL) AND (decided_by IS NULL)) OR ((state <> 'PROPOSED'::text) AND (decided_at IS NOT NULL) AND (decided_by IS NOT NULL)))),
    CONSTRAINT ai_action_proposal_idempotency_key_check CHECK ((idempotency_key ~~ 'action:%'::text)),
    CONSTRAINT ai_action_proposal_payload_check CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ai_action_proposal_risk_class_check CHECK ((risk_class = ANY (ARRAY['LOW'::text, 'MEDIUM'::text, 'HIGH'::text, 'CRITICAL'::text]))),
    CONSTRAINT ai_action_proposal_state_check CHECK ((state = ANY (ARRAY['PROPOSED'::text, 'APPROVED'::text, 'REJECTED'::text, 'CANCELLED'::text, 'EXECUTING'::text, 'EXECUTED'::text, 'EXECUTION_FAILED'::text])))
);


ALTER TABLE core.ai_action_proposal OWNER TO function_owner;

--
-- Name: ai_action_proposal_action_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

ALTER TABLE core.ai_action_proposal ALTER COLUMN action_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.ai_action_proposal_action_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ai_action_type; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_action_type (
    action_type text NOT NULL,
    risk_class text NOT NULL,
    approval_mode text NOT NULL,
    proposal_enabled boolean DEFAULT true NOT NULL,
    execution_enabled boolean DEFAULT false NOT NULL,
    schema_version text NOT NULL,
    description text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ai_action_type_approval_mode_check CHECK ((approval_mode = ANY (ARRAY['ONE_PERSON'::text, 'TWO_PERSON'::text]))),
    CONSTRAINT ai_action_type_execution_enabled_check CHECK ((execution_enabled IS NOT NULL)),
    CONSTRAINT ai_action_type_risk_class_check CHECK ((risk_class = ANY (ARRAY['LOW'::text, 'MEDIUM'::text, 'HIGH'::text, 'CRITICAL'::text])))
);


ALTER TABLE core.ai_action_type OWNER TO function_owner;

--
-- Name: ai_calisma_log; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.ai_calisma_log (
    calisma_id bigint NOT NULL,
    zaman timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    saglayici text NOT NULL,
    model text NOT NULL,
    gorev text NOT NULL,
    anlik_id bigint,
    girdi_token integer,
    cikti_token integer,
    maliyet_usd numeric(12,6),
    sonuc text
);


ALTER TABLE core.ai_calisma_log OWNER TO n8n;

--
-- Name: ai_calisma_log_calisma_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.ai_calisma_log_calisma_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_calisma_log_calisma_id_seq OWNER TO n8n;

--
-- Name: ai_calisma_log_calisma_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.ai_calisma_log_calisma_id_seq OWNED BY core.ai_calisma_log.calisma_id;


--
-- Name: ai_evidence_followup; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_evidence_followup (
    followup_id bigint NOT NULL,
    decision_id bigint NOT NULL,
    question_id bigint NOT NULL,
    baseline_evidence_id bigint NOT NULL,
    state text DEFAULT 'WAITING'::text NOT NULL,
    enqueued_task_id bigint,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    enqueued_at timestamp with time zone,
    CONSTRAINT ai_evidence_followup_state_check CHECK ((state = ANY (ARRAY['WAITING'::text, 'ENQUEUED'::text, 'CANCELLED'::text])))
);


ALTER TABLE core.ai_evidence_followup OWNER TO function_owner;

--
-- Name: ai_evidence_followup_followup_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

ALTER TABLE core.ai_evidence_followup ALTER COLUMN followup_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.ai_evidence_followup_followup_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ai_executive_brief; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_executive_brief (
    brief_key text NOT NULL,
    message_id bigint,
    provider text NOT NULL,
    model text NOT NULL,
    context_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ai_executive_brief OWNER TO function_owner;

--
-- Name: ai_generated_question; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_generated_question (
    question_key text NOT NULL,
    soru_id bigint,
    provider text NOT NULL,
    context_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ai_generated_question OWNER TO function_owner;

--
-- Name: ai_human_data_attestation; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_human_data_attestation (
    attestation_id bigint NOT NULL,
    attestation_type text NOT NULL,
    scope text NOT NULL,
    value_json jsonb NOT NULL,
    attested_by text NOT NULL,
    attested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    active boolean DEFAULT true NOT NULL
);


ALTER TABLE core.ai_human_data_attestation OWNER TO function_owner;

--
-- Name: ai_human_data_attestation_attestation_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

ALTER TABLE core.ai_human_data_attestation ALTER COLUMN attestation_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.ai_human_data_attestation_attestation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ai_human_supersede_audit; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_human_supersede_audit (
    audit_id bigint NOT NULL,
    old_karar_id bigint NOT NULL,
    canonical_karar_id bigint NOT NULL,
    approver text NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ai_human_supersede_audit OWNER TO function_owner;

--
-- Name: ai_human_supersede_audit_audit_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.ai_human_supersede_audit_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_human_supersede_audit_audit_id_seq OWNER TO function_owner;

--
-- Name: ai_human_supersede_audit_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.ai_human_supersede_audit_audit_id_seq OWNED BY core.ai_human_supersede_audit.audit_id;


--
-- Name: ai_measurement_plan; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_measurement_plan (
    karar_id bigint NOT NULL,
    experiment_message_id bigint,
    data_message_id bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ai_measurement_plan OWNER TO function_owner;

--
-- Name: ai_model_policy; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_model_policy (
    policy_name text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    provider_order text[] NOT NULL,
    premium_providers text[] DEFAULT ARRAY['claude'::text, 'openai'::text] NOT NULL,
    standard_max_output_tokens integer NOT NULL,
    high_risk_max_output_tokens integer NOT NULL,
    high_risk_types text[] NOT NULL,
    council_opinions integer NOT NULL,
    context_limits jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ai_model_policy_council_opinions_check CHECK (((council_opinions >= 1) AND (council_opinions <= 3))),
    CONSTRAINT ai_model_policy_high_risk_max_output_tokens_check CHECK (((high_risk_max_output_tokens >= 128) AND (high_risk_max_output_tokens <= 3000))),
    CONSTRAINT ai_model_policy_standard_max_output_tokens_check CHECK (((standard_max_output_tokens >= 128) AND (standard_max_output_tokens <= 2000)))
);


ALTER TABLE core.ai_model_policy OWNER TO function_owner;

--
-- Name: ai_orchestrator_config; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_orchestrator_config (
    config_key text NOT NULL,
    config_value text NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE core.ai_orchestrator_config OWNER TO function_owner;

--
-- Name: ai_provider_attempt; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_provider_attempt (
    attempt_id bigint NOT NULL,
    task_id bigint,
    provider text NOT NULL,
    model text NOT NULL,
    attempt integer NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    latency_ms integer,
    result_class text NOT NULL,
    rate_limit boolean DEFAULT false NOT NULL,
    timeout boolean DEFAULT false NOT NULL,
    validation_result text,
    failover_reason text,
    context_profile text NOT NULL,
    context_version text NOT NULL,
    context_hash text,
    prompt_hash text,
    response_hash text,
    safe_summary text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    token_estimated boolean DEFAULT true NOT NULL,
    CONSTRAINT ai_provider_attempt_input_tokens_check CHECK ((input_tokens >= 0)),
    CONSTRAINT ai_provider_attempt_output_tokens_check CHECK ((output_tokens >= 0)),
    CONSTRAINT ai_provider_attempt_result_class_check CHECK ((result_class = ANY (ARRAY['SUCCESS'::text, 'RATE_LIMIT'::text, 'TIMEOUT'::text, 'PROVIDER_ERROR'::text, 'VALIDATION_FAILED'::text, 'POLICY_BLOCKED'::text, 'DUPLICATE'::text, 'FAILED'::text])))
);


ALTER TABLE core.ai_provider_attempt OWNER TO function_owner;

--
-- Name: ai_provider_attempt_attempt_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.ai_provider_attempt_attempt_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_provider_attempt_attempt_id_seq OWNER TO function_owner;

--
-- Name: ai_provider_attempt_attempt_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.ai_provider_attempt_attempt_id_seq OWNED BY core.ai_provider_attempt.attempt_id;


--
-- Name: ai_provider_budget; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_provider_budget (
    provider text NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    daily_attempt_limit integer NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    failure_threshold integer DEFAULT 3 NOT NULL,
    failure_window_minutes integer DEFAULT 15 NOT NULL,
    cooldown_minutes integer DEFAULT 15 NOT NULL,
    daily_token_limit bigint DEFAULT 100000 NOT NULL,
    CONSTRAINT ai_provider_budget_cooldown_minutes_check CHECK (((cooldown_minutes >= 1) AND (cooldown_minutes <= 1440))),
    CONSTRAINT ai_provider_budget_daily_attempt_limit_check CHECK (((daily_attempt_limit >= 0) AND (daily_attempt_limit <= 100000))),
    CONSTRAINT ai_provider_budget_daily_token_limit_check CHECK (((daily_token_limit >= 0) AND (daily_token_limit <= 100000000))),
    CONSTRAINT ai_provider_budget_failure_threshold_check CHECK (((failure_threshold >= 1) AND (failure_threshold <= 100))),
    CONSTRAINT ai_provider_budget_failure_window_minutes_check CHECK (((failure_window_minutes >= 1) AND (failure_window_minutes <= 1440)))
);


ALTER TABLE core.ai_provider_budget OWNER TO function_owner;

--
-- Name: ai_provider_price_config; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_provider_price_config (
    provider text NOT NULL,
    input_usd_per_million numeric(12,6),
    output_usd_per_million numeric(12,6),
    pricing_status text NOT NULL,
    effective_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT ai_provider_price_config_pricing_status_check CHECK ((pricing_status = ANY (ARRAY['FREE'::text, 'CONFIGURED'::text, 'UNKNOWN'::text])))
);


ALTER TABLE core.ai_provider_price_config OWNER TO function_owner;

--
-- Name: ai_question_route; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_question_route (
    soru_id bigint NOT NULL,
    departman text NOT NULL,
    mesaj_id bigint,
    reason text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ai_question_route OWNER TO function_owner;

--
-- Name: ai_red_team_attempt; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_red_team_attempt (
    attempt_id bigint NOT NULL,
    job_id bigint NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone NOT NULL,
    result_class text NOT NULL,
    validation_result text,
    failover_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    latency_ms integer,
    rate_limit boolean DEFAULT false NOT NULL,
    timeout boolean DEFAULT false NOT NULL,
    context_profile text,
    context_version text,
    context_hash text,
    input_tokens integer DEFAULT 0 NOT NULL,
    output_tokens integer DEFAULT 0 NOT NULL,
    token_estimated boolean DEFAULT true NOT NULL,
    CONSTRAINT ai_red_team_attempt_input_tokens_check CHECK ((input_tokens >= 0)),
    CONSTRAINT ai_red_team_attempt_output_tokens_check CHECK ((output_tokens >= 0))
);


ALTER TABLE core.ai_red_team_attempt OWNER TO function_owner;

--
-- Name: ai_red_team_attempt_attempt_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.ai_red_team_attempt_attempt_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_red_team_attempt_attempt_id_seq OWNER TO function_owner;

--
-- Name: ai_red_team_attempt_attempt_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.ai_red_team_attempt_attempt_id_seq OWNED BY core.ai_red_team_attempt.attempt_id;


--
-- Name: ai_red_team_job; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_red_team_job (
    job_id bigint NOT NULL,
    karar_id bigint NOT NULL,
    state text DEFAULT 'OPEN'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_error text,
    CONSTRAINT ai_red_team_job_state_check CHECK ((state = ANY (ARRAY['OPEN'::text, 'LEASED'::text, 'DONE'::text, 'RETRY'::text, 'FAILED'::text])))
);


ALTER TABLE core.ai_red_team_job OWNER TO function_owner;

--
-- Name: ai_red_team_job_job_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.ai_red_team_job_job_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_red_team_job_job_id_seq OWNER TO function_owner;

--
-- Name: ai_red_team_job_job_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.ai_red_team_job_job_id_seq OWNED BY core.ai_red_team_job.job_id;


--
-- Name: ai_task; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.ai_task (
    task_id bigint NOT NULL,
    source_type text NOT NULL,
    source_id bigint,
    task_type text NOT NULL,
    state text DEFAULT 'OPEN'::text NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    eligible_after timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    lease_owner text,
    lease_token uuid,
    lease_until timestamp with time zone,
    attempt_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 3 NOT NULL,
    idempotency_key text NOT NULL,
    cutoff_version text NOT NULL,
    ai_enqueue boolean DEFAULT false NOT NULL,
    enqueue_reason text,
    context_profile text DEFAULT 'default'::text NOT NULL,
    last_error text,
    completed_at timestamp with time zone,
    CONSTRAINT ai_task_attempt_count_check CHECK ((attempt_count >= 0)),
    CONSTRAINT ai_task_check CHECK (((source_type = 'MANUAL'::text) OR (source_id IS NOT NULL))),
    CONSTRAINT ai_task_max_attempts_check CHECK ((max_attempts > 0)),
    CONSTRAINT ai_task_source_type_check CHECK ((source_type = ANY (ARRAY['ACIK_SORU'::text, 'BULGU'::text, 'KARAR'::text, 'IC_MESAJ'::text, 'MANUAL'::text]))),
    CONSTRAINT ai_task_state_check CHECK ((state = ANY (ARRAY['OPEN'::text, 'LEASED'::text, 'RUNNING'::text, 'PROPOSED_WRITTEN'::text, 'NEEDS_REVIEW'::text, 'DONE'::text, 'FAILED_RETRYABLE'::text, 'FAILED_FINAL'::text, 'SKIPPED_CUTOFF'::text, 'DUPLICATE'::text]))),
    CONSTRAINT ai_task_task_type_check CHECK ((task_type = ANY (ARRAY['ANALYZE'::text, 'REDTEAM'::text, 'PROPOSE_DECISION'::text, 'PROPOSE_ACTION'::text, 'SUMMARIZE'::text, 'CLASSIFY'::text])))
);


ALTER TABLE core.ai_task OWNER TO function_owner;

--
-- Name: ai_task_task_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.ai_task_task_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ai_task_task_id_seq OWNER TO function_owner;

--
-- Name: ai_task_task_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.ai_task_task_id_seq OWNED BY core.ai_task.task_id;


--
-- Name: anayasa; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.anayasa (
    kural_kod text NOT NULL,
    kural text NOT NULL,
    kapsam text DEFAULT 'TUM_SIRKET'::text NOT NULL,
    ihlal_sonucu text NOT NULL,
    aktif boolean DEFAULT true NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE core.anayasa OWNER TO n8n;

--
-- Name: arac_envanteri; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.arac_envanteri (
    arac_id bigint NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    ad text NOT NULL,
    tur text NOT NULL,
    kaynak text,
    lisans text,
    ne_ise_yariyor text NOT NULL,
    nerede text,
    surum text,
    kurulu boolean DEFAULT true NOT NULL,
    calisiyor boolean DEFAULT false NOT NULL,
    calismiyorsa_neden text,
    son_arastirma date,
    alternatif_bakildi boolean DEFAULT false NOT NULL,
    arastirma_notu text
);


ALTER TABLE core.arac_envanteri OWNER TO n8n;

--
-- Name: arac_envanteri_arac_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.arac_envanteri_arac_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.arac_envanteri_arac_id_seq OWNER TO n8n;

--
-- Name: arac_envanteri_arac_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.arac_envanteri_arac_id_seq OWNED BY core.arac_envanteri.arac_id;


--
-- Name: arastirma_plani; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.arastirma_plani (
    plan_id bigint NOT NULL,
    kapsam text NOT NULL,
    hedef text NOT NULL,
    konu text NOT NULL,
    siklik_gun integer NOT NULL,
    oncelik integer DEFAULT 5 NOT NULL,
    gerekce text NOT NULL,
    planlayan text DEFAULT 'is_planlama'::text NOT NULL,
    olusturuldu timestamp with time zone DEFAULT now() NOT NULL,
    aktif boolean DEFAULT true NOT NULL,
    son_kosu timestamp with time zone,
    son_bulgu integer DEFAULT 0 NOT NULL,
    CONSTRAINT arastirma_plani_kapsam CHECK ((kapsam = ANY (ARRAY['DEPARTMAN'::text, 'URUN'::text]))),
    CONSTRAINT arastirma_plani_oncelik CHECK (((oncelik >= 1) AND (oncelik <= 9))),
    CONSTRAINT arastirma_plani_siklik CHECK (((siklik_gun >= 1) AND (siklik_gun <= 90)))
);


ALTER TABLE core.arastirma_plani OWNER TO n8n;

--
-- Name: arastirma_plani_plan_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.arastirma_plani_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.arastirma_plani_plan_id_seq OWNER TO n8n;

--
-- Name: arastirma_plani_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.arastirma_plani_plan_id_seq OWNED BY core.arastirma_plani.plan_id;


--
-- Name: ayar; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.ayar (
    anahtar text NOT NULL,
    deger text NOT NULL,
    aciklama text,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.ayar OWNER TO n8n;

--
-- Name: basin_bahsi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.basin_bahsi (
    bahis_id bigint NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    baslik text NOT NULL,
    kaynak_site text NOT NULL,
    url text,
    yayin_tarihi text,
    ozet text,
    arama_terimi text NOT NULL,
    bulundu timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    mevzuat_bayragi text[],
    mevzuat_durumu text DEFAULT 'DENETLENMEDI'::text NOT NULL,
    not_dusen text,
    CONSTRAINT basin_bahsi_mevzuat_durumu_check CHECK ((mevzuat_durumu = ANY (ARRAY['DENETLENMEDI'::text, 'TEMIZ'::text, 'RISKLI'::text])))
);


ALTER TABLE core.basin_bahsi OWNER TO n8n;

--
-- Name: basin_bahsi_bahis_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.basin_bahsi_bahis_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.basin_bahsi_bahis_id_seq OWNER TO n8n;

--
-- Name: basin_bahsi_bahis_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.basin_bahsi_bahis_id_seq OWNED BY core.basin_bahsi.bahis_id;


--
-- Name: bayi_kampanya; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.bayi_kampanya (
    sira smallint NOT NULL,
    baslik text NOT NULL,
    kosul text,
    gecerli boolean DEFAULT true NOT NULL,
    kaynak text,
    girildi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.bayi_kampanya OWNER TO n8n;

--
-- Name: birlestirme_karari; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.birlestirme_karari (
    karar_id bigint NOT NULL,
    kaynak text NOT NULL,
    kimlik_tipi text NOT NULL,
    source_id_a text NOT NULL,
    source_id_b text NOT NULL,
    karar text NOT NULL,
    gerekce text NOT NULL,
    karar_veren text NOT NULL,
    karar_at timestamp with time zone DEFAULT now() NOT NULL,
    uygulandi_at timestamp with time zone,
    CONSTRAINT birlestirme_karari_karar_check CHECK ((karar = ANY (ARRAY['BIRLESTIR'::text, 'AYRI_TUT'::text])))
);


ALTER TABLE core.birlestirme_karari OWNER TO n8n;

--
-- Name: birlestirme_karari_karar_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.birlestirme_karari ALTER COLUMN karar_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.birlestirme_karari_karar_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: buyume_bulgu; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.buyume_bulgu (
    bulgu_id bigint NOT NULL,
    anlik_id bigint NOT NULL,
    modul text NOT NULL,
    seviye text NOT NULL,
    sinif text,
    baslik text NOT NULL,
    kanit text NOT NULL,
    beklenen_etki text,
    risk text,
    kanit_sinifi text,
    yanlislama text,
    insan_onayi boolean DEFAULT true NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guven numeric(3,2),
    fikrimi_degistirecek text,
    inanc_durumu text,
    ustunu_alan bigint,
    guncelleme timestamp with time zone,
    CONSTRAINT buyume_bulgu_guven_chk CHECK (((guven IS NULL) OR ((guven >= (0)::numeric) AND (guven <= (1)::numeric)))),
    CONSTRAINT buyume_bulgu_inanc_chk CHECK (((inanc_durumu IS NULL) OR (inanc_durumu = ANY (ARRAY['ACTIVE'::text, 'WEAKENED'::text, 'REFUTED'::text, 'SUPERSEDED'::text, 'PARKED'::text, 'CONFIRMED'::text])))),
    CONSTRAINT buyume_bulgu_seviye_check CHECK ((seviye = ANY (ARRAY['OBSERVED'::text, 'INFERRED'::text, 'HYPOTHESIS'::text, 'NOT_CONNECTED'::text])))
);


ALTER TABLE core.buyume_bulgu OWNER TO n8n;

--
-- Name: buyume_bulgu_bulgu_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.buyume_bulgu_bulgu_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.buyume_bulgu_bulgu_id_seq OWNER TO n8n;

--
-- Name: buyume_bulgu_bulgu_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.buyume_bulgu_bulgu_id_seq OWNED BY core.buyume_bulgu.bulgu_id;


--
-- Name: customer; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.customer (
    customer_id bigint NOT NULL,
    phone_normalized text,
    email_normalized text,
    identity_status text DEFAULT 'UNKNOWN'::text NOT NULL,
    match_method text,
    match_confidence smallint,
    notlar jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT customer_identity_status_check CHECK ((identity_status = ANY (ARRAY['MATCHED'::text, 'CONFLICT'::text, 'INVALID'::text, 'UNKNOWN'::text]))),
    CONSTRAINT customer_match_confidence_check CHECK (((match_confidence >= 0) AND (match_confidence <= 100)))
);


ALTER TABLE core.customer OWNER TO n8n;

--
-- Name: customer_customer_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.customer ALTER COLUMN customer_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.customer_customer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: customer_identity; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.customer_identity (
    identity_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    kaynak text NOT NULL,
    kimlik_tipi text NOT NULL,
    source_customer_id text,
    deger_ham text NOT NULL,
    deger_normal text,
    gecerli boolean DEFAULT true NOT NULL,
    match_method text NOT NULL,
    match_confidence smallint NOT NULL,
    match_reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT customer_identity_kimlik_tipi_check CHECK ((kimlik_tipi = ANY (ARRAY['phone'::text, 'email'::text, 'wix_buyer_id'::text, 'wa_id'::text, 'ig_id'::text, 'psid'::text, 'web_id'::text]))),
    CONSTRAINT customer_identity_match_confidence_check CHECK (((match_confidence >= 0) AND (match_confidence <= 100)))
);


ALTER TABLE core.customer_identity OWNER TO n8n;

--
-- Name: customer_identity_identity_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.customer_identity ALTER COLUMN identity_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.customer_identity_identity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: departman; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.departman (
    kod text NOT NULL,
    ad text NOT NULL,
    aile text NOT NULL,
    misyon text NOT NULL,
    durum text NOT NULL,
    veri_kaynagi text,
    kanit text,
    otonomi_tavani text DEFAULT 'L5'::text NOT NULL,
    escalation text DEFAULT 'MANAGING_DIRECTOR'::text NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT departman_durum_chk CHECK ((durum = ANY (ARRAY['CALISIYOR'::text, 'KISMI'::text, 'YOK'::text]))),
    CONSTRAINT departman_otonomi_chk CHECK ((otonomi_tavani = ANY (ARRAY['L1'::text, 'L2'::text, 'L3'::text, 'L4'::text, 'L5'::text, 'L6'::text, 'L7'::text])))
);


ALTER TABLE core.departman OWNER TO n8n;

--
-- Name: funnel_adim; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.funnel_adim (
    adim_kod text NOT NULL,
    sira integer NOT NULL,
    ad text NOT NULL,
    ga4_event_adi text,
    enstrumantasyon text NOT NULL,
    olcum_yeri text,
    olcum_kaniti text NOT NULL,
    olcum_zamani timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    olcum_yontemi text NOT NULL,
    notlar text,
    CONSTRAINT funnel_adim_enstrumantasyon_check CHECK ((enstrumantasyon = ANY (ARRAY['MEASURED'::text, 'NOT_INSTRUMENTED'::text, 'PARTIAL'::text, 'DEGRADED'::text, 'UNKNOWN'::text, 'NOT_TESTED'::text])))
);


ALTER TABLE core.funnel_adim OWNER TO n8n;

--
-- Name: funnel_sayfa_kapsama; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.funnel_sayfa_kapsama (
    adim_kod text NOT NULL,
    sayfa text NOT NULL,
    sayfa_rolu text NOT NULL,
    enstrumantasyon text NOT NULL,
    olcum_kaniti text NOT NULL,
    olcum_zamani timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    urun_id text,
    CONSTRAINT funnel_sayfa_kapsama_enstrumantasyon_check CHECK ((enstrumantasyon = ANY (ARRAY['MEASURED'::text, 'NOT_INSTRUMENTED'::text, 'NOT_TESTED'::text, 'UNKNOWN'::text])))
);


ALTER TABLE core.funnel_sayfa_kapsama OWNER TO n8n;

--
-- Name: geo_alias; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_alias (
    alias_id bigint NOT NULL,
    canonical_brand_id bigint NOT NULL,
    alias text NOT NULL,
    normalized_alias text NOT NULL,
    alias_type text NOT NULL,
    language text,
    active boolean DEFAULT true NOT NULL,
    CONSTRAINT ck_geo_alias_tip CHECK ((alias_type = ANY (ARRAY['OFFICIAL'::text, 'UNICODE_VARIANT'::text, 'ASCII_FOLD'::text, 'SPACING'::text, 'MISSPELLING'::text, 'ABBREVIATION'::text, 'LEGACY'::text])))
);


ALTER TABLE core.geo_alias OWNER TO n8n;

--
-- Name: geo_alias_alias_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_alias_alias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_alias_alias_id_seq OWNER TO n8n;

--
-- Name: geo_alias_alias_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_alias_alias_id_seq OWNED BY core.geo_alias.alias_id;


--
-- Name: geo_brand; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_brand (
    brand_id bigint NOT NULL,
    canonical_name text NOT NULL,
    bizim_mi boolean DEFAULT false NOT NULL,
    ilk_gorulme timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.geo_brand OWNER TO n8n;

--
-- Name: geo_brand_brand_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_brand_brand_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_brand_brand_id_seq OWNER TO n8n;

--
-- Name: geo_brand_brand_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_brand_brand_id_seq OWNED BY core.geo_brand.brand_id;


--
-- Name: geo_citation; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_citation (
    citation_id bigint NOT NULL,
    observation_id bigint NOT NULL,
    source_id bigint NOT NULL,
    kanonik_url text NOT NULL,
    url_hash text NOT NULL,
    baslik text,
    sira integer
);


ALTER TABLE core.geo_citation OWNER TO n8n;

--
-- Name: geo_citation_citation_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_citation_citation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_citation_citation_id_seq OWNER TO n8n;

--
-- Name: geo_citation_citation_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_citation_citation_id_seq OWNED BY core.geo_citation.citation_id;


--
-- Name: geo_citation_mention; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_citation_mention (
    citation_id bigint NOT NULL,
    mention_id bigint NOT NULL,
    iliski_turu text NOT NULL,
    kanit text NOT NULL,
    guven numeric(4,3) NOT NULL,
    CONSTRAINT ck_geo_cm_turu CHECK ((iliski_turu = ANY (ARRAY['EXPLICIT_INLINE'::text, 'EXPLICIT_FOOTNOTE'::text, 'EXPLICIT_ATTRIBUTION'::text])))
);


ALTER TABLE core.geo_citation_mention OWNER TO n8n;

--
-- Name: geo_entity_conflict; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_entity_conflict (
    conflict_id bigint NOT NULL,
    urun text NOT NULL,
    alan text NOT NULL,
    beklenen text NOT NULL,
    gozlenen text NOT NULL,
    kaynak_url text,
    source_id bigint,
    siddet text NOT NULL,
    guven numeric(4,3),
    durum text DEFAULT 'ACIK'::text NOT NULL,
    tespit_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.geo_entity_conflict OWNER TO n8n;

--
-- Name: geo_entity_conflict_conflict_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_entity_conflict_conflict_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_entity_conflict_conflict_id_seq OWNER TO n8n;

--
-- Name: geo_entity_conflict_conflict_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_entity_conflict_conflict_id_seq OWNED BY core.geo_entity_conflict.conflict_id;


--
-- Name: geo_gap; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_gap (
    gap_id bigint NOT NULL,
    tip text NOT NULL,
    urun text,
    query_id bigint,
    source_id bigint,
    siddet text NOT NULL,
    kanit text NOT NULL,
    action_id bigint,
    durum text DEFAULT 'ACIK'::text NOT NULL,
    tespit_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_geo_gap_tip CHECK ((tip = ANY (ARRAY['QUERY'::text, 'CONTENT'::text, 'ENTITY'::text, 'CITATION'::text, 'AUTHORITY'::text, 'TECHNICAL'::text, 'EVIDENCE'::text])))
);


ALTER TABLE core.geo_gap OWNER TO n8n;

--
-- Name: geo_gap_gap_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_gap_gap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_gap_gap_id_seq OWNER TO n8n;

--
-- Name: geo_gap_gap_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_gap_gap_id_seq OWNED BY core.geo_gap.gap_id;


--
-- Name: geo_karar_kapsami; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_karar_kapsami (
    karar_id bigint NOT NULL,
    query_id bigint,
    kume_anahtari text,
    urun text,
    rol text NOT NULL,
    kapsam_id bigint NOT NULL,
    CONSTRAINT ck_geo_kk_dolu CHECK (((query_id IS NOT NULL) OR (kume_anahtari IS NOT NULL) OR (urun IS NOT NULL))),
    CONSTRAINT ck_geo_kk_rol CHECK ((rol = ANY (ARRAY['TARGET'::text, 'CONTROL'::text, 'CONFOUNDER'::text])))
);


ALTER TABLE core.geo_karar_kapsami OWNER TO n8n;

--
-- Name: geo_karar_kapsami_kapsam_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_karar_kapsami_kapsam_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_karar_kapsami_kapsam_id_seq OWNER TO n8n;

--
-- Name: geo_karar_kapsami_kapsam_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_karar_kapsami_kapsam_id_seq OWNED BY core.geo_karar_kapsami.kapsam_id;


--
-- Name: geo_mention; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_mention (
    mention_id bigint NOT NULL,
    observation_id bigint NOT NULL,
    brand_id bigint NOT NULL,
    urun text,
    tip text NOT NULL,
    baglam text,
    sira integer,
    CONSTRAINT ck_geo_mention_tip CHECK ((tip = ANY (ARRAY['BRAND'::text, 'PRODUCT'::text])))
);


ALTER TABLE core.geo_mention OWNER TO n8n;

--
-- Name: geo_mention_mention_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_mention_mention_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_mention_mention_id_seq OWNER TO n8n;

--
-- Name: geo_mention_mention_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_mention_mention_id_seq OWNED BY core.geo_mention.mention_id;


--
-- Name: geo_observation; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_observation (
    observation_id bigint NOT NULL,
    query_id bigint NOT NULL,
    yuzey text NOT NULL,
    model text,
    language text NOT NULL,
    country text NOT NULL,
    gozlem_at timestamp with time zone NOT NULL,
    durum text NOT NULL,
    ham_id bigint,
    cevap_hash text,
    guven numeric(4,3),
    parser_surum text NOT NULL,
    normalizer_surum text NOT NULL,
    CONSTRAINT ck_geo_obs_durum CHECK ((durum = ANY (ARRAY['OBSERVED'::text, 'UNAVAILABLE'::text, 'UNSUPPORTED'::text, 'REQUIRES_MANUAL_VALIDATION'::text]))),
    CONSTRAINT ck_geo_obs_kanit CHECK (((durum <> 'OBSERVED'::text) OR (ham_id IS NOT NULL)))
);


ALTER TABLE core.geo_observation OWNER TO n8n;

--
-- Name: geo_observation_observation_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_observation_observation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_observation_observation_id_seq OWNER TO n8n;

--
-- Name: geo_observation_observation_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_observation_observation_id_seq OWNED BY core.geo_observation.observation_id;


--
-- Name: geo_query; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_query (
    query_id bigint NOT NULL,
    sorgu_metni text NOT NULL,
    language text NOT NULL,
    country text NOT NULL,
    niyet text NOT NULL,
    kume_anahtari text,
    urun text,
    kaynak text NOT NULL,
    oncelik integer DEFAULT 5 NOT NULL,
    uygunluk text DEFAULT 'REQUIRES_EVIDENCE'::text NOT NULL,
    iddia_riski text DEFAULT 'UNKNOWN'::text NOT NULL,
    set_surum text NOT NULL,
    kesif_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_geo_query_uygunluk CHECK ((uygunluk = ANY (ARRAY['SUPPORTED'::text, 'PARTIALLY_SUPPORTED'::text, 'UNSUPPORTED'::text, 'REQUIRES_EVIDENCE'::text])))
);


ALTER TABLE core.geo_query OWNER TO n8n;

--
-- Name: geo_query_query_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_query_query_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_query_query_id_seq OWNER TO n8n;

--
-- Name: geo_query_query_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_query_query_id_seq OWNED BY core.geo_query.query_id;


--
-- Name: geo_source; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.geo_source (
    source_id bigint NOT NULL,
    domain text NOT NULL,
    tur text,
    ilk_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    son_gorulme timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.geo_source OWNER TO n8n;

--
-- Name: geo_source_source_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.geo_source_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.geo_source_source_id_seq OWNER TO n8n;

--
-- Name: geo_source_source_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.geo_source_source_id_seq OWNED BY core.geo_source.source_id;


--
-- Name: gonderi_notu; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.gonderi_notu (
    not_id bigint NOT NULL,
    siparis_ref text,
    tur text NOT NULL,
    alici text,
    urun_adi text,
    adet numeric,
    elle_fiyat numeric,
    not_metni text,
    giren text NOT NULL,
    girildi timestamp with time zone DEFAULT now() NOT NULL,
    kanal text,
    CONSTRAINT gonderi_notu_adet CHECK (((adet IS NULL) OR (adet >= (0)::numeric))),
    CONSTRAINT gonderi_notu_fiyat CHECK (((elle_fiyat IS NULL) OR (elle_fiyat >= (0)::numeric))),
    CONSTRAINT gonderi_notu_kanal CHECK (((kanal IS NULL) OR (kanal = ANY (ARRAY['KAPIDA'::text, 'WHATSAPP'::text, 'TELEFON'::text, 'TRENDYOL'::text, 'ELDEN'::text, 'DIGER'::text, 'BILINMIYOR'::text])))),
    CONSTRAINT gonderi_notu_tur CHECK ((tur = ANY (ARRAY['SATIS'::text, 'UGC'::text, 'INFLUENCER'::text, 'NUMUNE'::text, 'HEDIYE'::text, 'IADE'::text, 'DEGISIM'::text, 'BILINMIYOR'::text])))
);


ALTER TABLE core.gonderi_notu OWNER TO n8n;

--
-- Name: gonderi_notu_not_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.gonderi_notu_not_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.gonderi_notu_not_id_seq OWNER TO n8n;

--
-- Name: gonderi_notu_not_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.gonderi_notu_not_id_seq OWNED BY core.gonderi_notu.not_id;


--
-- Name: gonderi_sinif_beyani; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.gonderi_sinif_beyani (
    gonderi_id text NOT NULL,
    sinif text NOT NULL,
    gerekce text,
    beyan_eden text NOT NULL,
    beyan_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT gonderi_sinif_beyani_sinif_check CHECK ((sinif = ANY (ARRAY['NUMUNE'::text, 'SATIS'::text, 'ELLE_SATIS'::text, 'IADE'::text])))
);


ALTER TABLE core.gonderi_sinif_beyani OWNER TO n8n;

--
-- Name: guncel_olay; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.guncel_olay (
    id bigint NOT NULL,
    gun date NOT NULL,
    aci text NOT NULL,
    baslik text NOT NULL,
    ozet text NOT NULL,
    neden_onemli text,
    kaynak_url text NOT NULL,
    kaynak_adi text,
    yayin_tarihi text,
    onem text DEFAULT 'BILGI'::text NOT NULL,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT guncel_olay_onem_check CHECK ((onem = ANY (ARRAY['KRITIK'::text, 'DIKKAT'::text, 'BILGI'::text])))
);


ALTER TABLE core.guncel_olay OWNER TO n8n;

--
-- Name: guncel_olay_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.guncel_olay_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.guncel_olay_id_seq OWNER TO n8n;

--
-- Name: guncel_olay_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.guncel_olay_id_seq OWNED BY core.guncel_olay.id;


--
-- Name: guncel_olay_kosu; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.guncel_olay_kosu (
    gun date NOT NULL,
    durum text NOT NULL,
    aci_sayisi integer DEFAULT 0 NOT NULL,
    kaynak_sayisi integer DEFAULT 0 NOT NULL,
    madde_sayisi integer DEFAULT 0 NOT NULL,
    model text,
    sure_sn numeric,
    not_metni text,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT guncel_olay_kosu_durum_check CHECK ((durum = ANY (ARRAY['URETILDI'::text, 'KAYNAK_YOK'::text, 'HATA'::text])))
);


ALTER TABLE core.guncel_olay_kosu OWNER TO n8n;

--
-- Name: hatirlatici; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.hatirlatici (
    id bigint NOT NULL,
    baslik text NOT NULL,
    not_ text,
    zaman timestamp with time zone NOT NULL,
    tekrar text,
    onem text DEFAULT 'NORMAL'::text NOT NULL,
    durum text DEFAULT 'ACIK'::text NOT NULL,
    kaynak text DEFAULT 'sahip'::text NOT NULL,
    tamamlandi timestamp with time zone,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT hatirlatici_baslik_dolu CHECK ((length(TRIM(BOTH FROM baslik)) >= 2)),
    CONSTRAINT hatirlatici_durum_izinli CHECK ((durum = ANY (ARRAY['ACIK'::text, 'TAMAM'::text, 'IPTAL'::text]))),
    CONSTRAINT hatirlatici_onem_izinli CHECK ((onem = ANY (ARRAY['DUSUK'::text, 'NORMAL'::text, 'YUKSEK'::text]))),
    CONSTRAINT hatirlatici_tekrar_izinli CHECK (((tekrar IS NULL) OR (tekrar = ANY (ARRAY['gunluk'::text, 'haftalik'::text, 'aylik'::text]))))
);


ALTER TABLE core.hatirlatici OWNER TO n8n;

--
-- Name: hatirlatici_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.hatirlatici_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.hatirlatici_id_seq OWNER TO n8n;

--
-- Name: hatirlatici_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.hatirlatici_id_seq OWNED BY core.hatirlatici.id;


--
-- Name: ic_mesaj; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.ic_mesaj (
    mesaj_id bigint NOT NULL,
    zaman timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    kimden text NOT NULL,
    kime text,
    tip text NOT NULL,
    konu text NOT NULL,
    icerik text NOT NULL,
    bagli_bulgu bigint,
    bagli_karar bigint,
    bagli_soru bigint,
    durum text DEFAULT 'OPEN'::text NOT NULL,
    yanit_veren text,
    yanit text,
    kapanma timestamp with time zone,
    CONSTRAINT ic_mesaj_durum_chk CHECK ((durum = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'BLOCKED'::text, 'COMPLETE'::text, 'DROPPED'::text]))),
    CONSTRAINT ic_mesaj_tip_chk CHECK ((tip = ANY (ARRAY['FINDING'::text, 'QUESTION'::text, 'REQUEST'::text, 'CHALLENGE'::text, 'RISK'::text, 'OPPORTUNITY'::text, 'TASK'::text, 'DEPENDENCY'::text, 'BLOCKER'::text, 'DECISION'::text, 'RESULT'::text, 'ALERT'::text, 'HANDOFF'::text])))
);


ALTER TABLE core.ic_mesaj OWNER TO n8n;

--
-- Name: ic_mesaj_mesaj_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.ic_mesaj_mesaj_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ic_mesaj_mesaj_id_seq OWNER TO n8n;

--
-- Name: ic_mesaj_mesaj_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.ic_mesaj_mesaj_id_seq OWNED BY core.ic_mesaj.mesaj_id;


--
-- Name: identity_conflict; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.identity_conflict (
    conflict_id bigint NOT NULL,
    kimlik_tipi text NOT NULL,
    deger_normal text NOT NULL,
    customer_ids bigint[] NOT NULL,
    kaynak_kayitlar jsonb DEFAULT '[]'::jsonb NOT NULL,
    durum text DEFAULT 'ACIK'::text NOT NULL,
    cozum_notu text,
    tespit_at timestamp with time zone DEFAULT now() NOT NULL,
    cozum_at timestamp with time zone,
    CONSTRAINT identity_conflict_durum_check CHECK ((durum = ANY (ARRAY['ACIK'::text, 'COZULDU'::text, 'YOKSAYILDI'::text])))
);


ALTER TABLE core.identity_conflict OWNER TO n8n;

--
-- Name: identity_conflict_conflict_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.identity_conflict ALTER COLUMN conflict_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.identity_conflict_conflict_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ig_gonderi_plani; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.ig_gonderi_plani (
    plan_id bigint NOT NULL,
    urun_slug text NOT NULL,
    amac text NOT NULL,
    bicim text NOT NULL,
    kanca text NOT NULL,
    caption text NOT NULL,
    hashtagler text[] DEFAULT '{}'::text[] NOT NULL,
    gorsel_brief text NOT NULL,
    cta text,
    cta_gerekce text,
    dayanak text NOT NULL,
    itiraz text,
    itiraza_yanit text,
    denetim text NOT NULL,
    denetim_notu text,
    durum text DEFAULT 'ONERI'::text NOT NULL,
    uretim_at timestamp with time zone DEFAULT now() NOT NULL,
    karar_at timestamp with time zone,
    karar_veren text,
    gorsel_dosya text,
    gorsel_rapor jsonb,
    konsept_id bigint,
    gorsel_taslak_mi boolean DEFAULT true NOT NULL,
    CONSTRAINT ig_plan_amac_ck CHECK ((amac = ANY (ARRAY['SATIS'::text, 'TANITIM'::text, 'B2B'::text]))),
    CONSTRAINT ig_plan_bicim_ck CHECK ((bicim = ANY (ARRAY['REELS'::text, 'KARUSEL'::text, 'TEK_GORSEL'::text]))),
    CONSTRAINT ig_plan_durum_ck CHECK ((durum = ANY (ARRAY['ONERI'::text, 'ONAYLANDI'::text, 'REDDEDILDI'::text, 'YAYINLANDI'::text]))),
    CONSTRAINT ig_plan_itiraz_ck CHECK (((durum <> ALL (ARRAY['ONAYLANDI'::text, 'YAYINLANDI'::text])) OR (COALESCE(btrim(itiraza_yanit), ''::text) <> ''::text))),
    CONSTRAINT ig_plan_konsept_ck CHECK ((gorsel_taslak_mi OR (konsept_id IS NOT NULL))),
    CONSTRAINT ig_plan_onay_ck CHECK (((durum <> ALL (ARRAY['ONAYLANDI'::text, 'YAYINLANDI'::text])) OR (denetim = 'TEMIZ'::text)))
);


ALTER TABLE core.ig_gonderi_plani OWNER TO n8n;

--
-- Name: ig_gonderi_plani_plan_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.ig_gonderi_plani_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.ig_gonderi_plani_plan_id_seq OWNER TO n8n;

--
-- Name: ig_gonderi_plani_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.ig_gonderi_plani_plan_id_seq OWNED BY core.ig_gonderi_plani.plan_id;


--
-- Name: inanc_catismasi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.inanc_catismasi (
    catisma_id bigint NOT NULL,
    zaman timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    bulgu_a bigint NOT NULL,
    bulgu_b bigint NOT NULL,
    aciklama text NOT NULL,
    cozum_yolu text,
    durum text DEFAULT 'OPEN'::text NOT NULL,
    cozum text,
    kapanma timestamp with time zone,
    CONSTRAINT inanc_catismasi_durum_chk CHECK ((durum = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'RESOLVED'::text, 'ACCEPTED_UNCERTAINTY'::text]))),
    CONSTRAINT inanc_catismasi_farkli CHECK ((bulgu_a <> bulgu_b))
);


ALTER TABLE core.inanc_catismasi OWNER TO n8n;

--
-- Name: inanc_catismasi_catisma_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.inanc_catismasi_catisma_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.inanc_catismasi_catisma_id_seq OWNER TO n8n;

--
-- Name: inanc_catismasi_catisma_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.inanc_catismasi_catisma_id_seq OWNED BY core.inanc_catismasi.catisma_id;


--
-- Name: jarvis_action_registry; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_action_registry (
    action_key text NOT NULL,
    source text NOT NULL,
    source_id text NOT NULL,
    owner text NOT NULL,
    kind text NOT NULL,
    description text NOT NULL,
    risk_level text NOT NULL,
    payload_hash text NOT NULL,
    status text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    payload jsonb NOT NULL,
    idempotency_key text NOT NULL,
    approved_by text,
    external_id text,
    message text,
    task_id bigint,
    CONSTRAINT jarvis_action_registry_source_check CHECK ((source = ANY (ARRAY['company'::text, 'personal'::text])))
);


ALTER TABLE core.jarvis_action_registry OWNER TO n8n;

--
-- Name: jarvis_action_registry_event; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_action_registry_event (
    event_id bigint NOT NULL,
    action_key text NOT NULL,
    event_type text NOT NULL,
    from_status text,
    to_status text NOT NULL,
    actor text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE core.jarvis_action_registry_event OWNER TO n8n;

--
-- Name: jarvis_action_registry_event_event_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.jarvis_action_registry_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.jarvis_action_registry_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: jarvis_cari_account; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_cari_account (
    account_id text NOT NULL,
    owner text NOT NULL,
    name text NOT NULL,
    name_key text NOT NULL,
    role text NOT NULL,
    contact text DEFAULT ''::text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    covers jsonb DEFAULT '{}'::jsonb NOT NULL,
    tax_id text DEFAULT ''::text NOT NULL,
    address text DEFAULT ''::text NOT NULL,
    email text DEFAULT ''::text NOT NULL,
    phone text DEFAULT ''::text NOT NULL,
    tax_office text DEFAULT ''::text NOT NULL,
    CONSTRAINT jarvis_cari_account_account_id_check CHECK ((account_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_cari_account_covers_object CHECK ((jsonb_typeof(covers) = 'object'::text)),
    CONSTRAINT jarvis_cari_account_name_check CHECK (((length(name) >= 1) AND (length(name) <= 160))),
    CONSTRAINT jarvis_cari_account_role_check CHECK ((role = ANY (ARRAY['customer'::text, 'supplier'::text, 'both'::text])))
);


ALTER TABLE core.jarvis_cari_account OWNER TO n8n;

--
-- Name: jarvis_cari_document; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_cari_document (
    document_id text NOT NULL,
    owner text NOT NULL,
    account_id text,
    entry_id text,
    source text NOT NULL,
    filename text NOT NULL,
    mime_type text NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    status text NOT NULL,
    extracted jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_cari_document_check CHECK (((entry_id IS NULL) OR (account_id IS NOT NULL))),
    CONSTRAINT jarvis_cari_document_content_check CHECK (((octet_length(content) >= 1) AND (octet_length(content) <= 8388608))),
    CONSTRAINT jarvis_cari_document_document_id_check CHECK ((document_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_cari_document_filename_check CHECK (((length(filename) >= 1) AND (length(filename) <= 160))),
    CONSTRAINT jarvis_cari_document_mime_type_check CHECK ((mime_type = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text, 'application/pdf'::text]))),
    CONSTRAINT jarvis_cari_document_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_cari_document_source_check CHECK ((source = ANY (ARRAY['invoice'::text, 'attachment'::text]))),
    CONSTRAINT jarvis_cari_document_status_check CHECK ((status = ANY (ARRAY['uploaded'::text, 'review'::text, 'posted'::text, 'rejected'::text])))
);


ALTER TABLE core.jarvis_cari_document OWNER TO n8n;

--
-- Name: jarvis_cari_draft; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_cari_draft (
    draft_id text NOT NULL,
    owner text NOT NULL,
    account_id text NOT NULL,
    body jsonb NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    posted_entry_id text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_cari_draft_check CHECK ((((status = 'draft'::text) AND (posted_entry_id IS NULL)) OR ((status = 'posted'::text) AND (posted_entry_id IS NOT NULL)))),
    CONSTRAINT jarvis_cari_draft_draft_id_check CHECK ((draft_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_cari_draft_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'posted'::text])))
);


ALTER TABLE core.jarvis_cari_draft OWNER TO n8n;

--
-- Name: jarvis_cari_entry; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_cari_entry (
    entry_id text NOT NULL,
    owner text NOT NULL,
    account_id text NOT NULL,
    request_id text NOT NULL,
    payload_hash text NOT NULL,
    document_date date NOT NULL,
    payload jsonb NOT NULL,
    signed_cents bigint NOT NULL,
    unknown_tax boolean NOT NULL,
    reverses text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_cari_entry_check CHECK (((reverses IS NULL) OR (reverses <> entry_id))),
    CONSTRAINT jarvis_cari_entry_entry_id_check CHECK ((entry_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_cari_entry_payload_hash_check CHECK ((payload_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_cari_entry_signed_cents_check CHECK ((abs(signed_cents) <= '1000000000000'::bigint))
);


ALTER TABLE core.jarvis_cari_entry OWNER TO n8n;

--
-- Name: jarvis_cari_source_event; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_cari_source_event (
    event_id text NOT NULL,
    owner text NOT NULL,
    source text NOT NULL,
    store_id text NOT NULL,
    object_id text NOT NULL,
    event_key text NOT NULL,
    source_updated_at timestamp with time zone NOT NULL,
    payload_hash text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_cari_source_event_event_id_check CHECK ((event_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_cari_source_event_event_key_check CHECK (((length(event_key) >= 1) AND (length(event_key) <= 160))),
    CONSTRAINT jarvis_cari_source_event_object_id_check CHECK (((length(object_id) >= 1) AND (length(object_id) <= 160))),
    CONSTRAINT jarvis_cari_source_event_payload_hash_check CHECK ((payload_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_cari_source_event_source_check CHECK ((source = ANY (ARRAY['trendyol'::text, 'n11'::text, 'amazon'::text, 'hepsiburada'::text, 'wix'::text, 'basitkargo'::text, 'qnb_pos'::text]))),
    CONSTRAINT jarvis_cari_source_event_store_id_check CHECK (((length(store_id) >= 1) AND (length(store_id) <= 160)))
);


ALTER TABLE core.jarvis_cari_source_event OWNER TO n8n;

--
-- Name: jarvis_expense_dispatch; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_expense_dispatch (
    owner text NOT NULL,
    period text NOT NULL,
    part integer NOT NULL,
    status text NOT NULL,
    package_sha256 text NOT NULL,
    document_count integer NOT NULL,
    sent_at timestamp with time zone,
    error text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_expense_dispatch_document_count_check CHECK ((document_count >= 0)),
    CONSTRAINT jarvis_expense_dispatch_package_sha256_check CHECK ((package_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_expense_dispatch_part_check CHECK ((part > 0)),
    CONSTRAINT jarvis_expense_dispatch_period_check CHECK ((period ~ '^[0-9]{4}-[0-9]{2}$'::text)),
    CONSTRAINT jarvis_expense_dispatch_status_check CHECK ((status = ANY (ARRAY['sending'::text, 'sent'::text, 'failed'::text])))
);


ALTER TABLE core.jarvis_expense_dispatch OWNER TO n8n;

--
-- Name: jarvis_expense_document; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_expense_document (
    document_id text NOT NULL,
    owner text NOT NULL,
    kind text NOT NULL,
    company text NOT NULL,
    origin text NOT NULL,
    source_message_id text DEFAULT ''::text NOT NULL,
    source_attachment_id text DEFAULT ''::text NOT NULL,
    filename text NOT NULL,
    mime_type text NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    document_date date,
    supplier text DEFAULT ''::text NOT NULL,
    buyer text DEFAULT ''::text NOT NULL,
    invoice_number text DEFAULT ''::text NOT NULL,
    currency text DEFAULT 'TRY'::text NOT NULL,
    gross_cents bigint,
    tax_cents bigint,
    note text DEFAULT ''::text NOT NULL,
    extracted jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'uploaded'::text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_expense_document_check CHECK ((((kind = 'receipt'::text) AND (company = 'common'::text)) OR ((kind = 'invoice'::text) AND (company <> 'common'::text)))),
    CONSTRAINT jarvis_expense_document_company_check CHECK ((company = ANY (ARRAY['common'::text, 'lemos'::text, 'moy'::text, 'unknown'::text]))),
    CONSTRAINT jarvis_expense_document_content_check CHECK (((octet_length(content) >= 1) AND (octet_length(content) <= 12582912))),
    CONSTRAINT jarvis_expense_document_currency_check CHECK ((currency ~ '^[A-Z]{3}$'::text)),
    CONSTRAINT jarvis_expense_document_document_id_check CHECK ((document_id ~ '^[0-9a-f]{32}$'::text)),
    CONSTRAINT jarvis_expense_document_filename_check CHECK (((length(filename) >= 1) AND (length(filename) <= 160))),
    CONSTRAINT jarvis_expense_document_gross_cents_check CHECK ((gross_cents >= 0)),
    CONSTRAINT jarvis_expense_document_kind_check CHECK ((kind = ANY (ARRAY['receipt'::text, 'invoice'::text]))),
    CONSTRAINT jarvis_expense_document_mime_type_check CHECK ((mime_type = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text, 'application/pdf'::text]))),
    CONSTRAINT jarvis_expense_document_origin_check CHECK ((origin = ANY (ARRAY['upload'::text, 'gmail'::text]))),
    CONSTRAINT jarvis_expense_document_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_expense_document_status_check CHECK ((status = ANY (ARRAY['uploaded'::text, 'review'::text, 'ready'::text, 'excluded'::text]))),
    CONSTRAINT jarvis_expense_document_tax_cents_check CHECK ((tax_cents >= 0))
);


ALTER TABLE core.jarvis_expense_document OWNER TO n8n;

--
-- Name: jarvis_personal_action; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_personal_action (
    action_id text NOT NULL,
    owner text NOT NULL,
    source_conversation text,
    kind text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    description text NOT NULL,
    risk_level text NOT NULL,
    idempotency_key text NOT NULL,
    status text NOT NULL,
    approved_by text,
    external_id text,
    message text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT jarvis_personal_action_kind_check CHECK ((kind = ANY (ARRAY['calendar.create'::text, 'gmail.send'::text, 'drive.upload'::text]))),
    CONSTRAINT jarvis_personal_action_payload_hash_check CHECK ((payload_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT jarvis_personal_action_risk_level_check CHECK ((risk_level = ANY (ARRAY['MEDIUM'::text, 'HIGH'::text]))),
    CONSTRAINT jarvis_personal_action_status_check CHECK ((status = ANY (ARRAY['AWAITING_APPROVAL'::text, 'RUNNING'::text, 'COMPLETED'::text, 'FAILED'::text, 'DENIED'::text, 'EXPIRED'::text, 'UNCERTAIN'::text])))
);


ALTER TABLE core.jarvis_personal_action OWNER TO n8n;

--
-- Name: jarvis_personal_action_event; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jarvis_personal_action_event (
    event_id bigint NOT NULL,
    action_id text NOT NULL,
    from_status text,
    to_status text NOT NULL,
    actor text NOT NULL,
    note text DEFAULT ''::text NOT NULL,
    at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);


ALTER TABLE core.jarvis_personal_action_event OWNER TO n8n;

--
-- Name: jarvis_personal_action_event_event_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.jarvis_personal_action_event ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME core.jarvis_personal_action_event_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: jarvis_task_state; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.jarvis_task_state (
    task_id bigint NOT NULL,
    state_json jsonb NOT NULL,
    version bigint DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT jarvis_task_state_state_json_check CHECK ((jsonb_typeof(state_json) = 'object'::text)),
    CONSTRAINT jarvis_task_state_version_check CHECK ((version > 0))
);


ALTER TABLE core.jarvis_task_state OWNER TO function_owner;

--
-- Name: jeton_otorite; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.jeton_otorite (
    jeton_adi text NOT NULL,
    amac text NOT NULL,
    izinler text[],
    paid_media_yetkisi boolean DEFAULT false NOT NULL,
    durum text DEFAULT 'ACTIVE'::text NOT NULL,
    dogrulama_zamani timestamp with time zone,
    dogrulama_yontemi text,
    not_ text
);


ALTER TABLE core.jeton_otorite OWNER TO n8n;

--
-- Name: kademe_denemesi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kademe_denemesi (
    id bigint NOT NULL,
    ts timestamp with time zone NOT NULL,
    uc text NOT NULL,
    kademe text,
    model text,
    sonuc text NOT NULL,
    gecikme_ms numeric,
    gerekce text,
    deneme integer,
    escalate boolean,
    is_anahtari text,
    kayit_hash text NOT NULL,
    aktarildi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.kademe_denemesi OWNER TO n8n;

--
-- Name: kademe_denemesi_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.kademe_denemesi_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.kademe_denemesi_id_seq OWNER TO n8n;

--
-- Name: kademe_denemesi_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.kademe_denemesi_id_seq OWNED BY core.kademe_denemesi.id;


--
-- Name: kanal_nabiz; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kanal_nabiz (
    kanal text NOT NULL,
    son_basarili timestamp with time zone,
    son_deneme timestamp with time zone,
    ardisik_hata integer DEFAULT 0 NOT NULL,
    son_hata text,
    son_siparis_sayisi integer,
    etkin boolean DEFAULT true NOT NULL,
    alarm_verildi timestamp with time zone
);


ALTER TABLE core.kanal_nabiz OWNER TO n8n;

--
-- Name: kanit_anlik; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kanit_anlik (
    anlik_id bigint NOT NULL,
    alindi timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    surum text NOT NULL,
    pencere_7 jsonb NOT NULL,
    pencere_30 jsonb NOT NULL,
    urun jsonb NOT NULL,
    kanal jsonb NOT NULL,
    konusma jsonb NOT NULL,
    veri_kalitesi jsonb NOT NULL,
    eksik_kaynak jsonb NOT NULL,
    kanit_puani integer NOT NULL,
    kanit_sinifi text NOT NULL
);


ALTER TABLE core.kanit_anlik OWNER TO n8n;

--
-- Name: kanit_anlik_anlik_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.kanit_anlik_anlik_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.kanit_anlik_anlik_id_seq OWNER TO n8n;

--
-- Name: kanit_anlik_anlik_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.kanit_anlik_anlik_id_seq OWNED BY core.kanit_anlik.anlik_id;


--
-- Name: karar; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar (
    karar_id bigint NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    karar_tipi text NOT NULL,
    urun text,
    kanal text,
    oneri text NOT NULL,
    anlik_id bigint NOT NULL,
    kanit_kalitesi text NOT NULL,
    beklenen_etki text,
    risk text,
    yanlislama_kosulu text NOT NULL,
    durum text DEFAULT 'PROPOSED'::text NOT NULL,
    idempotency_key text NOT NULL,
    fixture boolean DEFAULT false NOT NULL,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    ustunu_alan bigint,
    gecersizlik_nedeni text,
    CONSTRAINT karar_durum_check CHECK ((durum = ANY (ARRAY['PROPOSED'::text, 'APPROVED'::text, 'REJECTED'::text, 'DEFERRED'::text, 'EXECUTED'::text, 'MEASURING'::text, 'CONCLUDED'::text, 'CANCELLED'::text]))),
    CONSTRAINT karar_kanit_kalitesi_check CHECK ((kanit_kalitesi = ANY (ARRAY['LOW'::text, 'MEDIUM'::text, 'HIGH'::text]))),
    CONSTRAINT karar_karar_tipi_check CHECK ((karar_tipi = ANY (ARRAY['PRODUCT_PRIORITY'::text, 'MEDIA_BUDGET'::text, 'OFFER_TEST'::text, 'CREATIVE_TEST'::text, 'CRO_CHANGE'::text, 'AUDIENCE_TEST'::text, 'CRM_ACTION'::text])))
);


ALTER TABLE core.karar OWNER TO n8n;

--
-- Name: karar_aksiyon; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar_aksiyon (
    aksiyon_id bigint NOT NULL,
    karar_id bigint NOT NULL,
    aksiyon_tipi text NOT NULL,
    aciklama text NOT NULL,
    uygulandi timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    uygulayan text NOT NULL,
    dis_referans text,
    onceki_durum text,
    sonraki_durum text,
    CONSTRAINT karar_aksiyon_aksiyon_tipi_check CHECK ((aksiyon_tipi = ANY (ARRAY['budget_changed'::text, 'campaign_paused'::text, 'campaign_launched'::text, 'creative_launched'::text, 'landing_page_changed'::text, 'offer_changed'::text, 'price_changed'::text, 'crm_message_sent'::text, 'no_action'::text])))
);


ALTER TABLE core.karar_aksiyon OWNER TO n8n;

--
-- Name: karar_aksiyon_aksiyon_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.karar_aksiyon_aksiyon_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.karar_aksiyon_aksiyon_id_seq OWNER TO n8n;

--
-- Name: karar_aksiyon_aksiyon_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.karar_aksiyon_aksiyon_id_seq OWNED BY core.karar_aksiyon.aksiyon_id;


--
-- Name: karar_insan; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar_insan (
    karar_id bigint NOT NULL,
    karar text NOT NULL,
    karar_zamani timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    karar_notu text,
    onaylayan text NOT NULL,
    CONSTRAINT karar_insan_karar_check CHECK ((karar = ANY (ARRAY['APPROVE'::text, 'REJECT'::text, 'DEFER'::text, 'MODIFY'::text])))
);


ALTER TABLE core.karar_insan OWNER TO n8n;

--
-- Name: karar_kanit; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar_kanit (
    karar_id bigint NOT NULL,
    bulgu_id bigint NOT NULL
);


ALTER TABLE core.karar_kanit OWNER TO n8n;

--
-- Name: karar_karar_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.karar_karar_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.karar_karar_id_seq OWNER TO n8n;

--
-- Name: karar_karar_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.karar_karar_id_seq OWNED BY core.karar.karar_id;


--
-- Name: karar_red_team; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar_red_team (
    inceleme_id bigint NOT NULL,
    karar_id bigint NOT NULL,
    sonuc text NOT NULL,
    itiraz_tipi text,
    gerekce text NOT NULL,
    kanit_referansi text,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT karar_red_team_sonuc_check CHECK ((sonuc = ANY (ARRAY['SUPPORT'::text, 'CHALLENGE'::text, 'INSUFFICIENT_EVIDENCE'::text])))
);


ALTER TABLE core.karar_red_team OWNER TO n8n;

--
-- Name: karar_red_team_inceleme_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.karar_red_team_inceleme_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.karar_red_team_inceleme_id_seq OWNER TO n8n;

--
-- Name: karar_red_team_inceleme_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.karar_red_team_inceleme_id_seq OWNED BY core.karar_red_team.inceleme_id;


--
-- Name: karar_sonuc; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.karar_sonuc (
    karar_id bigint NOT NULL,
    olcum_baslangic date,
    olcum_bitis date,
    ana_metrik text NOT NULL,
    baz_deger numeric,
    gozlenen_deger numeric,
    mutlak_degisim numeric GENERATED ALWAYS AS ((gozlenen_deger - baz_deger)) STORED,
    goreli_degisim numeric,
    veri_kalitesi text NOT NULL,
    orneklem integer,
    sonuc_durumu text NOT NULL,
    yanlislandi text DEFAULT 'unknown'::text NOT NULL,
    uygunluk_gerekcesi text,
    kapatan text,
    kapanis timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT karar_sonuc_sonuc_durumu_check CHECK ((sonuc_durumu = ANY (ARRAY['POSITIVE'::text, 'NEGATIVE'::text, 'INCONCLUSIVE'::text, 'NOT_MEASURABLE'::text]))),
    CONSTRAINT karar_sonuc_veri_kalitesi_check CHECK ((veri_kalitesi = ANY (ARRAY['SUCCESS'::text, 'NO_DATA'::text, 'PARTIAL'::text, 'FAILED'::text]))),
    CONSTRAINT karar_sonuc_yanlislandi_check CHECK ((yanlislandi = ANY (ARRAY['true'::text, 'false'::text, 'unknown'::text])))
);


ALTER TABLE core.karar_sonuc OWNER TO n8n;

--
-- Name: kargo_karar; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kargo_karar (
    karar_id bigint NOT NULL,
    siparis_id text NOT NULL,
    tasiyici text NOT NULL,
    gosterilen_ucret numeric,
    karsi_odemeli boolean DEFAULT false NOT NULL,
    karsi_odeme_tutari numeric,
    karar text NOT NULL,
    barkod text,
    hata text,
    veren text NOT NULL,
    verildi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT kargo_karar_durum CHECK ((karar = ANY (ARRAY['ISTENDI'::text, 'ONAYLANDI'::text, 'HATA'::text]))),
    CONSTRAINT kargo_karar_kapida CHECK (((NOT karsi_odemeli) OR ((karsi_odeme_tutari IS NOT NULL) AND (karsi_odeme_tutari > (0)::numeric)))),
    CONSTRAINT kargo_karar_ucret CHECK (((gosterilen_ucret IS NULL) OR (gosterilen_ucret >= (0)::numeric)))
);


ALTER TABLE core.kargo_karar OWNER TO n8n;

--
-- Name: kargo_karar_karar_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.kargo_karar_karar_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.kargo_karar_karar_id_seq OWNER TO n8n;

--
-- Name: kargo_karar_karar_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.kargo_karar_karar_id_seq OWNED BY core.kargo_karar.karar_id;


--
-- Name: katalog_not; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.katalog_not (
    not_id bigint NOT NULL,
    urun_slug text NOT NULL,
    hedef_anahtari text,
    ziyaret_id bigint,
    ilgi text,
    not_metni text,
    giren text NOT NULL,
    girildi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT katalog_not_bos_ck CHECK (((ilgi IS NOT NULL) OR (COALESCE(btrim(not_metni), ''::text) <> ''::text))),
    CONSTRAINT katalog_not_ilgi_ck CHECK (((ilgi IS NULL) OR (ilgi = ANY (ARRAY['YOK'::text, 'SORDU'::text, 'ILGILENDI'::text, 'NUMUNE'::text, 'SIPARIS_SOZU'::text]))))
);


ALTER TABLE core.katalog_not OWNER TO n8n;

--
-- Name: katalog_not_not_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.katalog_not_not_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.katalog_not_not_id_seq OWNER TO n8n;

--
-- Name: katalog_not_not_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.katalog_not_not_id_seq OWNED BY core.katalog_not.not_id;


--
-- Name: kreatif_itiraz; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kreatif_itiraz (
    itiraz_id bigint NOT NULL,
    parti text NOT NULL,
    dosya text,
    konu text NOT NULL,
    aciklama text NOT NULL,
    muhatap text NOT NULL,
    durum text DEFAULT 'ACIK'::text NOT NULL,
    cevap text,
    cevaplayan text,
    cevaplandi timestamp with time zone,
    acan text NOT NULL,
    acildi timestamp with time zone DEFAULT now() NOT NULL,
    kapatan text,
    kapandi timestamp with time zone,
    CONSTRAINT kreatif_itiraz_aciklama CHECK ((length(btrim(aciklama)) >= 8)),
    CONSTRAINT kreatif_itiraz_durum CHECK ((durum = ANY (ARRAY['ACIK'::text, 'CEVAPLANDI'::text, 'KAPANDI'::text, 'TEKRAR_ACILDI'::text]))),
    CONSTRAINT kreatif_itiraz_konu CHECK ((konu = ANY (ARRAY['LOGO'::text, 'URUN'::text, 'METIN'::text, 'MARKA'::text, 'MEVZUAT'::text, 'DIGER'::text])))
);


ALTER TABLE core.kreatif_itiraz OWNER TO n8n;

--
-- Name: kreatif_itiraz_itiraz_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.kreatif_itiraz_itiraz_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.kreatif_itiraz_itiraz_id_seq OWNER TO n8n;

--
-- Name: kreatif_itiraz_itiraz_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.kreatif_itiraz_itiraz_id_seq OWNED BY core.kreatif_itiraz.itiraz_id;


--
-- Name: kreatif_konsept; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.kreatif_konsept (
    konsept_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    amac_iletisim text NOT NULL,
    hedef_kitle text NOT NULL,
    istenen_tepki text NOT NULL,
    ana_mesaj text NOT NULL,
    ikincil_mesaj text,
    ad text NOT NULL,
    ana_fikir text NOT NULL,
    gorsel_metafor text NOT NULL,
    kompozisyon text NOT NULL,
    odak text NOT NULL,
    duygu text NOT NULL,
    urunle_iliski text NOT NULL,
    neden_durdurur text NOT NULL,
    p_marka_uyumu smallint NOT NULL,
    p_ozgunluk smallint NOT NULL,
    p_mesaj_netligi smallint NOT NULL,
    p_durdurma_gucu smallint NOT NULL,
    p_uretilebilirlik smallint NOT NULL,
    p_gorsel_olgunluk smallint NOT NULL,
    secildi boolean DEFAULT false NOT NULL,
    secim_gerekce text,
    ay_kamera text,
    ay_isik text,
    ay_malzeme text,
    ay_ortam text,
    ay_derinlik text,
    ay_negatif_alan text,
    ay_yerlesim text,
    ay_tipografi_alani text,
    ay_renk text,
    istem text,
    negatif_istem text,
    ozelestiri jsonb,
    ozelestiri_sonuc text,
    uretim_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT konsept_ay_ck CHECK (((NOT secildi) OR ((COALESCE(btrim(ay_kamera), ''::text) <> ''::text) AND (COALESCE(btrim(ay_isik), ''::text) <> ''::text) AND (COALESCE(btrim(ay_negatif_alan), ''::text) <> ''::text) AND (COALESCE(btrim(ay_tipografi_alani), ''::text) <> ''::text) AND (COALESCE(btrim(secim_gerekce), ''::text) <> ''::text)))),
    CONSTRAINT konsept_ozelestiri_ck CHECK (((ozelestiri_sonuc IS NULL) OR (ozelestiri_sonuc = ANY (ARRAY['KABUL'::text, 'YENIDEN'::text, 'TERK'::text])))),
    CONSTRAINT kreatif_konsept_p_durdurma_gucu_check CHECK (((p_durdurma_gucu >= 1) AND (p_durdurma_gucu <= 5))),
    CONSTRAINT kreatif_konsept_p_gorsel_olgunluk_check CHECK (((p_gorsel_olgunluk >= 1) AND (p_gorsel_olgunluk <= 5))),
    CONSTRAINT kreatif_konsept_p_marka_uyumu_check CHECK (((p_marka_uyumu >= 1) AND (p_marka_uyumu <= 5))),
    CONSTRAINT kreatif_konsept_p_mesaj_netligi_check CHECK (((p_mesaj_netligi >= 1) AND (p_mesaj_netligi <= 5))),
    CONSTRAINT kreatif_konsept_p_ozgunluk_check CHECK (((p_ozgunluk >= 1) AND (p_ozgunluk <= 5))),
    CONSTRAINT kreatif_konsept_p_uretilebilirlik_check CHECK (((p_uretilebilirlik >= 1) AND (p_uretilebilirlik <= 5)))
);


ALTER TABLE core.kreatif_konsept OWNER TO n8n;

--
-- Name: kreatif_konsept_konsept_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.kreatif_konsept_konsept_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.kreatif_konsept_konsept_id_seq OWNER TO n8n;

--
-- Name: kreatif_konsept_konsept_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.kreatif_konsept_konsept_id_seq OWNED BY core.kreatif_konsept.konsept_id;


--
-- Name: lead; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.lead (
    lead_id bigint NOT NULL,
    kaynak text NOT NULL,
    kaynak_kimlik text NOT NULL,
    segment text NOT NULL,
    il text NOT NULL,
    ilce text,
    ad text NOT NULL,
    telefon text,
    site text,
    adres text,
    enlem double precision,
    boylam double precision,
    temas_edilebilir boolean GENERATED ALWAYS AS ((telefon IS NOT NULL)) STORED,
    iys_durumu text DEFAULT 'SORULMADI'::text NOT NULL,
    iys_tarih timestamp with time zone,
    toplandi timestamp with time zone DEFAULT now() NOT NULL,
    saklama_sonu date NOT NULL,
    notlar jsonb DEFAULT '{}'::jsonb NOT NULL,
    yakin_saglik_500m integer,
    yakin_rakip_200m integer,
    yakin_guzellik_1km integer,
    zenginlestirildi timestamp with time zone,
    CONSTRAINT lead_ad_check CHECK ((length(btrim(ad)) > 1)),
    CONSTRAINT lead_iys_durumu_check CHECK ((iys_durumu = ANY (ARRAY['SORULMADI'::text, 'ONAYLI'::text, 'RET'::text]))),
    CONSTRAINT lead_kaynak_check CHECK ((kaynak = ANY (ARRAY['osm'::text, 'places'::text, 'elle'::text])))
);


ALTER TABLE core.lead OWNER TO n8n;

--
-- Name: lead_lead_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.lead_lead_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.lead_lead_id_seq OWNER TO n8n;

--
-- Name: lead_lead_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.lead_lead_id_seq OWNED BY core.lead.lead_id;


--
-- Name: maliyet_bileseni; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.maliyet_bileseni (
    bilesen_id bigint NOT NULL,
    bilesen text NOT NULL,
    uygulama text NOT NULL,
    deger numeric,
    para_birimi text DEFAULT 'TRY'::text NOT NULL,
    kdv_tabani text DEFAULT 'BILINMIYOR'::text NOT NULL,
    kanit_sinifi text NOT NULL,
    kapsam text NOT NULL,
    kaynak text NOT NULL,
    gerekce text,
    gecerli_baslangic timestamp with time zone DEFAULT '2025-12-31 21:00:00+00'::timestamp with time zone NOT NULL,
    gecerli_bitis timestamp with time zone,
    son_dogrulama timestamp with time zone,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    kritiklik text DEFAULT 'CRITICAL'::text NOT NULL,
    katki_yonu text DEFAULT 'BILINMIYOR'::text NOT NULL,
    CONSTRAINT maliyet_bileseni_kanit_sinifi_check CHECK ((kanit_sinifi = ANY (ARRAY['MEASURED'::text, 'BUSINESS_INPUT'::text, 'DERIVED'::text, 'ESTIMATED'::text, 'UNKNOWN'::text, 'NOT_YET_KNOWN'::text, 'UNKNOWN_BUSINESS_INPUT_REQUIRED'::text]))),
    CONSTRAINT maliyet_bileseni_katki_yonu_check CHECK ((katki_yonu = ANY (ARRAY['AZALTIR'::text, 'ARTIRIR'::text, 'BILINMIYOR'::text]))),
    CONSTRAINT maliyet_bileseni_kdv_tabani_check CHECK ((kdv_tabani = ANY (ARRAY['KDV_HARIC'::text, 'KDV_DAHIL'::text, 'BILINMIYOR'::text, 'YOK'::text]))),
    CONSTRAINT maliyet_bileseni_kritiklik_check CHECK ((kritiklik = ANY (ARRAY['CRITICAL'::text, 'SECONDARY'::text]))),
    CONSTRAINT maliyet_bileseni_uygulama_check CHECK ((uygulama = ANY (ARRAY['SIPARIS_SABIT'::text, 'BIRIM_SABIT'::text, 'CIRO_YUZDE'::text])))
);


ALTER TABLE core.maliyet_bileseni OWNER TO n8n;

--
-- Name: maliyet_bileseni_bilesen_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.maliyet_bileseni_bilesen_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.maliyet_bileseni_bilesen_id_seq OWNER TO n8n;

--
-- Name: maliyet_bileseni_bilesen_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.maliyet_bileseni_bilesen_id_seq OWNED BY core.maliyet_bileseni.bilesen_id;


--
-- Name: medya_istegi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.medya_istegi (
    istek_no bigint NOT NULL,
    request_id uuid,
    uc text NOT NULL,
    uc_yolu text NOT NULL,
    tur text NOT NULL,
    govde jsonb NOT NULL,
    ham_istem text NOT NULL,
    istek_imzasi text NOT NULL,
    durum text DEFAULT 'GONDERILIYOR'::text NOT NULL,
    hata text,
    cikti_url text,
    yerel_dosya text,
    yerel_bayt bigint,
    tahmini_usd numeric(12,4),
    tahmini_kredi numeric(12,4),
    is_anahtari text,
    parti text,
    talep_eden text NOT NULL,
    yoklama_sayisi integer DEFAULT 0 NOT NULL,
    son_yoklama timestamp with time zone,
    insan_onayi boolean,
    onay_notu text,
    onaylayan text,
    onaylandi timestamp with time zone,
    olusturuldu timestamp with time zone DEFAULT now() NOT NULL,
    guncellendi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT medya_istegi_durum_check CHECK ((durum = ANY (ARRAY['GONDERILIYOR'::text, 'GONDERIM_BILINMIYOR'::text, 'REDDEDILDI'::text, 'queued'::text, 'in_progress'::text, 'completed'::text, 'failed'::text, 'nsfw'::text, 'canceled'::text, 'BEKLEME_ASILDI'::text]))),
    CONSTRAINT medya_istegi_tur_check CHECK ((tur = ANY (ARRAY['video'::text, 'gorsel'::text])))
);


ALTER TABLE core.medya_istegi OWNER TO n8n;

--
-- Name: medya_istegi_istek_no_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.medya_istegi_istek_no_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.medya_istegi_istek_no_seq OWNER TO n8n;

--
-- Name: medya_istegi_istek_no_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.medya_istegi_istek_no_seq OWNED BY core.medya_istegi.istek_no;


--
-- Name: meta_hesap_kayit; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.meta_hesap_kayit (
    hesap_id text NOT NULL,
    ad text,
    operasyonel_durum text NOT NULL,
    durum_kaynagi text NOT NULL,
    son_dogrulama timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    notlar text,
    CONSTRAINT meta_hesap_kayit_operasyonel_durum_check CHECK ((operasyonel_durum = ANY (ARRAY['ACTIVE'::text, 'INACTIVE_EXCLUDED'::text])))
);


ALTER TABLE core.meta_hesap_kayit OWNER TO n8n;

--
-- Name: mimari_ders; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.mimari_ders (
    ders_id bigint NOT NULL,
    kod text NOT NULL,
    baslik text NOT NULL,
    ders text NOT NULL,
    tetikleyen text NOT NULL,
    kanit text NOT NULL,
    sonuc text NOT NULL,
    kaydeden text NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    gecersiz_kilan bigint,
    gecersizlik_nedeni text
);


ALTER TABLE core.mimari_ders OWNER TO n8n;

--
-- Name: mimari_ders_ders_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.mimari_ders_ders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.mimari_ders_ders_id_seq OWNER TO n8n;

--
-- Name: mimari_ders_ders_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.mimari_ders_ders_id_seq OWNED BY core.mimari_ders.ders_id;


--
-- Name: model_kademe; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.model_kademe (
    is_anahtari text NOT NULL,
    kademe text NOT NULL,
    gerekce text NOT NULL,
    risk text DEFAULT 'IC'::text NOT NULL,
    atayan text NOT NULL,
    atandi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT model_kademe_gecerli CHECK ((kademe = ANY (ARRAY['hizli'::text, 'muhakeme'::text]))),
    CONSTRAINT model_kademe_gerekce CHECK ((length(btrim(gerekce)) >= 12)),
    CONSTRAINT model_kademe_risk CHECK ((risk = ANY (ARRAY['MUSTERIYE'::text, 'KARARA'::text, 'IC'::text])))
);


ALTER TABLE core.model_kademe OWNER TO n8n;

--
-- Name: pazar_bulgu; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.pazar_bulgu (
    bulgu_id bigint NOT NULL,
    kod text NOT NULL,
    seviye text NOT NULL,
    bulgu text NOT NULL,
    kaynak text NOT NULL,
    tarih text NOT NULL,
    yorum text,
    kaydeden text DEFAULT CURRENT_USER NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    departman text NOT NULL,
    CONSTRAINT pazar_bulgu_kaynak_dolu CHECK ((length(btrim(kaynak)) >= 3)),
    CONSTRAINT pazar_bulgu_metin_dolu CHECK ((length(btrim(bulgu)) >= 8)),
    CONSTRAINT pazar_bulgu_seviye_check CHECK ((seviye = ANY (ARRAY['FACT'::text, 'INTERPRETATION'::text, 'HYPOTHESIS'::text, 'NOT_CONNECTED'::text])))
);


ALTER TABLE core.pazar_bulgu OWNER TO n8n;

--
-- Name: pazar_bulgu_bulgu_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.pazar_bulgu ALTER COLUMN bulgu_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.pazar_bulgu_bulgu_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: pazaryeri_siparis; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.pazaryeri_siparis (
    id bigint NOT NULL,
    kanal text NOT NULL,
    siparis_no text NOT NULL,
    paket_no text,
    durum text NOT NULL,
    siparis_zamani timestamp with time zone,
    tutar numeric(12,2),
    para_birimi text DEFAULT 'TRY'::text,
    musteri_ad text,
    sehir text,
    kalem_sayisi integer,
    kalemler jsonb DEFAULT '[]'::jsonb NOT NULL,
    ham jsonb DEFAULT '{}'::jsonb NOT NULL,
    ilk_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    son_guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    kaynak text DEFAULT 'api'::text NOT NULL
);


ALTER TABLE core.pazaryeri_siparis OWNER TO n8n;

--
-- Name: pazaryeri_siparis_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.pazaryeri_siparis_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.pazaryeri_siparis_id_seq OWNER TO n8n;

--
-- Name: pazaryeri_siparis_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.pazaryeri_siparis_id_seq OWNED BY core.pazaryeri_siparis.id;


--
-- Name: platform; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.platform (
    kod text NOT NULL,
    ad text NOT NULL,
    aktif boolean DEFAULT false NOT NULL,
    yazma_izni boolean DEFAULT false NOT NULL,
    fiyat_otoritesi boolean DEFAULT false NOT NULL,
    not_ text,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    komisyon_yuzde numeric,
    kdv_yuzde numeric DEFAULT 20 NOT NULL,
    kargo_bedeli numeric DEFAULT 0 NOT NULL,
    CONSTRAINT platform_kargo_bedeli_check CHECK ((kargo_bedeli >= (0)::numeric)),
    CONSTRAINT platform_kdv_yuzde_check CHECK ((kdv_yuzde >= (0)::numeric)),
    CONSTRAINT platform_komisyon_yuzde_check CHECK (((komisyon_yuzde >= (0)::numeric) AND (komisyon_yuzde < (100)::numeric)))
);


ALTER TABLE core.platform OWNER TO n8n;

--
-- Name: rapor_anlik; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.rapor_anlik (
    kayit_id bigint NOT NULL,
    rapor_gunu date NOT NULL,
    calisma_no integer NOT NULL,
    yazildi timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    metrik_surumu text NOT NULL,
    karar_hazir boolean,
    eksikler text,
    kapsama_json jsonb,
    metrikler jsonb NOT NULL
);


ALTER TABLE core.rapor_anlik OWNER TO n8n;

--
-- Name: rapor_anlik_kayit_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.rapor_anlik_kayit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.rapor_anlik_kayit_id_seq OWNER TO n8n;

--
-- Name: rapor_anlik_kayit_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.rapor_anlik_kayit_id_seq OWNED BY core.rapor_anlik.kayit_id;


--
-- Name: reklam_urun; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.reklam_urun (
    ad_id text NOT NULL,
    urun_id text,
    urun_adi text,
    kaynak text NOT NULL,
    gerekce text,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT reklam_urun_kaynak_check CHECK ((kaynak = ANY (ARRAY['TUREV'::text, 'ELLE'::text, 'YOK'::text])))
);


ALTER TABLE core.reklam_urun OWNER TO n8n;

--
-- Name: saha_bilgi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_bilgi (
    osm_tur text,
    osm_id bigint,
    ad text,
    brans text,
    telefon text,
    eposta text,
    ilgili_kisi text,
    notlar text,
    hedef_disi boolean DEFAULT false NOT NULL,
    giren text NOT NULL,
    girildi timestamp with time zone DEFAULT now() NOT NULL,
    hedef_anahtari text NOT NULL
);


ALTER TABLE core.saha_bilgi OWNER TO n8n;

--
-- Name: saha_brans_esleme; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_brans_esleme (
    kategori text NOT NULL,
    brans text NOT NULL
);


ALTER TABLE core.saha_brans_esleme OWNER TO n8n;

--
-- Name: saha_disla_kalip; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_disla_kalip (
    kalip text NOT NULL,
    neden text NOT NULL,
    ekleyen text DEFAULT 'sistem'::text NOT NULL,
    eklendi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.saha_disla_kalip OWNER TO n8n;

--
-- Name: saha_elle_nokta; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_elle_nokta (
    nokta_id bigint NOT NULL,
    ad text NOT NULL,
    tur text NOT NULL,
    brans text,
    enlem double precision NOT NULL,
    boylam double precision NOT NULL,
    telefon text,
    eposta text,
    website text,
    adres text,
    ilce text,
    ilgili_kisi text,
    notlar text,
    hedef_disi boolean DEFAULT false NOT NULL,
    konum_kaynagi text DEFAULT 'ELLE'::text NOT NULL,
    konum_dogruluk_m numeric,
    ekleyen text NOT NULL,
    eklendi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT saha_elle_nokta_konum_kaynagi_check CHECK ((konum_kaynagi = ANY (ARRAY['GPS'::text, 'HARITA'::text, 'ELLE'::text])))
);


ALTER TABLE core.saha_elle_nokta OWNER TO n8n;

--
-- Name: saha_elle_nokta_nokta_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.saha_elle_nokta_nokta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.saha_elle_nokta_nokta_id_seq OWNER TO n8n;

--
-- Name: saha_elle_nokta_nokta_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.saha_elle_nokta_nokta_id_seq OWNED BY core.saha_elle_nokta.nokta_id;


--
-- Name: saha_ilce_esleme; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_ilce_esleme (
    ham text NOT NULL,
    ilce text NOT NULL,
    cesit text NOT NULL
);


ALTER TABLE core.saha_ilce_esleme OWNER TO n8n;

--
-- Name: saha_konum; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_konum (
    konum_id bigint NOT NULL,
    kullanici text NOT NULL,
    ts timestamp with time zone DEFAULT now() NOT NULL,
    enlem double precision NOT NULL,
    boylam double precision NOT NULL,
    dogruluk_m numeric,
    hiz_m_s numeric,
    kaynak text DEFAULT 'TARAYICI'::text NOT NULL,
    rota_id bigint,
    CONSTRAINT saha_konum_kaynak_check CHECK ((kaynak = ANY (ARRAY['TARAYICI'::text, 'OWNTRACKS'::text])))
);


ALTER TABLE core.saha_konum OWNER TO n8n;

--
-- Name: saha_konum_konum_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.saha_konum_konum_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.saha_konum_konum_id_seq OWNER TO n8n;

--
-- Name: saha_konum_konum_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.saha_konum_konum_id_seq OWNED BY core.saha_konum.konum_id;


--
-- Name: saha_rota; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_rota (
    rota_id bigint NOT NULL,
    ad text NOT NULL,
    bolge text,
    baslangic_enlem double precision,
    baslangic_boylam double precision,
    baslangic_adi text,
    olusturan text NOT NULL,
    olusturuldu timestamp with time zone DEFAULT now() NOT NULL,
    planlanan_gun date
);


ALTER TABLE core.saha_rota OWNER TO n8n;

--
-- Name: saha_rota_durak; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_rota_durak (
    rota_id bigint NOT NULL,
    sira integer NOT NULL,
    osm_tur text NOT NULL,
    osm_id bigint NOT NULL,
    onceki_mesafe_m numeric,
    hedef_anahtari text
);


ALTER TABLE core.saha_rota_durak OWNER TO n8n;

--
-- Name: saha_rota_rota_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.saha_rota_rota_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.saha_rota_rota_id_seq OWNER TO n8n;

--
-- Name: saha_rota_rota_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.saha_rota_rota_id_seq OWNED BY core.saha_rota.rota_id;


--
-- Name: saha_ziyaret; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_ziyaret (
    ziyaret_id bigint NOT NULL,
    osm_tur text,
    osm_id bigint,
    ziyaret_at timestamp with time zone DEFAULT now() NOT NULL,
    giden text NOT NULL,
    sonuc text NOT NULL,
    not_metni text,
    siparis_ref text,
    enlem double precision,
    boylam double precision,
    konum_dogruluk_m numeric,
    nokta_id bigint,
    hedef_anahtari text NOT NULL,
    CONSTRAINT saha_ziyaret_sonuc_check CHECK ((sonuc = ANY (ARRAY['GORUSULDU'::text, 'KAPALI'::text, 'YETKILI_YOK'::text, 'ILGILENMEDI'::text, 'NUMUNE_BIRAKILDI'::text, 'SIPARIS_SOZU'::text, 'TEKRAR_GEL'::text])))
);


ALTER TABLE core.saha_ziyaret OWNER TO n8n;

--
-- Name: saha_ziyaret_foto; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.saha_ziyaret_foto (
    foto_id bigint NOT NULL,
    ziyaret_id bigint NOT NULL,
    dosya_yolu text NOT NULL,
    bayt integer NOT NULL,
    enlem double precision,
    boylam double precision,
    eklendi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.saha_ziyaret_foto OWNER TO n8n;

--
-- Name: saha_ziyaret_foto_foto_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.saha_ziyaret_foto_foto_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.saha_ziyaret_foto_foto_id_seq OWNER TO n8n;

--
-- Name: saha_ziyaret_foto_foto_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.saha_ziyaret_foto_foto_id_seq OWNED BY core.saha_ziyaret_foto.foto_id;


--
-- Name: saha_ziyaret_ziyaret_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.saha_ziyaret_ziyaret_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.saha_ziyaret_ziyaret_id_seq OWNER TO n8n;

--
-- Name: saha_ziyaret_ziyaret_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.saha_ziyaret_ziyaret_id_seq OWNED BY core.saha_ziyaret.ziyaret_id;


--
-- Name: sayfa_olcum; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.sayfa_olcum (
    url text NOT NULL,
    olcum_zamani timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    tur text NOT NULL,
    http_kodu integer,
    baslik text,
    baslik_uzunluk integer,
    meta_uzunluk integer,
    h1_adet integer,
    h1_metni text,
    kelime_sayisi integer,
    kanonik text,
    ham_bayt integer,
    js_calistirildi boolean DEFAULT false NOT NULL,
    robots_durumu text,
    sitemap_var boolean,
    jsonld_turleri text[],
    hreflang_sayisi integer,
    yonlendirme_zinciri integer
);


ALTER TABLE core.sayfa_olcum OWNER TO n8n;

--
-- Name: sayfa_urun; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.sayfa_urun (
    sayfa_yolu text NOT NULL,
    urun_id text,
    sayfa_rolu text NOT NULL,
    kaynak text NOT NULL,
    notlar text,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT sayfa_urun_sayfa_rolu_check CHECK ((sayfa_rolu = ANY (ARRAY['NATIVE_URUN'::text, 'OZEL_LANDING'::text, 'KAMPANYA_LANDING'::text, 'KATEGORI'::text, 'ANASAYFA'::text, 'SEPET'::text, 'ODEME'::text, 'ICERIK'::text, 'DIGER'::text])))
);


ALTER TABLE core.sayfa_urun OWNER TO n8n;

--
-- Name: siparis_bildirim; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.siparis_bildirim (
    id bigint NOT NULL,
    siparis_id bigint NOT NULL,
    yol text NOT NULL,
    durum text NOT NULL,
    deneme integer DEFAULT 0 NOT NULL,
    dis_kimlik text,
    hata text,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE core.siparis_bildirim OWNER TO n8n;

--
-- Name: siparis_bildirim_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.siparis_bildirim_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.siparis_bildirim_id_seq OWNER TO n8n;

--
-- Name: siparis_bildirim_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.siparis_bildirim_id_seq OWNED BY core.siparis_bildirim.id;


--
-- Name: siparis_teyit; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.siparis_teyit (
    siparis_no bigint NOT NULL,
    siparis_id text NOT NULL,
    yol text NOT NULL,
    sablon text NOT NULL,
    durum text NOT NULL,
    sebep text,
    wamid text,
    telefon_son4 text,
    deneme integer DEFAULT 0 NOT NULL,
    ilk_deneme timestamp with time zone DEFAULT now() NOT NULL,
    son_deneme timestamp with time zone DEFAULT now() NOT NULL,
    onay_zaman timestamp with time zone,
    onay_metni text,
    kargo_durum text,
    kargo_siparis_id text,
    barkod text,
    kargo_sebep text,
    kargo_deneme integer DEFAULT 0 NOT NULL
);


ALTER TABLE core.siparis_teyit OWNER TO n8n;

--
-- Name: source_authority; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.source_authority (
    alan text NOT NULL,
    authority text NOT NULL,
    mirror text,
    freshness text,
    current_connection text NOT NULL,
    gap text,
    dogrulama_zamani timestamp with time zone,
    dogrulama_yontemi text,
    notlar text,
    CONSTRAINT source_authority_current_connection_check CHECK ((current_connection = ANY (ARRAY['CONNECTED'::text, 'PARTIAL'::text, 'SOURCE_NOT_CONNECTED'::text, 'NONE'::text, 'UNKNOWN'::text, 'MANUAL_CONTROLLED_INPUT'::text, 'OPTIONAL_RECONCILIATION_GAP'::text, 'BLOCKED_BY_EXTERNAL_CREDENTIAL'::text])))
);


ALTER TABLE core.source_authority OWNER TO n8n;

--
-- Name: stok_sayim; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.stok_sayim (
    sayim_id bigint NOT NULL,
    urun_adi text NOT NULL,
    adet integer NOT NULL,
    nerede text DEFAULT 'DEPO'::text NOT NULL,
    giren text NOT NULL,
    sayim_zamani timestamp with time zone DEFAULT now() NOT NULL,
    not_metni text,
    CONSTRAINT stok_sayim_adet CHECK ((adet >= 0))
);


ALTER TABLE core.stok_sayim OWNER TO n8n;

--
-- Name: stok_sayim_sayim_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.stok_sayim_sayim_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.stok_sayim_sayim_id_seq OWNER TO n8n;

--
-- Name: stok_sayim_sayim_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.stok_sayim_sayim_id_seq OWNED BY core.stok_sayim.sayim_id;


--
-- Name: tarayici_isi; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.tarayici_isi (
    is_id bigint NOT NULL,
    olusturuldu timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guncellendi timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    isteyen text NOT NULL,
    hedef text NOT NULL,
    istem text NOT NULL,
    girdi_dosyalari jsonb DEFAULT '[]'::jsonb NOT NULL,
    durum text DEFAULT 'BEKLIYOR'::text NOT NULL,
    kiralayan text,
    kira_zamani timestamp with time zone,
    kira_sonu timestamp with time zone,
    kira_jetonu uuid,
    deneme integer DEFAULT 0 NOT NULL,
    en_cok_deneme integer DEFAULT 2 NOT NULL,
    sonuc_metin text,
    sonuc_dosyalari jsonb DEFAULT '[]'::jsonb NOT NULL,
    ekran_goruntusu text,
    hata text,
    uyum_durumu text,
    slug text,
    idempotency_key text NOT NULL,
    CONSTRAINT tarayici_isi_deneme_check CHECK ((deneme >= 0)),
    CONSTRAINT tarayici_isi_durum_check CHECK ((durum = ANY (ARRAY['BEKLIYOR'::text, 'CALISIYOR'::text, 'BITTI'::text, 'SUNULDU'::text, 'HATA'::text, 'INSAN_GEREKLI'::text]))),
    CONSTRAINT tarayici_isi_en_cok_deneme_check CHECK ((en_cok_deneme > 0)),
    CONSTRAINT tarayici_isi_girdi_dosyalari_check CHECK ((jsonb_typeof(girdi_dosyalari) = 'array'::text)),
    CONSTRAINT tarayici_isi_hedef_check CHECK ((hedef = ANY (ARRAY['chatgpt_image'::text, 'chatgpt_chat'::text, 'claude_chat'::text]))),
    CONSTRAINT tarayici_isi_idempotency_key_check CHECK (((btrim(idempotency_key) <> ''::text) AND (length(idempotency_key) <= 200))),
    CONSTRAINT tarayici_isi_istem_check CHECK (((btrim(istem) <> ''::text) AND (length(istem) <= 8000))),
    CONSTRAINT tarayici_isi_isteyen_check CHECK (((btrim(isteyen) <> ''::text) AND (length(isteyen) <= 80))),
    CONSTRAINT tarayici_isi_slug_check CHECK (((slug IS NULL) OR (slug ~ '^[A-Za-z0-9_.-]{1,80}$'::text))),
    CONSTRAINT tarayici_isi_sonuc_dosyalari_check CHECK ((jsonb_typeof(sonuc_dosyalari) = 'array'::text)),
    CONSTRAINT tarayici_isi_uyum_durumu_check CHECK ((uyum_durumu = ANY (ARRAY['GECTI'::text, 'BLOKLU'::text])))
);


ALTER TABLE core.tarayici_isi OWNER TO function_owner;

--
-- Name: tarayici_isi_is_id_seq; Type: SEQUENCE; Schema: core; Owner: function_owner
--

CREATE SEQUENCE core.tarayici_isi_is_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.tarayici_isi_is_id_seq OWNER TO function_owner;

--
-- Name: tarayici_isi_is_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: function_owner
--

ALTER SEQUENCE core.tarayici_isi_is_id_seq OWNED BY core.tarayici_isi.is_id;


--
-- Name: tarayici_nabiz; Type: TABLE; Schema: core; Owner: function_owner
--

CREATE TABLE core.tarayici_nabiz (
    worker text NOT NULL,
    son_gorulme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    ayrinti jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT tarayici_nabiz_ayrinti_check CHECK ((jsonb_typeof(ayrinti) = 'object'::text)),
    CONSTRAINT tarayici_nabiz_worker_check CHECK (((btrim(worker) <> ''::text) AND (length(worker) <= 80)))
);


ALTER TABLE core.tarayici_nabiz OWNER TO function_owner;

--
-- Name: tasarim_isi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.tasarim_isi (
    is_id bigint NOT NULL,
    is_turu text NOT NULL,
    sablon_id bigint,
    isteyen text NOT NULL,
    istek text NOT NULL,
    veri jsonb DEFAULT '{}'::jsonb NOT NULL,
    canva_tasarim text,
    disa_aktarim text,
    durum text DEFAULT 'URETILDI'::text NOT NULL,
    denetim jsonb DEFAULT '{}'::jsonb NOT NULL,
    maliyet_tl numeric(10,4) DEFAULT 0 NOT NULL,
    onay text,
    onaylayan text,
    onaylandi timestamp with time zone,
    red_sebebi text,
    uretildi timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tasarim_isi_durum_izinli CHECK ((durum = ANY (ARRAY['URETILDI'::text, 'BASARISIZ'::text, 'DENETIMDE'::text, 'ARSIVLENDI'::text]))),
    CONSTRAINT tasarim_isi_onay_izinli CHECK (((onay IS NULL) OR (onay = ANY (ARRAY['ONAYLANDI'::text, 'REDDEDILDI'::text])))),
    CONSTRAINT tasarim_isi_red_sebepli CHECK (((onay IS DISTINCT FROM 'REDDEDILDI'::text) OR (length(TRIM(BOTH FROM COALESCE(red_sebebi, ''::text))) >= 8)))
);


ALTER TABLE core.tasarim_isi OWNER TO n8n;

--
-- Name: tasarim_isi_is_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.tasarim_isi_is_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.tasarim_isi_is_id_seq OWNER TO n8n;

--
-- Name: tasarim_isi_is_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.tasarim_isi_is_id_seq OWNED BY core.tasarim_isi.is_id;


--
-- Name: tasarim_sablon; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.tasarim_sablon (
    sablon_id bigint NOT NULL,
    is_turu text NOT NULL,
    ad text NOT NULL,
    canva_id text,
    alan_haritasi jsonb DEFAULT '{}'::jsonb NOT NULL,
    en integer,
    boy integer,
    gerekce text NOT NULL,
    aktif boolean DEFAULT true NOT NULL,
    ekleyen text NOT NULL,
    eklendi timestamp with time zone DEFAULT now() NOT NULL,
    sablon_kodu text,
    kategori text,
    platform text,
    bicim text DEFAULT 'PNG'::text NOT NULL,
    en_mm numeric(8,2),
    boy_mm numeric(8,2),
    dpi integer,
    beklenen_alanlar jsonb DEFAULT '[]'::jsonb NOT NULL,
    marka_kurallari text,
    mevzuat_kurallari text,
    surum integer DEFAULT 1 NOT NULL,
    durum text DEFAULT 'TASLAK'::text NOT NULL,
    motor text DEFAULT 'canva'::text NOT NULL,
    onay_zorunlu boolean DEFAULT true NOT NULL,
    faz integer,
    CONSTRAINT tasarim_sablon_canva_id_bicim CHECK (((canva_id IS NULL) OR (canva_id ~ '^[A-Za-z0-9_-]{6,30}$'::text))),
    CONSTRAINT tasarim_sablon_durum_izinli CHECK ((durum = ANY (ARRAY['TASLAK'::text, 'HAZIR'::text, 'ARSIVDE'::text]))),
    CONSTRAINT tasarim_sablon_gerekce_dolu CHECK ((length(TRIM(BOTH FROM gerekce)) >= 12)),
    CONSTRAINT tasarim_sablon_hazir_tasarimli CHECK (((durum <> 'HAZIR'::text) OR (canva_id IS NOT NULL)))
);


ALTER TABLE core.tasarim_sablon OWNER TO n8n;

--
-- Name: tasarim_sablon_sablon_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.tasarim_sablon_sablon_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.tasarim_sablon_sablon_id_seq OWNER TO n8n;

--
-- Name: tasarim_sablon_sablon_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.tasarim_sablon_sablon_id_seq OWNED BY core.tasarim_sablon.sablon_id;


--
-- Name: urun_bayi_fiyat; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_bayi_fiyat (
    urun_slug text NOT NULL,
    bayi_fiyat numeric(12,2),
    para text DEFAULT 'TRY'::text NOT NULL,
    en_az_adet integer,
    gecerli_bas date DEFAULT CURRENT_DATE NOT NULL,
    giren text NOT NULL,
    girildi timestamp with time zone DEFAULT now() NOT NULL,
    psf numeric(12,2),
    isk30_haric numeric(12,2),
    isk30_dahil numeric(12,2),
    isk40_haric numeric(12,2),
    isk40_dahil numeric(12,2),
    trendyol numeric(12,2),
    barkod text,
    celiskili boolean DEFAULT false NOT NULL,
    celiski_notu text,
    kaynak text,
    barkod_celiskili boolean DEFAULT false NOT NULL,
    barkod_notu text,
    psf_kaynagi text,
    CONSTRAINT bayi_barkod_celiski_ck CHECK (((NOT barkod_celiskili) OR (COALESCE(btrim(barkod_notu), ''::text) <> ''::text))),
    CONSTRAINT bayi_celiski_ck CHECK (((NOT celiskili) OR (COALESCE(btrim(celiski_notu), ''::text) <> ''::text)))
);


ALTER TABLE core.urun_bayi_fiyat OWNER TO n8n;

--
-- Name: urun_fiyat_gercegi; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_fiyat_gercegi (
    urun_id text NOT NULL,
    base_price numeric,
    kampanya_fiyati numeric,
    fiyat_durumu text DEFAULT 'NORMAL'::text NOT NULL,
    kampanya_suresi text,
    kampanya_kaynagi text,
    kampanya_bitisi text,
    karsilastirma_izni text DEFAULT 'HAYIR'::text NOT NULL,
    gerekce text,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT urun_fiyat_gercegi_fiyat_durumu_check CHECK ((fiyat_durumu = ANY (ARRAY['NORMAL'::text, 'CAMPAIGN'::text, 'UNKNOWN'::text]))),
    CONSTRAINT urun_fiyat_gercegi_karsilastirma_izni_check CHECK ((karsilastirma_izni = ANY (ARRAY['EVET'::text, 'HAYIR'::text])))
);


ALTER TABLE core.urun_fiyat_gercegi OWNER TO n8n;

--
-- Name: urun_inci; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_inci (
    urun_anahtari text NOT NULL,
    urun_adi text,
    inci text,
    kaynak text,
    kaynak_tur text,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT urun_inci_bos_metin CHECK (((inci IS NULL) OR (length(btrim(inci)) > 0)))
);


ALTER TABLE core.urun_inci OWNER TO n8n;

--
-- Name: urun_maliyet; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_maliyet (
    maliyet_id bigint NOT NULL,
    urun_id text NOT NULL,
    maliyet numeric(14,2) NOT NULL,
    para_birimi text DEFAULT 'TRY'::text NOT NULL,
    gecerli_baslangic timestamp with time zone NOT NULL,
    gecerli_bitis timestamp with time zone,
    kaynak text NOT NULL,
    gerekce text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT urun_maliyet_kaynak_check CHECK ((kaynak = ANY (ARRAY['WIX'::text, 'ELLE'::text]))),
    CONSTRAINT urun_maliyet_maliyet_check CHECK ((maliyet > (0)::numeric))
);


ALTER TABLE core.urun_maliyet OWNER TO n8n;

--
-- Name: urun_maliyet_maliyet_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

ALTER TABLE core.urun_maliyet ALTER COLUMN maliyet_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME core.urun_maliyet_maliyet_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: urun_platform_fiyat; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_platform_fiyat (
    id bigint NOT NULL,
    urun_id text NOT NULL,
    platform_kod text NOT NULL,
    fiyat numeric NOT NULL,
    para_birimi text DEFAULT 'TRY'::text NOT NULL,
    yontem text NOT NULL,
    toplu_islem_id uuid,
    onay_action_id text,
    gerekce text,
    gecerli_baslangic timestamp with time zone DEFAULT now() NOT NULL,
    gecerli_bitis timestamp with time zone,
    kaydeden text NOT NULL,
    kayit_zamani timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT urun_platform_fiyat_fiyat_check CHECK ((fiyat > (0)::numeric)),
    CONSTRAINT urun_platform_fiyat_yontem_check CHECK ((yontem = ANY (ARRAY['MANUEL'::text, 'TOPLU_YUZDE'::text, 'TOPLU_SABIT'::text, 'PLATFORM'::text])))
);


ALTER TABLE core.urun_platform_fiyat OWNER TO n8n;

--
-- Name: urun_platform_fiyat_id_seq; Type: SEQUENCE; Schema: core; Owner: n8n
--

CREATE SEQUENCE core.urun_platform_fiyat_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE core.urun_platform_fiyat_id_seq OWNER TO n8n;

--
-- Name: urun_platform_fiyat_id_seq; Type: SEQUENCE OWNED BY; Schema: core; Owner: n8n
--

ALTER SEQUENCE core.urun_platform_fiyat_id_seq OWNED BY core.urun_platform_fiyat.id;


--
-- Name: urun_platform_komisyon; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_platform_komisyon (
    urun_id text NOT NULL,
    platform_kod text NOT NULL,
    komisyon_yuzde numeric NOT NULL,
    gerekce text,
    kaydeden text NOT NULL,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT urun_platform_komisyon_komisyon_yuzde_check CHECK (((komisyon_yuzde >= (0)::numeric) AND (komisyon_yuzde < (100)::numeric)))
);


ALTER TABLE core.urun_platform_komisyon OWNER TO n8n;

--
-- Name: urun_seo; Type: TABLE; Schema: core; Owner: n8n
--

CREATE TABLE core.urun_seo (
    urun_id text NOT NULL,
    olusturma timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    guncelleme timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    urun_adi text NOT NULL,
    sku text,
    slug text,
    seo_baslik text,
    seo_aciklama text,
    og_baslik text,
    anahtar_kelimeler text[],
    ana_anahtar text,
    baslik_uzunluk integer,
    aciklama_uzunluk integer,
    baslik_var boolean DEFAULT false NOT NULL,
    aciklama_var boolean DEFAULT false NOT NULL,
    anahtar_var boolean DEFAULT false NOT NULL,
    yayinda boolean
);


ALTER TABLE core.urun_seo OWNER TO n8n;

--
-- Name: hiz; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.hiz (
    kova text NOT NULL,
    pencere_bas timestamp with time zone NOT NULL,
    sayac integer NOT NULL,
    ust integer NOT NULL,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE lcarlie.hiz OWNER TO n8n;

--
-- Name: kalip; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.kalip (
    id bigint NOT NULL,
    soru_norm text NOT NULL,
    cevap_imza text NOT NULL,
    adet integer NOT NULL,
    oran numeric(5,2),
    ornek_soru text,
    ornek_cevap text,
    gecikme_sn integer,
    uretim timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE lcarlie.kalip OWNER TO n8n;

--
-- Name: kalip_id_seq; Type: SEQUENCE; Schema: lcarlie; Owner: n8n
--

CREATE SEQUENCE lcarlie.kalip_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE lcarlie.kalip_id_seq OWNER TO n8n;

--
-- Name: kalip_id_seq; Type: SEQUENCE OWNED BY; Schema: lcarlie; Owner: n8n
--

ALTER SEQUENCE lcarlie.kalip_id_seq OWNED BY lcarlie.kalip.id;


--
-- Name: konusma; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.konusma (
    id bigint NOT NULL,
    kanal text NOT NULL,
    harici_id text NOT NULL,
    musteri_ref text,
    musteri_ad text,
    ilk_mesaj timestamp with time zone,
    son_mesaj timestamp with time zone,
    mesaj_sayisi integer DEFAULT 0 NOT NULL,
    sonuc text DEFAULT 'bilinmiyor'::text NOT NULL,
    siparis_no text,
    siparis_tutar numeric(12,2),
    notlar jsonb DEFAULT '{}'::jsonb NOT NULL,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    guncelleme timestamp with time zone DEFAULT now() NOT NULL,
    devir_durumu text DEFAULT 'INSANDA'::text NOT NULL,
    devir_sebep text,
    devir_zaman timestamp with time zone,
    CONSTRAINT konusma_devir_durumu_gecerli CHECK ((devir_durumu = ANY (ARRAY['JARVIS'::text, 'INSANDA'::text, 'KAPALI'::text])))
);


ALTER TABLE lcarlie.konusma OWNER TO n8n;

--
-- Name: konusma_id_seq; Type: SEQUENCE; Schema: lcarlie; Owner: n8n
--

CREATE SEQUENCE lcarlie.konusma_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE lcarlie.konusma_id_seq OWNER TO n8n;

--
-- Name: konusma_id_seq; Type: SEQUENCE OWNED BY; Schema: lcarlie; Owner: n8n
--

ALTER SEQUENCE lcarlie.konusma_id_seq OWNED BY lcarlie.konusma.id;


--
-- Name: mesaj; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.mesaj (
    id bigint NOT NULL,
    konusma_id bigint NOT NULL,
    harici_id text NOT NULL,
    zaman timestamp with time zone NOT NULL,
    yon text NOT NULL,
    gonderen text NOT NULL,
    metin text DEFAULT ''::text NOT NULL,
    ek jsonb DEFAULT '{}'::jsonb NOT NULL,
    sinif text,
    mevzuat text,
    bulgular jsonb,
    olusturma timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE lcarlie.mesaj OWNER TO n8n;

--
-- Name: mesaj_id_seq; Type: SEQUENCE; Schema: lcarlie; Owner: n8n
--

CREATE SEQUENCE lcarlie.mesaj_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE lcarlie.mesaj_id_seq OWNER TO n8n;

--
-- Name: mesaj_id_seq; Type: SEQUENCE OWNED BY; Schema: lcarlie; Owner: n8n
--

ALTER SEQUENCE lcarlie.mesaj_id_seq OWNED BY lcarlie.mesaj.id;


--
-- Name: satis_cevap; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.satis_cevap (
    id bigint NOT NULL,
    konusma_id bigint,
    tetik_mesaj_id bigint,
    yaklasim_id bigint,
    urun text,
    soru_tipi text NOT NULL,
    metin text NOT NULL,
    mevzuat text NOT NULL,
    model text,
    gonderildi boolean DEFAULT false NOT NULL,
    gonderim_zamani timestamp with time zone,
    donus_zamani timestamp with time zone,
    donus_sn integer,
    sonuc text DEFAULT 'UNKNOWN'::text NOT NULL,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT satis_cevap_sonuc_check CHECK ((sonuc = ANY (ARRAY['UNKNOWN'::text, 'DONUS_VAR'::text, 'DONUS_YOK'::text, 'PENCERE_ACIK'::text])))
);


ALTER TABLE lcarlie.satis_cevap OWNER TO n8n;

--
-- Name: satis_cevap_id_seq; Type: SEQUENCE; Schema: lcarlie; Owner: n8n
--

CREATE SEQUENCE lcarlie.satis_cevap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE lcarlie.satis_cevap_id_seq OWNER TO n8n;

--
-- Name: satis_cevap_id_seq; Type: SEQUENCE OWNED BY; Schema: lcarlie; Owner: n8n
--

ALTER SEQUENCE lcarlie.satis_cevap_id_seq OWNED BY lcarlie.satis_cevap.id;


--
-- Name: satis_yaklasim; Type: TABLE; Schema: lcarlie; Owner: n8n
--

CREATE TABLE lcarlie.satis_yaklasim (
    id bigint NOT NULL,
    surum integer NOT NULL,
    urun text,
    soru_tipi text,
    yonerge text NOT NULL,
    gerekce text NOT NULL,
    durum text DEFAULT 'TASLAK'::text NOT NULL,
    olusturan text NOT NULL,
    onaylayan text,
    onay_zamani timestamp with time zone,
    olusturma timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT satis_yaklasim_durum_check CHECK ((durum = ANY (ARRAY['TASLAK'::text, 'ONAYLI'::text, 'EMEKLI'::text, 'REDDEDILDI'::text])))
);


ALTER TABLE lcarlie.satis_yaklasim OWNER TO n8n;

--
-- Name: satis_yaklasim_id_seq; Type: SEQUENCE; Schema: lcarlie; Owner: n8n
--

CREATE SEQUENCE lcarlie.satis_yaklasim_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE lcarlie.satis_yaklasim_id_seq OWNER TO n8n;

--
-- Name: satis_yaklasim_id_seq; Type: SEQUENCE OWNED BY; Schema: lcarlie; Owner: n8n
--

ALTER SEQUENCE lcarlie.satis_yaklasim_id_seq OWNED BY lcarlie.satis_yaklasim.id;


--
-- Name: v_konusma_ozet; Type: VIEW; Schema: lcarlie; Owner: n8n
--

CREATE VIEW lcarlie.v_konusma_ozet AS
 SELECT id,
    kanal,
    musteri_ad,
    musteri_ref,
    mesaj_sayisi,
    ilk_mesaj,
    son_mesaj,
    sonuc,
    siparis_no,
    ( SELECT count(*) AS count
           FROM lcarlie.mesaj m
          WHERE ((m.konusma_id = k.id) AND (m.gonderen = 'musteri'::text))) AS musteri_mesaji,
    ( SELECT count(*) AS count
           FROM lcarlie.mesaj m
          WHERE ((m.konusma_id = k.id) AND (m.gonderen = 'meta_ai'::text))) AS ai_mesaji,
    ( SELECT count(*) AS count
           FROM lcarlie.mesaj m
          WHERE ((m.konusma_id = k.id) AND (m.gonderen = 'insan'::text))) AS insan_mesaji,
    ( SELECT m.metin
           FROM lcarlie.mesaj m
          WHERE ((m.konusma_id = k.id) AND (m.gonderen = 'musteri'::text))
          ORDER BY m.zaman
         LIMIT 1) AS ilk_soru
   FROM lcarlie.konusma k;


ALTER VIEW lcarlie.v_konusma_ozet OWNER TO n8n;

--
-- Name: v_soru_cevap; Type: VIEW; Schema: lcarlie; Owner: n8n
--

CREATE VIEW lcarlie.v_soru_cevap AS
 SELECT s.konusma_id,
    s.zaman AS soru_zaman,
    s.metin AS soru,
    c.metin AS cevap,
    (EXTRACT(epoch FROM (c.zaman - s.zaman)))::integer AS gecikme_sn
   FROM (lcarlie.mesaj s
     CROSS JOIN LATERAL ( SELECT m.metin,
            m.zaman
           FROM lcarlie.mesaj m
          WHERE ((m.konusma_id = s.konusma_id) AND (m.gonderen = 'insan'::text) AND (m.zaman > s.zaman))
          ORDER BY m.zaman
         LIMIT 1) c)
  WHERE ((s.gonderen = 'musteri'::text) AND (length(btrim(s.metin)) > 2) AND (length(btrim(c.metin)) > 2));


ALTER VIEW lcarlie.v_soru_cevap OWNER TO n8n;

--
-- Name: bk_shipment; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.bk_shipment (
    gonderi_id text NOT NULL,
    barkod text,
    foreign_code text,
    ek_bilgi text,
    durum text,
    tasiyici text,
    olusturma timestamp with time zone,
    guncelleme timestamp with time zone,
    kargoya_verilis timestamp with time zone,
    teslim timestamp with time zone,
    son_hareket text,
    desi numeric(10,2),
    kargo_ucreti numeric(14,2),
    toplam_maliyet numeric(14,2),
    cod_var boolean DEFAULT false NOT NULL,
    cod_tutar numeric(14,2),
    cod_durum text,
    siparis_tutari numeric(14,2),
    urun_adlari text[],
    sehir text,
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL,
    icerik_kodu text,
    yon text,
    gonderi_no text,
    ilce text
);


ALTER TABLE raw.bk_shipment OWNER TO n8n;

--
-- Name: wix_order; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.wix_order (
    siparis_id text NOT NULL,
    siparis_no bigint,
    buyer_id text,
    buyer_tipi text,
    olusturma timestamp with time zone,
    guncelleme timestamp with time zone,
    odeme_durumu text,
    odeme_yontemi text,
    teslimat_durumu text,
    toplam numeric(14,2),
    para_birimi text,
    kanal text,
    arsivlendi boolean,
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL,
    giren_id text,
    giren_tipi text,
    ic_siparis boolean,
    ara_toplam numeric(14,2),
    kdv numeric(14,2),
    kargo_bedeli numeric(14,2),
    siparis_indirimi numeric(14,2)
);


ALTER TABLE raw.wix_order OWNER TO n8n;

--
-- Name: gonderi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gonderi AS
 SELECT b.gonderi_id,
    b.barkod,
    b.olusturma,
    ((b.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
    b.foreign_code AS siparis_id,
    w.siparis_no,
    b.ek_bilgi,
    b.durum,
    b.tasiyici,
    b.sehir,
    b.kargo_ucreti,
    b.toplam_maliyet,
    b.cod_var,
    b.cod_tutar,
    b.cod_durum,
    ((b.ham #>> '{codInfo,fee}'::text[]))::numeric AS cod_komisyon,
        CASE
            WHEN (NOT b.cod_var) THEN 'YOK'::text
            WHEN ((b.ham #>> '{codInfo,fee}'::text[]) IS NOT NULL) THEN 'MEASURED'::text
            WHEN (b.cod_durum = 'COLLECTION_PENDING'::text) THEN 'NOT_YET_KNOWN'::text
            ELSE 'UNKNOWN'::text
        END AS cod_komisyon_sinifi,
    b.urun_adlari,
        CASE
            WHEN (beyan.sinif IS NOT NULL) THEN beyan.sinif
            WHEN (b.yon IS NULL) THEN 'YON_BILINMIYOR'::text
            WHEN (b.yon = 'INCOMING'::text) THEN 'IADE'::text
            WHEN (b.ek_bilgi ~~* 'NUMUNE-%'::text) THEN 'NUMUNE'::text
            WHEN (w.siparis_id IS NOT NULL) THEN 'SATIS'::text
            WHEN (b.cod_var AND (b.cod_tutar > (0)::numeric)) THEN 'ELLE_SATIS'::text
            ELSE 'UNKNOWN'::text
        END AS sinif,
        CASE
            WHEN ((b.yon IS DISTINCT FROM 'INCOMING'::text) AND (w.siparis_id IS NULL) AND b.cod_var AND (b.cod_durum = 'TRANSFERRED'::text)) THEN b.cod_tutar
            ELSE NULL::numeric
        END AS elle_ciro_tahsil,
        CASE
            WHEN ((b.yon IS DISTINCT FROM 'INCOMING'::text) AND (w.siparis_id IS NULL) AND b.cod_var AND (b.cod_durum IS DISTINCT FROM 'TRANSFERRED'::text)) THEN b.cod_tutar
            ELSE NULL::numeric
        END AS elle_ciro_bekleyen,
    (b.yon IS NULL) AS alarm,
    (b.olusturma >= mart.kesim()) AS olcumde,
        CASE
            WHEN ((b.teslim IS NOT NULL) AND (b.kargoya_verilis IS NOT NULL)) THEN round((EXTRACT(epoch FROM (b.teslim - b.kargoya_verilis)) / 86400.0), 2)
            ELSE NULL::numeric
        END AS transit_gun,
        CASE
            WHEN (beyan.sinif IS NOT NULL) THEN 'BEYAN'::text
            ELSE 'CIKARIM'::text
        END AS sinif_kaynagi,
    beyan.beyan_eden,
    beyan.gerekce AS sinif_gerekcesi
   FROM ((raw.bk_shipment b
     LEFT JOIN raw.wix_order w ON ((w.siparis_id = b.foreign_code)))
     LEFT JOIN core.gonderi_sinif_beyani beyan ON ((beyan.gonderi_id = b.gonderi_id)));


ALTER VIEW mart.gonderi OWNER TO n8n;

--
-- Name: konusma_cevapsiz; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.konusma_cevapsiz AS
 SELECT id AS konusma_id,
    kanal,
    son_mesaj,
    ((son_mesaj AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
    mesaj_sayisi,
    round((EXTRACT(epoch FROM (now() - son_mesaj)) / 3600.0), 1) AS bekleme_saat,
    "left"(md5(musteri_ref), 8) AS musteri_takma
   FROM lcarlie.konusma k
  WHERE (( SELECT m.yon
           FROM lcarlie.mesaj m
          WHERE (m.konusma_id = k.id)
          ORDER BY m.zaman DESC
         LIMIT 1) = 'gelen'::text);


ALTER VIEW mart.konusma_cevapsiz OWNER TO n8n;

--
-- Name: siparis; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.siparis AS
 SELECT w.siparis_id,
    w.siparis_no,
    w.olusturma,
    ((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
    ci.customer_id,
    w.odeme_yontemi,
    w.odeme_durumu,
    w.teslimat_durumu,
    w.arsivlendi,
    w.toplam,
    (w.toplam - w.kdv) AS toplam_kdv_haric,
    w.kdv,
        CASE
            WHEN ((w.odeme_durumu IS NULL) OR (w.teslimat_durumu IS NULL)) THEN 'BILINMIYOR'::text
            WHEN (w.teslimat_durumu = 'CANCELED'::text) THEN 'IPTAL'::text
            WHEN (w.odeme_durumu IS DISTINCT FROM 'PAID'::text) THEN 'ODENMEDI'::text
            WHEN (w.odeme_yontemi = 'PayTR'::text) THEN 'DOGRULANMIS'::text
            ELSE 'BEYAN_EDILMIS'::text
        END AS ciro_sinifi,
        CASE
            WHEN ((w.odeme_durumu IS NOT NULL) AND (w.teslimat_durumu IS NOT NULL) AND (w.teslimat_durumu <> 'CANCELED'::text) AND (w.odeme_durumu = 'PAID'::text) AND (w.odeme_yontemi = 'PayTR'::text)) THEN w.toplam
            ELSE NULL::numeric
        END AS ciro_dogrulanmis,
        CASE
            WHEN ((w.odeme_durumu IS NOT NULL) AND (w.teslimat_durumu IS NOT NULL) AND (w.teslimat_durumu <> 'CANCELED'::text) AND (w.odeme_durumu = 'PAID'::text) AND (w.odeme_yontemi IS DISTINCT FROM 'PayTR'::text)) THEN w.toplam
            ELSE NULL::numeric
        END AS ciro_beyan_edilmis,
        CASE
            WHEN ((w.odeme_durumu IS NOT NULL) AND (w.teslimat_durumu IS NOT NULL) AND (w.teslimat_durumu <> 'CANCELED'::text) AND (w.odeme_durumu IS DISTINCT FROM 'PAID'::text)) THEN w.toplam
            ELSE NULL::numeric
        END AS tutar_bekleyen,
        CASE
            WHEN ((w.odeme_durumu IS NULL) OR (w.teslimat_durumu IS NULL)) THEN w.toplam
            ELSE NULL::numeric
        END AS tutar_bilinmiyor,
        CASE
            WHEN ((w.odeme_durumu IS NOT NULL) AND (w.teslimat_durumu IS NOT NULL) AND (w.teslimat_durumu <> 'CANCELED'::text) AND (w.odeme_durumu = 'PAID'::text) AND (w.odeme_yontemi = 'PayTR'::text)) THEN (w.toplam - w.kdv)
            ELSE NULL::numeric
        END AS ciro_dogrulanmis_net,
        CASE
            WHEN ((w.odeme_durumu IS NOT NULL) AND (w.teslimat_durumu IS NOT NULL) AND (w.teslimat_durumu <> 'CANCELED'::text) AND (w.odeme_durumu = 'PAID'::text) AND (w.odeme_yontemi IS DISTINCT FROM 'PayTR'::text)) THEN (w.toplam - w.kdv)
            ELSE NULL::numeric
        END AS ciro_beyan_edilmis_net,
    (w.olusturma >= mart.kesim()) AS olcumde,
    w.giren_tipi,
    w.kanal
   FROM (raw.wix_order w
     LEFT JOIN core.customer_identity ci ON (((ci.kaynak = 'wix'::text) AND (ci.kimlik_tipi = 'wix_buyer_id'::text) AND (ci.source_customer_id = w.buyer_id))));


ALTER VIEW mart.siparis OWNER TO n8n;

--
-- Name: wix_order_item; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.wix_order_item (
    siparis_id text NOT NULL,
    sira integer NOT NULL,
    urun_adi text,
    sku text,
    adet numeric(12,3),
    birim_fiyat numeric(14,2),
    toplam numeric(14,2),
    ham jsonb NOT NULL,
    urun_id text,
    indirim numeric(14,2) DEFAULT 0 NOT NULL,
    net_toplam numeric(14,2) GENERATED ALWAYS AS ((toplam - indirim)) STORED
);


ALTER TABLE raw.wix_order_item OWNER TO n8n;

--
-- Name: wix_urun; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.wix_urun (
    urun_id text NOT NULL,
    sku text,
    ad text,
    slug text,
    fiyat numeric(14,2),
    maliyet numeric(14,2),
    para_birimi text,
    gorunur boolean,
    stok_takip boolean,
    stok_adet numeric(14,3),
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.wix_urun OWNER TO n8n;

--
-- Name: siparis_kalem; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.siparis_kalem AS
 SELECT i.siparis_id,
    i.sira,
    s.gun,
    s.olusturma,
    s.ciro_sinifi,
    s.olcumde,
    i.urun_id,
    COALESCE(u.ad, i.urun_adi) AS urun_adi,
    u.sku,
    i.adet,
    i.birim_fiyat,
    i.toplam AS satir_brut,
    i.indirim,
    i.net_toplam AS satir_ciro,
    round(((i.net_toplam * (w.toplam - w.kdv)) / NULLIF(w.toplam, (0)::numeric)), 2) AS satir_ciro_net,
    core.maliyet_bul(i.urun_id, s.olusturma) AS birim_maliyet,
    (core.maliyet_bul(i.urun_id, s.olusturma) * i.adet) AS satir_maliyet,
        CASE
            WHEN (core.maliyet_bul(i.urun_id, s.olusturma) IS NOT NULL) THEN (round(((i.net_toplam * (w.toplam - w.kdv)) / NULLIF(w.toplam, (0)::numeric)), 2) - (core.maliyet_bul(i.urun_id, s.olusturma) * i.adet))
            ELSE NULL::numeric
        END AS brut_marj,
    (core.maliyet_bul(i.urun_id, s.olusturma) IS NOT NULL) AS maliyeti_biliniyor
   FROM (((raw.wix_order_item i
     JOIN mart.siparis s ON ((s.siparis_id = i.siparis_id)))
     JOIN raw.wix_order w ON ((w.siparis_id = i.siparis_id)))
     LEFT JOIN raw.wix_urun u ON ((u.urun_id = i.urun_id)));


ALTER VIEW mart.siparis_kalem OWNER TO n8n;

--
-- Name: maliyet_eksik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.maliyet_eksik AS
 SELECT urun_id,
    urun_adi,
    sku,
    count(*) AS satilan_kalem,
    sum(adet) AS satilan_adet,
    sum(satir_ciro) AS olculemeyen_ciro,
    max(gun) AS son_satis
   FROM mart.siparis_kalem k
  WHERE ((NOT maliyeti_biliniyor) AND (ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text])))
  GROUP BY urun_id, urun_adi, sku
  ORDER BY (sum(satir_ciro)) DESC;


ALTER VIEW mart.maliyet_eksik OWNER TO n8n;

--
-- Name: tasarim_sablon_kutuk; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.tasarim_sablon_kutuk AS
 SELECT sablon_id,
    sablon_kodu,
    is_turu,
    ad,
    kategori,
    platform,
    bicim,
    en,
    boy,
    en_mm,
    boy_mm,
    dpi,
    beklenen_alanlar,
    alan_haritasi,
    marka_kurallari,
    mevzuat_kurallari,
    surum,
    durum,
    motor,
    onay_zorunlu,
    faz,
    canva_id,
    aktif,
    eklendi,
    gerekce,
    ((durum = ((((chr(72) || chr(65)) || chr(90)) || chr(73)) || chr(82))) AND (canva_id IS NOT NULL)) AS uretilebilir,
        CASE
            WHEN ((en IS NOT NULL) AND (boy IS NOT NULL) AND (boy > 0)) THEN round(((en)::numeric / (boy)::numeric), 3)
            ELSE NULL::numeric
        END AS oran
   FROM core.tasarim_sablon
  ORDER BY faz, kategori, sablon_kodu;


ALTER VIEW mart.tasarim_sablon_kutuk OWNER TO n8n;

--
-- Name: acik_isler; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.acik_isler AS
 SELECT 'SINIFLANDIRILMAMIS_GONDERI'::text AS tur,
    g.gonderi_id AS anahtar,
    format('%s · %s · %s'::text, COALESCE(g.barkod, '-'::text), COALESCE(g.sehir, '-'::text), COALESCE(array_to_string(g.urun_adlari, ', '::text), '-'::text)) AS detay,
    g.olusturma AS zaman,
    'BasitKargo kaydina EK BILGI yaz (NUMUNE-<tarih>) ya da Wix siparisiyle esle'::text AS yapilacak
   FROM mart.gonderi g
  WHERE (g.alarm AND g.olcumde)
UNION ALL
 SELECT 'ACIK_KIMLIK_CAKISMASI'::text AS tur,
    (k.conflict_id)::text AS anahtar,
    format('%s degeri %s musteriye bagli'::text, k.kimlik_tipi, array_length(k.customer_ids, 1)) AS detay,
    k.tespit_at AS zaman,
    'core.birlestirme_karari tablosuna BIRLESTIR/AYRI_TUT karari gir'::text AS yapilacak
   FROM core.identity_conflict k
  WHERE (k.durum = 'ACIK'::text)
UNION ALL
 SELECT 'ODENMEMIS_SIPARIS'::text AS tur,
    s.siparis_id AS anahtar,
    format('#%s · %s TL · %s'::text, s.siparis_no, s.toplam, s.odeme_yontemi) AS detay,
    s.olusturma AS zaman,
    'Odeme geldi mi kontrol et; geldiyse Wix''te odendi isaretle'::text AS yapilacak
   FROM mart.siparis s
  WHERE ((s.ciro_sinifi = 'ODENMEDI'::text) AND s.olcumde)
UNION ALL
 SELECT 'BEKLEYEN_KAPIDA_TAHSILAT'::text AS tur,
    g.gonderi_id AS anahtar,
    format('%s TL · %s'::text, g.cod_tutar, COALESCE(g.cod_durum, '-'::text)) AS detay,
    g.olusturma AS zaman,
    'BasitKargo tahsilat aktarimini izle'::text AS yapilacak
   FROM mart.gonderi g
  WHERE (g.cod_var AND (g.cod_durum = 'COLLECTION_PENDING'::text) AND g.olcumde)
UNION ALL
 SELECT 'MALIYET_GIRILMEMIS'::text AS tur,
    m.urun_id AS anahtar,
    format('%s · %s TL ciro · %s kalem'::text, "left"(m.urun_adi, 40), m.olculemeyen_ciro, m.satilan_kalem) AS detay,
    (m.son_satis)::timestamp with time zone AS zaman,
    'Wix''te urunun Maliyet alanini doldur (Urunler -> urun -> Maliyet)'::text AS yapilacak
   FROM mart.maliyet_eksik m
  WHERE (m.son_satis >= ((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text))::date)
UNION ALL
 SELECT 'SINIFI_BILINMEYEN_GONDERI'::text AS tur,
    g.gonderi_id AS anahtar,
    format('%s · %s · %s TL kargo · EK BILGI: %s'::text, COALESCE(g.barkod, '-'::text), COALESCE(g.sehir, '-'::text), to_char(COALESCE(g.kargo_ucreti, (0)::numeric), 'FM999990.00'::text), COALESCE(NULLIF(g.ek_bilgi, ''::text), '(bos)'::text)) AS detay,
    g.olusturma AS zaman,
    'Bu gonderi neydi? Numune ise BasitKargo EK BILGI alanina NUMUNE-<tarih> yaz; satis ise Wix''e siparis olarak gir. Isaretlenene kadar ne ciroya ne pazarlama giderine yazilir.'::text AS yapilacak
   FROM mart.gonderi g
  WHERE (g.sinif = 'UNKNOWN'::text)
UNION ALL
 SELECT 'TUTARI_BILINMEYEN_SIPARIS'::text AS tur,
    s.siparis_id AS anahtar,
    format('#%s · %s TL · odeme=%s teslimat=%s'::text, s.siparis_no, s.toplam, COALESCE(s.odeme_durumu, '(bos)'::text), COALESCE(s.teslimat_durumu, '(bos)'::text)) AS detay,
    s.olusturma AS zaman,
    'Wix''te siparisin odeme/teslimat durumunu kontrol et - alan bos gorunuyor'::text AS yapilacak
   FROM mart.siparis s
  WHERE ((s.ciro_sinifi = 'BILINMIYOR'::text) AND s.olcumde)
UNION ALL
 SELECT 'YONU_BILINMEYEN_GONDERI'::text AS tur,
    g.gonderi_id AS anahtar,
    format('%s · %s'::text, COALESCE(g.barkod, '-'::text), COALESCE(g.sehir, '-'::text)) AS detay,
    g.olusturma AS zaman,
    'BasitKargo kaydinda gonderi yonu (OUTGOING/INCOMING) okunamadi'::text AS yapilacak
   FROM mart.gonderi g
  WHERE ((g.sinif = 'YON_BILINMIYOR'::text) AND g.olcumde)
UNION ALL
 SELECT 'CEVAPSIZ_MESAJ'::text AS tur,
    (c.konusma_id)::text AS anahtar,
    format('%s · %s · %s mesajlik konusma · %s saattir bekliyor'::text, c.musteri_takma, c.kanal, c.mesaj_sayisi, c.bekleme_saat) AS detay,
    c.son_mesaj AS zaman,
    'Meta gelen kutusundan cevapla (Sayfa gelen kutusu, filtresiz liste)'::text AS yapilacak
   FROM mart.konusma_cevapsiz c
  WHERE (c.bekleme_saat > (24)::numeric)
UNION ALL
 SELECT 'SABLON_TASARIMSIZ'::text AS tur,
    s.sablon_kodu AS anahtar,
    format('%s · %s · %s'::text, s.kategori, s.ad, COALESCE(((((s.en_mm)::text || 'x'::text) || (s.boy_mm)::text) || ' mm'::text), ((((s.en)::text || 'x'::text) || (s.boy)::text) || ' px'::text))) AS detay,
    s.eklendi AS zaman,
    'Bu olcude Canva tasarimi ac, alanlarini isaretle, kutuge HAZIR yaz'::text AS yapilacak
   FROM mart.tasarim_sablon_kutuk s
  WHERE ((NOT s.uretilebilir) AND s.aktif)
UNION ALL
 SELECT 'URUN_GORSELSIZ'::text AS tur,
    u.ad AS anahtar,
    'Kesilmis urun gorseli yok; sablonun gorsel alani doldurulamaz'::text AS detay,
    now() AS zaman,
    'Urun cekimi yap (Wix gorseli FILIGRANLI, kullanma), kes ve Canvaya yukle'::text AS yapilacak
   FROM ( VALUES ('BABYDENT'::text), ('BABYRESCUE'::text), ('BEBEPUR-PROBIOBEBEKSAMPUANI'::text), ('BRIGHTSMILE'::text), ('LIPVORA'::text)) u(ad)
  WHERE (u.ad <> '-'::text)
UNION ALL
 SELECT 'FILIGRANLI_KARANTINA'::text AS tur,
    '09 KULLANMA - FILIGRANLI'::text AS anahtar,
    format('%s varlik karantinada; Wix kaynakli, arka planda filigran kalintisi var'::text, 35) AS detay,
    now() AS zaman,
    'Sahip karari: silinsin mi, kalsin mi? Silme geri alinamaz'::text AS yapilacak
  WHERE (35 > 0);


ALTER VIEW mart.acik_isler OWNER TO n8n;

--
-- Name: ai_evidence_readiness; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_evidence_readiness AS
 SELECT k.karar_id,
    k.durum,
    k.karar_tipi,
    k.kanit_kalitesi,
    k.anlik_id,
    q.soru_id,
    q.durum AS soru_durumu,
    f.state AS takip_durumu,
    ka.kanit_puani,
    ka.kanit_sinifi,
    ka.eksik_kaynak,
    ka.veri_kalitesi,
        CASE
            WHEN ((q.durum = 'ANSWERED'::text) AND (f.state = 'ENQUEUED'::text)) THEN 'REANALYSIS_ENQUEUED'::text
            WHEN (q.durum = 'ANSWERED'::text) THEN 'WAITING_NEW_EVIDENCE'::text
            ELSE 'WAITING_DATA'::text
        END AS readiness
   FROM (((core.karar k
     LEFT JOIN core.ai_evidence_followup f ON ((f.decision_id = k.karar_id)))
     LEFT JOIN core.acik_soru q ON ((q.soru_id = f.question_id)))
     LEFT JOIN core.kanit_anlik ka ON ((ka.anlik_id = k.anlik_id)))
  WHERE (k.durum = 'PROPOSED'::text);


ALTER VIEW mart.ai_evidence_readiness OWNER TO function_owner;

--
-- Name: ai_provider_budget_status; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_provider_budget_status AS
 WITH u AS (
         SELECT x.provider,
            count(*) AS attempts,
            COALESCE(sum((x.input_tokens + x.output_tokens)), (0)::bigint) AS tokens
           FROM ( SELECT ai_provider_attempt.provider,
                    ai_provider_attempt.input_tokens,
                    ai_provider_attempt.output_tokens,
                    ai_provider_attempt.started_at
                   FROM core.ai_provider_attempt
                UNION ALL
                 SELECT ai_red_team_attempt.provider,
                    ai_red_team_attempt.input_tokens,
                    ai_red_team_attempt.output_tokens,
                    ai_red_team_attempt.started_at
                   FROM core.ai_red_team_attempt) x
          WHERE (x.started_at >= (now() - '24:00:00'::interval))
          GROUP BY x.provider
        )
 SELECT b.provider,
    b.enabled,
    COALESCE(u.attempts, (0)::bigint) AS attempts_24h,
    b.daily_attempt_limit,
    COALESCE(u.tokens, (0)::bigint) AS tokens_24h,
    b.daily_token_limit,
    round(((100.0 * (COALESCE(u.tokens, (0)::bigint))::numeric) / (NULLIF(b.daily_token_limit, 0))::numeric), 1) AS token_limit_yuzde,
    core.ai_provider_allowed(b.provider) AS allowed,
        CASE
            WHEN (NOT b.enabled) THEN 'DISABLED'::text
            WHEN (NOT core.ai_provider_allowed(b.provider)) THEN 'BLOCKED'::text
            WHEN ((COALESCE(u.tokens, (0)::bigint))::numeric >= ((b.daily_token_limit)::numeric * 0.8)) THEN 'WARNING'::text
            ELSE 'OK'::text
        END AS durum
   FROM (core.ai_provider_budget b
     LEFT JOIN u USING (provider));


ALTER VIEW mart.ai_provider_budget_status OWNER TO function_owner;

--
-- Name: ai_alert_candidates; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_alert_candidates AS
 SELECT ('PROVIDER_'::text || ai_provider_budget_status.durum) AS alert_type,
    ai_provider_budget_status.provider AS entity,
    ai_provider_budget_status.token_limit_yuzde AS severity_metric,
    'Provider budget/circuit state requires review'::text AS message
   FROM mart.ai_provider_budget_status
  WHERE (ai_provider_budget_status.durum = ANY (ARRAY['WARNING'::text, 'BLOCKED'::text]))
UNION ALL
 SELECT 'EVIDENCE_WAITING'::text AS alert_type,
    (e.karar_id)::text AS entity,
    (EXTRACT(epoch FROM (now() - k.olusturma)) / (3600)::numeric) AS severity_metric,
    'Proposed decision waits for verified evidence'::text AS message
   FROM (mart.ai_evidence_readiness e
     JOIN core.karar k USING (karar_id))
  WHERE ((e.readiness = 'WAITING_DATA'::text) AND ((now() - k.olusturma) > '24:00:00'::interval));


ALTER VIEW mart.ai_alert_candidates OWNER TO function_owner;

--
-- Name: ai_approval_inbox; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_approval_inbox WITH (security_barrier='true') AS
 WITH cfg AS (
         SELECT (ai_orchestrator_config.config_value)::timestamp with time zone AS cutoff
           FROM core.ai_orchestrator_config
          WHERE (ai_orchestrator_config.config_key = 'orchestrator_enabled_after'::text)
        )
 SELECT k.karar_id,
    k.olusturma,
    k.karar_tipi,
    k.urun,
    k.kanal,
    k.oneri,
    k.kanit_kalitesi,
    k.beklenen_etki,
    k.risk,
    k.yanlislama_kosulu,
    e.kanit_puani,
    e.kanit_sinifi,
    e.veri_kalitesi,
    e.eksik_kaynak,
    j.state AS red_team_job_state,
    r.sonuc AS red_team_result,
    r.itiraz_tipi,
    r.gerekce AS red_team_reason,
    r.kanit_referansi,
    (k.olusturma >= cfg.cutoff) AS red_team_required,
    ((k.olusturma < cfg.cutoff) OR ((j.state = 'DONE'::text) AND (r.inceleme_id IS NOT NULL))) AS eligible_for_human_decision
   FROM ((((core.karar k
     CROSS JOIN cfg)
     LEFT JOIN core.kanit_anlik e ON ((e.anlik_id = k.anlik_id)))
     LEFT JOIN core.ai_red_team_job j ON ((j.karar_id = k.karar_id)))
     LEFT JOIN LATERAL ( SELECT x.inceleme_id,
            x.karar_id,
            x.sonuc,
            x.itiraz_tipi,
            x.gerekce,
            x.kanit_referansi,
            x.olusturma
           FROM core.karar_red_team x
          WHERE (x.karar_id = k.karar_id)
          ORDER BY x.inceleme_id DESC
         LIMIT 1) r ON (true))
  WHERE (k.durum = 'PROPOSED'::text)
  ORDER BY
        CASE r.sonuc
            WHEN 'CHALLENGE'::text THEN 1
            WHEN 'INSUFFICIENT_EVIDENCE'::text THEN 2
            WHEN 'SUPPORT'::text THEN 3
            ELSE 4
        END, k.olusturma;


ALTER VIEW mart.ai_approval_inbox OWNER TO function_owner;

--
-- Name: ai_approval_priority; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_approval_priority WITH (security_barrier='true') AS
 SELECT karar_id,
    olusturma,
    karar_tipi,
    urun,
    kanal,
    oneri,
    kanit_kalitesi,
    beklenen_etki,
    risk,
    yanlislama_kosulu,
    kanit_puani,
    kanit_sinifi,
    veri_kalitesi,
    eksik_kaynak,
    red_team_job_state,
    red_team_result,
    itiraz_tipi,
    red_team_reason,
    kanit_referansi,
    red_team_required,
    eligible_for_human_decision,
    ((
        CASE red_team_result
            WHEN 'CHALLENGE'::text THEN 100
            WHEN 'INSUFFICIENT_EVIDENCE'::text THEN 90
            WHEN 'SUPPORT'::text THEN 40
            ELSE 80
        END +
        CASE kanit_kalitesi
            WHEN 'LOW'::text THEN 30
            WHEN 'MEDIUM'::text THEN 15
            ELSE 0
        END) +
        CASE
            WHEN ((risk IS NOT NULL) AND (length(risk) > 0)) THEN 10
            ELSE 0
        END) AS review_priority_score,
        CASE
            WHEN (red_team_result = 'CHALLENGE'::text) THEN 'REVIEW_REQUIRED'::text
            WHEN (red_team_result = 'INSUFFICIENT_EVIDENCE'::text) THEN 'EVIDENCE_REQUIRED'::text
            WHEN ((red_team_result = 'SUPPORT'::text) AND (kanit_kalitesi = 'HIGH'::text)) THEN 'APPROVAL_CANDIDATE'::text
            WHEN (red_team_result = 'SUPPORT'::text) THEN 'EVIDENCE_REVIEW'::text
            ELSE 'RED_TEAM_REQUIRED'::text
        END AS review_disposition
   FROM mart.ai_approval_inbox i
  ORDER BY ((
        CASE red_team_result
            WHEN 'CHALLENGE'::text THEN 100
            WHEN 'INSUFFICIENT_EVIDENCE'::text THEN 90
            WHEN 'SUPPORT'::text THEN 40
            ELSE 80
        END +
        CASE kanit_kalitesi
            WHEN 'LOW'::text THEN 30
            WHEN 'MEDIUM'::text THEN 15
            ELSE 0
        END) +
        CASE
            WHEN ((risk IS NOT NULL) AND (length(risk) > 0)) THEN 10
            ELSE 0
        END) DESC, olusturma;


ALTER VIEW mart.ai_approval_priority OWNER TO function_owner;

--
-- Name: ai_decision_duplicate_groups; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_decision_duplicate_groups WITH (security_barrier='true') AS
 SELECT md5(concat_ws('|'::text, p.karar_tipi, COALESCE(p.urun, ''::text), COALESCE(p.kanal, ''::text), (k.anlik_id)::text)) AS group_key,
    p.karar_tipi,
    p.urun,
    p.kanal,
    k.anlik_id,
    count(*) AS duplicate_count,
    array_agg(p.karar_id ORDER BY p.karar_id) AS karar_ids,
    array_agg(DISTINCT p.red_team_result ORDER BY p.red_team_result) AS red_team_results,
    min(p.review_priority_score) AS min_review_score,
    max(p.review_priority_score) AS max_review_score
   FROM (mart.ai_approval_priority p
     JOIN core.karar k USING (karar_id))
  GROUP BY p.karar_tipi, p.urun, p.kanal, k.anlik_id
 HAVING (count(*) > 1)
  ORDER BY (count(*)) DESC, (max(p.review_priority_score)) DESC;


ALTER VIEW mart.ai_decision_duplicate_groups OWNER TO function_owner;

--
-- Name: ai_company_intelligence_dashboard; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_company_intelligence_dashboard WITH (security_barrier='true') AS
 SELECT clock_timestamp() AS generated_at,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'PROPOSED'::text)) AS proposed,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'APPROVED'::text)) AS approved,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'MEASURING'::text)) AS measuring,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'CONCLUDED'::text)) AS concluded,
    ( SELECT count(*) AS count
           FROM mart.ai_decision_duplicate_groups) AS duplicate_groups,
    ( SELECT count(*) AS count
           FROM core.ai_red_team_job
          WHERE (ai_red_team_job.state = 'DONE'::text)) AS red_team_done,
    ( SELECT count(*) AS count
           FROM core.ai_red_team_job
          WHERE (ai_red_team_job.state <> 'DONE'::text)) AS red_team_pending,
    ( SELECT count(*) AS count
           FROM core.ai_generated_question) AS ai_questions,
    ( SELECT count(*) AS count
           FROM core.ai_question_route) AS question_routes,
    ( SELECT count(*) AS count
           FROM core.ai_executive_brief) AS executive_briefs,
    ( SELECT count(*) AS count
           FROM core.ai_measurement_plan) AS measurement_plans,
    ( SELECT count(*) AS count
           FROM core.ai_action_type
          WHERE (ai_action_type.execution_enabled AND (ai_action_type.action_type <> 'REQUEST_HUMAN_REVIEW'::text))) AS unsafe_external_actions,
    ( SELECT count(*) AS count
           FROM core.ai_red_team_job
          WHERE ((ai_red_team_job.state = 'LEASED'::text) AND (ai_red_team_job.lease_until < now()))) AS stale_red_team_leases;


ALTER VIEW mart.ai_company_intelligence_dashboard OWNER TO function_owner;

--
-- Name: ai_cost_estimate_24h; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_cost_estimate_24h AS
 WITH u AS (
         SELECT x.provider,
            sum(x.input_tokens) AS input_tokens,
            sum(x.output_tokens) AS output_tokens
           FROM ( SELECT ai_provider_attempt.provider,
                    ai_provider_attempt.input_tokens,
                    ai_provider_attempt.output_tokens,
                    ai_provider_attempt.started_at
                   FROM core.ai_provider_attempt
                UNION ALL
                 SELECT ai_red_team_attempt.provider,
                    ai_red_team_attempt.input_tokens,
                    ai_red_team_attempt.output_tokens,
                    ai_red_team_attempt.started_at
                   FROM core.ai_red_team_attempt) x
          WHERE (x.started_at >= (now() - '24:00:00'::interval))
          GROUP BY x.provider
        )
 SELECT p.provider,
    COALESCE(u.input_tokens, (0)::bigint) AS input_tokens,
    COALESCE(u.output_tokens, (0)::bigint) AS output_tokens,
    p.pricing_status,
        CASE
            WHEN (p.pricing_status = ANY (ARRAY['FREE'::text, 'CONFIGURED'::text])) THEN round(((((COALESCE(u.input_tokens, (0)::bigint))::numeric * p.input_usd_per_million) + ((COALESCE(u.output_tokens, (0)::bigint))::numeric * p.output_usd_per_million)) / (1000000)::numeric), 6)
            ELSE NULL::numeric
        END AS tahmini_usd
   FROM (core.ai_provider_price_config p
     LEFT JOIN u USING (provider));


ALTER VIEW mart.ai_cost_estimate_24h OWNER TO function_owner;

--
-- Name: ai_data_quality_gate; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_data_quality_gate AS
 SELECT 'REAL_STOCK'::text AS check_name,
    (EXISTS ( SELECT 1
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'STOCK_CONFIRMATION'::text) AND ai_human_data_attestation.active))) AS passed,
    ( SELECT format('%s urun / her biri %s / OWNER_ATTESTED'::text, (ai_human_data_attestation.value_json ->> 'product_count'::text), (ai_human_data_attestation.value_json ->> 'stock_each'::text)) AS format
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'STOCK_CONFIRMATION'::text) AND (ai_human_data_attestation.scope = 'ALL_PRODUCTS'::text) AND ai_human_data_attestation.active)) AS detail,
    clock_timestamp() AS checked_at
UNION ALL
 SELECT 'PRODUCT_COGS'::text AS check_name,
    (EXISTS ( SELECT 1
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'COGS_CONFIRMATION'::text) AND ai_human_data_attestation.active))) AS passed,
    ( SELECT format('%s urun / her biri %s TL / OWNER_ATTESTED'::text, (ai_human_data_attestation.value_json ->> 'product_count'::text), (ai_human_data_attestation.value_json ->> 'cogs_each_try'::text)) AS format
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'COGS_CONFIRMATION'::text) AND (ai_human_data_attestation.scope = 'ALL_PRODUCTS'::text) AND ai_human_data_attestation.active)) AS detail,
    clock_timestamp() AS checked_at
UNION ALL
 SELECT 'OFFLINE_PAYMENT_VERIFICATION'::text AS check_name,
    (EXISTS ( SELECT 1
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'OFFLINE_PAYMENT_CONFIRMATION'::text) AND ai_human_data_attestation.active AND ((ai_human_data_attestation.value_json ->> 'collected'::text))::boolean))) AS passed,
    ( SELECT format('%s siparis / %s TL / COLLECTED'::text, (ai_human_data_attestation.value_json ->> 'order_count'::text), (ai_human_data_attestation.value_json ->> 'total_try'::text)) AS format
           FROM core.ai_human_data_attestation
          WHERE ((ai_human_data_attestation.attestation_type = 'OFFLINE_PAYMENT_CONFIRMATION'::text) AND ai_human_data_attestation.active)
         LIMIT 1) AS detail,
    clock_timestamp() AS checked_at;


ALTER VIEW mart.ai_data_quality_gate OWNER TO function_owner;

--
-- Name: ai_data_quality_summary; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_data_quality_summary AS
 SELECT count(*) AS kontroller,
    count(*) FILTER (WHERE passed) AS gecen,
    count(*) FILTER (WHERE (NOT passed)) AS kalan,
    bool_and(passed) AS ai_reanalysis_ready
   FROM mart.ai_data_quality_gate;


ALTER VIEW mart.ai_data_quality_summary OWNER TO function_owner;

--
-- Name: ai_human_approval_dashboard; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_human_approval_dashboard AS
 SELECT k.karar_id,
    k.olusturma,
    k.karar_tipi,
    k.urun,
    k.kanal,
    k.oneri,
    k.kanit_kalitesi,
    k.risk,
    k.durum,
    rt.sonuc AS red_team_sonucu,
    rt.itiraz_tipi,
    rt.gerekce AS red_team_gerekce,
        CASE
            WHEN ((k.durum = 'PROPOSED'::text) AND (COALESCE(rt.sonuc, ''::text) = 'SUPPORT'::text)) THEN 'REVIEW_READY'::text
            WHEN (k.durum = 'PROPOSED'::text) THEN 'EVIDENCE_OR_REVIEW_NEEDED'::text
            ELSE 'NO_ACTION'::text
        END AS onay_hazirligi
   FROM (core.karar k
     LEFT JOIN LATERAL ( SELECT r.inceleme_id,
            r.karar_id,
            r.sonuc,
            r.itiraz_tipi,
            r.gerekce,
            r.kanit_referansi,
            r.olusturma
           FROM core.karar_red_team r
          WHERE (r.karar_id = k.karar_id)
          ORDER BY r.olusturma DESC
         LIMIT 1) rt ON (true));


ALTER VIEW mart.ai_human_approval_dashboard OWNER TO function_owner;

--
-- Name: ai_provider_business_score; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_provider_business_score AS
 WITH outcomes AS (
         SELECT a.provider,
            a.model,
            k.karar_id,
            k.durum,
                CASE k.durum
                    WHEN 'CONCLUDED'::text THEN 100
                    WHEN 'APPROVED'::text THEN 80
                    WHEN 'PROPOSED'::text THEN 50
                    WHEN 'DEFERRED'::text THEN 40
                    WHEN 'CANCELLED'::text THEN 20
                    WHEN 'REJECTED'::text THEN 10
                    ELSE 30
                END AS puan
           FROM ((core.ai_provider_attempt a
             JOIN core.ai_task t ON ((t.task_id = a.task_id)))
             JOIN core.karar k ON ((k.idempotency_key = t.idempotency_key)))
          WHERE ((a.result_class = 'SUCCESS'::text) AND (a.validation_result = 'PASS'::text))
        )
 SELECT provider,
    model,
    count(*) AS karar_sayisi,
    round(avg(puan), 1) AS ham_is_sonucu_puani,
    round((((sum(puan))::numeric + 250.0) / ((count(*) + 5))::numeric), 1) AS dengelenmis_is_puani,
    count(*) FILTER (WHERE (durum = ANY (ARRAY['APPROVED'::text, 'CONCLUDED'::text]))) AS olumlu,
    count(*) FILTER (WHERE (durum = ANY (ARRAY['REJECTED'::text, 'CANCELLED'::text]))) AS olumsuz
   FROM outcomes
  GROUP BY provider, model;


ALTER VIEW mart.ai_provider_business_score OWNER TO function_owner;

--
-- Name: ai_provider_score; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_provider_score AS
 WITH a AS (
         SELECT ai_provider_attempt.provider,
            ai_provider_attempt.model,
            ai_provider_attempt.latency_ms,
            ai_provider_attempt.result_class,
            ai_provider_attempt.validation_result,
            (ai_provider_attempt.input_tokens + ai_provider_attempt.output_tokens) AS tokens
           FROM core.ai_provider_attempt
          WHERE (ai_provider_attempt.started_at >= (now() - '7 days'::interval))
        UNION ALL
         SELECT ai_red_team_attempt.provider,
            ai_red_team_attempt.model,
            ai_red_team_attempt.latency_ms,
            ai_red_team_attempt.result_class,
            ai_red_team_attempt.validation_result,
            (ai_red_team_attempt.input_tokens + ai_red_team_attempt.output_tokens)
           FROM core.ai_red_team_attempt
          WHERE (ai_red_team_attempt.started_at >= (now() - '7 days'::interval))
        )
 SELECT provider,
    model,
    count(*) AS deneme,
    round(((100.0 * (count(*) FILTER (WHERE ((result_class = 'SUCCESS'::text) AND (validation_result = 'PASS'::text))))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS basari_orani,
    (round(avg(latency_ms)))::bigint AS ortalama_ms,
    sum(tokens) AS token,
    (provider = ANY (ARRAY['claude'::text, 'openai'::text])) AS premium,
    round(((((100.0 * (count(*) FILTER (WHERE ((result_class = 'SUCCESS'::text) AND (validation_result = 'PASS'::text))))::numeric) / (NULLIF(count(*), 0))::numeric) - LEAST((avg(latency_ms) / 1000.0), (30)::numeric)) - (
        CASE
            WHEN (provider = ANY (ARRAY['claude'::text, 'openai'::text])) THEN 15
            ELSE 0
        END)::numeric), 1) AS kalite_maliyet_puani
   FROM a
  GROUP BY provider, model;


ALTER VIEW mart.ai_provider_score OWNER TO function_owner;

--
-- Name: ai_provider_routing_score; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_provider_routing_score AS
 SELECT t.provider,
    t.model,
    t.deneme,
    t.basari_orani,
    t.ortalama_ms,
    t.token,
    t.premium,
    t.kalite_maliyet_puani,
    COALESCE(b.karar_sayisi, (0)::bigint) AS karar_sayisi,
    COALESCE(b.dengelenmis_is_puani, (50)::numeric) AS is_puani,
    round(((t.kalite_maliyet_puani * 0.6) + (COALESCE(b.dengelenmis_is_puani, (50)::numeric) * 0.4)), 1) AS routing_puani
   FROM (mart.ai_provider_score t
     LEFT JOIN mart.ai_provider_business_score b USING (provider, model));


ALTER VIEW mart.ai_provider_routing_score OWNER TO function_owner;

--
-- Name: ai_learning_loop; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_learning_loop AS
 SELECT r.provider,
    r.model,
    r.deneme,
    r.basari_orani,
    r.ortalama_ms,
    r.token,
    r.premium,
    r.kalite_maliyet_puani,
    r.karar_sayisi,
    r.is_puani,
    r.routing_puani,
    COALESCE(b.olumlu, (0)::bigint) AS olumlu,
    COALESCE(b.olumsuz, (0)::bigint) AS olumsuz
   FROM (mart.ai_provider_routing_score r
     LEFT JOIN mart.ai_provider_business_score b USING (provider, model));


ALTER VIEW mart.ai_learning_loop OWNER TO function_owner;

--
-- Name: ai_model_efficiency; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_model_efficiency AS
 WITH attempts AS (
         SELECT 'DECISION'::text AS workload,
            ai_provider_attempt.provider,
            ai_provider_attempt.model,
            ai_provider_attempt.started_at,
            ai_provider_attempt.latency_ms,
            ai_provider_attempt.result_class,
            ai_provider_attempt.validation_result,
            ai_provider_attempt.rate_limit,
            ai_provider_attempt.timeout,
            ai_provider_attempt.input_tokens,
            ai_provider_attempt.output_tokens,
            ai_provider_attempt.token_estimated
           FROM core.ai_provider_attempt
        UNION ALL
         SELECT 'RED_TEAM'::text AS text,
            ai_red_team_attempt.provider,
            ai_red_team_attempt.model,
            ai_red_team_attempt.started_at,
            ai_red_team_attempt.latency_ms,
            ai_red_team_attempt.result_class,
            ai_red_team_attempt.validation_result,
            ai_red_team_attempt.rate_limit,
            ai_red_team_attempt.timeout,
            ai_red_team_attempt.input_tokens,
            ai_red_team_attempt.output_tokens,
            ai_red_team_attempt.token_estimated
           FROM core.ai_red_team_attempt
        )
 SELECT date_trunc('day'::text, started_at) AS gun,
    workload,
    provider,
    model,
    count(*) AS deneme,
    count(*) FILTER (WHERE ((result_class = 'SUCCESS'::text) AND (validation_result = 'PASS'::text))) AS basarili,
    count(*) FILTER (WHERE ((result_class <> 'SUCCESS'::text) OR (validation_result = 'FAIL'::text))) AS basarisiz,
    count(*) FILTER (WHERE rate_limit) AS rate_limit,
    count(*) FILTER (WHERE timeout) AS timeout,
    (round(avg(latency_ms)))::bigint AS ortalama_gecikme_ms,
    round(((100.0 * (count(*) FILTER (WHERE ((result_class = 'SUCCESS'::text) AND (validation_result = 'PASS'::text))))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS basari_orani,
    (provider = ANY (ARRAY['claude'::text, 'openai'::text])) AS premium,
    sum(input_tokens) AS girdi_token,
    sum(output_tokens) AS cikti_token,
    bool_or(token_estimated) AS token_tahmini
   FROM attempts
  GROUP BY (date_trunc('day'::text, started_at)), workload, provider, model;


ALTER VIEW mart.ai_model_efficiency OWNER TO function_owner;

--
-- Name: ai_oneri_sonuc; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ai_oneri_sonuc AS
 SELECT action_id,
    task_id,
    action_type,
    risk_class,
    state,
        CASE state
            WHEN 'PROPOSED'::text THEN 'PROPOSED'::text
            WHEN 'APPROVED'::text THEN 'APPROVED'::text
            WHEN 'EXECUTED'::text THEN 'CONCLUDED'::text
            WHEN 'REJECTED'::text THEN 'REJECTED'::text
            WHEN 'EXPIRED'::text THEN 'CANCELLED'::text
            WHEN 'CANCELLED'::text THEN 'CANCELLED'::text
            ELSE state
        END AS durum,
    proposed_at,
    decided_at,
    expires_at,
        CASE
            WHEN (decided_at IS NULL) THEN NULL::numeric
            ELSE round((EXTRACT(epoch FROM (decided_at - proposed_at)) / 3600.0), 2)
        END AS karar_saati
   FROM core.ai_action_proposal p;


ALTER VIEW mart.ai_oneri_sonuc OWNER TO n8n;

--
-- Name: ai_operations_dashboard; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_operations_dashboard AS
 SELECT clock_timestamp() AS rapor_zamani,
    ( SELECT count(*) AS count
           FROM core.ai_task
          WHERE (ai_task.state = 'OPEN'::text)) AS acik_gorev,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'PROPOSED'::text)) AS proposed_karar,
    ( SELECT count(*) AS count
           FROM mart.ai_human_approval_dashboard
          WHERE (ai_human_approval_dashboard.onay_hazirligi = 'REVIEW_READY'::text)) AS onaya_hazir,
    ( SELECT count(*) AS count
           FROM mart.ai_human_approval_dashboard
          WHERE (ai_human_approval_dashboard.onay_hazirligi = 'EVIDENCE_OR_REVIEW_NEEDED'::text)) AS kanit_bekleyen,
    ( SELECT count(*) AS count
           FROM core.ai_evidence_followup
          WHERE (ai_evidence_followup.state = 'WAITING'::text)) AS takip_bekleyen,
    ( SELECT count(*) AS count
           FROM mart.ai_provider_budget_status
          WHERE (ai_provider_budget_status.durum = 'BLOCKED'::text)) AS bloklu_provider,
    ( SELECT COALESCE(sum(ai_provider_budget_status.tokens_24h), (0)::numeric) AS "coalesce"
           FROM mart.ai_provider_budget_status) AS toplam_token_24h,
    ( SELECT COALESCE(sum(ai_provider_budget_status.tokens_24h), (0)::numeric) AS "coalesce"
           FROM mart.ai_provider_budget_status
          WHERE (ai_provider_budget_status.provider = ANY (ARRAY['claude'::text, 'openai'::text]))) AS premium_token_24h,
    ( SELECT count(*) AS count
           FROM core.ai_action_execution) AS dis_aksiyon_kaydi,
    ( SELECT count(*) AS count
           FROM core.ai_action_execution
          WHERE (ai_action_execution.state = 'EXECUTED'::text)) AS uygulanan_dis_aksiyon;


ALTER VIEW mart.ai_operations_dashboard OWNER TO function_owner;

--
-- Name: ai_orchestrator_status; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_orchestrator_status WITH (security_barrier='true') AS
 WITH task_states AS (
         SELECT COALESCE(jsonb_object_agg(s.state, s.n), '{}'::jsonb) AS value
           FROM ( SELECT ai_task.state,
                    count(*) AS n
                   FROM core.ai_task
                  GROUP BY ai_task.state) s
        ), rt_states AS (
         SELECT COALESCE(jsonb_object_agg(s.state, s.n), '{}'::jsonb) AS value
           FROM ( SELECT ai_red_team_job.state,
                    count(*) AS n
                   FROM core.ai_red_team_job
                  GROUP BY ai_red_team_job.state) s
        ), action_states AS (
         SELECT COALESCE(jsonb_object_agg(s.state, s.n), '{}'::jsonb) AS value
           FROM ( SELECT ai_action_proposal.state,
                    count(*) AS n
                   FROM core.ai_action_proposal
                  GROUP BY ai_action_proposal.state) s
        ), execution_states AS (
         SELECT COALESCE(jsonb_object_agg(s.state, s.n), '{}'::jsonb) AS value
           FROM ( SELECT ai_action_execution.state,
                    count(*) AS n
                   FROM core.ai_action_execution
                  GROUP BY ai_action_execution.state) s
        ), providers AS (
         SELECT COALESCE(jsonb_object_agg(ai_provider_budget.provider, jsonb_build_object('enabled', ai_provider_budget.enabled, 'allowed_now', core.ai_provider_allowed(ai_provider_budget.provider), 'daily_limit', ai_provider_budget.daily_attempt_limit)), '{}'::jsonb) AS value
           FROM core.ai_provider_budget
        )
 SELECT clock_timestamp() AS generated_at,
    ( SELECT task_states.value
           FROM task_states) AS task_states,
    ( SELECT rt_states.value
           FROM rt_states) AS red_team_states,
    ( SELECT action_states.value
           FROM action_states) AS action_states,
    ( SELECT execution_states.value
           FROM execution_states) AS execution_states,
    ( SELECT providers.value
           FROM providers) AS provider_status,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'PROPOSED'::text)) AS proposed_decisions,
    ( SELECT count(*) AS count
           FROM core.karar k
          WHERE ((k.durum = 'PROPOSED'::text) AND (NOT (EXISTS ( SELECT 1
                   FROM core.karar_red_team r
                  WHERE (r.karar_id = k.karar_id)))))) AS proposed_without_red_team,
    ( SELECT count(*) AS count
           FROM core.ai_red_team_job
          WHERE ((ai_red_team_job.state = 'LEASED'::text) AND (ai_red_team_job.lease_until < clock_timestamp()))) AS stale_red_team_leases,
    ( SELECT count(*) AS count
           FROM core.ai_action_execution
          WHERE ((ai_action_execution.state = 'LEASED'::text) AND (ai_action_execution.lease_until < clock_timestamp()))) AS stale_action_leases,
    ( SELECT max(ai_provider_attempt.finished_at) AS max
           FROM core.ai_provider_attempt) AS last_decision_ai_attempt,
    ( SELECT max(ai_red_team_attempt.finished_at) AS max
           FROM core.ai_red_team_attempt) AS last_red_team_ai_attempt;


ALTER VIEW mart.ai_orchestrator_status OWNER TO function_owner;

--
-- Name: ai_token_cost_summary; Type: VIEW; Schema: mart; Owner: function_owner
--

CREATE VIEW mart.ai_token_cost_summary AS
 SELECT date_trunc('day'::text, zaman) AS gun,
    saglayici AS provider,
    model,
    count(*) AS calisma,
    COALESCE(sum(girdi_token), (0)::bigint) AS girdi_token,
    COALESCE(sum(cikti_token), (0)::bigint) AS cikti_token,
    (COALESCE(sum(maliyet_usd), (0)::numeric))::numeric(14,6) AS maliyet_usd,
    count(*) FILTER (WHERE ((sonuc ~~* '%success%'::text) OR (sonuc ~~* '%pass%'::text))) AS basarili
   FROM core.ai_calisma_log
  GROUP BY (date_trunc('day'::text, zaman)), saglayici, model;


ALTER VIEW mart.ai_token_cost_summary OWNER TO function_owner;

--
-- Name: arac_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.arac_guncel AS
 SELECT arac_id,
    ad,
    tur,
    kaynak,
    lisans,
    ne_ise_yariyor,
    nerede,
    surum,
    kurulu,
    calisiyor,
    calismiyorsa_neden,
    son_arastirma,
    alternatif_bakildi,
    arastirma_notu,
    guncelleme
   FROM core.arac_envanteri
  ORDER BY calisiyor DESC, tur, ad;


ALTER VIEW mart.arac_guncel OWNER TO n8n;

--
-- Name: arastirma_sirasi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.arastirma_sirasi AS
 SELECT plan_id,
    kapsam,
    hedef,
    konu,
    siklik_gun,
    oncelik,
    gerekce,
    planlayan,
    olusturuldu,
    aktif,
    son_kosu,
    son_bulgu,
    (son_kosu IS NULL) AS hic_kosmadi,
        CASE
            WHEN (son_kosu IS NULL) THEN 999999
            ELSE (EXTRACT(day FROM (now() - son_kosu)))::integer
        END AS gun_gecti,
        CASE
            WHEN (son_kosu IS NULL) THEN true
            ELSE ((now() - son_kosu) > ((siklik_gun || ' days'::text))::interval)
        END AS vakti_geldi
   FROM core.arastirma_plani p
  WHERE aktif
  ORDER BY (son_kosu IS NULL) DESC, oncelik, son_kosu NULLS FIRST;


ALTER VIEW mart.arastirma_sirasi OWNER TO n8n;

--
-- Name: basin_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.basin_guncel AS
 SELECT bahis_id,
    baslik,
    kaynak_site,
    url,
    yayin_tarihi,
    arama_terimi,
    mevzuat_durumu,
    mevzuat_bayragi,
    bulundu,
    ozet
   FROM core.basin_bahsi
  ORDER BY bulundu DESC;


ALTER VIEW mart.basin_guncel OWNER TO n8n;

--
-- Name: bayi_fiyat_gecerli; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.bayi_fiyat_gecerli AS
 SELECT urun_slug,
    barkod,
    psf,
    psf_kaynagi,
        CASE
            WHEN celiskili THEN NULL::numeric
            ELSE isk30_haric
        END AS isk30_haric,
        CASE
            WHEN celiskili THEN NULL::numeric
            ELSE isk30_dahil
        END AS isk30_dahil,
        CASE
            WHEN celiskili THEN NULL::numeric
            ELSE isk40_haric
        END AS isk40_haric,
        CASE
            WHEN celiskili THEN NULL::numeric
            ELSE isk40_dahil
        END AS isk40_dahil,
        CASE
            WHEN celiskili THEN NULL::numeric
            ELSE trendyol
        END AS trendyol,
    celiskili,
    celiski_notu,
    barkod_celiskili,
    barkod_notu,
    kaynak,
    girildi
   FROM core.urun_bayi_fiyat b;


ALTER VIEW mart.bayi_fiyat_gecerli OWNER TO n8n;

--
-- Name: elle_satis; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.elle_satis AS
 SELECT not_id,
    (girildi)::date AS gun,
    COALESCE(kanal, 'BILINMIYOR'::text) AS kanal,
    urun_adi,
    adet,
    elle_fiyat AS tutar,
    (elle_fiyat IS NULL) AS tutar_eksik,
    alici,
    not_metni,
    giren,
    girildi
   FROM core.gonderi_notu n
  WHERE ((tur = 'SATIS'::text) AND (siparis_ref IS NULL));


ALTER VIEW mart.elle_satis OWNER TO n8n;

--
-- Name: ciro_kanal; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ciro_kanal AS
 SELECT s.gun,
    COALESCE(s.kanal, 'BILINMIYOR'::text) AS kanal,
    'OLCULDU'::text AS kaynak_tipi,
    (count(*))::integer AS siparis,
    round(sum(COALESCE(s.ciro_dogrulanmis_net, (0)::numeric))) AS ciro_dogrulanmis,
    round(sum(COALESCE(s.ciro_beyan_edilmis_net, (0)::numeric))) AS ciro_beyan,
    0 AS tutar_eksik
   FROM mart.siparis s
  GROUP BY s.gun, COALESCE(s.kanal, 'BILINMIYOR'::text)
UNION ALL
 SELECT e.gun,
    e.kanal,
    'BEYAN'::text AS kaynak_tipi,
    (count(*))::integer AS siparis,
    0 AS ciro_dogrulanmis,
    round(sum(COALESCE(e.tutar, (0)::numeric))) AS ciro_beyan,
    (count(*) FILTER (WHERE e.tutar_eksik))::integer AS tutar_eksik
   FROM mart.elle_satis e
  GROUP BY e.gun, e.kanal;


ALTER VIEW mart.ciro_kanal OWNER TO n8n;

--
-- Name: cro_sinyal; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.cro_sinyal AS
 SELECT 'ODEME_TAMAMLANMAMA'::text AS kod,
    'OBSERVED'::text AS seviye,
    format('%s siparis NOT_PAID durumunda (%s TL net) - odeme adimi tamamlanmiyor'::text, ( SELECT count(*) AS count
           FROM raw.wix_order
          WHERE ((((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30)) AND (wix_order.odeme_durumu = 'NOT_PAID'::text) AND (wix_order.teslimat_durumu IS DISTINCT FROM 'CANCELED'::text))), ( SELECT to_char(COALESCE(sum((wix_order.toplam - wix_order.kdv)), (0)::numeric), 'FM999990.00'::text) AS to_char
           FROM raw.wix_order
          WHERE ((((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30)) AND (wix_order.odeme_durumu = 'NOT_PAID'::text) AND (wix_order.teslimat_durumu IS DISTINCT FROM 'CANCELED'::text)))) AS bulgu,
    'Wix siparis kaydi'::text AS kaynak
UNION ALL
 SELECT 'IPTAL_ORANI'::text AS kod,
    'OBSERVED'::text AS seviye,
    format('Son 30 gunde %s siparis IPTAL (%s TL net) - odenmeyen siparisler iptale donuyor'::text, ( SELECT count(*) AS count
           FROM raw.wix_order
          WHERE ((((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30)) AND (wix_order.teslimat_durumu = 'CANCELED'::text))), ( SELECT to_char(COALESCE(sum((wix_order.toplam - wix_order.kdv)), (0)::numeric), 'FM999990.00'::text) AS to_char
           FROM raw.wix_order
          WHERE ((((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30)) AND (wix_order.teslimat_durumu = 'CANCELED'::text)))) AS bulgu,
    'Wix siparis kaydi'::text AS kaynak
UNION ALL
 SELECT 'CEVRIM_DISI_AGIRLIK'::text AS kod,
    'OBSERVED'::text AS seviye,
    format('Siparislerin %s''inin odeme yontemi Wix checkout (PayTR) DISINDA: kapida odeme / havale / telefon. Bu satislarin tahsilati sistemde insan girisiyle tamamlanir (MANUAL_CONTROLLED_INPUT). NEDEN SOYLENMEZ: tercih mi zorunluluk mu oldugu OLCULMEDI.'::text, ( SELECT ((round(((100.0 * (count(*) FILTER (WHERE (wix_order.odeme_yontemi IS DISTINCT FROM 'PayTR'::text)))::numeric) / (NULLIF(count(*), 0))::numeric)))::text || '%'::text)
           FROM raw.wix_order)) AS bulgu,
    'Wix odeme yontemi (PayTR = Wix checkout saglayicisi, ayri kanal DEGIL)'::text AS kaynak
UNION ALL
 SELECT 'SORU_YUKU'::text AS kod,
    'INFERRED'::text AS seviye,
    format('Konusmalarin buyuk kismi icerik/fiyat soruyor; bu bilgiler sayfada bulunsaydi konusma gerekmezdi (%s konusma)'::text, ( SELECT count(DISTINCT mesaj.konusma_id) AS count
           FROM lcarlie.mesaj
          WHERE ((mesaj.yon = 'gelen'::text) AND ((mesaj.metin ~~* '%çindekiler%'::text) OR (mesaj.metin ~~* '%iyat%'::text))))) AS bulgu,
    'lcarlie.mesaj - dolayli cikarim'::text AS kaynak
UNION ALL
 SELECT 'DAVRANIS_VERISI'::text AS kod,
    'NOT_CONNECTED'::text AS seviye,
    'GA4/GTM verisi ambara AKMIYOR - sayfa gorunumu, sepet terk orani, huni adimlari OLCULEMIYOR'::text AS bulgu,
    'core.source_authority.behavior'::text AS kaynak
UNION ALL
 SELECT 'SAYFA_HIZI'::text AS kod,
    'HYPOTHESIS'::text AS seviye,
    'Sayfa hizinin donusume etkisi bu sistemde olculmedi; iyilestirme onerisi kanit gerektirir'::text AS bulgu,
    'test edilmemis'::text AS kaynak;


ALTER VIEW mart.cro_sinyal OWNER TO n8n;

--
-- Name: funnel_kapsama_matrisi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.funnel_kapsama_matrisi AS
 SELECT s.sayfa_yolu,
    s.sayfa_rolu,
    s.urun_id,
    u.ad AS urun_adi,
    f.adim_kod,
    f.sira AS adim_sira,
    f.ad AS adim_adi,
    f.ga4_event_adi,
    COALESCE(k.enstrumantasyon, 'NOT_TESTED'::text) AS enstrumantasyon,
    COALESCE(k.olcum_kaniti, 'Bu sayfada OLCULMEDI - kapsama BILINMIYOR.'::text) AS olcum_kaniti,
    (k.adim_kod IS NOT NULL) AS olculdu
   FROM (((core.sayfa_urun s
     CROSS JOIN core.funnel_adim f)
     LEFT JOIN core.funnel_sayfa_kapsama k ON (((k.sayfa = s.sayfa_yolu) AND (k.adim_kod = f.adim_kod))))
     LEFT JOIN raw.wix_urun u ON ((u.urun_id = s.urun_id)))
  WHERE ((s.urun_id IS NOT NULL) OR (f.adim_kod = ANY (ARRAY['LANDING'::text, 'VIEW_CART'::text, 'BEGIN_CHECKOUT'::text, 'PURCHASE'::text])))
  ORDER BY u.ad NULLS FIRST, s.sayfa_rolu, f.sira;


ALTER VIEW mart.funnel_kapsama_matrisi OWNER TO n8n;

--
-- Name: ga4_event; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.ga4_event (
    ga4_event_id bigint NOT NULL,
    event_name text NOT NULL,
    event_timestamp timestamp with time zone,
    event_date date NOT NULL,
    user_pseudo_id text,
    session_id text,
    page_location text,
    page_path text,
    source text,
    medium text,
    campaign text,
    content text,
    term text,
    transaction_id text,
    currency text,
    value numeric,
    item_id text,
    item_name text,
    quantity numeric,
    kanit_durumu text DEFAULT 'OBSERVED'::text NOT NULL,
    ham jsonb,
    cekim_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    granulerlik text DEFAULT 'EVENT'::text NOT NULL,
    CONSTRAINT ga4_event_granulerlik_check CHECK ((granulerlik = ANY (ARRAY['EVENT'::text, 'GUNLUK_TOPLAM'::text]))),
    CONSTRAINT ga4_event_kanit_durumu_check CHECK ((kanit_durumu = ANY (ARRAY['OBSERVED'::text, 'CONSENT_LIMITED'::text, 'SAMPLED'::text, 'SUSPECT'::text])))
);


ALTER TABLE raw.ga4_event OWNER TO n8n;

--
-- Name: ga4_siparis_mutabakat; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ga4_siparis_mutabakat AS
 WITH ga4 AS (
         SELECT count(*) AS purchase_event,
            count(*) FILTER (WHERE (ga4_event.transaction_id IS NOT NULL)) AS islem_kimlikli,
            count(*) FILTER (WHERE (ga4_event.transaction_id IS NULL)) AS islem_kimliksiz,
            count(DISTINCT ga4_event.transaction_id) AS tekil_islem,
            COALESCE(sum(ga4_event.value), (0)::numeric) AS gozlenen_deger
           FROM raw.ga4_event
          WHERE (ga4_event.event_name = 'purchase'::text)
        ), wix AS (
         SELECT count(*) AS siparis,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text]))) AS gerceklesmis,
            COALESCE(sum((siparis.toplam - siparis.kdv)) FILTER (WHERE (siparis.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text]))), (0)::numeric) AS net_ciro
           FROM mart.siparis
        ), es AS (
         SELECT count(*) FILTER (WHERE (w.siparis_id IS NOT NULL)) AS eslesen,
            count(*) FILTER (WHERE (w.siparis_id IS NULL)) AS ga4_only
           FROM (( SELECT DISTINCT ga4_event.transaction_id
                   FROM raw.ga4_event
                  WHERE ((ga4_event.event_name = 'purchase'::text) AND (ga4_event.transaction_id IS NOT NULL))) g
             LEFT JOIN mart.siparis w ON (((w.siparis_id = g.transaction_id) OR ((w.siparis_no)::text = g.transaction_id))))
        )
 SELECT ga4.purchase_event AS ga4_purchase_sayisi,
    ga4.tekil_islem AS ga4_tekil_islem,
    ga4.islem_kimliksiz AS ga4_islem_kimliksiz,
    round(ga4.gozlenen_deger, 2) AS ga4_gozlenen_deger,
    wix.siparis AS wix_siparis_sayisi,
    wix.gerceklesmis AS wix_gerceklesmis,
    round(wix.net_ciro, 2) AS wix_net_ciro,
    es.eslesen,
    es.ga4_only,
    (wix.siparis - es.eslesen) AS wix_only,
    (ga4.islem_kimlikli - ga4.tekil_islem) AS duplicate_islem,
        CASE
            WHEN ((ga4.purchase_event = 0) AND (wix.siparis > 0)) THEN 'GA4_TARAFI_OLCULMEDI'::text
            WHEN ((ga4.purchase_event = 0) AND (wix.siparis = 0)) THEN 'VERI_YOK'::text
            WHEN ((es.ga4_only > 0) OR ((wix.siparis - es.eslesen) > 0)) THEN 'AYRISMA_VAR'::text
            ELSE 'MUTABIK'::text
        END AS durum,
        CASE
            WHEN ((ga4.purchase_event = 0) AND (wix.siparis > 0)) THEN format('GA4 tarafinda 0 purchase event''i var, Wix tarafinda %s siparis. Bu "siparis yok" DEMEK DEGILDIR - GA4 Data API bagli degil ve purchase enstrumantasyonu TEST EDILMEDI. Ticari gercek Wix''tedir ve %s TL net ciro DEGISMEZ.'::text, wix.siparis, round(wix.net_ciro, 2))
            WHEN (es.ga4_only > 0) THEN format('%s GA4 purchase''i Wix siparisiyle ESLESMIYOR - tracking anomalisi. Bu bir ciro kaydi DEGILDIR.'::text, es.ga4_only)
            WHEN ((wix.siparis - es.eslesen) > 0) THEN format('Wix''teki %s siparisin %s tanesi GA4''te HIC GORUNMUYOR. Bu, o siparislerin olmadigi anlamina GELMEZ -- ticari gercek Wix''tedir. Anlami sudur: GA4 uzerinden "bu satisi hangi reklam getirdi" sorusu siparislerin yalniz %s%%''i icin cevaplanabilir, geri kalani icin KAYNAK BILINMIYOR.'::text, wix.siparis, (wix.siparis - es.eslesen), round(((100.0 * (es.eslesen)::numeric) / (NULLIF(wix.siparis, 0))::numeric), 0))
            ELSE 'Iki taraf mutabik.'::text
        END AS ifade
   FROM ga4,
    wix,
    es;


ALTER VIEW mart.ga4_siparis_mutabakat OWNER TO n8n;

--
-- Name: davranis_kapsama_matrisi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.davranis_kapsama_matrisi AS
 SELECT 1 AS sira,
    'SITE GA4 CONNECTION'::text AS boyut,
    ( SELECT source_authority.current_connection
           FROM core.source_authority
          WHERE (source_authority.alan = 'behavior_site_tracking'::text)) AS durum,
    'GA4 sitede canli, page_view gonderiyor (olculdu)'::text AS kanit
UNION ALL
 SELECT 2 AS sira,
    'GROWTH OS GA4 INGESTION'::text AS boyut,
    ( SELECT source_authority.current_connection
           FROM core.source_authority
          WHERE (source_authority.alan = 'behavior'::text)) AS durum,
    format('raw.ga4_event: %s satir · Data API credential: YOK'::text, ( SELECT count(*) AS count
           FROM raw.ga4_event)) AS kanit
UNION ALL
 SELECT 3 AS sira,
    'PAGE_VIEW COVERAGE'::text AS boyut,
    ( SELECT
                CASE
                    WHEN (count(*) FILTER (WHERE (funnel_sayfa_kapsama.enstrumantasyon = 'MEASURED'::text)) = count(*)) THEN 'MEASURED'::text
                    WHEN (count(*) FILTER (WHERE (funnel_sayfa_kapsama.enstrumantasyon = 'MEASURED'::text)) > 0) THEN 'PARTIAL'::text
                    ELSE 'NOT_MEASURED'::text
                END AS "case"
           FROM core.funnel_sayfa_kapsama
          WHERE (funnel_sayfa_kapsama.adim_kod = 'LANDING'::text)) AS durum,
    ( SELECT format('%s/%s OLCULEN sayfada page_view gozlendi (toplam kayitli sayfa: %s)'::text, count(*) FILTER (WHERE (funnel_sayfa_kapsama.enstrumantasyon = 'MEASURED'::text)), count(*), ( SELECT count(*) AS count
                   FROM core.sayfa_urun)) AS format
           FROM core.funnel_sayfa_kapsama
          WHERE (funnel_sayfa_kapsama.adim_kod = 'LANDING'::text)) AS kanit
UNION ALL
 SELECT 4 AS sira,
    'VIEW_ITEM COVERAGE — ozel landing (reklam trafigi)'::text AS boyut,
    ( SELECT COALESCE(string_agg(DISTINCT k.enstrumantasyon, '/'::text), 'NOT_TESTED'::text) AS "coalesce"
           FROM (core.funnel_sayfa_kapsama k
             JOIN core.sayfa_urun s ON ((s.sayfa_yolu = k.sayfa)))
          WHERE ((k.adim_kod = 'PRODUCT_VIEW'::text) AND (s.sayfa_rolu = ANY (ARRAY['OZEL_LANDING'::text, 'KAMPANYA_LANDING'::text])))) AS durum,
    ( SELECT format('%s ozel landing kayitli, %s tanesi olculdu'::text, ( SELECT count(*) AS count
                   FROM core.sayfa_urun
                  WHERE (sayfa_urun.sayfa_rolu = ANY (ARRAY['OZEL_LANDING'::text, 'KAMPANYA_LANDING'::text]))), count(*)) AS format
           FROM (core.funnel_sayfa_kapsama k
             JOIN core.sayfa_urun s ON ((s.sayfa_yolu = k.sayfa)))
          WHERE ((k.adim_kod = 'PRODUCT_VIEW'::text) AND (s.sayfa_rolu = ANY (ARRAY['OZEL_LANDING'::text, 'KAMPANYA_LANDING'::text])))) AS kanit
UNION ALL
 SELECT 5 AS sira,
    'VIEW_ITEM COVERAGE — native urun sayfasi'::text AS boyut,
    ( SELECT COALESCE(string_agg(DISTINCT k.enstrumantasyon, '/'::text), 'NOT_TESTED'::text) AS "coalesce"
           FROM (core.funnel_sayfa_kapsama k
             JOIN core.sayfa_urun s ON ((s.sayfa_yolu = k.sayfa)))
          WHERE ((k.adim_kod = 'PRODUCT_VIEW'::text) AND (s.sayfa_rolu = 'NATIVE_URUN'::text))) AS durum,
    ( SELECT format('%s native urun sayfasi kayitli, %s tanesi olculdu - kalanlar NOT_TESTED (kapsama varsayilmiyor)'::text, ( SELECT count(*) AS count
                   FROM core.sayfa_urun
                  WHERE (sayfa_urun.sayfa_rolu = 'NATIVE_URUN'::text)), count(*)) AS format
           FROM (core.funnel_sayfa_kapsama k
             JOIN core.sayfa_urun s ON ((s.sayfa_yolu = k.sayfa)))
          WHERE ((k.adim_kod = 'PRODUCT_VIEW'::text) AND (s.sayfa_rolu = 'NATIVE_URUN'::text))) AS kanit
UNION ALL
 SELECT 6 AS sira,
    'ADD_TO_CART COVERAGE'::text AS boyut,
    ( SELECT funnel_adim.enstrumantasyon
           FROM core.funnel_adim
          WHERE (funnel_adim.adim_kod = 'ADD_TO_CART'::text)) AS durum,
    'Tiklandi, urun sepete eklendi, GA4 istegi OLUSMADI'::text AS kanit
UNION ALL
 SELECT 7 AS sira,
    'BEGIN_CHECKOUT COVERAGE'::text AS boyut,
    ( SELECT funnel_adim.enstrumantasyon
           FROM core.funnel_adim
          WHERE (funnel_adim.adim_kod = 'BEGIN_CHECKOUT'::text)) AS durum,
    'Ayni alan adi + ayni GTM container -> teknik engel YOK'::text AS kanit
UNION ALL
 SELECT 8 AS sira,
    'PURCHASE COVERAGE'::text AS boyut,
    ( SELECT funnel_adim.enstrumantasyon
           FROM core.funnel_adim
          WHERE (funnel_adim.adim_kod = 'PURCHASE'::text)) AS durum,
    'Gercek siparis gerektirir - OLCULMEDI, tahmin URETILMEDI'::text AS kanit
UNION ALL
 SELECT 9 AS sira,
    'PURCHASE↔WIX RECONCILIATION'::text AS boyut,
    ( SELECT ga4_siparis_mutabakat.durum
           FROM mart.ga4_siparis_mutabakat) AS durum,
    ( SELECT format('GA4 %s / Wix %s · eslesen %s · GA4_ONLY %s · WIX_ONLY %s'::text, ga4_siparis_mutabakat.ga4_purchase_sayisi, ga4_siparis_mutabakat.wix_siparis_sayisi, ga4_siparis_mutabakat.eslesen, ga4_siparis_mutabakat.ga4_only, ga4_siparis_mutabakat.wix_only) AS format
           FROM mart.ga4_siparis_mutabakat) AS kanit
UNION ALL
 SELECT 10 AS sira,
    'META BROWSER PIXEL EVENT COVERAGE'::text AS boyut,
    ( SELECT ayar.deger
           FROM core.ayar
          WHERE (ayar.anahtar = 'meta_browser_pixel_event_coverage'::text)) AS durum,
    'Yalniz tarayici pikseli icin gecerli'::text AS kanit
UNION ALL
 SELECT 11 AS sira,
    'META TOTAL OPTIMIZATION SIGNAL'::text AS boyut,
    ( SELECT ayar.deger
           FROM core.ayar
          WHERE (ayar.anahtar = 'meta_total_optimization_signal'::text)) AS durum,
    'CAPI / server-side / native entegrasyon OLCULMEDI'::text AS kanit
UNION ALL
 SELECT 12 AS sira,
    'GOOGLE ADS TAG'::text AS boyut,
    ( SELECT ayar.deger
           FROM core.ayar
          WHERE (ayar.anahtar = 'kesif_google_ads_etiketi'::text)) AS durum,
    'Etiket bulundu; hesap/harcama DOGRULANMADI - blocker DEGIL'::text AS kanit
UNION ALL
 SELECT 13 AS sira,
    'URUN KAPSAMASI (funnel olcumu)'::text AS boyut,
    ( SELECT
                CASE
                    WHEN (count(DISTINCT funnel_kapsama_matrisi.urun_id) FILTER (WHERE funnel_kapsama_matrisi.olculdu) = 0) THEN 'NOT_TESTED'::text
                    WHEN (count(DISTINCT funnel_kapsama_matrisi.urun_id) FILTER (WHERE funnel_kapsama_matrisi.olculdu) < ( SELECT count(*) AS count
                       FROM raw.wix_urun)) THEN 'PARTIAL'::text
                    ELSE 'MEASURED'::text
                END AS "case"
           FROM mart.funnel_kapsama_matrisi
          WHERE (funnel_kapsama_matrisi.urun_id IS NOT NULL)) AS durum,
    ( SELECT format('%s/%s urunun funnel''i OLCULDU. Kalanlar NOT_TESTED - kapsamalari VARSAYILMIYOR.'::text, count(DISTINCT funnel_kapsama_matrisi.urun_id) FILTER (WHERE funnel_kapsama_matrisi.olculdu), ( SELECT count(*) AS count
                   FROM raw.wix_urun)) AS format
           FROM mart.funnel_kapsama_matrisi
          WHERE (funnel_kapsama_matrisi.urun_id IS NOT NULL)) AS kanit
UNION ALL
 SELECT 14 AS sira,
    'FIYAT GERCEGI KAPSAMASI'::text AS boyut,
    ( SELECT
                CASE
                    WHEN (count(*) FILTER (WHERE (urun_fiyat_gercegi.fiyat_durumu = 'UNKNOWN'::text)) = 0) THEN 'MEASURED'::text
                    WHEN (count(*) FILTER (WHERE (urun_fiyat_gercegi.fiyat_durumu <> 'UNKNOWN'::text)) > 0) THEN 'PARTIAL'::text
                    ELSE 'NOT_MEASURED'::text
                END AS "case"
           FROM core.urun_fiyat_gercegi) AS durum,
    ( SELECT format('%s/%s urunun isletme fiyat gercegi beyan edilmis'::text, count(*) FILTER (WHERE (urun_fiyat_gercegi.fiyat_durumu <> 'UNKNOWN'::text)), count(*)) AS format
           FROM core.urun_fiyat_gercegi) AS kanit
  ORDER BY 1;


ALTER VIEW mart.davranis_kapsama_matrisi OWNER TO n8n;

--
-- Name: departman_sagligi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.departman_sagligi AS
 SELECT aile,
    durum,
    count(*) AS departman,
    string_agg(kod, ', '::text ORDER BY kod) AS kodlar
   FROM core.departman d
  GROUP BY aile, durum
  ORDER BY aile,
        CASE durum
            WHEN 'CALISIYOR'::text THEN 0
            WHEN 'KISMI'::text THEN 1
            ELSE 2
        END;


ALTER VIEW mart.departman_sagligi OWNER TO n8n;

--
-- Name: maliyet_kalite; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.maliyet_kalite AS
 SELECT m.urun_id,
    u.ad AS urun_adi,
    u.fiyat,
    m.maliyet,
    m.kaynak,
    m.gerekce,
    COALESCE(( SELECT ayar.deger
           FROM core.ayar
          WHERE (ayar.anahtar = 'maliyet_kdv_tabani'::text)), 'TEYIT_EDILMEDI'::text) AS kdv_tabani,
        CASE
            WHEN (m.kaynak = 'WIX'::text) THEN 'OLCULMUS'::text
            WHEN ((m.gerekce ~~* '%ORTALAMA%'::text) OR (m.gerekce ~~* '%GERCEK URUN MALIYETI DEGIL%'::text)) THEN 'TAHMIN'::text
            WHEN (m.kaynak = 'ELLE'::text) THEN 'ELLE_BEYAN'::text
            ELSE 'BILINMIYOR'::text
        END AS kalite
   FROM (core.urun_maliyet m
     LEFT JOIN raw.wix_urun u ON ((u.urun_id = m.urun_id)))
  WHERE (m.gecerli_bitis IS NULL);


ALTER VIEW mart.maliyet_kalite OWNER TO n8n;

--
-- Name: siparis_ekonomi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.siparis_ekonomi AS
 WITH kalem AS (
         SELECT k.siparis_id,
            sum(k.satir_ciro_net) AS net_ciro,
            sum(k.satir_maliyet) AS cogs,
            count(*) FILTER (WHERE (NOT k.maliyeti_biliniyor)) AS cogs_eksik_kalem
           FROM mart.siparis_kalem k
          GROUP BY k.siparis_id
        ), kargo AS (
         SELECT g.siparis_id,
            sum(g.toplam_maliyet) AS kargo_maliyet,
            sum(g.cod_komisyon) AS cod_komisyon,
            count(*) FILTER (WHERE (g.cod_komisyon_sinifi = 'NOT_YET_KNOWN'::text)) AS cod_bekleyen,
            count(*) FILTER (WHERE (g.cod_komisyon_sinifi = 'UNKNOWN'::text)) AS cod_bilinmeyen
           FROM mart.gonderi g
          WHERE (g.siparis_id IS NOT NULL)
          GROUP BY g.siparis_id
        ), b AS (
         SELECT s.siparis_id,
            s.olusturma,
            s.ciro_sinifi,
            s.olcumde,
            s.teslimat_durumu,
            s.odeme_durumu,
            k.net_ciro,
                CASE
                    WHEN (( SELECT ayar.deger
                       FROM core.ayar
                      WHERE (ayar.anahtar = 'maliyet_kdv_tabani'::text)) = 'KDV_DAHIL'::text) THEN round((k.cogs / 1.2), 2)
                    ELSE k.cogs
                END AS cogs,
            k.cogs_eksik_kalem,
            kg.kargo_maliyet,
            kg.cod_komisyon,
            kg.cod_bekleyen,
            kg.cod_bilinmeyen,
            (kg.siparis_id IS NOT NULL) AS kargo_bagli,
            ( SELECT bilesen_bul.deger
                   FROM core.bilesen_bul('PAKETLEME'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS paketleme,
            ( SELECT bilesen_bul.kritiklik
                   FROM core.bilesen_bul('PAKETLEME'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS paketleme_kritiklik,
            ( SELECT bilesen_bul.deger
                   FROM core.bilesen_bul('ODEME_KOMISYONU'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS odeme_yuzde,
            ( SELECT bilesen_bul.kritiklik
                   FROM core.bilesen_bul('ODEME_KOMISYONU'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS odeme_kritiklik,
            ( SELECT bilesen_bul.deger
                   FROM core.bilesen_bul('KANAL_KOMISYONU'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS kanal_yuzde,
            ( SELECT bilesen_bul.kritiklik
                   FROM core.bilesen_bul('KANAL_KOMISYONU'::text, s.olusturma) bilesen_bul(deger, uygulama, kanit_sinifi, kritiklik)) AS kanal_kritiklik,
            ( SELECT ayar.deger
                   FROM core.ayar
                  WHERE (ayar.anahtar = 'maliyet_kdv_tabani'::text)) AS cogs_kdv_tabani,
            ( SELECT ayar.deger
                   FROM core.ayar
                  WHERE (ayar.anahtar = 'maliyet_kargo_dahil'::text)) AS cogs_kargo_dahil
           FROM ((mart.siparis s
             LEFT JOIN kalem k ON ((k.siparis_id = s.siparis_id)))
             LEFT JOIN kargo kg ON ((kg.siparis_id = s.siparis_id)))
        ), h AS (
         SELECT b.siparis_id,
            b.olusturma,
            b.ciro_sinifi,
            b.olcumde,
            b.teslimat_durumu,
            b.odeme_durumu,
            b.net_ciro,
            b.cogs,
            b.cogs_eksik_kalem,
            b.kargo_maliyet,
            b.cod_komisyon,
            b.cod_bekleyen,
            b.cod_bilinmeyen,
            b.kargo_bagli,
            b.paketleme,
            b.paketleme_kritiklik,
            b.odeme_yuzde,
            b.odeme_kritiklik,
            b.kanal_yuzde,
            b.kanal_kritiklik,
            b.cogs_kdv_tabani,
            b.cogs_kargo_dahil,
            ((((((COALESCE(b.net_ciro, (0)::numeric) - COALESCE(b.cogs, (0)::numeric)) -
                CASE
                    WHEN (b.cogs_kargo_dahil = 'EVET'::text) THEN (0)::numeric
                    ELSE COALESCE(b.kargo_maliyet, (0)::numeric)
                END) - COALESCE(b.cod_komisyon, (0)::numeric)) - COALESCE(b.paketleme, (0)::numeric)) - COALESCE(((COALESCE(b.net_ciro, (0)::numeric) * b.odeme_yuzde) / 100.0), (0)::numeric)) - COALESCE(((COALESCE(b.net_ciro, (0)::numeric) * b.kanal_yuzde) / 100.0), (0)::numeric)) AS katki,
                CASE
                    WHEN ((b.cogs_kdv_tabani IS NULL) AND (b.cogs IS NOT NULL)) THEN round((b.cogs - (b.cogs / 1.2)), 2)
                    ELSE (0)::numeric
                END AS cogs_kdv_lehte_duzeltme,
            array_remove(ARRAY[
                CASE
                    WHEN ((b.cogs IS NULL) OR (b.cogs_eksik_kalem > 0)) THEN 'urun_cogs'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN ((NOT b.kargo_bagli) AND (COALESCE(b.cogs_kargo_dahil, 'HAYIR'::text) <> 'EVET'::text)) THEN 'giden_kargo(siparis-gonderi bagi yok)'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN (COALESCE(b.cod_bilinmeyen, (0)::bigint) > 0) THEN 'cod_komisyonu(UNKNOWN)'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN ((b.odeme_yuzde IS NULL) AND (b.odeme_kritiklik = 'CRITICAL'::text)) THEN 'odeme_komisyonu'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN ((b.kanal_yuzde IS NULL) AND (b.kanal_kritiklik = 'CRITICAL'::text)) THEN 'kanal_komisyonu'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN (b.teslimat_durumu = 'CANCELED'::text) THEN 'iade_ekonomisi(UNKNOWN)'::text
                    ELSE NULL::text
                END], NULL::text) AS kritik_eksik,
            array_remove(ARRAY[
                CASE
                    WHEN ((b.paketleme IS NULL) AND (b.paketleme_kritiklik = 'SECONDARY'::text)) THEN 'paketleme'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN (COALESCE(b.cod_bekleyen, (0)::bigint) > 0) THEN 'cod_komisyonu(NOT_YET_KNOWN)'::text
                    ELSE NULL::text
                END,
                CASE
                    WHEN (b.cogs_kdv_tabani IS NULL) THEN 'cogs_kdv_tabani(yon: katkiyi ARTIRABILIR)'::text
                    ELSE NULL::text
                END], NULL::text) AS ikincil_eksik
           FROM b
        )
 SELECT siparis_id,
    olusturma,
    ciro_sinifi,
    olcumde,
    teslimat_durumu,
    odeme_durumu,
    round(COALESCE(net_ciro, (0)::numeric), 2) AS net_ciro_kdv_haric,
        CASE
            WHEN (ciro_sinifi = 'IPTAL'::text) THEN 'IPTAL'::text
            WHEN (ciro_sinifi = 'ODENMEDI'::text) THEN 'BOOKED_NOT_REALIZED'::text
            WHEN (ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text])) THEN 'REALIZED'::text
            ELSE 'BILINMIYOR'::text
        END AS gelir_durumu,
    (0)::numeric AS kargo_geliri,
    round(cogs, 2) AS cogs,
    round(kargo_maliyet, 2) AS kargo_maliyet,
    round(cod_komisyon, 2) AS cod_komisyon,
    paketleme,
        CASE
            WHEN (odeme_yuzde IS NOT NULL) THEN round(((COALESCE(net_ciro, (0)::numeric) * odeme_yuzde) / 100.0), 2)
            ELSE NULL::numeric
        END AS odeme_komisyonu,
        CASE
            WHEN (kanal_yuzde IS NOT NULL) THEN round(((COALESCE(net_ciro, (0)::numeric) * kanal_yuzde) / 100.0), 2)
            ELSE NULL::numeric
        END AS kanal_komisyonu,
    round(katki, 2) AS bilinen_bilesen_katkisi,
    cogs_kdv_lehte_duzeltme,
    round((katki + cogs_kdv_lehte_duzeltme), 2) AS en_iyi_olasi_katki,
    kritik_eksik,
    ikincil_eksik,
    (kritik_eksik || ikincil_eksik) AS eksik_bilesenler,
        CASE
            WHEN (cardinality(kritik_eksik) > 0) THEN 'INCOMPLETE'::text
            WHEN (cardinality(ikincil_eksik) > 0) THEN 'PARTIAL'::text
            ELSE 'COMPLETE'::text
        END AS tamlik,
    (cardinality(kritik_eksik) = 0) AS ekonomik_dogrulanmis,
        CASE
            WHEN (cogs IS NULL) THEN 'UNKNOWN'::text
            ELSE COALESCE(( SELECT
                    CASE
                        WHEN bool_and((mk.kalite = 'OLCULMUS'::text)) THEN 'MEASURED'::text
                        ELSE 'BUSINESS_INPUT'::text
                    END AS "case"
               FROM (mart.siparis_kalem k2
                 JOIN mart.maliyet_kalite mk ON ((mk.urun_id = k2.urun_id)))
              WHERE (k2.siparis_id = h.siparis_id)), 'UNKNOWN'::text)
        END AS cogs_kanit_sinifi
   FROM h;


ALTER VIEW mart.siparis_ekonomi OWNER TO n8n;

--
-- Name: meta_harcama; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.meta_harcama (
    gun date NOT NULL,
    hesap_id text NOT NULL,
    kampanya_id text NOT NULL,
    kaynak text DEFAULT 'META_API'::text NOT NULL,
    kampanya_adi text,
    harcama numeric(14,2),
    para_birimi text,
    gosterim bigint,
    erisim bigint,
    tiklama bigint,
    link_tiklama bigint,
    cpm numeric(14,4),
    cpc numeric(14,4),
    ctr numeric(10,6),
    sikligi numeric(10,4),
    meta_donusum numeric(14,2),
    meta_donusum_degeri numeric(14,2),
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT meta_harcama_kaynak_check CHECK ((kaynak = ANY (ARRAY['META_API'::text, 'ELLE'::text])))
);


ALTER TABLE raw.meta_harcama OWNER TO n8n;

--
-- Name: ekonomi_gunluk; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ekonomi_gunluk AS
 WITH gunler AS (
         SELECT ((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun
           FROM raw.wix_order
        UNION
         SELECT meta_harcama.gun
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
        ), sip AS (
         SELECT ((e.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            count(*) AS siparis,
            count(*) FILTER (WHERE (e.gelir_durumu = 'REALIZED'::text)) AS gerceklesmis,
            count(*) FILTER (WHERE (e.tamlik = 'COMPLETE'::text)) AS tam,
            count(*) FILTER (WHERE (e.tamlik = 'PARTIAL'::text)) AS kismi,
            count(*) FILTER (WHERE (e.tamlik = 'INCOMPLETE'::text)) AS eksik,
            sum(e.net_ciro_kdv_haric) FILTER (WHERE (e.gelir_durumu = 'REALIZED'::text)) AS net_ciro,
            sum(e.bilinen_bilesen_katkisi) FILTER (WHERE (e.gelir_durumu = 'REALIZED'::text)) AS bilinen_katki,
            sum(e.en_iyi_olasi_katki) FILTER (WHERE (e.gelir_durumu = 'REALIZED'::text)) AS ust_sinir,
            sum(e.bilinen_bilesen_katkisi) FILTER (WHERE (e.ekonomik_dogrulanmis AND (e.gelir_durumu = 'REALIZED'::text))) AS dogrulanmis_katki
           FROM mart.siparis_ekonomi e
          GROUP BY (((e.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date)
        ), rek AS (
         SELECT meta_harcama.gun,
            sum(meta_harcama.harcama) AS harcama
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
          GROUP BY meta_harcama.gun
        )
 SELECT g.gun,
    COALESCE(s.siparis, (0)::bigint) AS siparis,
    COALESCE(s.gerceklesmis, (0)::bigint) AS gerceklesmis_siparis,
    COALESCE(s.tam, (0)::bigint) AS ekonomi_tam,
    COALESCE(s.kismi, (0)::bigint) AS ekonomi_kismi,
    COALESCE(s.eksik, (0)::bigint) AS ekonomi_eksik,
    round(COALESCE(s.net_ciro, (0)::numeric), 2) AS net_ciro,
    round(COALESCE(s.bilinen_katki, (0)::numeric), 2) AS bilinen_bilesen_katkisi,
    round(COALESCE(s.ust_sinir, (0)::numeric), 2) AS katki_ust_siniri,
    round(COALESCE(s.dogrulanmis_katki, (0)::numeric), 2) AS dogrulanmis_katki,
    round(COALESCE(r.harcama, (0)::numeric), 2) AS reklam_harcamasi,
    round((COALESCE(s.bilinen_katki, (0)::numeric) - COALESCE(r.harcama, (0)::numeric)), 2) AS reklam_sonrasi_katki,
    round((COALESCE(s.ust_sinir, (0)::numeric) - COALESCE(r.harcama, (0)::numeric)), 2) AS reklam_sonrasi_ust_sinir,
        CASE
            WHEN (COALESCE(s.siparis, (0)::bigint) = 0) THEN NULL::numeric
            ELSE round(((100.0 * (s.tam)::numeric) / (s.siparis)::numeric), 1)
        END AS ekonomi_tamlik_yuzde,
        CASE
            WHEN ((COALESCE(s.siparis, (0)::bigint) = 0) AND (COALESCE(r.harcama, (0)::numeric) = (0)::numeric)) THEN 'VERI_YOK'::text
            WHEN (COALESCE(s.siparis, (0)::bigint) = 0) THEN 'HARCAMA_VAR_SIPARIS_YOK'::text
            WHEN (COALESCE(s.tam, (0)::bigint) = 0) THEN 'EKONOMI_OLCULEMEDI'::text
            WHEN (s.tam < s.siparis) THEN 'EKONOMI_KISMI'::text
            ELSE 'EKONOMI_TAM'::text
        END AS ekonomi_durumu
   FROM ((gunler g
     LEFT JOIN sip s ON ((s.gun = g.gun)))
     LEFT JOIN rek r ON ((r.gun = g.gun)))
  ORDER BY g.gun DESC;


ALTER VIEW mart.ekonomi_gunluk OWNER TO n8n;

--
-- Name: ekonomi_veri_kalitesi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ekonomi_veri_kalitesi AS
 SELECT m.bilesen AS kalem,
    m.kanit_sinifi AS durum,
        CASE
            WHEN (m.deger IS NULL) THEN format('[%s] deger BILINMIYOR (%s) - 0 TL SAYILMIYOR. %s'::text, m.kritiklik, m.kaynak, m.gerekce)
            ELSE format('[%s] %s %s (%s)'::text, m.kritiklik, m.deger, m.uygulama, m.kdv_tabani)
        END AS aciklama,
        CASE
            WHEN ((m.deger IS NULL) AND (m.kritiklik = 'CRITICAL'::text)) THEN 'siparis ekonomisi INCOMPLETE'::text
            WHEN (m.deger IS NULL) THEN 'ekonomi PARTIAL - katki IYIMSER'::text
            ELSE 'hesaba giriyor'::text
        END AS etki
   FROM core.maliyet_bileseni m
  WHERE (m.gecerli_bitis IS NULL)
UNION ALL
 SELECT 'Urun COGS kalitesi'::text AS kalem,
        CASE
            WHEN (( SELECT count(*) AS count
               FROM mart.maliyet_kalite
              WHERE (maliyet_kalite.kalite = 'OLCULMUS'::text)) > 0) THEN 'PARTIAL'::text
            ELSE 'BUSINESS_INPUT'::text
        END AS durum,
    format('%s urunun %s''i sahip beyani, olculmus %s'::text, ( SELECT count(*) AS count
           FROM mart.maliyet_kalite), ( SELECT count(*) AS count
           FROM mart.maliyet_kalite
          WHERE (maliyet_kalite.kalite = 'TAHMIN'::text)), ( SELECT count(*) AS count
           FROM mart.maliyet_kalite
          WHERE (maliyet_kalite.kalite = 'OLCULMUS'::text))) AS aciklama,
    'katki OLDUGUNDAN IYIMSER olabilir'::text AS etki
UNION ALL
 SELECT 'COGS KDV tabani'::text AS kalem,
        CASE
            WHEN (( SELECT ayar.deger
               FROM core.ayar
              WHERE (ayar.anahtar = 'maliyet_kdv_tabani'::text)) IS NULL) THEN 'UNKNOWN_BUSINESS_INPUT_REQUIRED'::text
            ELSE 'BUSINESS_INPUT'::text
        END AS durum,
    format('400 TL beyaninin KDV dahil mi haric mi oldugu TEYIT EDILMEDI. KDV DAHIL ise gercek COGS 333,33''tur ve katki ARTAR. Etki (son 30 gun, gerceklesmis): %s TL'::text, ( SELECT to_char(COALESCE(sum(siparis_ekonomi.cogs_kdv_lehte_duzeltme), (0)::numeric), 'FM999990.00'::text) AS to_char
           FROM mart.siparis_ekonomi
          WHERE ((siparis_ekonomi.gelir_durumu = 'REALIZED'::text) AND (((siparis_ekonomi.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30))))) AS aciklama,
    'katkiyi ARTIRABILIR - diger eksiklerin TERSI yon'::text AS etki
UNION ALL
 SELECT 'Kargo-siparis bagi'::text AS kalem,
        CASE
            WHEN (( SELECT count(*) AS count
               FROM mart.gonderi
              WHERE (gonderi.siparis_id IS NOT NULL)) = ( SELECT count(*) AS count
               FROM mart.gonderi)) THEN 'MEASURED'::text
            ELSE 'PARTIAL'::text
        END AS durum,
    format('%s siparisin kargosu deterministik bagli (%s gonderinin %s''inde foreignCode var). Bagsiz sipariste kargo UNKNOWN - ortalama DAGITILMIYOR.'::text, ( SELECT count(DISTINCT gonderi.siparis_id) AS count
           FROM mart.gonderi
          WHERE (gonderi.siparis_id IS NOT NULL)), ( SELECT count(*) AS count
           FROM mart.gonderi), ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.siparis_id IS NOT NULL))) AS aciklama,
    'bagsiz siparisler INCOMPLETE (CRITICAL)'::text AS etki
UNION ALL
 SELECT 'COD komisyonu'::text AS kalem,
    'PARTIAL'::text AS durum,
    format('%s kapida odemeli gonderinin %s''inde komisyon OLCULDU; %s''i tahsilat bekliyor'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE gonderi.cod_var), ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.cod_komisyon_sinifi = 'MEASURED'::text)), ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.cod_komisyon_sinifi = 'NOT_YET_KNOWN'::text))) AS aciklama,
    'NOT_YET_KNOWN zamanla kendiliginden kapanir (SECONDARY)'::text AS etki
UNION ALL
 SELECT 'Numune/tester urun maliyeti'::text AS kalem,
    'UNKNOWN'::text AS durum,
    format('%s gonderinin urun maliyeti BAGLANAMIYOR: BasitKargo''da productId YOK. Ad eslesmesi yalniz ONERI uretebilir, otoriter baglama YAPILMAZ.'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = ANY (ARRAY['NUMUNE'::text, 'UNKNOWN'::text])))) AS aciklama,
    'hicbir siparise yazilmiyor'::text AS etki
UNION ALL
 SELECT 'Iade/refund ekonomisi'::text AS kalem,
    'UNKNOWN'::text AS durum,
    format('%s iptal siparis, %s iade gonderisi. Iade TUTARI, kismi iade, geri kazanilan stok ve geri kazanilamayan komisyon AYRISTIRILAMIYOR - kayit yapisi YOK.'::text, ( SELECT count(*) AS count
           FROM raw.wix_order
          WHERE (wix_order.teslimat_durumu = 'CANCELED'::text)), ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'IADE'::text))) AS aciklama,
    'iptal siparisler INCOMPLETE (CRITICAL)'::text AS etki;


ALTER VIEW mart.ekonomi_veri_kalitesi OWNER TO n8n;

--
-- Name: gonderi_eslestirme; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gonderi_eslestirme AS
 WITH aday AS (
         SELECT b.gonderi_id,
            b.barkod,
            b.olusturma AS gonderi_zamani,
            b.sehir,
            COALESCE(b.siparis_tutari, b.cod_tutar) AS gonderi_tutari,
            w.siparis_id,
            w.siparis_no,
            w.toplam
           FROM (raw.bk_shipment b
             LEFT JOIN raw.wix_order w ON (((round(w.toplam, 2) = round(COALESCE(b.siparis_tutari, b.cod_tutar), 2)) AND (b.olusturma >= w.olusturma) AND (b.olusturma <= (w.olusturma + '7 days'::interval)) AND (NOT (EXISTS ( SELECT 1
                   FROM raw.bk_shipment b2
                  WHERE (b2.foreign_code = w.siparis_id)))))))
          WHERE (((b.foreign_code IS NULL) OR (NOT (EXISTS ( SELECT 1
                   FROM raw.wix_order w2
                  WHERE (w2.siparis_id = b.foreign_code))))) AND (b.yon IS DISTINCT FROM 'INCOMING'::text))
        ), sayim AS (
         SELECT aday.gonderi_id,
            count(aday.siparis_id) AS aday_sayisi
           FROM aday
          GROUP BY aday.gonderi_id
        )
 SELECT b.gonderi_id,
    b.barkod,
    b.sehir,
    b.foreign_code AS siparis_id,
    w.siparis_no,
    'MATCHED'::text AS sinif,
    'foreign_code'::text AS yontem,
    1 AS aday_sayisi,
    'BasitKargo kaydinda Wix siparis kimligi var'::text AS gerekce
   FROM (raw.bk_shipment b
     JOIN raw.wix_order w ON ((w.siparis_id = b.foreign_code)))
UNION ALL
 SELECT a.gonderi_id,
    a.barkod,
    a.sehir,
    a.siparis_id,
    a.siparis_no,
    'MATCHED'::text AS sinif,
    'tutar+tarih'::text AS yontem,
    1 AS aday_sayisi,
    format('tutar %s TL birebir, gonderi siparisten %s gun sonra'::text, to_char(a.gonderi_tutari, 'FM999990.00'::text), ((a.gonderi_zamani)::date - ( SELECT (w3.olusturma)::date AS olusturma
           FROM raw.wix_order w3
          WHERE (w3.siparis_id = a.siparis_id)))) AS gerekce
   FROM (aday a
     JOIN sayim s USING (gonderi_id))
  WHERE ((s.aday_sayisi = 1) AND (a.siparis_id IS NOT NULL))
UNION ALL
 SELECT a.gonderi_id,
    a.barkod,
    a.sehir,
    NULL::text AS siparis_id,
    NULL::bigint AS siparis_no,
    'AMBIGUOUS'::text AS sinif,
    'tutar+tarih'::text AS yontem,
    s.aday_sayisi,
    format('%s siparis ayni tutar/pencereye uyuyor - ZORLA BIRLESTIRILMEDI'::text, s.aday_sayisi) AS gerekce
   FROM (( SELECT DISTINCT aday.gonderi_id,
            aday.barkod,
            aday.sehir
           FROM aday) a
     JOIN sayim s USING (gonderi_id))
  WHERE (s.aday_sayisi > 1)
UNION ALL
 SELECT a.gonderi_id,
    a.barkod,
    a.sehir,
    NULL::text AS siparis_id,
    NULL::bigint AS siparis_no,
    'UNMATCHED'::text AS sinif,
    'yok'::text AS yontem,
    0 AS aday_sayisi,
        CASE
            WHEN (a.gonderi_tutari IS NULL) THEN 'gonderide tutar bilgisi YOK - eslestirilecek sinyal yok'::text
            ELSE 'tutar/tarih penceresinde eslesen siparis yok'::text
        END AS gerekce
   FROM (( SELECT DISTINCT ON (aday.gonderi_id) aday.gonderi_id,
            aday.barkod,
            aday.sehir,
            aday.gonderi_tutari
           FROM aday
          ORDER BY aday.gonderi_id) a
     JOIN sayim s USING (gonderi_id))
  WHERE (s.aday_sayisi = 0);


ALTER VIEW mart.gonderi_eslestirme OWNER TO n8n;

--
-- Name: eslestirme_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.eslestirme_ozet AS
 WITH gon AS (
         SELECT gonderi_eslestirme.sinif,
            count(*) AS adet
           FROM mart.gonderi_eslestirme
          GROUP BY gonderi_eslestirme.sinif
        ), gon_t AS (
         SELECT count(*) AS toplam
           FROM raw.bk_shipment
        ), sip AS (
         SELECT count(*) AS toplam,
            count(*) FILTER (WHERE (EXISTS ( SELECT 1
                   FROM mart.gonderi_eslestirme e
                  WHERE ((e.siparis_id = w.siparis_id) AND (e.sinif = 'MATCHED'::text))))) AS eslesen,
            count(*) FILTER (WHERE ((NOT (EXISTS ( SELECT 1
                   FROM mart.gonderi_eslestirme e
                  WHERE ((e.siparis_id = w.siparis_id) AND (e.sinif = 'MATCHED'::text))))) AND (EXISTS ( SELECT 1
                   FROM raw.bk_shipment b
                  WHERE ((round(b.siparis_tutari, 2) = round(w.toplam, 2)) OR (round(b.cod_tutar, 2) = round(w.toplam, 2))))))) AS belirsiz
           FROM raw.wix_order w
        )
 SELECT 'ORDER SIDE'::text AS taraf,
    sip.toplam,
    sip.eslesen AS matched,
    sip.belirsiz AS ambiguous,
    ((sip.toplam - sip.eslesen) - sip.belirsiz) AS unmatched,
    round(((100.0 * (sip.eslesen)::numeric) / (NULLIF(sip.toplam, 0))::numeric), 1) AS match_rate_yuzde
   FROM sip
UNION ALL
 SELECT 'SHIPMENT SIDE'::text AS taraf,
    gon_t.toplam,
    COALESCE(( SELECT gon.adet
           FROM gon
          WHERE (gon.sinif = 'MATCHED'::text)), (0)::bigint) AS matched,
    COALESCE(( SELECT gon.adet
           FROM gon
          WHERE (gon.sinif = 'AMBIGUOUS'::text)), (0)::bigint) AS ambiguous,
    COALESCE(( SELECT gon.adet
           FROM gon
          WHERE (gon.sinif = 'UNMATCHED'::text)), (0)::bigint) AS unmatched,
    round(((100.0 * (COALESCE(( SELECT gon.adet
           FROM gon
          WHERE (gon.sinif = 'MATCHED'::text)), (0)::bigint))::numeric) / (NULLIF(gon_t.toplam, 0))::numeric), 1) AS match_rate_yuzde
   FROM gon_t;


ALTER VIEW mart.eslestirme_ozet OWNER TO n8n;

--
-- Name: fiyat_gercegi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.fiyat_gercegi AS
 WITH w AS (
         SELECT u.urun_id,
            u.ad,
            ((u.ham #>> '{priceData,price}'::text[]))::numeric AS wix_liste,
            ((u.ham #>> '{priceData,discountedPrice}'::text[]))::numeric AS wix_satis,
            (u.ham #>> '{visible}'::text[]) AS wix_yayinda
           FROM raw.wix_urun u
        )
 SELECT f.urun_id,
    w.ad AS urun_adi,
    f.base_price,
    f.kampanya_fiyati,
    f.fiyat_durumu,
    f.kampanya_suresi,
    f.kampanya_kaynagi,
    f.kampanya_bitisi,
    f.karsilastirma_izni,
    w.wix_liste,
    w.wix_satis,
    w.wix_yayinda,
        CASE
            WHEN (f.fiyat_durumu = 'CAMPAIGN'::text) THEN f.kampanya_fiyati
            WHEN (f.fiyat_durumu = 'NORMAL'::text) THEN f.base_price
            ELSE NULL::numeric
        END AS beklenen_satis,
        CASE
            WHEN (f.fiyat_durumu = 'CAMPAIGN'::text) THEN f.kampanya_fiyati
            WHEN (f.fiyat_durumu = 'NORMAL'::text) THEN f.base_price
            ELSE w.wix_satis
        END AS musteriye_soylenecek_fiyat,
        CASE
            WHEN ((f.fiyat_durumu = 'UNKNOWN'::text) AND (w.wix_satis IS NOT NULL)) THEN 'WIX_AUTHORITATIVE'::text
            WHEN (f.fiyat_durumu = 'UNKNOWN'::text) THEN 'FIYAT_YOK'::text
            WHEN ((w.wix_satis IS NULL) OR (w.wix_liste IS NULL)) THEN 'WIX_OKUNAMADI'::text
            WHEN ((w.wix_satis IS DISTINCT FROM
            CASE
                WHEN (f.fiyat_durumu = 'CAMPAIGN'::text) THEN f.kampanya_fiyati
                ELSE f.base_price
            END) OR (w.wix_liste IS DISTINCT FROM f.base_price)) THEN 'PRICE_TRUTH_MISMATCH'::text
            ELSE 'MATCH'::text
        END AS durum,
        CASE
            WHEN ((f.fiyat_durumu = 'UNKNOWN'::text) AND (w.wix_satis IS NOT NULL)) THEN format('%s: %s TL. Kaynak Wix vitrini. Isletme ayrica fiyat beyan etmedi; sahip karariyla (20.09.2026) Wix fiyat otoritesidir.'::text, w.ad, w.wix_satis)
            WHEN (f.fiyat_durumu = 'UNKNOWN'::text) THEN format('%s: fiyat YOK. Ne isletme beyani ne Wix fiyati okunabildi.'::text, w.ad)
            WHEN ((w.wix_satis IS DISTINCT FROM
            CASE
                WHEN (f.fiyat_durumu = 'CAMPAIGN'::text) THEN f.kampanya_fiyati
                ELSE f.base_price
            END) OR (w.wix_liste IS DISTINCT FROM f.base_price)) THEN format('PRICE_TRUTH_MISMATCH (%s). Isletme: base %s, %s fiyati %s. Wix vitrini: liste %s, satis %s. SISTEM HICBIR TARAFI OTOMATIK DUZELTMEZ - iki kaynak da doluysa insan karari gerekir.'::text, w.ad, f.base_price, f.fiyat_durumu, f.kampanya_fiyati, w.wix_liste, w.wix_satis)
            ELSE format('MATCH (%s): isletme gercegi ile Wix vitrini ortusuyor.'::text, w.ad)
        END AS aciklama,
        CASE
            WHEN (f.fiyat_durumu = ANY (ARRAY['CAMPAIGN'::text, 'NORMAL'::text])) THEN 'BEYAN'::text
            WHEN (w.wix_satis IS NOT NULL) THEN 'WIX'::text
            ELSE 'YOK'::text
        END AS fiyat_kaynagi
   FROM (core.urun_fiyat_gercegi f
     JOIN w ON ((w.urun_id = f.urun_id)));


ALTER VIEW mart.fiyat_gercegi OWNER TO n8n;

--
-- Name: funnel_saglik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.funnel_saglik AS
 WITH veri AS (
         SELECT f_1.adim_kod,
            count(e.ga4_event_id) AS event_satiri,
            max(e.event_timestamp) AS son_event,
            count(*) FILTER (WHERE (e.kanit_durumu = 'CONSENT_LIMITED'::text)) AS consent_kisitli
           FROM (core.funnel_adim f_1
             LEFT JOIN raw.ga4_event e ON ((e.event_name = f_1.ga4_event_adi)))
          GROUP BY f_1.adim_kod
        )
 SELECT f.sira,
    f.adim_kod,
    f.ad,
    f.ga4_event_adi,
    f.enstrumantasyon,
    v.event_satiri,
    v.son_event,
        CASE
            WHEN (v.event_satiri > 0) THEN 'AKIYOR'::text
            WHEN (f.enstrumantasyon = 'NOT_INSTRUMENTED'::text) THEN 'ENSTRUMANTASYON_YOK'::text
            WHEN (f.enstrumantasyon = 'NOT_TESTED'::text) THEN 'TEST_EDILMEDI'::text
            ELSE 'ETL_YOK'::text
        END AS veri_akisi,
        CASE
            WHEN (v.event_satiri > 0) THEN 'OBSERVED'::text
            WHEN ((f.enstrumantasyon = 'MEASURED'::text) AND (EXISTS ( SELECT 1
               FROM raw.ga4_event))) THEN 'NOT_OBSERVED'::text
            ELSE 'NOT_MEASURED'::text
        END AS gozlem_durumu,
        CASE
            WHEN (v.event_satiri > 0) THEN format('%s satir gozlendi (son: %s)'::text, v.event_satiri, to_char((v.son_event AT TIME ZONE 'Europe/Istanbul'::text), 'DD.MM HH24:MI'::text))
            WHEN (f.enstrumantasyon = 'NOT_INSTRUMENTED'::text) THEN 'ENSTRUMANTASYON YOK - olay gerceklesse bile olculmez. "0" YAZILAMAZ.'::text
            WHEN (f.enstrumantasyon = 'NOT_TESTED'::text) THEN 'TEST EDILMEDI - dogrulamak gercek siparis gerektirir (insan onayi).'::text
            WHEN (f.enstrumantasyon = ANY (ARRAY['MEASURED'::text, 'PARTIAL'::text])) THEN 'Tarayicida event GONDERILIYOR ama ambara AKMIYOR (GA4 Data API bagli degil).'::text
            ELSE 'Durum bilinmiyor.'::text
        END AS ifade,
    f.olcum_kaniti,
    f.olcum_yeri,
    f.notlar
   FROM (core.funnel_adim f
     JOIN veri v ON ((v.adim_kod = f.adim_kod)))
  ORDER BY f.sira;


ALTER VIEW mart.funnel_saglik OWNER TO n8n;

--
-- Name: funnel_orani; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.funnel_orani AS
 WITH a AS (
         SELECT funnel_saglik.adim_kod,
            funnel_saglik.sira,
            funnel_saglik.ad,
            funnel_saglik.enstrumantasyon,
            funnel_saglik.event_satiri,
            funnel_saglik.gozlem_durumu
           FROM mart.funnel_saglik
        ), ciftler AS (
         SELECT u.adim_kod AS ust_kod,
            u.ad AS ust_ad,
            u.event_satiri AS ust_sayi,
            u.gozlem_durumu AS ust_durum,
            u.enstrumantasyon AS ust_ens,
            a.adim_kod AS alt_kod,
            a.ad AS alt_ad,
            a.event_satiri AS alt_sayi,
            a.gozlem_durumu AS alt_durum,
            a.enstrumantasyon AS alt_ens
           FROM (a u
             JOIN a ON ((a.sira = (u.sira + 1))))
        )
 SELECT ust_kod,
    ust_ad,
    alt_kod,
    alt_ad,
        CASE
            WHEN ((ust_durum = 'OBSERVED'::text) AND (alt_durum = 'OBSERVED'::text) AND (ust_sayi > 0)) THEN round(((100.0 * (alt_sayi)::numeric) / (ust_sayi)::numeric), 1)
            ELSE NULL::numeric
        END AS oran_yuzde,
        CASE
            WHEN ((ust_durum = 'OBSERVED'::text) AND (alt_durum = 'OBSERVED'::text) AND (ust_sayi > 0)) THEN 'HESAPLANDI'::text
            ELSE 'NOT_MEASURABLE'::text
        END AS oran_durumu,
        CASE
            WHEN ((ust_durum = 'OBSERVED'::text) AND (alt_durum = 'OBSERVED'::text) AND (ust_sayi > 0)) THEN round(((100.0 * ((ust_sayi - alt_sayi))::numeric) / (ust_sayi)::numeric), 1)
            ELSE NULL::numeric
        END AS dusus_yuzde,
        CASE
            WHEN ((ust_durum = 'OBSERVED'::text) AND (alt_durum = 'OBSERVED'::text) AND (ust_sayi > 0)) THEN format('%s -> %s: %s%%'::text, ust_ad, alt_ad, round(((100.0 * (alt_sayi)::numeric) / (ust_sayi)::numeric), 1))
            WHEN (alt_ens = 'NOT_INSTRUMENTED'::text) THEN format('NOT_MEASURABLE - "%s" enstrumantasyonu YOK. Oran 0 DEGIL, BILINMIYOR.'::text, alt_ad)
            WHEN (ust_ens = 'NOT_INSTRUMENTED'::text) THEN format('NOT_MEASURABLE - payda "%s" olculmuyor.'::text, ust_ad)
            ELSE 'NOT_MEASURABLE - veri ambara akmiyor (GA4 Data API bagli degil).'::text
        END AS ifade
   FROM ciftler
  ORDER BY ust_kod;


ALTER VIEW mart.funnel_orani OWNER TO n8n;

--
-- Name: guncel_olaylar; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.guncel_olaylar AS
 SELECT o.gun,
    o.aci,
    o.onem,
    o.baslik,
    o.ozet,
    o.neden_onemli,
    o.kaynak_url,
    o.kaynak_adi,
    o.yayin_tarihi,
    o.olusturma,
    k.durum AS gun_durumu,
    k.model,
    k.kaynak_sayisi
   FROM (core.guncel_olay o
     LEFT JOIN core.guncel_olay_kosu k ON ((k.gun = o.gun)))
  ORDER BY o.gun DESC,
        CASE o.onem
            WHEN 'KRITIK'::text THEN 0
            WHEN 'DIKKAT'::text THEN 1
            ELSE 2
        END, o.aci;


ALTER VIEW mart.guncel_olaylar OWNER TO n8n;

--
-- Name: gunluk; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gunluk AS
 WITH s AS (
         SELECT siparis.gun,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = 'DOGRULANMIS'::text)) AS siparis_dogrulanmis,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = 'BEYAN_EDILMIS'::text)) AS siparis_beyan,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = 'ODENMEDI'::text)) AS siparis_odenmedi,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = 'IPTAL'::text)) AS siparis_iptal,
            count(*) FILTER (WHERE (siparis.ciro_sinifi = 'BILINMIYOR'::text)) AS siparis_bilinmiyor,
            COALESCE(sum(siparis.ciro_dogrulanmis), (0)::numeric) AS ciro_dogrulanmis,
            COALESCE(sum(siparis.ciro_beyan_edilmis), (0)::numeric) AS ciro_beyan_edilmis,
            COALESCE(sum(siparis.tutar_bekleyen), (0)::numeric) AS tutar_bekleyen,
            COALESCE(sum(siparis.tutar_bilinmiyor), (0)::numeric) AS tutar_bilinmiyor
           FROM mart.siparis
          WHERE siparis.olcumde
          GROUP BY siparis.gun
        ), g AS (
         SELECT gonderi.gun,
            count(*) FILTER (WHERE (gonderi.sinif = 'SATIS'::text)) AS gonderi_satis,
            count(*) FILTER (WHERE (gonderi.sinif = 'NUMUNE'::text)) AS gonderi_numune,
            count(*) FILTER (WHERE (gonderi.sinif = 'IADE'::text)) AS gonderi_iade,
            count(*) FILTER (WHERE (gonderi.sinif = 'UNKNOWN'::text)) AS gonderi_bilinmiyor,
            COALESCE(sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'UNKNOWN'::text)), (0)::numeric) AS bilinmeyen_kargo,
            count(*) FILTER (WHERE (gonderi.sinif = 'SINIFLANDIRILMAMIS'::text)) AS gonderi_sinifsiz,
            count(*) FILTER (WHERE (gonderi.sinif = 'YON_BILINMIYOR'::text)) AS gonderi_yon_bilinmiyor,
            count(*) FILTER (WHERE (gonderi.sinif = 'ELLE_SATIS'::text)) AS gonderi_elle_satis,
            COALESCE(sum(gonderi.elle_ciro_tahsil), (0)::numeric) AS ciro_elle_tahsil,
            COALESCE(sum(gonderi.elle_ciro_bekleyen), (0)::numeric) AS ciro_elle_bekleyen,
            count(*) FILTER (WHERE gonderi.alarm) AS gonderi_alarm,
            COALESCE(sum(gonderi.kargo_ucreti), (0)::numeric) AS kargo_maliyeti,
            COALESCE(sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'NUMUNE'::text)), (0)::numeric) AS numune_kargo_maliyeti
           FROM mart.gonderi
          WHERE gonderi.olcumde
          GROUP BY gonderi.gun
        )
 SELECT COALESCE(s.gun, g.gun) AS gun,
    COALESCE(s.siparis_dogrulanmis, (0)::bigint) AS siparis_dogrulanmis,
    COALESCE(s.siparis_beyan, (0)::bigint) AS siparis_beyan,
    COALESCE(s.siparis_odenmedi, (0)::bigint) AS siparis_odenmedi,
    COALESCE(s.siparis_iptal, (0)::bigint) AS siparis_iptal,
    COALESCE(s.siparis_bilinmiyor, (0)::bigint) AS siparis_bilinmiyor,
    COALESCE(s.ciro_dogrulanmis, (0)::numeric) AS ciro_dogrulanmis,
    COALESCE(s.ciro_beyan_edilmis, (0)::numeric) AS ciro_beyan_edilmis,
    COALESCE(s.tutar_bekleyen, (0)::numeric) AS tutar_bekleyen,
    COALESCE(s.tutar_bilinmiyor, (0)::numeric) AS tutar_bilinmiyor,
    COALESCE(g.gonderi_satis, (0)::bigint) AS gonderi_satis,
    COALESCE(g.gonderi_numune, (0)::bigint) AS gonderi_numune,
    COALESCE(g.gonderi_iade, (0)::bigint) AS gonderi_iade,
    COALESCE(g.gonderi_bilinmiyor, (0)::bigint) AS gonderi_bilinmiyor,
    COALESCE(g.bilinmeyen_kargo, (0)::numeric) AS bilinmeyen_kargo,
    COALESCE(g.gonderi_sinifsiz, (0)::bigint) AS gonderi_sinifsiz,
    COALESCE(g.gonderi_yon_bilinmiyor, (0)::bigint) AS gonderi_yon_bilinmiyor,
    COALESCE(g.gonderi_elle_satis, (0)::bigint) AS gonderi_elle_satis,
    COALESCE(g.ciro_elle_tahsil, (0)::numeric) AS ciro_elle_tahsil,
    COALESCE(g.ciro_elle_bekleyen, (0)::numeric) AS ciro_elle_bekleyen,
    COALESCE(g.gonderi_alarm, (0)::bigint) AS gonderi_alarm,
    COALESCE(g.kargo_maliyeti, (0)::numeric) AS kargo_maliyeti,
    COALESCE(g.numune_kargo_maliyeti, (0)::numeric) AS numune_pazarlama_maliyeti
   FROM (s
     FULL JOIN g ON ((g.gun = s.gun)))
  ORDER BY COALESCE(s.gun, g.gun);


ALTER VIEW mart.gunluk OWNER TO n8n;

--
-- Name: gunluk_brief; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gunluk_brief AS
 SELECT b.brief_key,
    b.provider,
    b.model,
    b.context_hash,
    b.created_at,
    m.konu,
    m.icerik,
    m.kimden,
    m.kime,
    m.durum,
    (now() - b.created_at) AS yas
   FROM (core.ai_executive_brief b
     LEFT JOIN core.ic_mesaj m ON ((m.mesaj_id = b.message_id)))
  ORDER BY b.created_at DESC;


ALTER VIEW mart.gunluk_brief OWNER TO n8n;

--
-- Name: hazirlik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.hazirlik AS
 SELECT 'OLCUM_BASLADI'::text AS kosul,
    (now() >= mart.kesim()) AS saglandi,
    format('olcum baslangici %s'::text, to_char((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text), 'DD.MM.YYYY'::text)) AS detay,
    'Kesim tarihi core.ayar.olcum_baslangici icinde'::text AS nereden
UNION ALL
 SELECT 'REKLAM_HARCAMASI_TAM'::text AS kosul,
    (NOT (EXISTS ( SELECT 1
           FROM core.source_authority
          WHERE ((source_authority.alan = 'ad_spend'::text) AND (source_authority.current_connection <> 'CONNECTED'::text))))) AS saglandi,
    COALESCE(( SELECT source_authority.current_connection
           FROM core.source_authority
          WHERE (source_authority.alan = 'ad_spend'::text)), '(kayit yok)'::text) AS detay,
    'core.source_authority.ad_spend'::text AS nereden
UNION ALL
 SELECT 'SIPARIS_KAYDI_TAM'::text AS kosul,
    (NOT (EXISTS ( SELECT 1
           FROM mart.gonderi
          WHERE (gonderi.olcumde AND (gonderi.sinif = 'ELLE_SATIS'::text))))) AS saglandi,
    format('%s gonderi Wix kaydi olmadan kapida odemeli'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.olcumde AND (gonderi.sinif = 'ELLE_SATIS'::text)))) AS detay,
    'mart.gonderi sinif=ELLE_SATIS'::text AS nereden
UNION ALL
 SELECT 'CIRO_TANIMI_GECERLI'::text AS kosul,
    (NOT (EXISTS ( SELECT 1
           FROM mart.siparis
          WHERE (siparis.olcumde AND (siparis.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text])) AND (siparis.kdv IS NULL))))) AS saglandi,
    format('%s sayilan siparişte KDV okunamadi'::text, ( SELECT count(*) AS count
           FROM mart.siparis
          WHERE (siparis.olcumde AND (siparis.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text])) AND (siparis.kdv IS NULL)))) AS detay,
    'raw.wix_order.kdv (totals.tax)'::text AS nereden
UNION ALL
 SELECT 'GONDERI_SINIFLANDI'::text AS kosul,
    (NOT (EXISTS ( SELECT 1
           FROM mart.gonderi
          WHERE (gonderi.olcumde AND gonderi.alarm)))) AS saglandi,
    format('%s gonderinin yonu bilinmiyor'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.olcumde AND gonderi.alarm))) AS detay,
    'mart.gonderi alarm=true'::text AS nereden;


ALTER VIEW mart.hazirlik OWNER TO n8n;

--
-- Name: meta_hesap; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.meta_hesap (
    hesap_id text NOT NULL,
    ad text,
    durum integer,
    para_birimi text,
    portfolyo text,
    ham jsonb,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.meta_hesap OWNER TO n8n;

--
-- Name: meta_kapsama; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.meta_kapsama AS
 WITH k AS (
         SELECT count(*) AS bilinen,
            count(*) FILTER (WHERE (meta_hesap_kayit.operasyonel_durum = 'ACTIVE'::text)) AS aktif,
            count(*) FILTER (WHERE (meta_hesap_kayit.operasyonel_durum = 'INACTIVE_EXCLUDED'::text)) AS kapsam_disi
           FROM core.meta_hesap_kayit
        ), e AS (
         SELECT count(*) AS erisilen,
            count(*) FILTER (WHERE (r.hesap_id IN ( SELECT meta_hesap_kayit.hesap_id
                   FROM core.meta_hesap_kayit
                  WHERE (meta_hesap_kayit.operasyonel_durum = 'ACTIVE'::text)))) AS erisilen_aktif
           FROM raw.meta_hesap r
        )
 SELECT k.bilinen,
    k.aktif,
    k.kapsam_disi,
    e.erisilen,
    e.erisilen_aktif,
    format('%s/%s'::text, e.erisilen, k.bilinen) AS bilinen_kapsama,
    format('%s/%s'::text, e.erisilen_aktif, k.aktif) AS aktif_kapsama,
    ((e.erisilen_aktif >= k.aktif) AND (k.aktif > 0)) AS aktif_tam,
        CASE
            WHEN (k.aktif = 0) THEN 'NO_ACTIVE_ACCOUNT'::text
            WHEN (e.erisilen_aktif >= k.aktif) THEN 'COMPLETE'::text
            ELSE 'PARTIAL'::text
        END AS aktif_durum,
    format('Operational Meta Coverage: %s%% (%s/%s active known accounts)'::text,
        CASE
            WHEN (k.aktif > 0) THEN (round(((100.0 * (e.erisilen_aktif)::numeric) / (k.aktif)::numeric)))::text
            ELSE '—'::text
        END, e.erisilen_aktif, k.aktif) AS etiket,
        CASE
            WHEN ((e.erisilen_aktif >= k.aktif) AND (k.aktif > 0)) THEN format('Registry''de bilinen ve AKTIF siniflandirilmis operasyonel hesaplarin tamami kapsaniyor (%s/%s). Bilinen %s hesabin %s tanesi reklam yayinlamiyor (INACTIVE_EXCLUDED) - bu bir veri acigi DEGIL, kapsam disi birakmadir. DIKKAT: bu "Meta Business''teki tum hesaplari kesfediyoruz" DEMEK DEGILDIR - business_management izni yok, kesif elle yapilir (DISCOVERY_VISIBILITY_RISK).'::text, e.erisilen_aktif, k.aktif, k.bilinen, k.kapsam_disi)
            ELSE format('AKTIF hesaplarin %s/%s tanesi okunabiliyor - EKSIK HARCAMA RISKI VAR.'::text, e.erisilen_aktif, k.aktif)
        END AS ifade,
    'DISCOVERY_VISIBILITY_RISK'::text AS kesif_riski,
    'OPS / elle kontrol - GROWTH BLOCKER DEGIL. business_management izni yok, hesap kesfi elle yapilir: yeni acilan bir reklam hesabi core.meta_hesap_kayit''a elle eklenmedikce kapsama paydasi eski kalir.'::text AS kesif_riski_aciklama
   FROM k,
    e;


ALTER VIEW mart.meta_kapsama OWNER TO n8n;

--
-- Name: p0_urun; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.p0_urun AS
 WITH sahip AS (
         SELECT btrim(x.x) AS urun_id
           FROM core.ayar a,
            LATERAL unnest(string_to_array(a.deger, ','::text)) x(x)
          WHERE ((a.anahtar = 'p0_urunler'::text) AND (btrim(COALESCE(a.deger, ''::text)) <> ''::text))
        ), vekil AS (
         SELECT k.urun_id
           FROM (mart.siparis_kalem k
             JOIN raw.wix_order w ON ((w.siparis_id = k.siparis_id)))
          WHERE ((k.ciro_sinifi <> 'IPTAL'::text) AND (w.olusturma >= (clock_timestamp() - '90 days'::interval)))
          GROUP BY k.urun_id
          ORDER BY (sum(k.satir_ciro_net)) DESC NULLS LAST
         LIMIT 5
        )
 SELECT sahip.urun_id,
    'SAHIP_KARARI'::text AS kaynak
   FROM sahip
UNION ALL
 SELECT vekil.urun_id,
    'VEKIL_SON_90_GUN_CIRO'::text AS kaynak
   FROM vekil
  WHERE (NOT (EXISTS ( SELECT 1
           FROM sahip)));


ALTER VIEW mart.p0_urun OWNER TO n8n;

--
-- Name: ticari_yasayabilirlik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.ticari_yasayabilirlik AS
 WITH o AS (
         SELECT ekonomi_ozet.gun_sayisi,
            ekonomi_ozet.baslangic,
            ekonomi_ozet.bitis,
            ekonomi_ozet.siparis,
            ekonomi_ozet.gerceklesmis,
            ekonomi_ozet.ekonomi_tam,
            ekonomi_ozet.ekonomi_kismi,
            ekonomi_ozet.ekonomi_eksik,
            ekonomi_ozet.net_ciro,
            ekonomi_ozet.bilinen_bilesen_katkisi,
            ekonomi_ozet.katki_ust_siniri,
            ekonomi_ozet.dogrulanmis_katki,
            ekonomi_ozet.reklam_harcamasi,
            ekonomi_ozet.reklam_sonrasi_katki,
            ekonomi_ozet.reklam_sonrasi_ust_sinir,
            ekonomi_ozet.ekonomi_tamlik_yuzde,
            ekonomi_ozet.eksik_bilesenler,
            ekonomi_ozet.ekonomi_durumu
           FROM mart.ekonomi_ozet(30) ekonomi_ozet(gun_sayisi, baslangic, bitis, siparis, gerceklesmis, ekonomi_tam, ekonomi_kismi, ekonomi_eksik, net_ciro, bilinen_bilesen_katkisi, katki_ust_siniri, dogrulanmis_katki, reklam_harcamasi, reklam_sonrasi_katki, reklam_sonrasi_ust_sinir, ekonomi_tamlik_yuzde, eksik_bilesenler, ekonomi_durumu)
        )
 SELECT siparis,
    ekonomi_tam,
    ekonomi_tamlik_yuzde,
    bilinen_bilesen_katkisi,
    katki_ust_siniri,
    dogrulanmis_katki,
    reklam_harcamasi,
    reklam_sonrasi_katki,
    reklam_sonrasi_ust_sinir,
    eksik_bilesenler,
    (ekonomi_tam > 0) AS olculebiliyor,
    ekonomi_durumu AS ekonomik_tamlik,
    ((ekonomi_tam > 0) AND (ekonomi_tamlik_yuzde >= (80)::numeric)) AS ekonomik_dogrulanmis,
        CASE
            WHEN (siparis = 0) THEN 'NO_DATA'::text
            WHEN (reklam_sonrasi_ust_sinir < (0)::numeric) THEN 'NEGATIVE_PROVEN_BY_BOUND'::text
            WHEN ((reklam_sonrasi_katki > (0)::numeric) AND (ekonomi_tamlik_yuzde >= (80)::numeric)) THEN 'POSITIVE_PROVEN_BY_BOUND'::text
            ELSE 'INDETERMINATE'::text
        END AS ticari_yon,
    ((ekonomi_tam > 0) AND (siparis >= 10) AND (ekonomi_tamlik_yuzde >= (80)::numeric) AND (reklam_sonrasi_ust_sinir > (0)::numeric)) AS scale_konusulabilir,
        CASE
            WHEN (siparis = 0) THEN 'Son 30 gunde siparis YOK - ticari yon soylenemez.'::text
            WHEN (reklam_sonrasi_ust_sinir < (0)::numeric) THEN format('TICARI YON: NEGATIF ve KANITLI. Ekonomi TAM DEGIL (%s/%s siparis tam) ama yon yine de soylenebilir: cozulmemis bilesenlerin hepsi maliyettir ve katkiyi yalniz DUSURUR; tek yukari yonlu bilesen (COGS KDV tabani) ust sinira dahildir. EN IYI OLASI katki %s TL, reklam %s TL -> en iyi durumda bile %s TL. Eksik bilesenler: %s. 🔴 Bu ECONOMICALLY_VALIDATED DEGILDIR: yon kanitli, TUTAR hala bilinmiyor.'::text, ekonomi_tam, siparis, katki_ust_siniri, reklam_harcamasi, reklam_sonrasi_ust_sinir, eksik_bilesenler)
            WHEN (ekonomi_tam = 0) THEN format('TICARI YON: BELIRSIZ. Ekonomisi TAM olan siparis YOK (%s siparisin %s''i eksik) ve ust sinir harcamanin ustunde - yani eksikler cozulunce sonuc pozitif de cikabilir negatif de. Eksik bilesenler: %s'::text, siparis, ekonomi_eksik, eksik_bilesenler)
            ELSE format('Ekonomi %%%s tam. Bilinen katki %s TL, ust sinir %s TL, reklam %s TL.'::text, ekonomi_tamlik_yuzde, bilinen_bilesen_katkisi, katki_ust_siniri, reklam_harcamasi)
        END AS ifade,
    'BLENDED_ONLY: Bu yon KARMA (blended) bir karsilastirmadir. Siparis ekonomisi TAM olsa bile reklam-basina karlilik CEVAPLANMAZ - order-level atif YOK (CR-011, ad eslesmesi 0/259). Kampanya/adset/ad bazli karlilik iddiasi URETILEMEZ.'::text AS atif_uyarisi
   FROM o;


ALTER VIEW mart.ticari_yasayabilirlik OWNER TO n8n;

--
-- Name: gunluk_hazirlik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gunluk_hazirlik AS
 SELECT 1 AS sira,
    'manual_order_capture_complete'::text AS anahtar,
    'P0'::text AS kapi,
    h.saglandi AS gecti,
    h.detay,
    'mart.hazirlik / SIPARIS_KAYDI_TAM'::text AS nereden,
    'Kapida odemeli ama Wix kaydi olmayan gonderi = cirosu gorunmeyen satis. WhatsApp/telefon siparis giris SOP''unu isletir.'::text AS neden_onemli
   FROM mart.hazirlik h
  WHERE (h.kosul = 'SIPARIS_KAYDI_TAM'::text)
UNION ALL
 SELECT 2 AS sira,
    'sample_classification_explicit'::text AS anahtar,
    'P0'::text AS kapi,
    (NOT (EXISTS ( SELECT 1
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'UNKNOWN'::text)))) AS gecti,
    format('%s gonderinin sinifi BILINMIYOR (%s TL kargo)'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'UNKNOWN'::text)), ( SELECT to_char(COALESCE(sum(gonderi.kargo_ucreti), (0)::numeric), 'FM999999990.00'::text) AS to_char
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'UNKNOWN'::text))) AS detay,
    'mart.gonderi sinif=UNKNOWN'::text AS nereden,
    'Isaretlenmemis gonderi ne satis ne pazarlama gideri sayilabilir. Varsayimla numune saymak, bir SATISI gider diye okumaktir.'::text AS neden_onemli
UNION ALL
 SELECT 3 AS sira,
    'gonderi_sinifi_biliniyor'::text AS anahtar,
    'P0'::text AS kapi,
    (NOT (EXISTS ( SELECT 1
           FROM mart.gonderi
          WHERE ((gonderi.sinif IS NULL) OR (gonderi.sinif = 'BILINMIYOR'::text))))) AS gecti,
    format('%s/%s gonderinin sinifi biliniyor · %s'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE ((gonderi.sinif IS NOT NULL) AND (gonderi.sinif <> 'BILINMIYOR'::text))), ( SELECT count(*) AS count
           FROM mart.gonderi), COALESCE(( SELECT string_agg(((d.sinif || ' '::text) || d.n), ' · '::text ORDER BY d.n DESC) AS string_agg
           FROM ( SELECT gonderi.sinif,
                    count(*) AS n
                   FROM mart.gonderi
                  WHERE (gonderi.sinif IS NOT NULL)
                  GROUP BY gonderi.sinif) d), 'kayit yok'::text)) AS detay,
    'mart.gonderi.sinif'::text AS nereden,
    'Numune ile satis ayrilamazsa ciro da maliyet de birbirine karisir: bedelsiz gonderi satis sayilir, kargo gideri yanlis siparise yazilir.'::text AS neden_onemli
UNION ALL
 SELECT 4 AS sira,
    'meta_spend_coverage'::text AS anahtar,
    'DESTEK'::text AS kapi,
    ( SELECT meta_kapsama.aktif_tam
           FROM mart.meta_kapsama) AS gecti,
    ( SELECT format('%s · bilinen envanter %s · kapsam disi %s (INACTIVE_EXCLUDED)'::text, meta_kapsama.etiket, meta_kapsama.bilinen_kapsama, meta_kapsama.kapsam_disi) AS format
           FROM mart.meta_kapsama) AS detay,
    'mart.meta_kapsama (core.meta_hesap_kayit + raw.meta_hesap)'::text AS nereden,
    'Okunmayan hesap harcamayi dusuk gosterir, ROAS''i oldugundan iyi gosterir.'::text AS neden_onemli
UNION ALL
 SELECT 5 AS sira,
    'cost_quality_p0'::text AS anahtar,
    'DESTEK'::text AS kapi,
    (NOT (EXISTS ( SELECT 1
           FROM (mart.p0_urun p
             LEFT JOIN mart.maliyet_kalite mk ON ((mk.urun_id = p.urun_id)))
          WHERE (COALESCE(mk.kalite, 'YOK'::text) <> 'OLCULMUS'::text)))) AS gecti,
    format('%s P0 urununun %s''inde gercek maliyet var (liste: %s)'::text, ( SELECT count(*) AS count
           FROM mart.p0_urun), ( SELECT count(*) AS count
           FROM (mart.p0_urun p
             JOIN mart.maliyet_kalite mk ON ((mk.urun_id = p.urun_id)))
          WHERE (mk.kalite = 'OLCULMUS'::text)), ( SELECT max(p0_urun.kaynak) AS max
           FROM mart.p0_urun)) AS detay,
    'mart.p0_urun + mart.maliyet_kalite'::text AS nereden,
    'Maliyet tahminse marj da tahmindir; tahmini marjla reklam butcesi buyutulmez.'::text AS neden_onemli
UNION ALL
 SELECT 6 AS sira,
    'unanswered_messages'::text AS anahtar,
    'DESTEK'::text AS kapi,
    (NOT (EXISTS ( SELECT 1
           FROM mart.konusma_cevapsiz
          WHERE (konusma_cevapsiz.bekleme_saat > (24)::numeric)))) AS gecti,
    format('%s mesaj 24 saati gecti (en eskisi %s gun)'::text, ( SELECT count(*) AS count
           FROM mart.konusma_cevapsiz
          WHERE (konusma_cevapsiz.bekleme_saat > (24)::numeric)), ( SELECT COALESCE(round((max(konusma_cevapsiz.bekleme_saat) / 24.0), 1), (0)::numeric) AS "coalesce"
           FROM mart.konusma_cevapsiz)) AS detay,
    'mart.konusma_cevapsiz'::text AS nereden,
    'Cevaplanmamis mesaj, reklamla satin alinmis ve sonra birakilmis taleptir.'::text AS neden_onemli
UNION ALL
 SELECT 7 AS sira,
    'backup_health'::text AS anahtar,
    'DESTEK'::text AS kapi,
    (COALESCE(( SELECT NULLIF(btrim(ayar.deger), ''::text) AS "nullif"
           FROM core.ayar
          WHERE (ayar.anahtar = 'son_yedek_durum'::text)), 'UNKNOWN'::text) = 'HEALTHY'::text) AS gecti,
        CASE
            WHEN (( SELECT NULLIF(btrim(ayar.deger), ''::text) AS "nullif"
               FROM core.ayar
              WHERE (ayar.anahtar = 'son_yedek_notu'::text)) IS NULL) THEN 'UNKNOWN - hazirlik-gunluk.sh hic calismadi, yedek OLCULMEDI'::text
            ELSE ( SELECT btrim(ayar.deger) AS btrim
               FROM core.ayar
              WHERE (ayar.anahtar = 'son_yedek_notu'::text))
        END AS detay,
    'core.ayar.son_yedek_durum + son_yedek_notu (hazirlik-gunluk.sh yazar)'::text AS nereden,
    '1 Ekim''den sonra bu veritabani ticari kaydin kendisidir; geri yuklenemeyen yedek, yedek degildir.'::text AS neden_onemli
UNION ALL
 SELECT 8 AS sira,
    'commercial_viability'::text AS anahtar,
    'TICARI'::text AS kapi,
    ( SELECT ticari_yasayabilirlik.olculebiliyor
           FROM mart.ticari_yasayabilirlik) AS gecti,
    ( SELECT "left"(ticari_yasayabilirlik.ifade, 220) AS "left"
           FROM mart.ticari_yasayabilirlik) AS detay,
    'mart.ticari_yasayabilirlik (mart.ekonomi_ozet(30))'::text AS nereden,
    'Olcum tamligi ticari tamlik DEGILDIR. Ekonomik olarak dogrulanmamis katki uzerinden SCALE/butce artisi onerilemez.'::text AS neden_onemli
UNION ALL
 SELECT 9 AS sira,
    'behavioral_funnel_visibility'::text AS anahtar,
    'DAVRANIS'::text AS kapi,
    ( SELECT bool_and((funnel_saglik.gozlem_durumu = 'OBSERVED'::text)) AS bool_and
           FROM mart.funnel_saglik
          WHERE (funnel_saglik.adim_kod = ANY (ARRAY['LANDING'::text, 'PRODUCT_VIEW'::text, 'ADD_TO_CART'::text, 'BEGIN_CHECKOUT'::text, 'PURCHASE'::text]))) AS gecti,
    ( SELECT format('%s/%s funnel adimi gozleniyor · enstrumantasyon: %s · GA4 Data API: %s'::text, count(*) FILTER (WHERE (funnel_saglik.gozlem_durumu = 'OBSERVED'::text)), count(*), string_agg(DISTINCT funnel_saglik.enstrumantasyon, '/'::text),
                CASE
                    WHEN (EXISTS ( SELECT 1
                       FROM raw.ga4_event)) THEN 'akiyor'::text
                    ELSE 'BAGLI DEGIL'::text
                END) AS format
           FROM mart.funnel_saglik) AS detay,
    'mart.funnel_saglik (core.funnel_adim + raw.ga4_event)'::text AS nereden,
    'Davranis verisi olmadan huni tikanikligi OLCULEMEZ. NOT_MEASURED asla 0 sayilmaz.'::text AS neden_onemli;


ALTER VIEW mart.gunluk_hazirlik OWNER TO n8n;

--
-- Name: gunluk_marj; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gunluk_marj AS
 WITH k AS (
         SELECT siparis_kalem.gun,
            sum(siparis_kalem.satir_ciro) AS ciro,
            sum(siparis_kalem.satir_ciro_net) AS ciro_net,
            sum(siparis_kalem.satir_maliyet) AS cogs,
            sum(siparis_kalem.brut_marj) AS brut_marj,
            sum(siparis_kalem.satir_ciro_net) FILTER (WHERE siparis_kalem.maliyeti_biliniyor) AS ciro_olculen
           FROM mart.siparis_kalem
          WHERE ((siparis_kalem.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text])) AND siparis_kalem.olcumde)
          GROUP BY siparis_kalem.gun
        ), kg AS (
         SELECT gonderi.gun,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'SATIS'::text)) AS kargo,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'IADE'::text)) AS iade_kargo,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif <> ALL (ARRAY['SATIS'::text, 'IADE'::text, 'NUMUNE'::text]))) AS sinifsiz_kargo,
            sum(gonderi.kargo_ucreti) AS kargo_tum
           FROM mart.gonderi
          WHERE gonderi.olcumde
          GROUP BY gonderi.gun
        ), nm AS (
         SELECT gonderi.gun,
            sum(gonderi.kargo_ucreti) AS numune_kargo
           FROM mart.gonderi
          WHERE (gonderi.olcumde AND (gonderi.sinif = 'NUMUNE'::text))
          GROUP BY gonderi.gun
        ), r AS (
         SELECT meta_harcama.gun,
            sum(meta_harcama.harcama) AS reklam
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
          GROUP BY meta_harcama.gun
        )
 SELECT COALESCE(k.gun, kg.gun, nm.gun, r.gun) AS gun,
    COALESCE(k.ciro, (0)::numeric) AS ciro,
    COALESCE(k.ciro_net, (0)::numeric) AS ciro_net,
    round(k.cogs, 2) AS cogs,
    round(k.brut_marj, 2) AS brut_marj,
    COALESCE(kg.kargo, (0)::numeric) AS kargo,
    COALESCE(kg.iade_kargo, (0)::numeric) AS iade_gideri,
    COALESCE(kg.sinifsiz_kargo, (0)::numeric) AS sinifsiz_kargo,
    COALESCE(nm.numune_kargo, (0)::numeric) AS numune_gideri,
    COALESCE(kg.kargo_tum, (0)::numeric) AS kargo_tum,
    COALESCE(r.reklam, (0)::numeric) AS reklam,
        CASE
            WHEN (k.brut_marj IS NOT NULL) THEN round((k.brut_marj - COALESCE(kg.kargo, (0)::numeric)), 2)
            ELSE NULL::numeric
        END AS katki_marji,
        CASE
            WHEN (k.brut_marj IS NOT NULL) THEN round(((k.brut_marj - COALESCE(kg.kargo_tum, (0)::numeric)) - COALESCE(r.reklam, (0)::numeric)), 2)
            ELSE NULL::numeric
        END AS reklam_sonrasi,
    round(((100.0 * COALESCE(k.ciro_olculen, (0)::numeric)) / NULLIF(k.ciro_net, (0)::numeric)), 1) AS maliyeti_bilinen_oran
   FROM (((k
     FULL JOIN kg ON ((kg.gun = k.gun)))
     FULL JOIN nm ON ((nm.gun = COALESCE(k.gun, kg.gun))))
     FULL JOIN r ON ((r.gun = COALESCE(k.gun, kg.gun, nm.gun))))
  WHERE (COALESCE(k.gun, kg.gun, nm.gun, r.gun) >= ((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text))::date)
  ORDER BY COALESCE(k.gun, kg.gun, nm.gun, r.gun);


ALTER VIEW mart.gunluk_marj OWNER TO n8n;

--
-- Name: gunluk_verimlilik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.gunluk_verimlilik AS
 WITH hrc AS (
         SELECT meta_harcama.gun,
            sum(meta_harcama.harcama) AS harcama,
            sum(meta_harcama.gosterim) AS gosterim,
            sum(meta_harcama.link_tiklama) AS link_tiklama,
            sum(meta_harcama.meta_donusum_degeri) AS meta_iddia_gelir
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
          GROUP BY meta_harcama.gun
        ), yeni AS (
         SELECT t.ilk_gun AS gun,
            count(*) AS yeni_musteri
           FROM ( SELECT siparis.customer_id,
                    ((min(siparis.olusturma) AT TIME ZONE 'Europe/Istanbul'::text))::date AS ilk_gun
                   FROM mart.siparis
                  WHERE ((siparis.customer_id IS NOT NULL) AND (siparis.ciro_sinifi <> 'IPTAL'::text))
                  GROUP BY siparis.customer_id) t
          GROUP BY t.ilk_gun
        )
 SELECT COALESCE(g.gun, hrc.gun, yeni.gun) AS gun,
    COALESCE(g.ciro_dogrulanmis, (0)::numeric) AS ciro_dogrulanmis,
    COALESCE(g.ciro_beyan_edilmis, (0)::numeric) AS ciro_beyan_edilmis,
    COALESCE(hrc.harcama, (0)::numeric) AS reklam_harcamasi,
    COALESCE(hrc.gosterim, (0)::numeric) AS gosterim,
    COALESCE(hrc.link_tiklama, (0)::numeric) AS link_tiklama,
    COALESCE(yeni.yeni_musteri, (0)::bigint) AS yeni_musteri,
    round((COALESCE(g.ciro_dogrulanmis, (0)::numeric) / NULLIF(hrc.harcama, (0)::numeric)), 2) AS karma_roas_dogrulanmis,
    round(((COALESCE(g.ciro_dogrulanmis, (0)::numeric) + COALESCE(g.ciro_beyan_edilmis, (0)::numeric)) / NULLIF(hrc.harcama, (0)::numeric)), 2) AS karma_roas_beyan_dahil,
    round((hrc.harcama / (NULLIF(yeni.yeni_musteri, 0))::numeric), 2) AS karma_musteri_maliyeti,
    COALESCE(hrc.meta_iddia_gelir, (0)::numeric) AS meta_iddia_gelir,
    COALESCE(g.gonderi_alarm, (0)::bigint) AS gonderi_alarm
   FROM ((mart.gunluk g
     FULL JOIN hrc ON ((hrc.gun = g.gun)))
     FULL JOIN yeni ON ((yeni.gun = COALESCE(g.gun, hrc.gun))))
  WHERE (COALESCE(g.gun, hrc.gun, yeni.gun) >= ((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text))::date)
  ORDER BY COALESCE(g.gun, hrc.gun, yeni.gun);


ALTER VIEW mart.gunluk_verimlilik OWNER TO n8n;

--
-- Name: harcama; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.harcama AS
 SELECT h.gun,
    h.hesap_id,
    COALESCE(a.ad, h.hesap_id) AS hesap_adi,
    h.kampanya_id,
    h.kampanya_adi,
    h.kaynak,
    h.harcama,
    h.gosterim,
    h.tiklama,
    h.link_tiklama,
    h.meta_donusum,
    h.meta_donusum_degeri,
    (h.gun >= ((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text))::date) AS olcumde
   FROM (raw.meta_harcama h
     LEFT JOIN raw.meta_hesap a ON ((a.hesap_id = h.hesap_id)))
  WHERE (h.kampanya_id <> '_HESAP'::text);


ALTER VIEW mart.harcama OWNER TO n8n;

--
-- Name: harcama_siparis_ortusmesi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.harcama_siparis_ortusmesi AS
 WITH gunler AS (
         SELECT meta_harcama.gun
           FROM raw.meta_harcama
        UNION
         SELECT (siparis.olusturma)::date AS olusturma
           FROM mart.siparis
        ), h AS (
         SELECT meta_harcama.gun,
            sum(meta_harcama.harcama) AS harcama,
            sum(meta_harcama.gosterim) AS gosterim,
            sum(meta_harcama.link_tiklama) AS link_tiklama
           FROM raw.meta_harcama
          GROUP BY meta_harcama.gun
        ), s AS (
         SELECT (siparis.olusturma)::date AS gun,
            count(*) AS siparis,
            sum((siparis.toplam - siparis.kdv)) FILTER (WHERE (siparis.ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text]))) AS net_ciro
           FROM mart.siparis
          GROUP BY ((siparis.olusturma)::date)
        )
 SELECT g.gun,
    COALESCE(h.harcama, (0)::numeric) AS harcama,
    h.gosterim,
    h.link_tiklama,
    COALESCE(s.siparis, (0)::bigint) AS siparis,
    s.net_ciro,
        CASE
            WHEN ((COALESCE(h.harcama, (0)::numeric) > (0)::numeric) AND (COALESCE(s.siparis, (0)::bigint) > 0)) THEN 'HARCAMA_VE_SIPARIS'::text
            WHEN (COALESCE(h.harcama, (0)::numeric) > (0)::numeric) THEN 'YALNIZ_HARCAMA'::text
            WHEN (COALESCE(s.siparis, (0)::bigint) > 0) THEN 'YALNIZ_SIPARIS'::text
            ELSE 'IKISI_DE_YOK'::text
        END AS ortusme
   FROM ((gunler g
     LEFT JOIN h ON ((h.gun = g.gun)))
     LEFT JOIN s ON ((s.gun = g.gun)))
  ORDER BY g.gun;


ALTER VIEW mart.harcama_siparis_ortusmesi OWNER TO n8n;

--
-- Name: harcama_uyari; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.harcama_uyari AS
 WITH p AS (
         SELECT gunluk_verimlilik.gun,
            sum(gunluk_verimlilik.reklam_harcamasi) OVER (ORDER BY gunluk_verimlilik.gun ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS h3,
            sum((gunluk_verimlilik.ciro_dogrulanmis + gunluk_verimlilik.ciro_beyan_edilmis)) OVER (ORDER BY gunluk_verimlilik.gun ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS c3
           FROM mart.gunluk_verimlilik
        )
 SELECT gun,
    h3 AS son3gun_harcama,
    c3 AS son3gun_ciro
   FROM p
  WHERE ((h3 > (0)::numeric) AND (c3 = (0)::numeric));


ALTER VIEW mart.harcama_uyari OWNER TO n8n;

--
-- Name: hatirlatici_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.hatirlatici_guncel AS
 SELECT id,
    baslik,
    not_,
    zaman,
    tekrar,
    onem,
    durum,
    kaynak,
    olusturma,
    ((durum = 'ACIK'::text) AND (zaman <= now())) AS zamani_geldi,
    ((durum = 'ACIK'::text) AND (zaman < (now() - '1 day'::interval))) AS gecikti,
    (EXTRACT(epoch FROM (zaman - now())))::bigint AS kalan_sn
   FROM core.hatirlatici
  WHERE (durum = 'ACIK'::text)
  ORDER BY zaman;


ALTER VIEW mart.hatirlatici_guncel OWNER TO n8n;

--
-- Name: hazirlik_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.hazirlik_ozet AS
 SELECT bool_and(saglandi) AS karar_hazir,
    count(*) FILTER (WHERE (NOT saglandi)) AS eksik_sayisi,
    COALESCE(string_agg(kosul, ', '::text ORDER BY kosul) FILTER (WHERE (NOT saglandi)), ''::text) AS eksikler,
    COALESCE(string_agg(format('%s (%s)'::text, kosul, detay), ' · '::text ORDER BY kosul) FILTER (WHERE (NOT saglandi)), ''::text) AS eksik_detay
   FROM mart.hazirlik;


ALTER VIEW mart.hazirlik_ozet OWNER TO n8n;

--
-- Name: ig_medya; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.ig_medya (
    medya_id text NOT NULL,
    ig_user_id text NOT NULL,
    tur text,
    urun_tipi text,
    metin text,
    zaman timestamp with time zone,
    begeni bigint,
    yorum bigint,
    baglanti text,
    kucuk_gorsel text,
    ham jsonb DEFAULT '{}'::jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.ig_medya OWNER TO n8n;

--
-- Name: icerik_performans; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.icerik_performans AS
 SELECT medya_id,
    zaman,
    ((zaman AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
    COALESCE(urun_tipi, tur) AS bicim,
    tur,
    "left"(COALESCE(metin, ''::text), 120) AS icerik_basi,
    length(COALESCE(metin, ''::text)) AS icerik_uzunluk,
    ( SELECT count(*) AS count
           FROM regexp_matches(COALESCE(m.metin, ''::text), '#[[:alnum:]_]+'::text, 'g'::text) regexp_matches(regexp_matches)) AS etiket_sayisi,
    (COALESCE(metin, ''::text) ~* '#?(reklam|tanitim|tanıtım|isbirligi|işbirliği)'::text) AS reklam_ibaresi,
    (COALESCE(metin, ''::text) ~* 'yapay zek'::text) AS yz_beyani,
    COALESCE(begeni, (0)::bigint) AS begeni,
    COALESCE(yorum, (0)::bigint) AS yorum,
    (COALESCE(begeni, (0)::bigint) + COALESCE(yorum, (0)::bigint)) AS etkilesim,
    baglanti,
    'ERISIM_YOK_ORAN_HESAPLANAMAZ'::text AS olcum_siniri
   FROM raw.ig_medya m;


ALTER VIEW mart.icerik_performans OWNER TO n8n;

--
-- Name: inanc_durumu; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.inanc_durumu AS
 SELECT bulgu_id,
    modul,
    seviye,
    inanc_durumu,
    guven,
    baslik,
    kanit,
    kanit_sinifi,
    COALESCE(fikrimi_degistirecek, yanlislama) AS fikrimi_degistirecek,
    ustunu_alan,
    olusturma,
    guncelleme,
    ( SELECT count(*) AS count
           FROM core.acik_soru s
          WHERE ((s.bagli_bulgu = b.bulgu_id) AND (s.durum = 'OPEN'::text))) AS acik_soru_sayisi
   FROM core.buyume_bulgu b
  WHERE ((seviye = ANY (ARRAY['HYPOTHESIS'::text, 'INFERRED'::text])) AND (COALESCE(inanc_durumu, 'ACTIVE'::text) <> ALL (ARRAY['REFUTED'::text, 'SUPERSEDED'::text])))
  ORDER BY COALESCE(guven, 0.5) DESC, olusturma DESC;


ALTER VIEW mart.inanc_durumu OWNER TO n8n;

--
-- Name: nakit_gunluk; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.nakit_gunluk AS
 WITH gunler AS (
         SELECT ((wix_order.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun
           FROM raw.wix_order
        UNION
         SELECT meta_harcama.gun
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
        UNION
         SELECT ((bk_shipment.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS timezone
           FROM raw.bk_shipment
        ), sip AS (
         SELECT ((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            count(*) AS siparis,
            sum(w.toplam) AS brut_ciro,
            sum((w.toplam - w.kdv)) AS net_ciro,
            sum((w.toplam - w.kdv)) FILTER (WHERE (w.odeme_durumu = 'PAID'::text)) AS tahsil_beyan,
            sum((w.toplam - w.kdv)) FILTER (WHERE (w.odeme_durumu IS DISTINCT FROM 'PAID'::text)) AS tahsil_edilmemis
           FROM raw.wix_order w
          WHERE (w.teslimat_durumu IS DISTINCT FROM 'CANCELED'::text)
          GROUP BY (((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date)
        ), kal AS (
         SELECT ((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            sum(k_1.satir_maliyet) AS cogs,
            sum(k_1.satir_ciro_net) AS kalem_net,
            sum(k_1.satir_ciro_net) FILTER (WHERE (mk.kalite = 'OLCULMUS'::text)) AS kalem_net_olculmus,
            count(*) AS kalem,
            count(*) FILTER (WHERE k_1.maliyeti_biliniyor) AS kalem_maliyetli
           FROM ((mart.siparis_kalem k_1
             JOIN raw.wix_order w ON ((w.siparis_id = k_1.siparis_id)))
             LEFT JOIN mart.maliyet_kalite mk ON ((mk.urun_id = k_1.urun_id)))
          WHERE (k_1.ciro_sinifi <> 'IPTAL'::text)
          GROUP BY (((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date)
        ), krg AS (
         SELECT ((gonderi.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = ANY (ARRAY['SATIS'::text, 'ELLE_SATIS'::text]))) AS satis_kargosu,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'NUMUNE'::text)) AS numune_kargosu,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'UNKNOWN'::text)) AS bilinmeyen_kargo,
            sum(gonderi.kargo_ucreti) FILTER (WHERE (gonderi.sinif = 'IADE'::text)) AS iade_kargosu,
            sum(gonderi.cod_tutar) FILTER (WHERE ((gonderi.sinif = 'ELLE_SATIS'::text) AND (gonderi.cod_durum = 'TRANSFERRED'::text))) AS wixdisi_tahsil_kdvli,
            sum(gonderi.cod_tutar) FILTER (WHERE ((gonderi.sinif = 'ELLE_SATIS'::text) AND (gonderi.cod_durum IS DISTINCT FROM 'TRANSFERRED'::text))) AS wixdisi_bekleyen_kdvli
           FROM mart.gonderi
          GROUP BY (((gonderi.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date)
        ), rek AS (
         SELECT meta_harcama.gun,
            sum(meta_harcama.harcama) AS harcama,
            sum(meta_harcama.gosterim) AS gosterim,
            sum(meta_harcama.link_tiklama) AS tiklama
           FROM raw.meta_harcama
          WHERE (meta_harcama.kampanya_id <> '_HESAP'::text)
          GROUP BY meta_harcama.gun
        ), hesap AS (
         SELECT count(*) AS okunan
           FROM raw.meta_hesap
        )
 SELECT g.gun,
    COALESCE(s.siparis, (0)::bigint) AS siparis,
    COALESCE(s.brut_ciro, (0)::numeric) AS brut_ciro,
    COALESCE(s.net_ciro, (0)::numeric) AS net_ciro,
    COALESCE(s.tahsil_beyan, (0)::numeric) AS tahsil_beyan_edilen,
    COALESCE(s.tahsil_edilmemis, (0)::numeric) AS tahsil_edilmemis,
    round((COALESCE(k.wixdisi_tahsil_kdvli, (0)::numeric) / 1.2), 2) AS wixdisi_tahsil_net,
    round((COALESCE(k.wixdisi_bekleyen_kdvli, (0)::numeric) / 1.2), 2) AS wixdisi_bekleyen_net,
    round(COALESCE(c.cogs, (0)::numeric), 2) AS bilinen_cogs,
        CASE
            WHEN ((c.kalem IS NULL) OR (c.kalem = 0)) THEN 'VERI_YOK'::text
            WHEN (c.kalem_maliyetli < c.kalem) THEN 'EKSIK'::text
            WHEN (COALESCE(c.kalem_net_olculmus, (0)::numeric) = (0)::numeric) THEN 'TAHMIN'::text
            WHEN (c.kalem_net_olculmus >= (c.kalem_net * 0.5)) THEN 'OLCULMUS'::text
            ELSE 'KARISIK'::text
        END AS cogs_kalite,
    round(((100.0 * COALESCE(c.kalem_net_olculmus, (0)::numeric)) / NULLIF(c.kalem_net, (0)::numeric)), 1) AS cogs_olculmus_yuzde,
    round(COALESCE(k.satis_kargosu, (0)::numeric), 2) AS satis_kargosu,
    round(COALESCE(k.numune_kargosu, (0)::numeric), 2) AS numune_kargosu,
    round(COALESCE(k.bilinmeyen_kargo, (0)::numeric), 2) AS bilinmeyen_kargo,
    round(COALESCE(k.iade_kargosu, (0)::numeric), 2) AS iade_kargosu,
    round(COALESCE(r.harcama, (0)::numeric), 2) AS meta_harcama_gozlenen,
    ( SELECT meta_kapsama.aktif_kapsama
           FROM mart.meta_kapsama) AS meta_hesap_kapsamasi,
    COALESCE(r.gosterim, (0)::numeric) AS gosterim,
    COALESCE(r.tiklama, (0)::numeric) AS link_tiklama,
    round(((((COALESCE(s.net_ciro, (0)::numeric) - COALESCE(c.cogs, (0)::numeric)) - COALESCE(k.satis_kargosu, (0)::numeric)) - COALESCE(k.numune_kargosu, (0)::numeric)) - COALESCE(k.bilinmeyen_kargo, (0)::numeric)), 2) AS reklam_oncesi_katki,
    round((((((COALESCE(s.net_ciro, (0)::numeric) - COALESCE(c.cogs, (0)::numeric)) - COALESCE(k.satis_kargosu, (0)::numeric)) - COALESCE(k.numune_kargosu, (0)::numeric)) - COALESCE(k.bilinmeyen_kargo, (0)::numeric)) - COALESCE(r.harcama, (0)::numeric)), 2) AS reklam_sonrasi_katki,
    round((COALESCE(r.harcama, (0)::numeric) / (NULLIF(s.siparis, 0))::numeric), 2) AS siparis_basina_harcama,
    round((COALESCE(s.net_ciro, (0)::numeric) / NULLIF(r.harcama, (0)::numeric)), 2) AS ciro_harcama_orani,
        CASE
            WHEN ((COALESCE(r.harcama, (0)::numeric) = (0)::numeric) AND (COALESCE(s.siparis, (0)::bigint) = 0)) THEN 'INSUFFICIENT_DATA'::text
            WHEN (COALESCE(r.harcama, (0)::numeric) > COALESCE(s.net_ciro, (0)::numeric)) THEN 'CRITICAL'::text
            WHEN (COALESCE(r.harcama, (0)::numeric) >= ((((COALESCE(s.net_ciro, (0)::numeric) - COALESCE(c.cogs, (0)::numeric)) - COALESCE(k.satis_kargosu, (0)::numeric)) - COALESCE(k.numune_kargosu, (0)::numeric)) - COALESCE(k.bilinmeyen_kargo, (0)::numeric))) THEN 'WATCH'::text
            WHEN (COALESCE(c.kalem_net_olculmus, (0)::numeric) < (COALESCE(c.kalem_net, (0)::numeric) * 0.5)) THEN 'WATCH'::text
            ELSE 'HEALTHY'::text
        END AS nakit_durum
   FROM ((((gunler g
     LEFT JOIN sip s ON ((s.gun = g.gun)))
     LEFT JOIN kal c ON ((c.gun = g.gun)))
     LEFT JOIN krg k ON ((k.gun = g.gun)))
     LEFT JOIN rek r ON ((r.gun = g.gun)))
  ORDER BY g.gun DESC;


ALTER VIEW mart.nakit_gunluk OWNER TO n8n;

--
-- Name: nakit_veri_kalitesi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.nakit_veri_kalitesi AS
 SELECT 'COGS (urun maliyeti)'::text AS kalem,
        CASE
            WHEN (( SELECT count(*) AS count
               FROM mart.maliyet_kalite
              WHERE (maliyet_kalite.kalite = 'OLCULMUS'::text)) > 0) THEN 'PARTIAL'::text
            ELSE 'TAHMIN'::text
        END AS durum,
    format('%s urunun %s''i SAHIP TAHMINI (ayni deger), olculmus: %s'::text, ( SELECT count(*) AS count
           FROM mart.maliyet_kalite), ( SELECT count(*) AS count
           FROM mart.maliyet_kalite
          WHERE (maliyet_kalite.kalite = 'TAHMIN'::text)), ( SELECT count(*) AS count
           FROM mart.maliyet_kalite
          WHERE (maliyet_kalite.kalite = 'OLCULMUS'::text))) AS aciklama,
    'katki OLDUGUNDAN IYIMSER olabilir'::text AS etki
UNION ALL
 SELECT 'COGS KDV tabani'::text AS kalem,
        CASE
            WHEN (( SELECT ayar.deger
               FROM core.ayar
              WHERE (ayar.anahtar = 'maliyet_kdv_tabani'::text)) IS NULL) THEN 'MISSING'::text
            ELSE 'TANIMLI'::text
        END AS durum,
    'Beyan edilen maliyetin KDV dahil mi haric mi oldugu sorulmadi; KDV HARIC varsayiliyor'::text AS aciklama,
    'marj yonu degismez, tutar degisir'::text AS etki
UNION ALL
 SELECT 'Odeme komisyonu (PayTR)'::text AS kalem,
    'MISSING'::text AS durum,
    'PayTR API baglantisi yok; komisyon hicbir yerde olculmuyor'::text AS aciklama,
    'gercek katki DAHA DUSUK'::text AS etki
UNION ALL
 SELECT 'Kapida odeme komisyonu'::text AS kalem,
    'MISSING'::text AS durum,
    'BasitKargo toplam_maliyet ile kargo_ucreti farki ihmal edilebilir; COD komisyonu ayri gorunmuyor'::text AS aciklama,
    'gercek katki DAHA DUSUK'::text AS etki
UNION ALL
 SELECT 'Basarisiz teslimat maliyeti'::text AS kalem,
    'MISSING'::text AS durum,
    format('%s gonderi henuz teslim edilmedi; sonucu ve bedeli bilinmiyor'::text, ( SELECT count(*) AS count
           FROM raw.bk_shipment
          WHERE ((bk_shipment.yon = 'OUTGOING'::text) AND (bk_shipment.teslim IS NULL)))) AS aciklama,
    'gercek katki DAHA DUSUK'::text AS etki
UNION ALL
 SELECT 'Numune/UGC URUN maliyeti'::text AS kalem,
    'MISSING'::text AS durum,
    format('%s numune gonderisinin kargosu biliniyor ama icindeki urunun maliyeti yok (BasitKargo''da productId yok)'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = ANY (ARRAY['NUMUNE'::text, 'UNKNOWN'::text])))) AS aciklama,
    'gercek katki DAHA DUSUK'::text AS etki
UNION ALL
 SELECT 'Gonderi sinifi (UNKNOWN)'::text AS kalem,
        CASE
            WHEN (( SELECT count(*) AS count
               FROM mart.gonderi
              WHERE (gonderi.sinif = 'UNKNOWN'::text)) = 0) THEN 'TANIMLI'::text
            ELSE 'MISSING'::text
        END AS durum,
    format('%s gonderinin ne oldugu BILINMIYOR (acik isaret yok). Satis mi numune mi hediye mi ayirt edilemiyor; varsayimla numune sayilmiyor'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'UNKNOWN'::text))) AS aciklama,
    'ne ciroya ne pazarlama giderine yazilir; kargosu katkidan DUSULUR'::text AS etki
UNION ALL
 SELECT 'Meta hesap kapsamasi'::text AS kalem,
    ( SELECT
                CASE
                    WHEN meta_kapsama.aktif_tam THEN 'TANIMLI'::text
                    ELSE 'PARTIAL'::text
                END AS "case"
           FROM mart.meta_kapsama) AS durum,
    ( SELECT meta_kapsama.ifade
           FROM mart.meta_kapsama) AS aciklama,
    ( SELECT
                CASE
                    WHEN meta_kapsama.aktif_tam THEN 'aktif hesaplarin tamami okunuyor - harcama TABAN degil TAM'::text
                    ELSE 'gercek harcama DAHA YUKSEK olabilir'::text
                END AS "case"
           FROM mart.meta_kapsama) AS etki
UNION ALL
 SELECT 'Meta harcamasi KDV tabani'::text AS kalem,
    'MISSING'::text AS durum,
    'Meta''nin bildirdigi harcamanin KDV dahil mi haric mi oldugu dogrulanmadi'::text AS aciklama,
    'sinandi: KDV dahil varsayilsa bile harcama ciroyu asiyor'::text AS etki
UNION ALL
 SELECT 'Stok'::text AS kalem,
    'PARTIAL'::text AS durum,
    format('%s urunun tamami sabit %s adet gorunuyor - gercek stok degil'::text, ( SELECT count(*) AS count
           FROM raw.wix_urun), ( SELECT (max(wix_urun.stok_adet))::integer AS max
           FROM raw.wix_urun)) AS aciklama,
    'nakit hesabina girmiyor'::text AS etki
UNION ALL
 SELECT 'Cevrim disi odeme dogrulamasi'::text AS kalem,
    'MISSING'::text AS durum,
    format('%s siparis cevrim disi odendi isaretli; muhasebe/banka kaydiyla karsilastirilmiyor'::text, ( SELECT count(*) AS count
           FROM raw.wix_order
          WHERE ((wix_order.odeme_yontemi IS DISTINCT FROM 'PayTR'::text) AND (wix_order.odeme_durumu = 'PAID'::text)))) AS aciklama,
    'tahsil edilmis ciro DOGRULANMAMIS'::text AS etki
UNION ALL
 SELECT 'Wix disi satis (WhatsApp/telefon)'::text AS kalem,
    'PARTIAL'::text AS durum,
    format('%s gonderi kapida odemeli ve Wix kaydi yok; ciro olarak net_ciro''ya EKLENMEZ'::text, ( SELECT count(*) AS count
           FROM mart.gonderi
          WHERE (gonderi.sinif = 'ELLE_SATIS'::text))) AS aciklama,
    'gercek ciro biraz DAHA YUKSEK olabilir'::text AS etki;


ALTER VIEW mart.nakit_veri_kalitesi OWNER TO n8n;

--
-- Name: yukleme_log; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.yukleme_log (
    id bigint NOT NULL,
    kaynak text NOT NULL,
    durum text NOT NULL,
    okunan integer,
    yazilan integer,
    guncellenen integer,
    mesaj text,
    baslangic timestamp with time zone NOT NULL,
    bitis timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT yukleme_log_durum_check CHECK ((durum = ANY (ARRAY['SUCCESS'::text, 'NO_DATA'::text, 'PARTIAL'::text, 'FAILED'::text])))
);


ALTER TABLE raw.yukleme_log OWNER TO n8n;

--
-- Name: kanit_kalitesi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kanit_kalitesi AS
 WITH f AS (
         SELECT ( SELECT
                        CASE
                            WHEN ((count(*) FILTER (WHERE (source_authority.current_connection = 'CONNECTED'::text)) * 3) >= count(*)) THEN 2
                            WHEN (count(*) FILTER (WHERE (source_authority.current_connection = 'CONNECTED'::text)) > 0) THEN 1
                            ELSE 0
                        END AS "case"
                   FROM core.source_authority
                  WHERE (source_authority.current_connection <> 'OPTIONAL_RECONCILIATION_GAP'::text)) AS kapsama,
            ( SELECT
                        CASE
                            WHEN (COALESCE(sum(nakit_gunluk.siparis), (0)::numeric) >= (30)::numeric) THEN 2
                            WHEN (COALESCE(sum(nakit_gunluk.siparis), (0)::numeric) >= (10)::numeric) THEN 1
                            ELSE 0
                        END AS "case"
                   FROM mart.nakit_gunluk
                  WHERE (nakit_gunluk.gun > (CURRENT_DATE - 30))) AS orneklem,
            ( SELECT
                        CASE
                            WHEN (min(t.son) > (now() - '30:00:00'::interval)) THEN 2
                            WHEN (min(t.son) > (now() - '72:00:00'::interval)) THEN 1
                            ELSE 0
                        END AS "case"
                   FROM ( SELECT max(yukleme_log.bitis) AS son
                           FROM raw.yukleme_log
                          GROUP BY yukleme_log.kaynak) t) AS tazelik,
            ( SELECT
                        CASE
                            WHEN (count(*) FILTER (WHERE ((source_authority.alan = ANY (ARRAY['order'::text, 'payment_online'::text])) AND (source_authority.current_connection = 'CONNECTED'::text))) < 2) THEN 0
                            WHEN ((now() >= mart.kesim()) AND (NOT (EXISTS ( SELECT 1
                               FROM mart.gonderi
                              WHERE (gonderi.olcumde AND (gonderi.sinif = 'ELLE_SATIS'::text)))))) THEN 2
                            ELSE 1
                        END AS "case"
                   FROM core.source_authority) AS otorite,
            ( SELECT
                        CASE
                            WHEN (count(*) = 0) THEN 2
                            ELSE 0
                        END AS "case"
                   FROM ( SELECT w.siparis_id
                           FROM (raw.wix_order w
                             JOIN raw.wix_order_item i ON ((i.siparis_id = w.siparis_id)))
                          GROUP BY w.siparis_id, w.toplam
                         HAVING (round(sum(i.net_toplam), 2) <> round(w.toplam, 2))) x) AS tutarlilik,
            ( SELECT
                        CASE
                            WHEN (count(*) FILTER (WHERE (nakit_veri_kalitesi.durum = 'MISSING'::text)) = 0) THEN 2
                            WHEN (count(*) FILTER (WHERE (nakit_veri_kalitesi.durum = 'MISSING'::text)) <= 3) THEN 1
                            ELSE 0
                        END AS "case"
                   FROM mart.nakit_veri_kalitesi) AS eksiklik
        ), k AS (
         SELECT f.kapsama,
            f.orneklem,
            f.tazelik,
            f.otorite,
            f.tutarlilik,
            f.eksiklik,
            ((
                CASE
                    WHEN (f.orneklem = 0) THEN 1
                    ELSE 0
                END +
                CASE
                    WHEN (f.otorite = 0) THEN 1
                    ELSE 0
                END) +
                CASE
                    WHEN (f.eksiklik = 0) THEN 1
                    ELSE 0
                END) AS kritik_sifir,
            (((((f.kapsama + f.orneklem) + f.tazelik) + f.otorite) + f.tutarlilik) + f.eksiklik) AS puan
           FROM f
        )
 SELECT kapsama,
    orneklem,
    tazelik,
    otorite,
    tutarlilik,
    eksiklik,
    puan,
    kritik_sifir,
        CASE
            WHEN (kritik_sifir >= 2) THEN 'LOW'::text
            WHEN (kritik_sifir = 1) THEN
            CASE
                WHEN (puan >= 5) THEN 'MEDIUM'::text
                ELSE 'LOW'::text
            END
            WHEN (puan >= 9) THEN 'HIGH'::text
            WHEN (puan >= 5) THEN 'MEDIUM'::text
            ELSE 'LOW'::text
        END AS sinif,
        CASE
            WHEN (kritik_sifir >= 2) THEN format('HARD-CAP: %s kritik boyut sifir (%s) -> puan %s olsa da LOW'::text, kritik_sifir, concat_ws(', '::text,
            CASE
                WHEN (orneklem = 0) THEN 'orneklem'::text
                ELSE NULL::text
            END,
            CASE
                WHEN (otorite = 0) THEN 'kaynak_otoritesi'::text
                ELSE NULL::text
            END,
            CASE
                WHEN (eksiklik = 0) THEN 'eksik_veri'::text
                ELSE NULL::text
            END), puan)
            WHEN (kritik_sifir = 1) THEN format('HARD-CAP: %s sifir -> HIGH imkansiz'::text, concat_ws(''::text,
            CASE
                WHEN (orneklem = 0) THEN 'orneklem'::text
                ELSE NULL::text
            END,
            CASE
                WHEN (otorite = 0) THEN 'kaynak_otoritesi'::text
                ELSE NULL::text
            END,
            CASE
                WHEN (eksiklik = 0) THEN 'eksik_veri'::text
                ELSE NULL::text
            END))
            ELSE 'hard-cap yok'::text
        END AS hard_cap_nedeni
   FROM k;


ALTER VIEW mart.kanit_kalitesi OWNER TO n8n;

--
-- Name: karar_fixture; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.karar_fixture AS
 SELECT k.karar_id,
    "left"(k.oneri, 52) AS senaryo,
    k.durum,
    COALESCE(i.karar, '—'::text) AS insan_karari,
    COALESCE(a.aksiyon_tipi, '—'::text) AS aksiyon,
    COALESCE(s.sonuc_durumu, '—'::text) AS sonuc,
    COALESCE(s.veri_kalitesi, '—'::text) AS veri_kalitesi,
    COALESCE(s.orneklem, 0) AS orneklem,
    COALESCE(s.yanlislandi, '—'::text) AS yanlislandi,
    "left"(COALESCE(s.uygunluk_gerekcesi, '—'::text), 52) AS uygunluk
   FROM (((core.karar k
     LEFT JOIN core.karar_insan i ON ((i.karar_id = k.karar_id)))
     LEFT JOIN LATERAL ( SELECT karar_aksiyon.aksiyon_tipi
           FROM core.karar_aksiyon
          WHERE (karar_aksiyon.karar_id = k.karar_id)
          ORDER BY karar_aksiyon.aksiyon_id
         LIMIT 1) a ON (true))
     LEFT JOIN core.karar_sonuc s ON ((s.karar_id = k.karar_id)))
  WHERE k.fixture
  ORDER BY k.karar_id;


ALTER VIEW mart.karar_fixture OWNER TO n8n;

--
-- Name: karar_kalibrasyon; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.karar_kalibrasyon AS
 SELECT k.kanit_kalitesi,
    COALESCE(i.karar, 'KARAR_YOK'::text) AS insan_karari,
    COALESCE(s.sonuc_durumu, 'SONUC_YOK'::text) AS sonuc,
    count(*) AS adet,
    'n cok kucuk - oran uretilmiyor'::text AS "not"
   FROM ((core.karar k
     LEFT JOIN core.karar_insan i ON ((i.karar_id = k.karar_id)))
     LEFT JOIN core.karar_sonuc s ON ((s.karar_id = k.karar_id)))
  WHERE (NOT k.fixture)
  GROUP BY k.kanit_kalitesi, COALESCE(i.karar, 'KARAR_YOK'::text), COALESCE(s.sonuc_durumu, 'SONUC_YOK'::text);


ALTER VIEW mart.karar_kalibrasyon OWNER TO n8n;

--
-- Name: karar_oncelik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.karar_oncelik AS
 WITH b AS (
         SELECT bb.bulgu_id,
            bb.anlik_id,
            bb.modul,
            bb.seviye,
            bb.sinif,
            bb.baslik,
            bb.kanit,
            bb.beklenen_etki,
            bb.risk,
            bb.kanit_sinifi,
            bb.yanlislama,
            bb.insan_onayi,
            bb.olusturma,
            ka.kanit_sinifi AS anlik_kalitesi
           FROM (core.buyume_bulgu bb
             JOIN core.kanit_anlik ka USING (anlik_id))
          WHERE ((bb.anlik_id = ( SELECT max(kanit_anlik.anlik_id) AS max
                   FROM core.kanit_anlik)) AND (bb.modul = ANY (ARRAY['URUN'::text, 'META'::text, 'KREATIF'::text])) AND (COALESCE(bb.sinif, ''::text) <> 'INSUFFICIENT_DATA'::text))
        )
 SELECT bulgu_id,
    modul,
    sinif,
    baslik,
    kanit,
    beklenen_etki,
    risk,
    yanlislama,
    anlik_kalitesi AS kanit_sinifi,
    (((
        CASE
            WHEN ((modul = 'META'::text) AND (sinif = 'CRITICAL'::text)) THEN 100
            ELSE 0
        END +
        CASE
            WHEN (modul = 'KREATIF'::text) THEN 60
            ELSE 0
        END) +
        CASE
            WHEN ((modul = 'URUN'::text) AND (sinif = 'FIX_FUNNEL_FIRST'::text)) THEN 40
            ELSE 0
        END) +
        CASE
            WHEN (anlik_kalitesi = 'HIGH'::text) THEN 10
            WHEN (anlik_kalitesi = 'MEDIUM'::text) THEN 5
            ELSE 0
        END) AS puan,
        CASE
            WHEN ((modul = 'META'::text) AND (sinif = 'CRITICAL'::text)) THEN 'nakit cikisini dogrudan durdurur - geri alinabilir'::text
            WHEN (modul = 'KREATIF'::text) THEN 'ucuz test, musteri sorusundan turemis, geri alinabilir'::text
            ELSE 'huni duzelmeden olcek anlamsiz - beklemeli'::text
        END AS oncelik_gerekcesi
   FROM b
  ORDER BY (((
        CASE
            WHEN ((modul = 'META'::text) AND (sinif = 'CRITICAL'::text)) THEN 100
            ELSE 0
        END +
        CASE
            WHEN (modul = 'KREATIF'::text) THEN 60
            ELSE 0
        END) +
        CASE
            WHEN ((modul = 'URUN'::text) AND (sinif = 'FIX_FUNNEL_FIRST'::text)) THEN 40
            ELSE 0
        END) +
        CASE
            WHEN (anlik_kalitesi = 'HIGH'::text) THEN 10
            WHEN (anlik_kalitesi = 'MEDIUM'::text) THEN 5
            ELSE 0
        END) DESC, bulgu_id;


ALTER VIEW mart.karar_oncelik OWNER TO n8n;

--
-- Name: karar_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.karar_ozet AS
 SELECT count(*) FILTER (WHERE (durum <> ALL (ARRAY['CONCLUDED'::text, 'CANCELLED'::text, 'REJECTED'::text]))) AS acik_karar,
    count(*) FILTER (WHERE (durum = 'PROPOSED'::text)) AS insan_onayi_bekleyen,
    count(*) FILTER (WHERE (durum = ANY (ARRAY['EXECUTED'::text, 'MEASURING'::text]))) AS uygulandi_olculuyor,
    count(*) FILTER (WHERE (durum = 'CONCLUDED'::text)) AS sonuclanan,
    count(*) FILTER (WHERE (durum = 'REJECTED'::text)) AS reddedilen,
    count(*) FILTER (WHERE (durum = 'DEFERRED'::text)) AS ertelenen,
    ( SELECT count(*) AS count
           FROM (core.karar_sonuc s
             JOIN core.karar k2 USING (karar_id))
          WHERE ((NOT k2.fixture) AND (s.sonuc_durumu = ANY (ARRAY['INCONCLUSIVE'::text, 'NOT_MEASURABLE'::text])))) AS sonucsuz,
    ( SELECT count(DISTINCT rt.itiraz_tipi) AS count
           FROM (core.karar_red_team rt
             JOIN core.karar k3 USING (karar_id))
          WHERE ((NOT k3.fixture) AND (rt.sonuc = 'CHALLENGE'::text))) AS red_team_itirazi,
    ( SELECT count(DISTINCT rt.karar_id) AS count
           FROM (core.karar_red_team rt
             JOIN core.karar k4 USING (karar_id))
          WHERE ((NOT k4.fixture) AND (rt.sonuc = 'CHALLENGE'::text))) AS itiraz_alan_karar,
    count(*) AS toplam
   FROM core.karar
  WHERE (NOT fixture);


ALTER VIEW mart.karar_ozet OWNER TO n8n;

--
-- Name: karar_son; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.karar_son AS
 SELECT k.karar_id,
    ((k.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date AS tarih,
    k.karar_tipi,
    "left"(k.oneri, 60) AS oneri,
    k.kanit_kalitesi,
    COALESCE(i.karar, '—'::text) AS insan_karari,
    k.durum,
    COALESCE(s.sonuc_durumu, '—'::text) AS sonuc,
    COALESCE(s.yanlislandi, '—'::text) AS yanlislandi,
    ( SELECT count(*) AS count
           FROM core.karar_red_team rt
          WHERE ((rt.karar_id = k.karar_id) AND (rt.sonuc = 'CHALLENGE'::text))) AS itiraz
   FROM ((core.karar k
     LEFT JOIN core.karar_insan i ON ((i.karar_id = k.karar_id)))
     LEFT JOIN core.karar_sonuc s ON ((s.karar_id = k.karar_id)))
  WHERE (NOT k.fixture)
  ORDER BY k.karar_id DESC;


ALTER VIEW mart.karar_son OWNER TO n8n;

--
-- Name: kargo_karar_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kargo_karar_ozet AS
 SELECT karar_id,
    siparis_id,
    tasiyici,
    gosterilen_ucret,
    karsi_odemeli,
    karsi_odeme_tutari,
    karar,
    barkod,
    hata,
    veren,
    verildi
   FROM core.kargo_karar
  ORDER BY verildi DESC;


ALTER VIEW mart.kargo_karar_ozet OWNER TO n8n;

--
-- Name: katalog_ilgi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.katalog_ilgi AS
 SELECT urun_slug,
    count(*) AS kayit,
    count(DISTINCT hedef_anahtari) AS hedef,
    count(*) FILTER (WHERE (ilgi = ANY (ARRAY['ILGILENDI'::text, 'NUMUNE'::text, 'SIPARIS_SOZU'::text]))) AS ilgili,
    count(*) FILTER (WHERE (ilgi = 'SIPARIS_SOZU'::text)) AS siparis_sozu,
    count(*) FILTER (WHERE (ilgi = 'YOK'::text)) AS ilgisiz,
    max(girildi) AS son_kayit
   FROM core.katalog_not n
  GROUP BY urun_slug;


ALTER VIEW mart.katalog_ilgi OWNER TO n8n;

--
-- Name: konusma_gunluk; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.konusma_gunluk AS
 WITH yeni AS (
         SELECT ((konusma.ilk_mesaj AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            konusma.kanal,
            count(*) AS yeni_konusma
           FROM lcarlie.konusma
          GROUP BY (((konusma.ilk_mesaj AT TIME ZONE 'Europe/Istanbul'::text))::date), konusma.kanal
        ), msj AS (
         SELECT ((m_1.zaman AT TIME ZONE 'Europe/Istanbul'::text))::date AS gun,
            k.kanal,
            count(*) FILTER (WHERE (m_1.yon = 'gelen'::text)) AS gelen_mesaj,
            count(*) FILTER (WHERE (m_1.yon = 'giden'::text)) AS giden_mesaj
           FROM (lcarlie.mesaj m_1
             JOIN lcarlie.konusma k ON ((k.id = m_1.konusma_id)))
          GROUP BY (((m_1.zaman AT TIME ZONE 'Europe/Istanbul'::text))::date), k.kanal
        )
 SELECT COALESCE(y.gun, m.gun) AS gun,
    COALESCE(y.kanal, m.kanal) AS kanal,
    COALESCE(y.yeni_konusma, (0)::bigint) AS yeni_konusma,
    COALESCE(m.gelen_mesaj, (0)::bigint) AS gelen_mesaj,
    COALESCE(m.giden_mesaj, (0)::bigint) AS giden_mesaj,
    COALESCE((COALESCE(y.gun, m.gun) >= ((mart.kesim() AT TIME ZONE 'Europe/Istanbul'::text))::date), false) AS olcumde,
    (COALESCE(y.gun, m.gun) IS NULL) AS tarih_bilinmiyor
   FROM (yeni y
     FULL JOIN msj m ON (((m.gun = y.gun) AND (m.kanal = y.kanal))))
  ORDER BY COALESCE(y.gun, m.gun) DESC NULLS LAST;


ALTER VIEW mart.konusma_gunluk OWNER TO n8n;

--
-- Name: soru_konu; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.soru_konu AS
 WITH kalip AS (
         SELECT t.konu,
            t.kaliplar,
            t.aciklama
           FROM ( VALUES ('ICERIK'::text,ARRAY['icindeki'::text, 'icinde ne'::text, 'icerik'::text, 'formul'::text],'Urunun icinde ne var'::text), ('FIYAT'::text,ARRAY['fiyat'::text, 'ne kadar'::text, 'kac para'::text, 'ucret'::text],'Fiyat'::text), ('SIPARIS_YOLU'::text,ARRAY['siparis'::text, 'nasil alin'::text, 'nereden al'::text],'Nasil siparis verilir'::text), ('ETKI_FAYDA'::text,ARRAY['ne ise'::text, 'fayda'::text, 'etki'::text, 'ise yar'::text],'Ne ise yarar / faydasi'::text), ('KULLANIM'::text,ARRAY['nasil kullan'::text, 'nereye'::text, 'ne kadar sur'::text, 'gunde'::text],'Nasil kullanilir'::text), ('GUVENLIK'::text,ARRAY['yan etki'::text, 'alerj'::text, 'zararl'::text, 'guvenl'::text],'Yan etki / guvenlik'::text), ('SELAMLAMA'::text,ARRAY['merhaba'::text, 'selam'::text, 'tesekkur'::text, 'sagol'::text],'Selamlasma / tesekkur'::text)) t(konu, kaliplar, aciklama)
        ), esles AS (
         SELECT k.konu,
            k.aciklama,
            m.konusma_id,
            m.metin
           FROM (lcarlie.mesaj m
             JOIN kalip k ON ((EXISTS ( SELECT 1
                   FROM unnest(k.kaliplar) p(p)
                  WHERE (core.tr_norm(m.metin) ~~ (('%'::text || p.p) || '%'::text))))))
          WHERE (m.yon = 'gelen'::text)
        ), toplam AS (
         SELECT (count(*))::numeric AS konusma
           FROM lcarlie.konusma
        )
 SELECT e.konu,
    max(e.aciklama) AS aciklama,
    count(DISTINCT e.konusma_id) AS distinct_konusma,
    count(*) AS eslesen_mesaj,
    round(((100.0 * (count(DISTINCT e.konusma_id))::numeric) / ( SELECT toplam.konusma
           FROM toplam))) AS konusma_yuzde,
    (array_agg(DISTINCT "left"(core.pii_maskele(btrim(e.metin)), 56)))[1:3] AS ornekler,
    'tr_norm + LIKE (her iki taraf normalize)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM esles e
  GROUP BY e.konu
UNION ALL
 SELECT 'DIGER'::text AS konu,
    'Hicbir konuya girmeyen musteri mesaji'::text AS aciklama,
    count(DISTINCT m.konusma_id) AS distinct_konusma,
    count(*) AS eslesen_mesaj,
    round(((100.0 * (count(DISTINCT m.konusma_id))::numeric) / ( SELECT toplam.konusma
           FROM toplam))) AS konusma_yuzde,
    (array_agg(DISTINCT "left"(core.pii_maskele(btrim(m.metin)), 56)))[1:3] AS ornekler,
    'tr_norm + LIKE (her iki taraf normalize)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM lcarlie.mesaj m
  WHERE ((m.yon = 'gelen'::text) AND (btrim(m.metin) <> ''::text) AND (NOT (EXISTS ( SELECT 1
           FROM kalip k,
            LATERAL unnest(k.kaliplar) p(p)
          WHERE (core.tr_norm(m.metin) ~~ (('%'::text || p.p) || '%'::text))))));


ALTER VIEW mart.soru_konu OWNER TO n8n;

--
-- Name: kreatif_hipotez; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kreatif_hipotez AS
 WITH s AS (
         SELECT ( SELECT soru_konu.distinct_konusma
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'ICERIK'::text)) AS icerik,
            ( SELECT soru_konu.distinct_konusma
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'FIYAT'::text)) AS fiyat,
            ( SELECT soru_konu.distinct_konusma
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'SIPARIS_YOLU'::text)) AS siparis_yolu,
            ( SELECT soru_konu.eslesen_mesaj
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'ICERIK'::text)) AS icerik_mesaj,
            ( SELECT soru_konu.eslesen_mesaj
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'FIYAT'::text)) AS fiyat_mesaj,
            ( SELECT soru_konu.eslesen_mesaj
                   FROM mart.soru_konu
                  WHERE (soru_konu.konu = 'SIPARIS_YOLU'::text)) AS siparis_mesaj,
            ( SELECT count(*) AS count
                   FROM lcarlie.konusma) AS toplam
        )
 SELECT h.kod,
    h.hipotez,
    h.kanit,
    h.adet,
    h.mesaj,
    s.toplam,
    round(((100.0 * (h.adet)::numeric) / (NULLIF(s.toplam, 0))::numeric)) AS yuzde,
    h.kanit_kaynagi,
    h.beklenen_etki,
    h.risk,
    h.yanlislama,
    'tr_norm + LIKE (konusma seviyesinde tekil)'::text AS olcum_yontemi,
    true AS normalize_edildi,
    'v2-2026-09-16'::text AS sorgu_surumu
   FROM s,
    LATERAL ( VALUES ('ICERIK_SEFFAFLIGI'::text,'Reklam/sayfa icerik listesini ONDE gostersin'::text,'musterinin kendi sorusu: "icindekiler nelerdir" / "icinde ne var"'::text,s.icerik,s.icerik_mesaj,'mesaj sorusu'::text,'konusma hacmi duser, kalan konusmalar daha yuksek niyetli olur'::text,'Konusma sayisi dusunce reklam performansi dusmus SANILABILIR - onlem: konusma degil SIPARIS olcusune bak'::text,'Icerik listesi one alindiktan sonra ayni soru orani DUSMEZSE hipotez curur'::text), ('FIYAT_SEFFAFLIGI'::text,'Fiyat reklamda/sayfada acikca gorunsun'::text,'musterinin kendi sorusu: "fiyati nedir"'::text,s.fiyat,s.fiyat_mesaj,'mesaj sorusu'::text,'fiyat itirazi konusmadan ONCE elenir, cevapsiz mesaj yuku azalir'::text,'Dusuk fiyat algisi rekabeti tetikleyebilir; ayrica 1.200 TL''ye inen fiyat birim katkiyi yariya indiriyor'::text,'Fiyat gosterildikten sonra soru orani ve cevapsiz mesaj sayisi DUSMEZSE hipotez curur'::text), ('SIPARIS_YOLU'::text,'Siparis adimi tek tikla ulasilir olsun'::text,'musterinin kendi sorusu: "siparis nasil verilir"'::text,s.siparis_yolu,s.siparis_mesaj,'mesaj sorusu'::text,'konusmadan siparise gecis kolaylasir'::text,'Mesajlasma tamamen kesilirse musteri sorusunu hic sormayip vazgecebilir'::text,'Siparis yolu sadelestikten sonra bu soru surerse hipotez curur'::text)) h(kod, hipotez, kanit, adet, mesaj, kanit_kaynagi, beklenen_etki, risk, yanlislama);


ALTER VIEW mart.kreatif_hipotez OWNER TO n8n;

--
-- Name: kreatif_itiraz_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kreatif_itiraz_guncel AS
 SELECT itiraz_id,
    parti,
    dosya,
    konu,
    aciklama,
    muhatap,
    durum,
    cevap,
    cevaplayan,
    cevaplandi,
    acan,
    acildi,
    kapatan,
    kapandi,
    (durum = ANY (ARRAY['ACIK'::text, 'TEKRAR_ACILDI'::text])) AS acik_mi,
    (EXTRACT(day FROM (now() - acildi)))::integer AS gun_gecti
   FROM core.kreatif_itiraz
  ORDER BY (durum = ANY (ARRAY['ACIK'::text, 'TEKRAR_ACILDI'::text])) DESC, acildi DESC;


ALTER VIEW mart.kreatif_itiraz_guncel OWNER TO n8n;

--
-- Name: meta_kreatif; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.meta_kreatif (
    ad_id text NOT NULL,
    ad_adi text,
    ad_durumu text,
    etkin_durum text,
    adset_id text,
    kampanya_id text,
    kreatif_id text,
    kreatif_adi text,
    baslik text,
    govde text,
    cta text,
    nesne_tipi text,
    kucuk_gorsel text,
    video_id text,
    olusturma timestamp with time zone,
    guncelleme timestamp with time zone,
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL,
    hedef_url text,
    url_etiketleri text
);


ALTER TABLE raw.meta_kreatif OWNER TO n8n;

--
-- Name: meta_reklam; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.meta_reklam (
    hesap_id text NOT NULL,
    gun date NOT NULL,
    ad_id text NOT NULL,
    ad_adi text,
    adset_id text,
    adset_adi text,
    kampanya_id text,
    kampanya_adi text,
    harcama numeric(14,2),
    gosterim bigint,
    erisim bigint,
    tiklama bigint,
    link_tiklama bigint,
    ctr numeric(10,6),
    cpc numeric(14,6),
    cpm numeric(14,6),
    frekans numeric(10,6),
    eylemler jsonb,
    eylem_degerleri jsonb,
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.meta_reklam OWNER TO n8n;

--
-- Name: reklam_performans; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.reklam_performans AS
 WITH p AS (
         SELECT r.ad_id,
            r.ad_adi,
            r.kampanya_adi,
            r.adset_adi,
            w.pencere,
            sum(r.harcama) AS harcama,
            sum(r.gosterim) AS gosterim,
            sum(r.erisim) AS erisim,
            sum(r.tiklama) AS tiklama,
            sum(r.link_tiklama) AS link_tiklama,
            round(((100.0 * sum(r.tiklama)) / NULLIF(sum(r.gosterim), (0)::numeric)), 2) AS ctr_yuzde,
            round((sum(r.harcama) / NULLIF(sum(r.tiklama), (0)::numeric)), 2) AS cpc,
            round(((1000.0 * sum(r.harcama)) / NULLIF(sum(r.gosterim), (0)::numeric)), 2) AS cpm,
            sum(( SELECT COALESCE(sum(((e.value ->> 'value'::text))::numeric), (0)::numeric) AS "coalesce"
                   FROM jsonb_array_elements(COALESCE(r.eylemler, '[]'::jsonb)) e(value)
                  WHERE ((e.value ->> 'action_type'::text) ~~ '%purchase%'::text))) AS meta_satis_iddiasi,
            sum(( SELECT COALESCE(sum(((e.value ->> 'value'::text))::numeric), (0)::numeric) AS "coalesce"
                   FROM jsonb_array_elements(COALESCE(r.eylem_degerleri, '[]'::jsonb)) e(value)
                  WHERE ((e.value ->> 'action_type'::text) ~~ '%purchase%'::text))) AS meta_gelir_iddiasi,
            sum(( SELECT COALESCE(sum(((e.value ->> 'value'::text))::numeric), (0)::numeric) AS "coalesce"
                   FROM jsonb_array_elements(COALESCE(r.eylemler, '[]'::jsonb)) e(value)
                  WHERE ((e.value ->> 'action_type'::text) = 'landing_page_view'::text))) AS sayfa_goruntuleme
           FROM (raw.meta_reklam r
             CROSS JOIN ( VALUES (7), (14), (30)) w(pencere))
          WHERE (r.gun > (CURRENT_DATE - w.pencere))
          GROUP BY r.ad_id, r.ad_adi, r.kampanya_adi, r.adset_adi, w.pencere
        )
 SELECT p.pencere,
    p.ad_id,
    p.ad_adi,
    p.kampanya_adi,
    p.adset_adi,
    round(p.harcama, 2) AS harcama,
    p.gosterim,
    p.erisim,
    p.tiklama,
    p.link_tiklama,
    p.ctr_yuzde,
    p.cpc,
    p.cpm,
    k.baslik,
    k.govde,
    k.cta,
    k.nesne_tipi,
    k.etkin_durum,
        CASE
            WHEN (p.gosterim < (1000)::numeric) THEN 'YETERSIZ_ORNEKLEM'::text
            WHEN (p.ctr_yuzde >= (8)::numeric) THEN 'YUKSEK_DIKKAT'::text
            WHEN (p.ctr_yuzde >= (4)::numeric) THEN 'ORTA_DIKKAT'::text
            ELSE 'DUSUK_DIKKAT'::text
        END AS attention,
    p.meta_satis_iddiasi,
    p.meta_gelir_iddiasi,
    p.sayfa_goruntuleme,
        CASE
            WHEN (p.meta_satis_iddiasi > (0)::numeric) THEN 'META_SATIS_IDDIA_EDIYOR'::text
            WHEN (p.sayfa_goruntuleme > (0)::numeric) THEN 'YALNIZ_SAYFA_GORUNTULEME'::text
            ELSE 'META_DONUSUM_YOK'::text
        END AS meta_conversion_signal,
    'NOT_AVAILABLE'::text AS commercial_confirmation,
    '1/3 hesap'::text AS kapsama
   FROM (p
     LEFT JOIN raw.meta_kreatif k ON ((k.ad_id = p.ad_id)));


ALTER VIEW mart.reklam_performans OWNER TO n8n;

--
-- Name: kreatif_karar; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kreatif_karar AS
 SELECT pencere,
    ad_id,
    "left"(COALESCE(ad_adi, '(adsiz)'::text), 28) AS reklam,
    "left"(COALESCE(kampanya_adi, ''::text), 26) AS kampanya,
    harcama,
    gosterim,
    tiklama,
    ctr_yuzde,
    cpc,
    attention,
    meta_conversion_signal,
    commercial_confirmation,
        CASE
            WHEN (attention = 'YETERSIZ_ORNEKLEM'::text) THEN 'INSUFFICIENT_DATA'::text
            WHEN ((attention = 'YUKSEK_DIKKAT'::text) AND (meta_conversion_signal = 'META_SATIS_IDDIA_EDIYOR'::text)) THEN 'YUKSEK_DIKKAT_+_META_IDDIASI'::text
            WHEN (attention = 'YUKSEK_DIKKAT'::text) THEN 'YUKSEK_DIKKAT_SATIS_DOGRULANMADI'::text
            WHEN ((attention = 'DUSUK_DIKKAT'::text) AND (harcama > (500)::numeric)) THEN 'DUSUK_DIKKAT_HARCAMA_SURUYOR'::text
            ELSE 'IZLE'::text
        END AS etiket,
        CASE
            WHEN (attention = 'YETERSIZ_ORNEKLEM'::text) THEN format('%s gosterim - 1000 altinda, oran yaniltici'::text, gosterim)
            WHEN (commercial_confirmation = 'NOT_AVAILABLE'::text) THEN 'Ticari dogrulama YOK: atif kurulamiyor, bu reklamin satis getirip getirmedigi BILINMIYOR. CTR yalnizca dikkat olcer.'::text
            ELSE 'izleniyor'::text
        END AS not_
   FROM mart.reklam_performans;


ALTER VIEW mart.kreatif_karar OWNER TO n8n;

--
-- Name: kreatif_performans; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.kreatif_performans AS
 WITH perf AS (
         SELECT meta_reklam.ad_id,
            count(DISTINCT meta_reklam.gun) AS gun_sayisi,
            min(meta_reklam.gun) AS ilk_gun,
            max(meta_reklam.gun) AS son_gun,
            sum(meta_reklam.harcama) AS harcama,
            sum(meta_reklam.gosterim) AS gosterim,
            sum(meta_reklam.erisim) AS erisim,
            sum(meta_reklam.tiklama) AS tiklama,
            sum(meta_reklam.link_tiklama) AS link_tiklama,
            max(meta_reklam.frekans) AS en_yuksek_frekans
           FROM raw.meta_reklam
          GROUP BY meta_reklam.ad_id
        )
 SELECT k.ad_id,
    k.ad_adi,
    k.kampanya_id,
    k.adset_id,
    k.etkin_durum,
    k.nesne_tipi AS bicim,
    k.cta,
    k.baslik,
    "left"(btrim(COALESCE(k.govde, ''::text)), 300) AS govde,
    length(btrim(COALESCE(k.govde, ''::text))) AS govde_uzunluk,
    (k.video_id IS NOT NULL) AS video_mu,
    p.gun_sayisi,
    p.ilk_gun,
    p.son_gun,
    p.harcama,
    p.gosterim,
    p.erisim,
    p.tiklama,
    p.link_tiklama,
    p.en_yuksek_frekans,
    round(((100.0 * p.tiklama) / NULLIF(p.gosterim, (0)::numeric)), 2) AS ctr,
    round(((100.0 * p.link_tiklama) / NULLIF(p.gosterim, (0)::numeric)), 2) AS link_ctr,
    round((p.harcama / NULLIF(p.link_tiklama, (0)::numeric)), 2) AS link_basi_maliyet,
    round(((1000.0 * p.harcama) / NULLIF(p.gosterim, (0)::numeric)), 2) AS cpm,
    (COALESCE(p.gosterim, (0)::numeric) >= (1000)::numeric) AS yeterli_ornek,
        CASE
            WHEN (p.ad_id IS NULL) THEN 'PERFORMANS_KAYDI_YOK'::text
            WHEN (COALESCE(p.gosterim, (0)::numeric) = (0)::numeric) THEN 'HIC_GOSTERILMEDI'::text
            WHEN (p.gosterim < (1000)::numeric) THEN 'YETERSIZ_ORNEK'::text
            ELSE 'OLCULEBILIR'::text
        END AS olcum_durumu
   FROM (raw.meta_kreatif k
     LEFT JOIN perf p ON ((p.ad_id = k.ad_id)));


ALTER VIEW mart.kreatif_performans OWNER TO n8n;

--
-- Name: lead_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.lead_ozet AS
 SELECT il,
    segment,
    kaynak,
    count(*) AS kayit,
    count(*) FILTER (WHERE temas_edilebilir) AS telefonlu,
    count(*) FILTER (WHERE (site IS NOT NULL)) AS siteli,
    count(*) FILTER (WHERE (ilce IS NOT NULL)) AS ilceli,
    count(*) FILTER (WHERE (iys_durumu = 'ONAYLI'::text)) AS iys_onayli,
    round(avg(yakin_saglik_500m), 2) AS ort_yakin_saglik,
    max(zenginlestirildi) AS son_zenginlestirme
   FROM core.lead
  GROUP BY il, segment, kaynak;


ALTER VIEW mart.lead_ozet OWNER TO n8n;

--
-- Name: urun_sinyal; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_sinyal AS
 WITH satis AS (
         SELECT k.urun_id,
            COALESCE(u.ad, k.urun_adi) AS urun_adi,
            sum(k.adet) AS adet,
            sum(k.satir_ciro_net) AS ciro_net,
            sum(k.satir_maliyet) AS cogs,
            sum(k.brut_marj) AS brut_marj,
            count(DISTINCT k.siparis_id) AS siparis,
            max(k.gun) AS son_satis
           FROM ((mart.siparis_kalem k
             JOIN raw.wix_order w ON ((w.siparis_id = k.siparis_id)))
             LEFT JOIN raw.wix_urun u ON ((u.urun_id = k.urun_id)))
          WHERE ((((w.olusturma AT TIME ZONE 'Europe/Istanbul'::text))::date > (CURRENT_DATE - 30)) AND (w.teslimat_durumu IS DISTINCT FROM 'CANCELED'::text))
          GROUP BY k.urun_id, COALESCE(u.ad, k.urun_adi)
        ), genel AS (
         SELECT nakit_ozet.nakit_durum
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)
        ), kal AS (
         SELECT maliyet_kalite.urun_id,
            maliyet_kalite.kalite
           FROM mart.maliyet_kalite
        )
 SELECT s.urun_id,
    s.urun_adi,
    (round(s.adet))::integer AS adet,
    s.siparis,
    round(s.ciro_net, 2) AS ciro_net,
    round(s.cogs, 2) AS cogs,
    round(s.brut_marj, 2) AS brut_marj,
    round(((100.0 * s.brut_marj) / NULLIF(s.ciro_net, (0)::numeric)), 1) AS brut_marj_yuzde,
    COALESCE(kal.kalite, 'YOK'::text) AS maliyet_kalitesi,
    s.son_satis,
        CASE
            WHEN (s.adet < (3)::numeric) THEN 'INSUFFICIENT_DATA'::text
            WHEN (( SELECT genel.nakit_durum
               FROM genel) = 'CRITICAL'::text) THEN 'FIX_FUNNEL_FIRST'::text
            WHEN (COALESCE(kal.kalite, 'YOK'::text) <> 'OLCULMUS'::text) THEN 'TEST_SMALL'::text
            WHEN (s.brut_marj > (0)::numeric) THEN 'SCALE_CANDIDATE'::text
            ELSE 'HOLD'::text
        END AS sinif,
        CASE
            WHEN (s.adet < (3)::numeric) THEN format('yalniz %s adet - istatistik degil, gozlem'::text, (round(s.adet))::integer)
            WHEN (( SELECT genel.nakit_durum
               FROM genel) = 'CRITICAL'::text) THEN 'son 30 gun nakit durumu CRITICAL: reklam harcamasi net ciroyu asiyor'::text
            WHEN (COALESCE(kal.kalite, 'YOK'::text) <> 'OLCULMUS'::text) THEN 'urun maliyeti olculmemis (sahip tahmini) - marj dogrulanamaz'::text
            ELSE 'brut katki pozitif ve maliyet olculmus'::text
        END AS gerekce
   FROM (satis s
     LEFT JOIN kal ON ((kal.urun_id = s.urun_id)))
  ORDER BY s.ciro_net DESC NULLS LAST;


ALTER VIEW mart.urun_sinyal OWNER TO n8n;

--
-- Name: maliyet_giris_sablonu; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.maliyet_giris_sablonu AS
 SELECT u.urun_id,
    u.ad AS urun_adi,
    u.sku,
    u.fiyat AS satis_fiyati,
    mk.maliyet AS mevcut_deger,
    mk.kalite AS mevcut_kalite,
    COALESCE(s.adet, 0) AS son30_adet,
    COALESCE(s.ciro_net, (0)::numeric) AS son30_ciro_net,
        CASE
            WHEN (mk.kalite = 'OLCULMUS'::text) THEN 'TAMAM'::text
            WHEN (COALESCE(s.ciro_net, (0)::numeric) > (0)::numeric) THEN 'P0 - satti, maliyeti olculmedi'::text
            ELSE 'P2 - satis yok'::text
        END AS oncelik,
    'Wix > Urunler > urun > Maliyet alani'::text AS nereye_girilir
   FROM ((raw.wix_urun u
     LEFT JOIN mart.maliyet_kalite mk ON ((mk.urun_id = u.urun_id)))
     LEFT JOIN ( SELECT urun_sinyal.urun_id,
            urun_sinyal.adet,
            urun_sinyal.ciro_net
           FROM mart.urun_sinyal) s ON ((s.urun_id = u.urun_id)))
  ORDER BY
        CASE
            WHEN (mk.kalite = 'OLCULMUS'::text) THEN 2
            ELSE 1
        END, COALESCE(s.ciro_net, (0)::numeric) DESC;


ALTER VIEW mart.maliyet_giris_sablonu OWNER TO n8n;

--
-- Name: medya_istegi_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.medya_istegi_guncel AS
 SELECT istek_no,
    request_id,
    uc,
    uc_yolu,
    tur,
    ham_istem,
    durum,
    (durum = 'completed'::text) AS uretildi_mi,
    (yerel_dosya IS NOT NULL) AS elimizde_mi,
    (insan_onayi IS NOT NULL) AS bakildi_mi,
    insan_onayi,
    onay_notu,
    onaylayan,
    hata,
    cikti_url,
    yerel_dosya,
    yerel_bayt,
    tahmini_usd,
    tahmini_kredi,
    is_anahtari,
    parti,
    talep_eden,
    yoklama_sayisi,
    son_yoklama,
    olusturuldu,
    guncellendi,
        CASE
            WHEN ((durum = 'completed'::text) AND (yerel_dosya IS NULL)) THEN GREATEST(0, (7 - (EXTRACT(day FROM (now() - guncellendi)))::integer))
            ELSE NULL::integer
        END AS baglanti_kalan_gun
   FROM core.medya_istegi i;


ALTER VIEW mart.medya_istegi_guncel OWNER TO n8n;

--
-- Name: meta_sinyal; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.meta_sinyal AS
 WITH p AS (
         SELECT 7 AS pencere,
            nakit_ozet.gun_sayisi,
            nakit_ozet.baslangic,
            nakit_ozet.bitis,
            nakit_ozet.siparis,
            nakit_ozet.brut_ciro,
            nakit_ozet.net_ciro,
            nakit_ozet.tahsil_beyan,
            nakit_ozet.tahsil_edilmemis,
            nakit_ozet.wixdisi_tahsil,
            nakit_ozet.wixdisi_bekleyen,
            nakit_ozet.bilinen_cogs,
            nakit_ozet.cogs_olculmus_yuzde,
            nakit_ozet.satis_kargosu,
            nakit_ozet.numune_kargosu,
            nakit_ozet.bilinmeyen_kargo,
            nakit_ozet.meta_harcama,
            nakit_ozet.meta_kapsama,
            nakit_ozet.reklam_oncesi,
            nakit_ozet.reklam_sonrasi,
            nakit_ozet.katki_yuzde,
            nakit_ozet.siparis_basina_harcama,
            nakit_ozet.ciro_harcama_orani,
            nakit_ozet.harcamali_satissiz_gun,
            nakit_ozet.nakit_durum
           FROM mart.nakit_ozet(7) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)
        UNION ALL
         SELECT 30 AS pencere,
            nakit_ozet.gun_sayisi,
            nakit_ozet.baslangic,
            nakit_ozet.bitis,
            nakit_ozet.siparis,
            nakit_ozet.brut_ciro,
            nakit_ozet.net_ciro,
            nakit_ozet.tahsil_beyan,
            nakit_ozet.tahsil_edilmemis,
            nakit_ozet.wixdisi_tahsil,
            nakit_ozet.wixdisi_bekleyen,
            nakit_ozet.bilinen_cogs,
            nakit_ozet.cogs_olculmus_yuzde,
            nakit_ozet.satis_kargosu,
            nakit_ozet.numune_kargosu,
            nakit_ozet.bilinmeyen_kargo,
            nakit_ozet.meta_harcama,
            nakit_ozet.meta_kapsama,
            nakit_ozet.reklam_oncesi,
            nakit_ozet.reklam_sonrasi,
            nakit_ozet.katki_yuzde,
            nakit_ozet.siparis_basina_harcama,
            nakit_ozet.ciro_harcama_orani,
            nakit_ozet.harcamali_satissiz_gun,
            nakit_ozet.nakit_durum
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)
        )
 SELECT pencere,
    meta_harcama AS harcama,
    meta_kapsama AS hesap_kapsamasi,
    ( SELECT sum(meta_harcama.gosterim) AS sum
           FROM raw.meta_harcama
          WHERE ((meta_harcama.kampanya_id <> '_HESAP'::text) AND (meta_harcama.gun > (CURRENT_DATE - p.pencere)))) AS gosterim,
    ( SELECT sum(meta_harcama.link_tiklama) AS sum
           FROM raw.meta_harcama
          WHERE ((meta_harcama.kampanya_id <> '_HESAP'::text) AND (meta_harcama.gun > (CURRENT_DATE - p.pencere)))) AS link_tiklama,
    ( SELECT count(DISTINCT meta_harcama.kampanya_id) AS count
           FROM raw.meta_harcama
          WHERE ((meta_harcama.kampanya_id <> '_HESAP'::text) AND (meta_harcama.gun > (CURRENT_DATE - p.pencere)))) AS kampanya,
    ( SELECT COALESCE(sum(meta_harcama.meta_donusum_degeri), (0)::numeric) AS "coalesce"
           FROM raw.meta_harcama
          WHERE ((meta_harcama.kampanya_id <> '_HESAP'::text) AND (meta_harcama.gun > (CURRENT_DATE - p.pencere)))) AS meta_iddia_gelir,
    net_ciro,
    ciro_harcama_orani,
    harcamali_satissiz_gun,
    nakit_durum,
    'NOT_CONNECTED'::text AS kreatif_seviyesi_veri
   FROM p;


ALTER VIEW mart.meta_sinyal OWNER TO n8n;

--
-- Name: mimari_ders; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.mimari_ders AS
 SELECT ders_id,
    kod,
    baslik,
    ders,
    tetikleyen,
    kanit,
    sonuc,
    kaydeden,
    olusturma,
    (gecersiz_kilan IS NULL) AS gecerli,
    gecersizlik_nedeni
   FROM core.mimari_ders d
  ORDER BY (gecersiz_kilan IS NULL) DESC, ders_id;


ALTER VIEW mart.mimari_ders OWNER TO n8n;

--
-- Name: model_kademe_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.model_kademe_guncel AS
 SELECT is_anahtari,
    kademe,
    risk,
    gerekce,
    atayan,
    atandi
   FROM core.model_kademe
  ORDER BY (kademe = 'muhakeme'::text) DESC, is_anahtari;


ALTER VIEW mart.model_kademe_guncel OWNER TO n8n;

--
-- Name: musteri; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.musteri AS
 SELECT c.customer_id,
    c.identity_status,
    c.match_method,
    count(s.siparis_id) FILTER (WHERE s.olcumde) AS siparis_olcumde,
    count(s.siparis_id) AS siparis_tum_zaman,
    COALESCE(sum(s.ciro_dogrulanmis) FILTER (WHERE s.olcumde), (0)::numeric) AS ciro_dogrulanmis,
    COALESCE(sum(s.ciro_beyan_edilmis) FILTER (WHERE s.olcumde), (0)::numeric) AS ciro_beyan_edilmis,
    min(s.olusturma) AS ilk_siparis,
    max(s.olusturma) AS son_siparis
   FROM (core.customer c
     LEFT JOIN mart.siparis s ON ((s.customer_id = c.customer_id)))
  GROUP BY c.customer_id, c.identity_status, c.match_method;


ALTER VIEW mart.musteri OWNER TO n8n;

--
-- Name: olcum_hazirligi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.olcum_hazirligi AS
 SELECT sira,
    engel,
    durum,
    bulgu,
    neyi_engelliyor,
    cozum,
    kimde
   FROM ( VALUES (1,'GA4 veri çekimi'::text,'YOK'::text,'GA4''ten veritabanına veri çeken istemci hiç yazılmadı. raw.yukleme_log''da ga4 kaydı yok.'::text,'Reklamın satışa dönüp dönmediği bilinemiyor.'::text,'GA4 Property ID (sayısal) + Google servis hesabı gerekir. Servis hesabına GA4 yönetiminden Görüntüleyici yetkisi verilmeli.'::text,'SAHIP'::text), (2,'Google kimlik bilgisi'::text,'YOK'::text,'/etc/lcarlie altında Google servis hesabı dosyası yok.'::text,'GA4 Data API çağrılamıyor.'::text,'Google Cloud''da servis hesabı açıp JSON anahtarı /etc/lcarlie/ga4.json olarak konmalı.'::text,'SAHIP'::text), (3,'Sipariş atıf verisi'::text,'YOK'::text,'37 siparişin 37''sinde utm/fbclid/gclid/referrer yok. channelInfo yalnız {"type":"WEB"}.'::text,'Sipariş düzeyinde "hangi reklamdan geldi" sorusu Wix verisiyle cevaplanamaz.'::text,'GA4 purchase olayındaki transaction_id, Wix sipariş numarasıyla eşleştirilecek. mart.ga4_siparis_mutabakat bunu bekliyor.'::text,'GA4_GELINCE'::text), (4,'Huni adımları'::text,'EKSIK'::text,'GA4''e page_view, view_item, add_to_cart gidiyor. begin_checkout ve view_cart GİTMİYOR. purchase''ın durumu ölçülmedi.'::text,'Sepete ekleyip almayan ile hiç sepete eklemeyen ayırt edilemiyor; dönüşüm hunisi karar adımlarında kopuk.'::text,'GTM''de begin_checkout ve view_cart tetikleyicileri kurulmalı; purchase''ın tekil gittiği ilk gerçek siparişte ölçülmeli.'::text,'SITE'::text), (5,'Özel landing ölçümü'::text,'EKSIK'::text,'Özel landing sayfalarında (/vireon gibi) view_item GA4''e gitmiyor; sepete ekleme postMessage köprüsünden geçiyor ve onCartChange ateşlenmiyor.'::text,'Reklam trafiğinin indiği sayfalar sessizce ölçüm dışı kalıyor.'::text,'wixDevelopersAnalytics köprüsü kullanılabilir — Özel Kod katmanından, site yayını gerektirmeden.'::text,'SITE'::text)) t(sira, engel, durum, bulgu, neyi_engelliyor, cozum, kimde);


ALTER VIEW mart.olcum_hazirligi OWNER TO n8n;

--
-- Name: otonomi_olcum; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.otonomi_olcum AS
 SELECT ( SELECT count(*) AS count
           FROM core.acik_soru
          WHERE (acik_soru.ureten <> 'USER'::text)) AS self_initiated_task,
    ( SELECT count(DISTINCT acik_soru.kaynak_plani) AS count
           FROM core.acik_soru
          WHERE (acik_soru.kaynak_plani IS NOT NULL)) AS self_discovered_source,
    ( SELECT count(*) AS count
           FROM core.buyume_bulgu
          WHERE (buyume_bulgu.seviye = 'HYPOTHESIS'::text)) AS hypothesis_generated,
    ( SELECT count(*) AS count
           FROM core.buyume_bulgu
          WHERE (buyume_bulgu.inanc_durumu = ANY (ARRAY['REFUTED'::text, 'WEAKENED'::text]))) AS hypothesis_rejected,
    ( SELECT count(*) AS count
           FROM core.buyume_bulgu
          WHERE (buyume_bulgu.ustunu_alan IS NOT NULL)) AS belief_revised,
    ( SELECT count(*) AS count
           FROM core.karar_red_team
          WHERE (karar_red_team.sonuc = 'CHALLENGE'::text)) AS red_team_challenge,
    ( SELECT count(*) AS count
           FROM core.buyume_bulgu
          WHERE (buyume_bulgu.modul = 'CREATIVE'::text)) AS autonomous_creative,
    ( SELECT count(*) AS count
           FROM core.acik_soru
          WHERE (acik_soru.ureten = 'USER'::text)) AS user_micro_direction,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = 'APPROVED'::text)) AS approval_only_decision,
    ( SELECT count(*) AS count
           FROM core.buyume_bulgu
          WHERE ((buyume_bulgu.seviye = 'HYPOTHESIS'::text) AND (buyume_bulgu.guven >= 0.60))) AS novel_finding,
    ( SELECT count(*) AS count
           FROM core.ic_mesaj) AS internal_message,
    ( SELECT count(*) AS count
           FROM core.ic_mesaj
          WHERE (ic_mesaj.durum = 'COMPLETE'::text)) AS internal_resolved,
    ( SELECT count(*) AS count
           FROM core.inanc_catismasi
          WHERE (inanc_catismasi.durum = 'OPEN'::text)) AS open_conflict,
    ( SELECT count(*) AS count
           FROM core.karar_sonuc) AS karar_sonuc_doluluk,
    ( SELECT count(*) AS count
           FROM core.karar
          WHERE (karar.durum = ANY (ARRAY['MEASURING'::text, 'EXECUTED'::text]))) AS kapatilmayi_bekleyen,
    ( SELECT count(*) AS count
           FROM core.departman
          WHERE (departman.durum = 'CALISIYOR'::text)) AS departman_calisiyor,
    ( SELECT count(*) AS count
           FROM core.departman
          WHERE (departman.durum = 'KISMI'::text)) AS departman_kismi,
    ( SELECT count(*) AS count
           FROM core.departman
          WHERE (departman.durum = 'YOK'::text)) AS departman_yok,
    clock_timestamp() AS olcum_ani;


ALTER VIEW mart.otonomi_olcum OWNER TO n8n;

--
-- Name: siparis_para; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.siparis_para AS
 WITH gnd AS (
         SELECT b.foreign_code AS siparis_id,
            count(*) FILTER (WHERE (b.yon IS DISTINCT FROM 'INCOMING'::text)) AS giden_gonderi,
            count(*) FILTER (WHERE (b.yon = 'INCOMING'::text)) AS iade_gonderi,
            count(*) FILTER (WHERE ((b.yon IS DISTINCT FROM 'INCOMING'::text) AND (b.kargoya_verilis IS NOT NULL))) AS kargolanan,
            count(*) FILTER (WHERE ((b.yon IS DISTINCT FROM 'INCOMING'::text) AND (b.teslim IS NOT NULL))) AS teslim_edilen,
            max(b.kargoya_verilis) AS kargoya_verilis,
            max(b.teslim) AS teslim,
            bool_or(b.cod_var) AS cod_var,
            sum(b.cod_tutar) FILTER (WHERE (b.cod_durum = 'TRANSFERRED'::text)) AS cod_tahsil,
            sum(b.cod_tutar) FILTER (WHERE ((b.cod_durum IS DISTINCT FROM 'TRANSFERRED'::text) AND b.cod_var)) AS cod_bekleyen,
            COALESCE(sum(b.kargo_ucreti), (0)::numeric) AS kargo_gideri
           FROM raw.bk_shipment b
          WHERE (b.foreign_code IS NOT NULL)
          GROUP BY b.foreign_code
        )
 SELECT s.siparis_id,
    s.siparis_no,
    s.gun,
    s.olusturma,
    s.ciro_sinifi,
    s.odeme_yontemi,
    s.toplam AS tutar_kdv_dahil,
    s.toplam_kdv_haric AS tutar_net,
    s.kdv,
    (g.siparis_id IS NOT NULL) AS gonderi_kaydi_var,
        CASE
            WHEN (g.siparis_id IS NULL) THEN NULL::boolean
            ELSE (g.kargolanan > 0)
        END AS kargolandi,
        CASE
            WHEN (g.siparis_id IS NULL) THEN NULL::boolean
            ELSE (g.teslim_edilen > 0)
        END AS teslim_edildi,
        CASE
            WHEN (g.siparis_id IS NULL) THEN NULL::boolean
            ELSE (g.iade_gonderi > 0)
        END AS iade_var,
    g.kargoya_verilis,
    g.teslim,
        CASE
            WHEN (s.ciro_sinifi = 'DOGRULANMIS'::text) THEN s.toplam
            ELSE NULL::numeric
        END AS odeme_onayli_kdv_dahil,
    COALESCE(g.cod_tahsil, (0)::numeric) AS cod_tahsil_edilen,
    COALESCE(g.cod_bekleyen, (0)::numeric) AS cod_bekleyen,
        CASE
            WHEN ((g.teslim_edilen > 0) AND (COALESCE(g.iade_gonderi, (0)::bigint) = 0)) THEN s.toplam_kdv_haric
            ELSE NULL::numeric
        END AS teslim_net_satis,
    COALESCE(g.kargo_gideri, (0)::numeric) AS kargo_gideri,
    s.olcumde
   FROM (mart.siparis s
     LEFT JOIN gnd g ON ((g.siparis_id = s.siparis_id)));


ALTER VIEW mart.siparis_para OWNER TO n8n;

--
-- Name: para_ozet; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.para_ozet AS
 SELECT gun,
    count(*) AS siparis,
    count(*) FILTER (WHERE kargolandi) AS kargolandi,
    count(*) FILTER (WHERE teslim_edildi) AS teslim_edildi,
    count(*) FILTER (WHERE iade_var) AS iadeli,
    count(*) FILTER (WHERE (NOT gonderi_kaydi_var)) AS gonderi_kaydi_yok,
    COALESCE(sum(tutar_kdv_dahil), (0)::numeric) AS tutar_kdv_dahil,
    COALESCE(sum(tutar_net), (0)::numeric) AS tutar_net,
    COALESCE(sum(kdv), (0)::numeric) AS kdv,
    COALESCE(sum(odeme_onayli_kdv_dahil), (0)::numeric) AS odeme_onayli,
    COALESCE(sum(cod_tahsil_edilen), (0)::numeric) AS cod_tahsil,
    COALESCE(sum(cod_bekleyen), (0)::numeric) AS cod_bekleyen,
    COALESCE(sum(teslim_net_satis), (0)::numeric) AS teslim_net_satis,
    COALESCE(sum(kargo_gideri), (0)::numeric) AS kargo_gideri
   FROM mart.siparis_para
  WHERE olcumde
  GROUP BY gun
  ORDER BY gun;


ALTER VIEW mart.para_ozet OWNER TO n8n;

--
-- Name: pazar_arastirma; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.pazar_arastirma AS
 SELECT departman,
    kod,
    seviye,
    bulgu,
    kaynak,
    tarih,
    yorum,
    kaydeden,
    olusturma
   FROM core.pazar_bulgu
  ORDER BY olusturma DESC;


ALTER VIEW mart.pazar_arastirma OWNER TO n8n;

--
-- Name: pazar_sinyal; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.pazar_sinyal AS
 SELECT 'RAKIP_IZLEME'::text AS kod,
    'NOT_CONNECTED'::text AS seviye,
    'Rakip reklam/fiyat izleme kaynagi bagli degil'::text AS bulgu,
    'MANUAL_RESEARCH_REQUIRED'::text AS durum
UNION ALL
 SELECT 'PAZAR_BUYUKLUGU'::text AS kod,
    'NOT_CONNECTED'::text AS seviye,
    'Kategori/pazar verisi kaynagi bagli degil'::text AS bulgu,
    'MANUAL_RESEARCH_REQUIRED'::text AS durum
UNION ALL
 SELECT 'ARAMA_TALEBI'::text AS kod,
    'NOT_CONNECTED'::text AS seviye,
    'Arama hacmi / SEO veri kaynagi bagli degil'::text AS bulgu,
    'MANUAL_RESEARCH_REQUIRED'::text AS durum
UNION ALL
 SELECT 'IC_TALEP_SINYALI'::text AS kod,
    'OBSERVED'::text AS seviye,
    format('Ic veri: %s konusma, %s tekil musteri, en sik iki soru icerik ve fiyat'::text, ( SELECT count(*) AS count
           FROM lcarlie.konusma), ( SELECT count(*) AS count
           FROM core.customer)) AS bulgu,
    'INTERNAL_EVIDENCE'::text AS durum
UNION ALL
 SELECT 'KANAL_DAGILIMI'::text AS kod,
    'OBSERVED'::text AS seviye,
    format('Konusmalarin tamami messenger (%s/%s); Instagram ve WhatsApp ambara akmiyor'::text, ( SELECT count(*) AS count
           FROM lcarlie.konusma
          WHERE (konusma.kanal = 'messenger'::text)), ( SELECT count(*) AS count
           FROM lcarlie.konusma)) AS bulgu,
    'INTERNAL_EVIDENCE'::text AS durum;


ALTER VIEW mart.pazar_sinyal OWNER TO n8n;

--
-- Name: platform_fiyat_matrisi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.platform_fiyat_matrisi AS
 WITH acik AS (
         SELECT urun_platform_fiyat.urun_id,
            urun_platform_fiyat.platform_kod,
            urun_platform_fiyat.fiyat,
            urun_platform_fiyat.yontem,
            urun_platform_fiyat.gerekce,
            urun_platform_fiyat.gecerli_baslangic,
            urun_platform_fiyat.kaydeden
           FROM core.urun_platform_fiyat
          WHERE (urun_platform_fiyat.gecerli_bitis IS NULL)
        ), maliyet AS (
         SELECT urun_maliyet.urun_id,
            urun_maliyet.maliyet,
            urun_maliyet.kaynak,
            urun_maliyet.gerekce
           FROM core.urun_maliyet
          WHERE (urun_maliyet.gecerli_bitis IS NULL)
        ), temel AS (
         SELECT g.urun_id,
            g.urun_adi,
            p.kod AS platform_kod,
            p.ad AS platform_adi,
            p.aktif AS platform_aktif,
            p.yazma_izni,
            p.kdv_yuzde,
            p.kargo_bedeli,
            COALESCE(k.komisyon_yuzde, p.komisyon_yuzde) AS komisyon_yuzde,
            (k.komisyon_yuzde IS NOT NULL) AS komisyon_istisnasi,
            g.musteriye_soylenecek_fiyat AS referans_fiyat,
            g.fiyat_kaynagi AS referans_kaynagi,
            a.fiyat AS platform_fiyati,
            a.yontem,
            a.gerekce,
            a.gecerli_baslangic,
            a.kaydeden,
            COALESCE(a.fiyat, g.musteriye_soylenecek_fiyat) AS gecerli_fiyat,
            m.maliyet AS birim_maliyet,
            m.kaynak AS maliyet_kaynagi,
            m.gerekce AS maliyet_gerekcesi
           FROM ((((mart.fiyat_gercegi g
             CROSS JOIN core.platform p)
             LEFT JOIN acik a ON (((a.urun_id = g.urun_id) AND (a.platform_kod = p.kod))))
             LEFT JOIN core.urun_platform_komisyon k ON (((k.urun_id = g.urun_id) AND (k.platform_kod = p.kod))))
             LEFT JOIN maliyet m ON ((m.urun_id = g.urun_id)))
        )
 SELECT urun_id,
    urun_adi,
    platform_kod,
    platform_adi,
    platform_aktif,
    yazma_izni,
    kdv_yuzde,
    kargo_bedeli,
    komisyon_yuzde,
    komisyon_istisnasi,
    referans_fiyat,
    referans_kaynagi,
    platform_fiyati,
    yontem,
    gerekce,
    gecerli_baslangic,
    kaydeden,
    gecerli_fiyat,
    birim_maliyet,
    maliyet_kaynagi,
    maliyet_gerekcesi,
        CASE
            WHEN (platform_fiyati IS NULL) THEN 'REFERANS'::text
            WHEN (referans_fiyat IS NULL) THEN 'REFERANS_YOK'::text
            WHEN (platform_fiyati > referans_fiyat) THEN 'YUKSEK'::text
            WHEN (platform_fiyati < referans_fiyat) THEN 'DUSUK'::text
            ELSE 'AYNI'::text
        END AS fark_durumu,
        CASE
            WHEN ((platform_fiyati IS NULL) OR (referans_fiyat IS NULL) OR (referans_fiyat = (0)::numeric)) THEN NULL::numeric
            ELSE round((((platform_fiyati / referans_fiyat) - (1)::numeric) * (100)::numeric), 1)
        END AS fark_yuzde,
    round(((gecerli_fiyat * komisyon_yuzde) / 100.0), 2) AS komisyon_tutari,
    round((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))), 2) AS net_kdvsiz,
    round(((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))) - birim_maliyet), 2) AS marj,
        CASE
            WHEN ((gecerli_fiyat IS NULL) OR (komisyon_yuzde IS NULL) OR (birim_maliyet IS NULL)) THEN NULL::numeric
            ELSE round(((100.0 * ((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))) - birim_maliyet)) / NULLIF((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))), (0)::numeric)), 1)
        END AS marj_yuzde,
        CASE
            WHEN (gecerli_fiyat IS NULL) THEN 'FIYAT_YOK'::text
            WHEN (komisyon_yuzde IS NULL) THEN 'KOMISYON_YOK'::text
            WHEN (birim_maliyet IS NULL) THEN 'MALIYET_YOK'::text
            WHEN (((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))) - birim_maliyet) < (0)::numeric) THEN 'ZARAR'::text
            WHEN (((100.0 * ((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))) - birim_maliyet)) / NULLIF((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))), (0)::numeric)) < (10)::numeric) THEN 'KRITIK'::text
            WHEN (((100.0 * ((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))) - birim_maliyet)) / NULLIF((((gecerli_fiyat * ((1)::numeric - (komisyon_yuzde / 100.0))) - kargo_bedeli) / ((1)::numeric + (kdv_yuzde / 100.0))), (0)::numeric)) < (25)::numeric) THEN 'DUSUK'::text
            ELSE 'OK'::text
        END AS marj_uyari
   FROM temel t;


ALTER VIEW mart.platform_fiyat_matrisi OWNER TO n8n;

--
-- Name: red_team; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.red_team AS
 SELECT 'ATIF'::text AS baslik,
    'CHALLENGE'::text AS hukum,
    'Hicbir urun/kampanya seviyesinde satis atfi yok (CR-011: ad eslesmesi 0/259). Reklamin hangi satisi getirdigi BILINMIYOR; urun bazli reklam karari bu veriyle verilemez.'::text AS gerekce,
    'core.source_authority.conversation_messenger = PARTIAL'::text AS kanit
UNION ALL
 SELECT 'KAPSAMA'::text AS baslik,
        CASE
            WHEN ( SELECT meta_kapsama.aktif_tam
               FROM mart.meta_kapsama) THEN 'INSUFFICIENT_EVIDENCE'::text
            ELSE 'CHALLENGE'::text
        END AS hukum,
        CASE
            WHEN ( SELECT meta_kapsama.aktif_tam
               FROM mart.meta_kapsama) THEN format('%s Harcama bu hesaplar icin TAM sayilir. KALAN SINIR bir GROWTH BLOCKER DEGIL, bir OPS riskidir: %s - %s'::text, ( SELECT meta_kapsama.ifade
               FROM mart.meta_kapsama), ( SELECT meta_kapsama.kesif_riski
               FROM mart.meta_kapsama), ( SELECT meta_kapsama.kesif_riski_aciklama
               FROM mart.meta_kapsama))
            ELSE format('%s Harcama bir TABANDIR; gercek harcama daha yuksek olabilir, yani zarar gosterilenden BUYUK olabilir.'::text, ( SELECT meta_kapsama.ifade
               FROM mart.meta_kapsama))
        END AS gerekce,
    'mart.meta_kapsama + core.jeton_otorite (business_management yok)'::text AS kanit
UNION ALL
 SELECT 'ORNEKLEM'::text AS baslik,
        CASE
            WHEN (( SELECT nakit_ozet.siparis
               FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)) < 30) THEN 'CHALLENGE'::text
            ELSE 'SUPPORT'::text
        END AS hukum,
    format('Son 30 gunde %s siparis var. Bu hacimde yuzdeler yaniltici; ham adet konusulmali. Tek bir siparis orani carpici sekilde degistirir.'::text, ( SELECT nakit_ozet.siparis
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum))) AS gerekce,
    'mart.nakit_ozet(30)'::text AS kanit
UNION ALL
 SELECT 'FINANSAL'::text AS baslik,
        CASE
            WHEN (( SELECT nakit_ozet.nakit_durum
               FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)) = 'CRITICAL'::text) THEN 'CHALLENGE'::text
            ELSE 'SUPPORT'::text
        END AS hukum,
    format('Son 30 gun nakit durumu %s: harcama %s TL, net ciro %s TL. Buyume onerisi once bu farki kapatmali; olcek zarari carpar.'::text, ( SELECT nakit_ozet.nakit_durum
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)), ( SELECT to_char(nakit_ozet.meta_harcama, 'FM999990.00'::text) AS to_char
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum)), ( SELECT to_char(nakit_ozet.net_ciro, 'FM999990.00'::text) AS to_char
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum))) AS gerekce,
    'mart.nakit_ozet(30)'::text AS kanit
UNION ALL
 SELECT 'OPERASYON'::text AS baslik,
        CASE
            WHEN (( SELECT count(*) AS count
               FROM mart.konusma_cevapsiz
              WHERE (konusma_cevapsiz.bekleme_saat > (24)::numeric)) > 0) THEN 'CHALLENGE'::text
            ELSE 'SUPPORT'::text
        END AS hukum,
    format('%s cevapsiz musteri mesaji var (en eskisi %s gun). Trafigi artirmak, cevaplanamayan mesaj sayisini artirir - once kapasite.'::text, ( SELECT count(*) AS count
           FROM mart.konusma_cevapsiz
          WHERE (konusma_cevapsiz.bekleme_saat > (24)::numeric)), ( SELECT COALESCE(round((max(konusma_cevapsiz.bekleme_saat) / 24.0), 1), (0)::numeric) AS "coalesce"
           FROM mart.konusma_cevapsiz)) AS gerekce,
    'mart.konusma_cevapsiz'::text AS kanit
UNION ALL
 SELECT 'MEVZUAT'::text AS baslik,
    'CHALLENGE'::text AS hukum,
    'Kozmetik urunde tibbi/performans iddiasi yasak. Hicbir kreatif hipotezi mevzuat kapisindan gecmeden "yayina hazir" sayilamaz; MEVZUAT FILTRESI workflow''u zorunlu adimdir.'::text AS gerekce,
    'n8n MEVZUAT FILTRESI (aktif)'::text AS kanit
UNION ALL
 SELECT 'ALTERNATIF'::text AS baslik,
    'INSUFFICIENT_EVIDENCE'::text AS hukum,
    'Konusma hacmi 81/gun -> 2/gun dustu. Bu reklam performansi, kreatif yorgunlugu, hedefleme degisikligi VEYA veri toplama sorunu olabilir. Elimizdeki veri bunlari AYIRT EDEMEZ; Meta tarafindaki mesaj-baslatma sayisiyla karsilastirilmadan neden ilan edilemez.'::text AS gerekce,
    'mart.konusma_gunluk + raw.meta_harcama'::text AS kanit
UNION ALL
 SELECT 'MALIYET'::text AS baslik,
    'CHALLENGE'::text AS hukum,
    format('Urun maliyetinin olculmus orani %s%%. Tum marj ve urun karsilastirmalari tek bir sahip tahminine dayaniyor; urun secimi bu veriyle yapilirsa yanlis urun secilebilir.'::text, ( SELECT (COALESCE(nakit_ozet.cogs_olculmus_yuzde, (0)::numeric))::text AS "coalesce"
           FROM mart.nakit_ozet(30) nakit_ozet(gun_sayisi, baslangic, bitis, siparis, brut_ciro, net_ciro, tahsil_beyan, tahsil_edilmemis, wixdisi_tahsil, wixdisi_bekleyen, bilinen_cogs, cogs_olculmus_yuzde, satis_kargosu, numune_kargosu, bilinmeyen_kargo, meta_harcama, meta_kapsama, reklam_oncesi, reklam_sonrasi, katki_yuzde, siparis_basina_harcama, ciro_harcama_orani, harcamali_satissiz_gun, nakit_durum))) AS gerekce,
    'mart.maliyet_kalite'::text AS kanit;


ALTER VIEW mart.red_team OWNER TO n8n;

--
-- Name: reklam_donem_kiyasi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.reklam_donem_kiyasi AS
 WITH sinir AS (
         SELECT min(meta_harcama.gun) AS reklam_baslangic,
            max(meta_harcama.gun) AS reklam_bitis
           FROM raw.meta_harcama
        ), donem AS (
         SELECT
                CASE
                    WHEN ((s.olusturma)::date < b.reklam_baslangic) THEN 'REKLAM_ONCESI'::text
                    ELSE 'REKLAM_DONEMI'::text
                END AS donem,
            s.siparis_id,
            s.siparis_no,
            s.olusturma,
            s.gun,
            s.customer_id,
            s.odeme_yontemi,
            s.odeme_durumu,
            s.teslimat_durumu,
            s.arsivlendi,
            s.toplam,
            s.toplam_kdv_haric,
            s.kdv,
            s.ciro_sinifi,
            s.ciro_dogrulanmis,
            s.ciro_beyan_edilmis,
            s.tutar_bekleyen,
            s.tutar_bilinmiyor,
            s.ciro_dogrulanmis_net,
            s.ciro_beyan_edilmis_net,
            s.olcumde,
            s.giren_tipi,
            s.kanal
           FROM (mart.siparis s
             CROSS JOIN sinir b)
        ), ozet AS (
         SELECT d.donem,
            count(*) AS siparis,
            round(sum((d.toplam - d.kdv)), 2) AS net_ciro,
            min((d.olusturma)::date) AS ilk_gun,
            max((d.olusturma)::date) AS son_gun
           FROM donem d
          GROUP BY d.donem
        )
 SELECT donem,
    ilk_gun,
    son_gun,
    ((son_gun - ilk_gun) + 1) AS gun_sayisi,
    round(((((son_gun - ilk_gun) + 1))::numeric / 30.0), 1) AS ay_sayisi,
    siparis,
    net_ciro,
    round(((siparis)::numeric / NULLIF(((((son_gun - ilk_gun) + 1))::numeric / 30.0), (0)::numeric)), 1) AS aylik_siparis,
    round((net_ciro / NULLIF(((((son_gun - ilk_gun) + 1))::numeric / 30.0), (0)::numeric)), 0) AS aylik_ciro,
        CASE
            WHEN (donem = 'REKLAM_DONEMI'::text) THEN ( SELECT round(sum(meta_harcama.harcama), 2) AS round
               FROM raw.meta_harcama)
            ELSE (0)::numeric
        END AS reklam_harcamasi,
        CASE
            WHEN (siparis < 30) THEN ((('ORNEK KUCUK ('::text || siparis) || ' siparis) -- bu sayilardan '::text) || 'nedensellik cikarilamaz'::text)
            ELSE 'ornek yeterli'::text
        END AS istatistik_uyarisi
   FROM ozet o
  ORDER BY donem DESC;


ALTER VIEW mart.reklam_donem_kiyasi OWNER TO n8n;

--
-- Name: reklam_urun; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.reklam_urun AS
 SELECT r.ad_id,
    r.urun_id,
    r.urun_adi,
    r.kaynak,
    r.gerekce,
    k.ad_adi,
    k.etkin_durum,
    r.guncelleme
   FROM (core.reklam_urun r
     LEFT JOIN raw.meta_kreatif k ON ((k.ad_id = r.ad_id)));


ALTER VIEW mart.reklam_urun OWNER TO n8n;

--
-- Name: roas_kapisi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.roas_kapisi AS
 SELECT bool_and(gecti) FILTER (WHERE (kapi = 'P0'::text)) AS p0_gecti,
    bool_and(gecti) AS hepsi_gecti,
    count(*) FILTER (WHERE ((NOT gecti) AND (kapi = 'P0'::text))) AS p0_eksik,
    count(*) FILTER (WHERE (NOT gecti)) AS toplam_eksik,
    COALESCE(string_agg(anahtar, ', '::text ORDER BY sira) FILTER (WHERE ((NOT gecti) AND (kapi = 'P0'::text))), ''::text) AS p0_eksikler,
    COALESCE(string_agg(anahtar, ', '::text ORDER BY sira) FILTER (WHERE ((NOT gecti) AND (kapi = 'DESTEK'::text))), ''::text) AS destek_eksikler,
    COALESCE(string_agg(anahtar, ', '::text ORDER BY sira) FILTER (WHERE ((NOT gecti) AND (kapi = 'TICARI'::text))), ''::text) AS ticari_eksikler,
    COALESCE(string_agg(anahtar, ', '::text ORDER BY sira) FILTER (WHERE ((NOT gecti) AND (kapi = 'DAVRANIS'::text))), ''::text) AS davranis_eksikler,
    COALESCE(bool_and(gecti) FILTER (WHERE (kapi = 'TICARI'::text)), false) AS ticari_gecti,
    (COALESCE(bool_and(gecti) FILTER (WHERE (kapi = 'P0'::text)), false) AND COALESCE(( SELECT ticari_yasayabilirlik.scale_konusulabilir
           FROM mart.ticari_yasayabilirlik), false)) AS scale_konusulabilir,
        CASE
            WHEN bool_and(gecti) FILTER (WHERE (kapi = 'P0'::text)) THEN 'ROAS_KARAR_METRIGI_OLABILIR'::text
            ELSE 'ROAS_KARAR_METRIGI_OLAMAZ'::text
        END AS karar,
        CASE
            WHEN bool_and(gecti) FILTER (WHERE (kapi = 'P0'::text)) THEN 'P0 kapisi acik. ROAS yorumlanabilir; yine de eksik hesap/maliyet varsa yon bellidir.'::text
            ELSE 'P0 kapisi KAPALI. 1 Ekim gelse bile ROAS karar metrigi yapilmaz: cikan sayinin hangi yone yanlis oldugu bilinemez.'::text
        END AS gerekce
   FROM mart.gunluk_hazirlik;


ALTER VIEW mart.roas_kapisi OWNER TO n8n;

--
-- Name: osm_poi; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.osm_poi (
    osm_tur text NOT NULL,
    osm_id bigint NOT NULL,
    ad text,
    tur text NOT NULL,
    enlem double precision NOT NULL,
    boylam double precision NOT NULL,
    telefon text,
    eposta text,
    website text,
    adres text,
    ilce text,
    etiket jsonb NOT NULL,
    ilk_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    son_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    kayip_at timestamp with time zone,
    brans_tahmin text,
    CONSTRAINT osm_poi_osm_tur_check CHECK ((osm_tur = ANY (ARRAY['node'::text, 'way'::text, 'relation'::text])))
);


ALTER TABLE raw.osm_poi OWNER TO n8n;

--
-- Name: overture_poi; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.overture_poi (
    overture_id text NOT NULL,
    ad text,
    tur text NOT NULL,
    kategori text,
    enlem double precision NOT NULL,
    boylam double precision NOT NULL,
    telefon text,
    eposta text,
    website text,
    sosyal text,
    adres text,
    ilce text,
    guven numeric,
    ilk_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    son_gorulme timestamp with time zone DEFAULT now() NOT NULL,
    kayip_at timestamp with time zone
);


ALTER TABLE raw.overture_poi OWNER TO n8n;

--
-- Name: saha_tum; Type: MATERIALIZED VIEW; Schema: mart; Owner: n8n
--

CREATE MATERIALIZED VIEW mart.saha_tum AS
 WITH hepsi AS (
         SELECT ((('osm:'::text || p.osm_tur) || ':'::text) || p.osm_id) AS hedef_anahtari,
            'OSM'::text AS kaynak,
            p.osm_tur,
            p.osm_id,
            NULL::bigint AS nokta_id,
            NULL::text AS overture_id,
            p.ad,
            p.tur,
            p.brans_tahmin AS brans,
                CASE
                    WHEN (p.brans_tahmin IS NOT NULL) THEN 'TAHMIN'::text
                    ELSE 'YOK'::text
                END AS brans_kaynagi,
            NULL::text AS kategori,
            p.telefon,
            p.eposta,
            p.website,
            NULL::text AS sosyal,
            p.adres,
            p.ilce AS ilce_ham,
            p.enlem,
            p.boylam,
            NULL::text AS ilgili_kisi,
            NULL::text AS notlar,
            NULL::numeric AS guven,
            p.ilk_gorulme,
            p.son_gorulme,
            p.kayip_at
           FROM raw.osm_poi p
        UNION ALL
         SELECT ('ovt:'::text || o.overture_id),
            'OVERTURE'::text AS text,
            NULL::text AS text,
            NULL::bigint AS int8,
            NULL::bigint AS int8,
            o.overture_id,
            o.ad,
            o.tur,
            m.brans,
                CASE
                    WHEN (m.brans IS NOT NULL) THEN 'CIKARIM'::text
                    ELSE 'YOK'::text
                END AS "case",
            o.kategori,
            o.telefon,
            o.eposta,
            o.website,
            o.sosyal,
            o.adres,
            o.ilce,
            o.enlem,
            o.boylam,
            NULL::text AS text,
            NULL::text AS text,
            o.guven,
            o.ilk_gorulme,
            o.son_gorulme,
            o.kayip_at
           FROM (raw.overture_poi o
             LEFT JOIN core.saha_brans_esleme m ON ((m.kategori = o.kategori)))
        UNION ALL
         SELECT ('elle:'::text || e_1.nokta_id),
            'ELLE'::text AS text,
            NULL::text AS text,
            NULL::bigint AS int8,
            e_1.nokta_id,
            NULL::text AS text,
            e_1.ad,
            e_1.tur,
            e_1.brans,
                CASE
                    WHEN (e_1.brans IS NOT NULL) THEN 'BEYAN'::text
                    ELSE 'YOK'::text
                END AS "case",
            NULL::text AS text,
            e_1.telefon,
            e_1.eposta,
            e_1.website,
            NULL::text AS text,
            e_1.adres,
            e_1.ilce,
            e_1.enlem,
            e_1.boylam,
            e_1.ilgili_kisi,
            e_1.notlar,
            NULL::numeric AS "numeric",
            e_1.eklendi,
            e_1.eklendi,
            NULL::timestamp with time zone AS timestamptz
           FROM core.saha_elle_nokta e_1
        )
 SELECT h.hedef_anahtari,
    h.kaynak,
    h.osm_tur,
    h.osm_id,
    h.nokta_id,
    h.overture_id,
    h.ad,
    h.tur,
    h.brans,
    h.brans_kaynagi,
    h.kategori,
    h.telefon,
    h.eposta,
    h.website,
    h.sosyal,
    h.adres,
    h.enlem,
    h.boylam,
    h.ilgili_kisi,
    h.notlar,
    h.guven,
    h.ilk_gorulme,
    h.son_gorulme,
    h.kayip_at,
    core.tr_anahtar(h.ad) AS ad_ara,
    h.ilce_ham,
        CASE
            WHEN (e.cesit = ANY (ARRAY['ILCE'::text, 'SEMT'::text])) THEN e.ilce
            ELSE NULL::text
        END AS ilce,
        CASE
            WHEN (e.cesit = 'ILCE'::text) THEN 'BEYAN'::text
            WHEN (e.cesit = 'SEMT'::text) THEN 'SEMTTEN'::text
            WHEN (e.cesit = 'IL'::text) THEN 'IL_YAZILMIS'::text
            WHEN (e.cesit = 'IL_DISI'::text) THEN 'BASKA_IL'::text
            WHEN (h.ilce_ham IS NOT NULL) THEN 'TANINMADI'::text
            ELSE 'YOK'::text
        END AS ilce_kaynagi,
    (d.neden IS NOT NULL) AS kalip_disi,
    d.neden AS kalip_neden,
    ((((((
        CASE
            WHEN (h.kaynak = 'ELLE'::text) THEN 100
            ELSE 0
        END + (((h.telefon IS NOT NULL))::integer * 3)) + (((h.eposta IS NOT NULL))::integer * 3)) + (((h.adres IS NOT NULL))::integer * 2)) + ((h.website IS NOT NULL))::integer) + (((h.brans IS NOT NULL))::integer * 2)) + ((h.ilce_ham IS NOT NULL))::integer) AS zenginlik,
        CASE
            WHEN ((core.tr_anahtar(h.ad) IS NULL) OR (h.enlem IS NULL) OR (h.boylam IS NULL)) THEN h.hedef_anahtari
            ELSE ((((replace(core.tr_anahtar(h.ad), ' '::text, ''::text) || '@'::text) || round((h.enlem)::numeric, 3)) || ','::text) || round((h.boylam)::numeric, 3))
        END AS grup
   FROM ((hepsi h
     LEFT JOIN LATERAL ( SELECT s.ilce,
            s.cesit
           FROM (( SELECT core.tr_anahtar(h.ilce_ham) AS kelime
                UNION ALL
                 SELECT unnest(string_to_array(core.tr_anahtar(h.ilce_ham), ' '::text)) AS unnest) t
             JOIN core.saha_ilce_esleme s ON ((s.ham = t.kelime)))
          ORDER BY
                CASE s.cesit
                    WHEN 'ILCE'::text THEN 1
                    WHEN 'SEMT'::text THEN 2
                    WHEN 'IL'::text THEN 3
                    ELSE 4
                END
         LIMIT 1) e ON (true))
     LEFT JOIN LATERAL ( SELECT k.neden
           FROM core.saha_disla_kalip k
          WHERE (core.tr_anahtar(h.ad) ~ k.kalip)
         LIMIT 1) d ON (true))
  WITH NO DATA;


ALTER MATERIALIZED VIEW mart.saha_tum OWNER TO n8n;

--
-- Name: saha_kaynak; Type: MATERIALIZED VIEW; Schema: mart; Owner: n8n
--

CREATE MATERIALIZED VIEW mart.saha_kaynak AS
 SELECT DISTINCT ON (grup) hedef_anahtari,
    kaynak,
    osm_tur,
    osm_id,
    nokta_id,
    overture_id,
    ad,
    tur,
    brans,
    brans_kaynagi,
    kategori,
    telefon,
    eposta,
    website,
    sosyal,
    adres,
    enlem,
    boylam,
    ilgili_kisi,
    notlar,
    guven,
    ilk_gorulme,
    son_gorulme,
    kayip_at,
    ad_ara,
    ilce_ham,
    ilce,
    ilce_kaynagi,
    kalip_disi,
    kalip_neden,
    zenginlik,
    grup
   FROM mart.saha_tum
  ORDER BY grup, zenginlik DESC, hedef_anahtari
  WITH NO DATA;


ALTER MATERIALIZED VIEW mart.saha_kaynak OWNER TO n8n;

--
-- Name: saha_hedef; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.saha_hedef AS
 SELECT k.hedef_anahtari,
    k.kaynak,
    k.osm_tur,
    k.osm_id,
    k.nokta_id,
    k.overture_id,
    k.grup,
    k.kategori,
    k.website,
    k.sosyal,
    k.adres,
    k.enlem,
    k.boylam,
    k.guven,
    k.ilk_gorulme,
    k.son_gorulme,
    k.kayip_at,
    k.zenginlik,
    k.ilce,
    k.ilce_ham,
    k.ilce_kaynagi,
    COALESCE(b.ad, k.ad) AS ad,
        CASE
            WHEN (lower(COALESCE(b.ad, k.ad)) ~ '\meczane(si)?\M'::text) THEN 'ECZANE'::text
            ELSE k.tur
        END AS tur,
    COALESCE(b.brans, k.brans) AS brans,
        CASE
            WHEN (b.brans IS NOT NULL) THEN 'BEYAN'::text
            ELSE k.brans_kaynagi
        END AS brans_kaynagi,
    COALESCE(b.telefon, k.telefon) AS telefon,
    COALESCE(b.eposta, k.eposta) AS eposta,
    COALESCE(b.ilgili_kisi, k.ilgili_kisi) AS ilgili_kisi,
    COALESCE(b.notlar, k.notlar) AS notlar,
    COALESCE(core.tr_anahtar(b.ad), k.ad_ara) AS ad_ara,
    COALESCE(b.hedef_disi, k.kalip_disi) AS hedef_disi,
        CASE
            WHEN (b.hedef_disi IS TRUE) THEN 'elle işaretlendi'::text
            WHEN (b.hedef_disi IS FALSE) THEN NULL::text
            ELSE k.kalip_neden
        END AS hedef_disi_neden,
    COALESCE(z.ziyaret_sayisi, (0)::bigint) AS ziyaret_sayisi,
    z.son_ziyaret,
    z.son_sonuc
   FROM ((mart.saha_kaynak k
     LEFT JOIN core.saha_bilgi b ON ((b.hedef_anahtari = k.hedef_anahtari)))
     LEFT JOIN LATERAL ( SELECT count(*) AS ziyaret_sayisi,
            max(v.ziyaret_at) AS son_ziyaret,
            (array_agg(v.sonuc ORDER BY v.ziyaret_at DESC))[1] AS son_sonuc
           FROM (core.saha_ziyaret v
             JOIN mart.saha_tum t ON ((t.hedef_anahtari = v.hedef_anahtari)))
          WHERE (t.grup = k.grup)) z ON (true));


ALTER VIEW mart.saha_hedef OWNER TO n8n;

--
-- Name: saha_son_konum; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.saha_son_konum AS
 SELECT DISTINCT ON (kullanici) kullanici,
    ts,
    enlem,
    boylam,
    dogruluk_m,
    kaynak,
    rota_id,
    (round(EXTRACT(epoch FROM (now() - ts))))::bigint AS kac_saniye_once,
        CASE
            WHEN ((now() - ts) > '00:10:00'::interval) THEN 'BAYAT'::text
            ELSE 'TAZE'::text
        END AS tazelik
   FROM core.saha_konum k
  ORDER BY kullanici, ts DESC;


ALTER VIEW mart.saha_son_konum OWNER TO n8n;

--
-- Name: satis_kohort; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.satis_kohort AS
 SELECT c.yaklasim_id,
    y.surum AS yaklasim_surum,
    y.durum AS yaklasim_durum,
    COALESCE(c.urun, '(ürün yok)'::text) AS urun,
    c.soru_tipi,
    count(*) AS gonderilen,
    count(*) FILTER (WHERE (c.sonuc = 'DONUS_VAR'::text)) AS donus_var,
    count(*) FILTER (WHERE (c.sonuc = 'DONUS_YOK'::text)) AS donus_yok,
    count(*) FILTER (WHERE (c.sonuc = 'PENCERE_ACIK'::text)) AS pencere_acik,
        CASE
            WHEN (count(*) FILTER (WHERE (c.sonuc = ANY (ARRAY['DONUS_VAR'::text, 'DONUS_YOK'::text]))) > 0) THEN round(((100.0 * (count(*) FILTER (WHERE (c.sonuc = 'DONUS_VAR'::text)))::numeric) / (count(*) FILTER (WHERE (c.sonuc = ANY (ARRAY['DONUS_VAR'::text, 'DONUS_YOK'::text]))))::numeric), 1)
            ELSE NULL::numeric
        END AS donus_yuzde,
        CASE
            WHEN (count(*) FILTER (WHERE (c.sonuc = ANY (ARRAY['DONUS_VAR'::text, 'DONUS_YOK'::text]))) < 10) THEN 'SMALL_SAMPLE'::text
            ELSE 'OLCULEBILIR'::text
        END AS olcum_durumu,
    min(c.gonderim_zamani) AS ilk_gonderim,
    max(c.gonderim_zamani) AS son_gonderim,
    (round(avg(c.donus_sn) FILTER (WHERE (c.donus_sn IS NOT NULL))))::integer AS ort_donus_sn
   FROM (lcarlie.satis_cevap c
     LEFT JOIN lcarlie.satis_yaklasim y ON ((y.id = c.yaklasim_id)))
  WHERE c.gonderildi
  GROUP BY c.yaklasim_id, y.surum, y.durum, COALESCE(c.urun, '(ürün yok)'::text), c.soru_tipi;


ALTER VIEW mart.satis_kohort OWNER TO n8n;

--
-- Name: sayfa_olcum_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.sayfa_olcum_guncel AS
 SELECT url,
    tur,
    http_kodu,
    baslik,
    baslik_uzunluk,
    meta_uzunluk,
    h1_adet,
    h1_metni,
    kelime_sayisi,
    kanonik,
    ham_bayt,
    js_calistirildi,
    olcum_zamani,
    (h1_adet = 0) AS h1_yok,
    (baslik_uzunluk > 60) AS baslik_kesilir,
    (meta_uzunluk = 0) AS meta_yok,
    (kelime_sayisi < 100) AS jssiz_bakana_ince
   FROM core.sayfa_olcum
  ORDER BY tur, url;


ALTER VIEW mart.sayfa_olcum_guncel OWNER TO n8n;

--
-- Name: sirket_gundemi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.sirket_gundemi AS
 SELECT soru_id,
    hedef,
    COALESCE(oncelik, 'P3'::text) AS oncelik,
    beklenen_bilgi_degeri,
    soru,
    neden_onemli,
    kaynak_plani,
    gereken_departmanlar,
    COALESCE(onay_gereksinimi, 'L3'::text) AS onay,
    ureten,
    durum,
    olusturma,
    (now() - olusturma) AS bekleme
   FROM core.acik_soru s
  WHERE (durum = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'BLOCKED_NEEDS_HUMAN'::text]))
  ORDER BY
        CASE COALESCE(oncelik, 'P3'::text)
            WHEN 'P0'::text THEN 0
            WHEN 'P1'::text THEN 1
            WHEN 'P2'::text THEN 2
            WHEN 'P3'::text THEN 3
            ELSE 4
        END,
        CASE beklenen_bilgi_degeri
            WHEN 'YUKSEK'::text THEN 0
            WHEN 'ORTA'::text THEN 1
            ELSE 2
        END, olusturma;


ALTER VIEW mart.sirket_gundemi OWNER TO n8n;

--
-- Name: soru_konu_semantik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.soru_konu_semantik AS
 WITH etiket AS (
         SELECT m.konusma_id,
            count(DISTINCT k.konu) AS etiket_sayisi
           FROM (lcarlie.mesaj m
             JOIN ( VALUES ('ICERIK'::text,ARRAY['icindeki'::text, 'icinde ne'::text, 'icerik'::text, 'formul'::text]), ('FIYAT'::text,ARRAY['fiyat'::text, 'ne kadar'::text, 'kac para'::text, 'ucret'::text]), ('SIPARIS_YOLU'::text,ARRAY['siparis'::text, 'nasil alin'::text, 'nereden al'::text]), ('ETKI_FAYDA'::text,ARRAY['ne ise'::text, 'fayda'::text, 'etki'::text, 'ise yar'::text]), ('KULLANIM'::text,ARRAY['nasil kullan'::text, 'nereye'::text, 'ne kadar sur'::text, 'gunde'::text]), ('GUVENLIK'::text,ARRAY['yan etki'::text, 'alerj'::text, 'zararl'::text, 'guvenl'::text]), ('SELAMLAMA'::text,ARRAY['merhaba'::text, 'selam'::text, 'tesekkur'::text, 'sagol'::text])) k(konu, kaliplar) ON ((EXISTS ( SELECT 1
                   FROM unnest(k.kaliplar) p(p)
                  WHERE (core.tr_norm(m.metin) ~~ (('%'::text || p.p) || '%'::text))))))
          WHERE (m.yon = 'gelen'::text)
          GROUP BY m.konusma_id
        )
 SELECT 'MULTI_LABEL'::text AS etiketleme,
    ( SELECT count(*) AS count
           FROM lcarlie.konusma) AS payda_tum_konusma,
    ( SELECT count(*) AS count
           FROM etiket) AS etiketli_konusma,
    (( SELECT count(*) AS count
           FROM lcarlie.konusma) - ( SELECT count(*) AS count
           FROM etiket)) AS etiketsiz_konusma,
    ( SELECT count(*) AS count
           FROM etiket
          WHERE (etiket.etiket_sayisi >= 2)) AS overlap_count,
    ( SELECT round(avg(etiket.etiket_sayisi), 2) AS round
           FROM etiket) AS ortalama_etiket,
    ( SELECT max(etiket.etiket_sayisi) AS max
           FROM etiket) AS en_cok_etiket,
    ( SELECT sum(soru_konu.distinct_konusma) AS sum
           FROM mart.soru_konu
          WHERE (soru_konu.konu <> 'DIGER'::text)) AS etiket_sayilari_toplami,
    'Yuzdeler TOPLANMAZ; payda TUM konusmalardir. share-of-classified URETILMEZ.'::text AS uyari;


ALTER VIEW mart.soru_konu_semantik OWNER TO n8n;

--
-- Name: stok_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.stok_guncel AS
 SELECT DISTINCT ON (urun_adi) urun_adi,
    adet,
    nerede,
    giren,
    sayim_zamani,
    not_metni,
    (EXTRACT(day FROM (now() - sayim_zamani)))::integer AS gun_gecti
   FROM core.stok_sayim
  ORDER BY urun_adi, sayim_zamani DESC;


ALTER VIEW mart.stok_guncel OWNER TO n8n;

--
-- Name: tasarim_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.tasarim_guncel AS
 SELECT i.is_id,
    i.is_turu,
    s.ad AS sablon_adi,
    i.isteyen,
    i.istek,
    i.canva_tasarim,
    i.disa_aktarim,
    i.durum,
    i.denetim,
    i.maliyet_tl,
    i.onay,
    i.onaylayan,
    i.onaylandi,
    i.red_sebebi,
    i.uretildi,
    ((i.onay IS NULL) AND (i.durum = 'URETILDI'::text)) AS onay_bekliyor
   FROM (core.tasarim_isi i
     LEFT JOIN core.tasarim_sablon s USING (sablon_id))
  ORDER BY (i.onay IS NULL) DESC, i.uretildi DESC;


ALTER VIEW mart.tasarim_guncel OWNER TO n8n;

--
-- Name: tekrar_kesif_uyarisi; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.tekrar_kesif_uyarisi AS
 SELECT bulgu_id,
    modul,
    seviye,
    baslik,
    guven,
    inanc_durumu,
    olusturma,
    COALESCE(guncelleme, olusturma) AS son_dokunus,
    (now() - COALESCE(guncelleme, olusturma)) AS yas,
        CASE
            WHEN ((now() - COALESCE(guncelleme, olusturma)) > '30 days'::interval) THEN 'BAYAT_YENIDEN_DOGRULA'::text
            ELSE 'TAZE_TEKRAR_ARASTIRMA'::text
        END AS tavsiye
   FROM core.buyume_bulgu b
  WHERE ((seviye = ANY (ARRAY['HYPOTHESIS'::text, 'INFERRED'::text])) AND (COALESCE(inanc_durumu, 'ACTIVE'::text) <> 'REFUTED'::text));


ALTER VIEW mart.tekrar_kesif_uyarisi OWNER TO n8n;

--
-- Name: trendyol_urun; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.trendyol_urun (
    barkod text NOT NULL,
    content_id bigint,
    ad text,
    ham jsonb NOT NULL,
    cekildi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.trendyol_urun OWNER TO n8n;

--
-- Name: urun_alan_karsilastirma; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_alan_karsilastirma AS
 WITH w AS (
         SELECT wix_urun.urun_id,
            wix_urun.ad,
            (wix_urun.ham ->> 'sku'::text) AS sku,
            (wix_urun.ham ->> 'name'::text) AS w_ad,
            (wix_urun.ham ->> 'description'::text) AS w_aciklama,
            ((wix_urun.ham #>> '{priceData,discountedPrice}'::text[]))::numeric AS w_satis,
            ((wix_urun.ham #>> '{priceData,price}'::text[]))::numeric AS w_liste,
            (wix_urun.ham #>> '{stock,quantity}'::text[]) AS w_stok,
            (wix_urun.ham ->> 'visible'::text) AS w_yayinda,
            (wix_urun.ham ->> 'ribbon'::text) AS w_rozet,
            (wix_urun.ham #>> '{seoData,tags}'::text[]) AS w_seo,
            (wix_urun.ham ->> 'slug'::text) AS w_slug,
            mart.dizi_uzunluk((wix_urun.ham #> '{media,items}'::text[])) AS w_gorsel
           FROM raw.wix_urun
        ), t AS (
         SELECT trendyol_urun.barkod,
            trendyol_urun.content_id,
            (trendyol_urun.ham ->> 'title'::text) AS t_ad,
            (trendyol_urun.ham ->> 'description'::text) AS t_aciklama,
            ((trendyol_urun.ham #>> '{fiyat,salePrice}'::text[]))::numeric AS t_satis,
            ((trendyol_urun.ham #>> '{fiyat,listPrice}'::text[]))::numeric AS t_liste,
            (trendyol_urun.ham #>> '{fiyat,quantity}'::text[]) AS t_stok,
            (trendyol_urun.ham #>> '{variant,onSale}'::text[]) AS t_yayinda,
            (trendyol_urun.ham #>> '{variant,vatRate}'::text[]) AS t_kdv,
            (trendyol_urun.ham #>> '{category,name}'::text[]) AS t_kategori,
            mart.dizi_uzunluk((trendyol_urun.ham -> 'images'::text)) AS t_gorsel,
            mart.dizi_uzunluk((trendyol_urun.ham -> 'attributes'::text)) AS t_ozellik
           FROM raw.trendyol_urun
        ), birlesik AS (
         SELECT w.urun_id,
            w.ad,
            w.sku,
            w.w_ad,
            w.w_aciklama,
            w.w_satis,
            w.w_liste,
            w.w_stok,
            w.w_yayinda,
            w.w_rozet,
            w.w_seo,
            w.w_slug,
            w.w_gorsel,
            t.barkod,
            t.content_id,
            t.t_ad,
            t.t_aciklama,
            t.t_satis,
            t.t_liste,
            t.t_stok,
            t.t_yayinda,
            t.t_kdv,
            t.t_kategori,
            t.t_gorsel,
            t.t_ozellik
           FROM (w
             LEFT JOIN t ON ((t.barkod = w.sku)))
        )
 SELECT birlesik.urun_id,
    birlesik.ad AS urun_adi,
    birlesik.sku,
    birlesik.content_id,
    f.sira,
    f.alan,
    f.grup,
    f.wix_deger,
    f.trendyol_deger,
    f.wix_yazilabilir,
    f.trendyol_yazilabilir,
        CASE
            WHEN ((f.wix_deger IS NULL) AND (f.trendyol_deger IS NULL)) THEN 'IKISINDE_DE_YOK'::text
            WHEN (f.trendyol_deger IS NULL) THEN 'YALNIZ_WIX'::text
            WHEN (f.wix_deger IS NULL) THEN 'YALNIZ_TRENDYOL'::text
            WHEN (btrim(f.wix_deger) = btrim(f.trendyol_deger)) THEN 'AYNI'::text
            ELSE 'FARKLI'::text
        END AS durum
   FROM birlesik,
    LATERAL ( VALUES (1,'Ürün adı'::text,'temel'::text,birlesik.w_ad,birlesik.t_ad,true,true), (2,'Açıklama'::text,'temel'::text,birlesik.w_aciklama,birlesik.t_aciklama,true,true), (3,'Satış fiyatı'::text,'fiyat'::text,(birlesik.w_satis)::text,(birlesik.t_satis)::text,true,true), (4,'Liste fiyatı'::text,'fiyat'::text,(birlesik.w_liste)::text,(birlesik.t_liste)::text,true,true), (5,'Stok'::text,'stok'::text,birlesik.w_stok,birlesik.t_stok,true,true), (6,'Yayında'::text,'durum'::text,birlesik.w_yayinda,birlesik.t_yayinda,true,true), (7,'Görsel sayısı'::text,'medya'::text,(birlesik.w_gorsel)::text,(birlesik.t_gorsel)::text,true,true), (8,'Barkod / SKU'::text,'kimlik'::text,birlesik.sku,birlesik.barkod,true,true), (9,'KDV oranı'::text,'fiyat'::text,NULL::text,birlesik.t_kdv,false,true), (10,'Kategori'::text,'temel'::text,NULL::text,birlesik.t_kategori,false,false), (11,'Özellik sayısı'::text,'medya'::text,NULL::text,(birlesik.t_ozellik)::text,false,true), (12,'Rozet'::text,'vitrin'::text,birlesik.w_rozet,NULL::text,true,false), (13,'SEO etiketleri'::text,'vitrin'::text,birlesik.w_seo,NULL::text,true,false), (14,'URL adı (slug)'::text,'vitrin'::text,birlesik.w_slug,NULL::text,true,false)) f(sira, alan, grup, wix_deger, trendyol_deger, wix_yazilabilir, trendyol_yazilabilir);


ALTER VIEW mart.urun_alan_karsilastirma OWNER TO n8n;

--
-- Name: urun_dagitim; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_dagitim AS
 WITH satilan AS (
         SELECT siparis_kalem.urun_adi,
            sum(siparis_kalem.adet) AS adet,
            (count(*))::integer AS satir
           FROM mart.siparis_kalem
          GROUP BY siparis_kalem.urun_adi
        ), elle AS (
         SELECT gonderi_notu.urun_adi,
            sum(COALESCE(gonderi_notu.adet, (0)::numeric)) AS adet,
            (count(*))::integer AS satir,
            sum(COALESCE(gonderi_notu.elle_fiyat, (0)::numeric)) AS tutar
           FROM core.gonderi_notu
          WHERE ((gonderi_notu.tur = 'SATIS'::text) AND (gonderi_notu.siparis_ref IS NULL))
          GROUP BY gonderi_notu.urun_adi
        ), bedelsiz AS (
         SELECT gonderi_notu.urun_adi,
            sum(COALESCE(gonderi_notu.adet, (0)::numeric)) AS adet,
            (count(*))::integer AS satir
           FROM core.gonderi_notu
          WHERE (gonderi_notu.tur = ANY (ARRAY['UGC'::text, 'INFLUENCER'::text, 'NUMUNE'::text, 'HEDIYE'::text]))
          GROUP BY gonderi_notu.urun_adi
        ), adlar AS (
         SELECT satilan.urun_adi
           FROM satilan
        UNION
         SELECT elle.urun_adi
           FROM elle
        UNION
         SELECT bedelsiz.urun_adi
           FROM bedelsiz
        )
 SELECT a.urun_adi,
    COALESCE(s.adet, (0)::numeric) AS satilan_adet,
    COALESCE(s.satir, 0) AS satis_satiri,
    COALESCE(b.adet, (0)::numeric) AS bedelsiz_adet,
    COALESCE(b.satir, 0) AS bedelsiz_satiri,
    ((COALESCE(s.adet, (0)::numeric) + COALESCE(e.adet, (0)::numeric)) + COALESCE(b.adet, (0)::numeric)) AS toplam_cikan,
    COALESCE(e.adet, (0)::numeric) AS elle_satis_adet,
    COALESCE(e.satir, 0) AS elle_satis_satiri,
    COALESCE(e.tutar, (0)::numeric) AS elle_satis_tutari
   FROM (((adlar a
     LEFT JOIN satilan s ON ((NOT (s.urun_adi IS DISTINCT FROM a.urun_adi))))
     LEFT JOIN elle e ON ((NOT (e.urun_adi IS DISTINCT FROM a.urun_adi))))
     LEFT JOIN bedelsiz b ON ((NOT (b.urun_adi IS DISTINCT FROM a.urun_adi))));


ALTER VIEW mart.urun_dagitim OWNER TO n8n;

--
-- Name: urun_inci_durum; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_inci_durum AS
 SELECT urun_anahtari,
    urun_adi,
    (inci IS NOT NULL) AS bilgi_var,
        CASE
            WHEN (inci IS NULL) THEN NULL::integer
            ELSE length(inci)
        END AS uzunluk,
    kaynak,
    kaynak_tur,
    guncelleme
   FROM core.urun_inci;


ALTER VIEW mart.urun_inci_durum OWNER TO n8n;

--
-- Name: urun_karlilik; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_karlilik AS
 SELECT urun_id,
    urun_adi,
    sku,
    count(*) AS kalem,
    sum(adet) AS adet,
    sum(satir_ciro) AS ciro,
    sum(satir_ciro_net) AS ciro_net,
    sum(satir_maliyet) AS maliyet,
    sum(brut_marj) AS brut_marj,
    round(((100.0 * sum(brut_marj)) / NULLIF(sum(satir_ciro_net) FILTER (WHERE maliyeti_biliniyor), (0)::numeric)), 1) AS brut_marj_yuzde,
    count(*) FILTER (WHERE maliyeti_biliniyor) AS maliyeti_bilinen_kalem,
    round(((100.0 * COALESCE(sum(satir_ciro) FILTER (WHERE maliyeti_biliniyor), (0)::numeric)) / NULLIF(sum(satir_ciro), (0)::numeric)), 1) AS kapsama_yuzde
   FROM mart.siparis_kalem k
  WHERE (ciro_sinifi = ANY (ARRAY['DOGRULANMIS'::text, 'BEYAN_EDILMIS'::text]))
  GROUP BY urun_id, urun_adi, sku;


ALTER VIEW mart.urun_karlilik OWNER TO n8n;

--
-- Name: urun_karti; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_karti AS
 WITH satis AS (
         SELECT urun_karlilik.urun_id,
            urun_karlilik.adet,
            urun_karlilik.ciro,
            urun_karlilik.ciro_net,
            urun_karlilik.brut_marj,
            urun_karlilik.brut_marj_yuzde,
            urun_karlilik.kalem
           FROM mart.urun_karlilik
        ), fark AS (
         SELECT urun_alan_karsilastirma.urun_id,
            count(*) FILTER (WHERE (urun_alan_karsilastirma.durum = 'FARKLI'::text)) AS farkli_alan,
            count(*) FILTER (WHERE (urun_alan_karsilastirma.durum = 'YALNIZ_WIX'::text)) AS yalniz_wix,
            count(*) FILTER (WHERE (urun_alan_karsilastirma.durum = 'YALNIZ_TRENDYOL'::text)) AS yalniz_trendyol
           FROM mart.urun_alan_karsilastirma
          GROUP BY urun_alan_karsilastirma.urun_id
        ), platform AS (
         SELECT platform_fiyat_matrisi.urun_id,
            count(*) FILTER (WHERE (platform_fiyat_matrisi.platform_fiyati IS NOT NULL)) AS platform_sayisi,
            min(platform_fiyat_matrisi.marj_yuzde) FILTER (WHERE (platform_fiyat_matrisi.marj_yuzde IS NOT NULL)) AS en_dusuk_marj,
            string_agg((((platform_fiyat_matrisi.platform_adi || ': '::text) || to_char(platform_fiyat_matrisi.gecerli_fiyat, 'FM999G999D00'::text)) || ' TL'::text), ' · '::text ORDER BY platform_fiyat_matrisi.platform_kod) FILTER (WHERE (platform_fiyat_matrisi.gecerli_fiyat IS NOT NULL)) AS fiyat_ozeti
           FROM mart.platform_fiyat_matrisi
          WHERE platform_fiyat_matrisi.platform_aktif
          GROUP BY platform_fiyat_matrisi.urun_id
        )
 SELECT w.urun_id,
    w.ad AS urun_adi,
    (w.ham ->> 'sku'::text) AS sku,
    btrim(regexp_replace(COALESCE((w.ham ->> 'description'::text), ''::text), '<[^>]*>'::text, ' '::text, 'g'::text)) AS aciklama_duz,
    ((w.ham #>> '{priceData,discountedPrice}'::text[]))::numeric AS wix_satis,
    ((w.ham #>> '{priceData,price}'::text[]))::numeric AS wix_liste,
    ((w.ham #>> '{stock,quantity}'::text[]))::integer AS wix_stok,
    ((w.ham ->> 'visible'::text) = 'true'::text) AS wix_yayinda,
    mart.dizi_uzunluk((w.ham #> '{media,items}'::text[])) AS wix_gorsel,
    (t.barkod IS NOT NULL) AS trendyolda_var,
    ((t.ham #>> '{fiyat,salePrice}'::text[]))::numeric AS trendyol_satis,
    ((t.ham #>> '{fiyat,quantity}'::text[]))::integer AS trendyol_stok,
    m.maliyet AS birim_maliyet,
    m.kaynak AS maliyet_kaynagi,
    s.adet AS satilan_adet,
    s.ciro,
    s.brut_marj_yuzde AS satis_marj_yuzde,
    p.platform_sayisi,
    p.fiyat_ozeti,
    p.en_dusuk_marj,
    f.farkli_alan,
    f.yalniz_wix,
    f.yalniz_trendyol
   FROM (((((raw.wix_urun w
     LEFT JOIN raw.trendyol_urun t ON ((t.barkod = (w.ham ->> 'sku'::text))))
     LEFT JOIN ( SELECT urun_maliyet.urun_id,
            urun_maliyet.maliyet,
            urun_maliyet.kaynak
           FROM core.urun_maliyet
          WHERE (urun_maliyet.gecerli_bitis IS NULL)) m ON ((m.urun_id = w.urun_id)))
     LEFT JOIN satis s ON ((s.urun_id = w.urun_id)))
     LEFT JOIN fark f ON ((f.urun_id = w.urun_id)))
     LEFT JOIN platform p ON ((p.urun_id = w.urun_id)));


ALTER VIEW mart.urun_karti OWNER TO n8n;

--
-- Name: urun_seo_guncel; Type: VIEW; Schema: mart; Owner: n8n
--

CREATE VIEW mart.urun_seo_guncel AS
 SELECT urun_id,
    urun_adi,
    sku,
    slug,
    seo_baslik,
    seo_aciklama,
    anahtar_kelimeler,
    ana_anahtar,
    baslik_uzunluk,
    aciklama_uzunluk,
    baslik_var,
    aciklama_var,
    anahtar_var,
    yayinda,
    guncelleme
   FROM core.urun_seo
  ORDER BY urun_adi;


ALTER VIEW mart.urun_seo_guncel OWNER TO n8n;

--
-- Name: hatira; Type: TABLE; Schema: mem0; Owner: mem0_writer
--

CREATE TABLE mem0.hatira (
    id uuid NOT NULL,
    vector public.vector(1024),
    payload jsonb
);


ALTER TABLE mem0.hatira OWNER TO mem0_writer;

--
-- Name: activity_event; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.activity_event (
    id integer NOT NULL,
    category character varying(32) NOT NULL,
    action character varying(64) NOT NULL,
    "typeVersion" integer DEFAULT 1 NOT NULL,
    "userId" uuid,
    "projectId" character varying(36) NOT NULL,
    "resourceType" character varying(32),
    "resourceId" character varying(36),
    "resourceName" text,
    data json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.activity_event OWNER TO n8n;

--
-- Name: activity_event_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.activity_event ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.activity_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: agent_background_job; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_background_job (
    id character varying(36) NOT NULL,
    kind character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    "parentAgentId" character varying(36) NOT NULL,
    "parentThreadId" character varying(128) NOT NULL,
    title character varying(255) NOT NULL,
    "subAgentId" character varying(36),
    "childThreadId" character varying(128),
    "childExecutionId" character varying(36),
    "workflowId" character varying(36),
    "timeoutAt" timestamp(3) with time zone,
    result text,
    error text,
    "settledAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "notifiedAt" timestamp(3) with time zone,
    "parentResourceId" character varying(255) NOT NULL,
    "parentPrincipalHash" character varying(64) NOT NULL,
    CONSTRAINT "CHK_agent_background_job_kind" CHECK (((kind)::text = ANY (ARRAY[('subagent'::character varying)::text, ('workflow'::character varying)::text]))),
    CONSTRAINT "CHK_agent_background_job_status" CHECK (((status)::text = ANY (ARRAY[('running'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text, ('cancelled'::character varying)::text])))
);


ALTER TABLE public.agent_background_job OWNER TO n8n;

--
-- Name: agent_channel_status; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_channel_status (
    "agentId" character varying(36) NOT NULL,
    "integrationType" character varying(64) NOT NULL,
    "credentialId" character varying(36) NOT NULL,
    "hostId" character varying(128) NOT NULL,
    status character varying(16) NOT NULL,
    "errorMessage" text,
    attempts integer DEFAULT 0 NOT NULL,
    "backoffUntil" timestamp(3) with time zone,
    "expiresAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_channel_status_status" CHECK (((status)::text = ANY (ARRAY[('connected'::character varying)::text, ('error'::character varying)::text])))
);


ALTER TABLE public.agent_channel_status OWNER TO n8n;

--
-- Name: agent_chat_attachments; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_chat_attachments (
    id character varying(16) NOT NULL,
    "agentId" character varying(36),
    "projectId" character varying(36) NOT NULL,
    "threadId" character varying(128) NOT NULL,
    "resourceId" character varying(255),
    "binaryDataId" text NOT NULL,
    "fileName" character varying(255) NOT NULL,
    "mimeType" character varying(255) NOT NULL,
    "fileSizeBytes" integer NOT NULL,
    source character varying(32) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_chat_attachments OWNER TO n8n;

--
-- Name: agent_chat_subscriptions; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_chat_subscriptions (
    "agentId" character varying(36) NOT NULL,
    "integrationType" character varying(64) NOT NULL,
    "credentialId" character varying(255) NOT NULL,
    "threadId" character varying(255) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_chat_subscriptions_integrationType" CHECK ((("integrationType")::text = ANY (ARRAY[('telegram'::character varying)::text, ('slack'::character varying)::text, ('linear'::character varying)::text, ('discord'::character varying)::text])))
);


ALTER TABLE public.agent_chat_subscriptions OWNER TO n8n;

--
-- Name: agent_checkpoints; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_checkpoints (
    "runId" character varying(255) NOT NULL,
    "agentId" character varying(255),
    state text,
    expired boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_checkpoints OWNER TO n8n;

--
-- Name: agent_credential_dependency; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_credential_dependency (
    "agentId" character varying(36) NOT NULL,
    "credentialId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_credential_dependency OWNER TO n8n;

--
-- Name: agent_eval_dataset; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_eval_dataset (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    description text,
    "agentId" character varying(36) NOT NULL,
    "datasetSource" character varying(32) NOT NULL,
    "datasetRef" json NOT NULL,
    "columnMapping" json,
    "createdById" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_eval_dataset_datasetSource" CHECK ((("datasetSource")::text = ANY (ARRAY[('data_table'::character varying)::text, ('google_sheets'::character varying)::text])))
);


ALTER TABLE public.agent_eval_dataset OWNER TO n8n;

--
-- Name: agent_eval_rating; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_eval_rating (
    id character varying(36) NOT NULL,
    "resultId" character varying(36) NOT NULL,
    vote character varying(8) NOT NULL,
    comment text,
    correction json,
    "ratedById" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_eval_rating_vote" CHECK (((vote)::text = ANY (ARRAY[('up'::character varying)::text, ('down'::character varying)::text])))
);


ALTER TABLE public.agent_eval_rating OWNER TO n8n;

--
-- Name: agent_eval_result; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_eval_result (
    id character varying(36) NOT NULL,
    "runId" character varying(36) NOT NULL,
    "sourceRowId" character varying(255),
    "runIndex" integer,
    status character varying NOT NULL,
    input json,
    output json,
    "toolCalls" json,
    metrics json,
    "runAt" timestamp(3) with time zone,
    "completedAt" timestamp(3) with time zone,
    "errorCode" character varying(255),
    "errorDetails" json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_eval_result_status" CHECK (((status)::text = ANY (ARRAY[('new'::character varying)::text, ('running'::character varying)::text, ('success'::character varying)::text, ('error'::character varying)::text, ('cancelled'::character varying)::text])))
);


ALTER TABLE public.agent_eval_result OWNER TO n8n;

--
-- Name: agent_eval_run; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_eval_run (
    id character varying(36) NOT NULL,
    "datasetId" character varying(36) NOT NULL,
    "agentVersionId" character varying(36),
    status character varying NOT NULL,
    "runAt" timestamp(3) with time zone,
    "completedAt" timestamp(3) with time zone,
    metrics json,
    "errorCode" character varying(255),
    "errorDetails" json,
    "runningInstanceId" character varying(255),
    "cancelRequested" boolean DEFAULT false NOT NULL,
    "createdById" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agent_eval_run_status" CHECK (((status)::text = ANY (ARRAY[('new'::character varying)::text, ('running'::character varying)::text, ('completed'::character varying)::text, ('error'::character varying)::text, ('cancelled'::character varying)::text])))
);


ALTER TABLE public.agent_eval_run OWNER TO n8n;

--
-- Name: agent_execution; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_execution (
    id character varying(36) NOT NULL,
    "threadId" character varying(128) NOT NULL,
    status character varying(16) NOT NULL,
    "startedAt" timestamp(3) with time zone,
    "stoppedAt" timestamp(3) with time zone,
    duration integer DEFAULT 0 NOT NULL,
    "userMessage" text,
    model character varying(255),
    "promptTokens" integer,
    "completionTokens" integer,
    "totalTokens" integer,
    cost double precision,
    timeline json,
    error text,
    "hitlStatus" character varying(16),
    source character varying(32),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "storedAt" character varying(2) DEFAULT 'db'::character varying NOT NULL,
    attachments json,
    "failureSummary" json,
    author json,
    CONSTRAINT "CHK_agent_execution_hitlStatus" CHECK ((("hitlStatus")::text = ANY (ARRAY[('suspended'::character varying)::text, ('resumed'::character varying)::text]))),
    CONSTRAINT "CHK_agent_execution_status" CHECK (((status)::text = ANY (ARRAY[('running'::character varying)::text, ('success'::character varying)::text, ('error'::character varying)::text, ('cancelled'::character varying)::text, ('interrupted'::character varying)::text]))),
    CONSTRAINT "CHK_agent_execution_storedAt" CHECK ((("storedAt")::text = ANY (ARRAY[('db'::character varying)::text, ('fs'::character varying)::text, ('s3'::character varying)::text, ('az'::character varying)::text])))
);


ALTER TABLE public.agent_execution OWNER TO n8n;

--
-- Name: agent_execution_threads; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_execution_threads (
    id character varying(128) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "agentName" character varying(255) NOT NULL,
    "projectId" character varying(255) NOT NULL,
    "sessionNumber" integer DEFAULT 0 NOT NULL,
    "totalPromptTokens" integer DEFAULT 0 NOT NULL,
    "totalCompletionTokens" integer DEFAULT 0 NOT NULL,
    "totalCost" double precision DEFAULT 0 NOT NULL,
    "totalDuration" integer DEFAULT 0 NOT NULL,
    title character varying(255),
    emoji character varying(8),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "taskId" character varying(32),
    "taskVersionId" character varying(36),
    "parentThreadId" character varying(128),
    "parentAgentId" character varying(36)
);


ALTER TABLE public.agent_execution_threads OWNER TO n8n;

--
-- Name: agent_files; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_files (
    id character varying(16) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "binaryDataId" text,
    "fileName" character varying(255) NOT NULL,
    "mimeType" character varying(255) NOT NULL,
    "fileSizeBytes" integer NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "storedAt" character varying(2) DEFAULT 'db'::character varying NOT NULL,
    "storageKey" text NOT NULL,
    CONSTRAINT "CHK_agent_files_storedAt" CHECK ((("storedAt")::text = ANY (ARRAY[('db'::character varying)::text, ('fs'::character varying)::text, ('s3'::character varying)::text, ('az'::character varying)::text])))
);


ALTER TABLE public.agent_files OWNER TO n8n;

--
-- Name: agent_history; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_history (
    "versionId" character varying(36) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    schema json,
    tools json,
    skills json,
    "publishedById" uuid,
    author character varying(255) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_history OWNER TO n8n;

--
-- Name: agent_task_definition; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_task_definition (
    id character varying(32) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    objective text NOT NULL,
    "cronExpression" character varying(128) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    timezone character varying(64)
);


ALTER TABLE public.agent_task_definition OWNER TO n8n;

--
-- Name: agent_task_run_lock; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_task_run_lock (
    "agentId" character varying(36) NOT NULL,
    "taskId" character varying(32) NOT NULL,
    "holderId" uuid NOT NULL,
    "heldUntil" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_task_run_lock OWNER TO n8n;

--
-- Name: agent_task_snapshot; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_task_snapshot (
    "versionId" character varying(36) NOT NULL,
    "taskId" character varying(32) NOT NULL,
    enabled boolean NOT NULL,
    name character varying(128) NOT NULL,
    objective text NOT NULL,
    "cronExpression" character varying(128) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    timezone character varying(64)
);


ALTER TABLE public.agent_task_snapshot OWNER TO n8n;

--
-- Name: agent_workflow_dependency; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agent_workflow_dependency (
    "agentId" character varying(36) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agent_workflow_dependency OWNER TO n8n;

--
-- Name: agents; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    "projectId" character varying(255) NOT NULL,
    integrations json DEFAULT '[]'::json NOT NULL,
    schema json,
    tools json DEFAULT '{}'::json NOT NULL,
    skills json DEFAULT '{}'::json NOT NULL,
    "versionId" character varying(36),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "activeVersionId" character varying(36),
    "availableInMCP" boolean DEFAULT false NOT NULL,
    "setupCompletedAt" timestamp(3) with time zone,
    revision integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.agents OWNER TO n8n;

--
-- Name: agents_memory_entries; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_memory_entries (
    id character varying(36) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    content text NOT NULL,
    "contentHash" character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    "supersededBy" character varying(36),
    "embeddingModel" character varying(128),
    embedding json,
    metadata json,
    "lastSeenAt" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agents_memory_entries_status" CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('superseded'::character varying)::text, ('dropped'::character varying)::text])))
);


ALTER TABLE public.agents_memory_entries OWNER TO n8n;

--
-- Name: agents_memory_entry_candidates; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_memory_entry_candidates (
    id character varying(36) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    "threadId" character varying(255) NOT NULL,
    "sourceMessageId" character varying(36),
    "runId" character varying(255) NOT NULL,
    "toolCallId" character varying(255) NOT NULL,
    content text NOT NULL,
    "evidenceText" text NOT NULL,
    kind character varying(32) NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    "attemptCount" smallint DEFAULT 0 NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agents_memory_entry_candidates_status" CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('completed'::character varying)::text, ('failed'::character varying)::text])))
);


ALTER TABLE public.agents_memory_entry_candidates OWNER TO n8n;

--
-- Name: agents_memory_entry_locks; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_memory_entry_locks (
    "agentId" character varying(36) NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    "holderId" character varying(64) NOT NULL,
    "heldUntil" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agents_memory_entry_locks OWNER TO n8n;

--
-- Name: agents_memory_entry_sources; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_memory_entry_sources (
    id character varying(36) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "memoryEntryId" character varying(36) NOT NULL,
    "observationId" character varying(36),
    "threadId" character varying(255) NOT NULL,
    "evidenceHash" character varying(64) NOT NULL,
    "evidenceText" text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "candidateId" character varying(36),
    CONSTRAINT "CHK_agents_memory_entry_sources_exactly_one_source" CHECK (((("observationId" IS NOT NULL) AND ("candidateId" IS NULL)) OR (("observationId" IS NULL) AND ("candidateId" IS NOT NULL))))
);


ALTER TABLE public.agents_memory_entry_sources OWNER TO n8n;

--
-- Name: agents_messages; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_messages (
    id character varying(36) NOT NULL,
    "threadId" character varying(255) NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    role character varying(36) NOT NULL,
    type character varying(36),
    content json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agents_messages OWNER TO n8n;

--
-- Name: agents_observation_cursors; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_observation_cursors (
    "agentId" character varying(36) NOT NULL,
    "observationScopeId" character varying(255) NOT NULL,
    "lastObservedMessageId" character varying(36) NOT NULL,
    "lastObservedAt" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agents_observation_cursors OWNER TO n8n;

--
-- Name: agents_observation_locks; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_observation_locks (
    "agentId" character varying(36) NOT NULL,
    "observationScopeId" character varying(255) NOT NULL,
    "taskKind" character varying(20) NOT NULL,
    "holderId" character varying(64) NOT NULL,
    "heldUntil" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agents_observation_locks_taskKind" CHECK ((("taskKind")::text = ANY (ARRAY[('observer'::character varying)::text, ('reflector'::character varying)::text])))
);


ALTER TABLE public.agents_observation_locks OWNER TO n8n;

--
-- Name: agents_observations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_observations (
    id character varying(36) NOT NULL,
    "agentId" character varying(36) NOT NULL,
    "observationScopeId" character varying(255) NOT NULL,
    marker character varying(16) NOT NULL,
    text text NOT NULL,
    "parentId" character varying(36),
    "tokenCount" integer DEFAULT 0 NOT NULL,
    status character varying(16) NOT NULL,
    "supersededBy" character varying(36),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_agents_observations_marker" CHECK (((marker)::text = ANY (ARRAY[('critical'::character varying)::text, ('important'::character varying)::text, ('info'::character varying)::text, ('completion'::character varying)::text]))),
    CONSTRAINT "CHK_agents_observations_status" CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('superseded'::character varying)::text, ('dropped'::character varying)::text])))
);


ALTER TABLE public.agents_observations OWNER TO n8n;

--
-- Name: agents_resources; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_resources (
    id character varying(255) NOT NULL,
    metadata text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agents_resources OWNER TO n8n;

--
-- Name: agents_threads; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.agents_threads (
    id character varying(128) NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    title character varying(255),
    metadata text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.agents_threads OWNER TO n8n;

--
-- Name: ai_builder_temporary_workflow; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.ai_builder_temporary_workflow (
    "workflowId" character varying(36) NOT NULL,
    "threadId" uuid NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.ai_builder_temporary_workflow OWNER TO n8n;

--
-- Name: ai_preference; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.ai_preference (
    id uuid NOT NULL,
    content text NOT NULL,
    "userId" uuid,
    "projectId" character varying(36),
    "createdById" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_ai_preference_single_target" CHECK ((("userId" IS NULL) OR ("projectId" IS NULL)))
);


ALTER TABLE public.ai_preference OWNER TO n8n;

--
-- Name: annotation_tag_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.annotation_tag_entity (
    id character varying(16) NOT NULL,
    name character varying(24) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.annotation_tag_entity OWNER TO n8n;

--
-- Name: auth_identity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.auth_identity (
    "userId" uuid,
    "providerId" character varying(255) NOT NULL,
    "providerType" character varying(32) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.auth_identity OWNER TO n8n;

--
-- Name: auth_provider_sync_history; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.auth_provider_sync_history (
    id integer NOT NULL,
    "providerType" character varying(32) NOT NULL,
    "runMode" text NOT NULL,
    status text NOT NULL,
    "startedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "endedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    scanned integer NOT NULL,
    created integer NOT NULL,
    updated integer NOT NULL,
    disabled integer NOT NULL,
    error text
);


ALTER TABLE public.auth_provider_sync_history OWNER TO n8n;

--
-- Name: auth_provider_sync_history_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.auth_provider_sync_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.auth_provider_sync_history_id_seq OWNER TO n8n;

--
-- Name: auth_provider_sync_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.auth_provider_sync_history_id_seq OWNED BY public.auth_provider_sync_history.id;


--
-- Name: binary_data; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.binary_data (
    "fileId" uuid NOT NULL,
    "sourceType" character varying(50) NOT NULL,
    "sourceId" character varying(255) NOT NULL,
    data bytea NOT NULL,
    "mimeType" character varying(255),
    "fileName" character varying(255),
    "fileSize" integer NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_binary_data_sourceType" CHECK ((("sourceType")::text = ANY (ARRAY[('execution'::character varying)::text, ('chat_message_attachment'::character varying)::text, ('agent_file'::character varying)::text, ('agent_chat_attachment'::character varying)::text])))
);


ALTER TABLE public.binary_data OWNER TO n8n;

--
-- Name: chat_hub_agent_tools; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_agent_tools (
    "agentId" uuid NOT NULL,
    "toolId" uuid NOT NULL
);


ALTER TABLE public.chat_hub_agent_tools OWNER TO n8n;

--
-- Name: chat_hub_agents; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_agents (
    id uuid NOT NULL,
    name character varying(256) NOT NULL,
    description character varying(512),
    "systemPrompt" text NOT NULL,
    "ownerId" uuid NOT NULL,
    "credentialId" character varying(36),
    provider character varying(16) NOT NULL,
    model character varying(64) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    icon json,
    files json DEFAULT '[]'::json NOT NULL,
    "suggestedPrompts" json DEFAULT '[]'::json NOT NULL
);


ALTER TABLE public.chat_hub_agents OWNER TO n8n;

--
-- Name: chat_hub_messages; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_messages (
    id uuid NOT NULL,
    "sessionId" uuid NOT NULL,
    "previousMessageId" uuid,
    "revisionOfMessageId" uuid,
    "retryOfMessageId" uuid,
    type character varying(16) NOT NULL,
    name character varying(128) NOT NULL,
    content text NOT NULL,
    provider character varying(16),
    model character varying(256),
    "workflowId" character varying(36),
    "executionId" integer,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "agentId" uuid,
    status character varying(16) DEFAULT 'success'::character varying NOT NULL,
    attachments json
);


ALTER TABLE public.chat_hub_messages OWNER TO n8n;

--
-- Name: chat_hub_session_tools; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_session_tools (
    "sessionId" uuid NOT NULL,
    "toolId" uuid NOT NULL
);


ALTER TABLE public.chat_hub_session_tools OWNER TO n8n;

--
-- Name: chat_hub_sessions; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_sessions (
    id uuid NOT NULL,
    title character varying(256) NOT NULL,
    "ownerId" uuid NOT NULL,
    "lastMessageAt" timestamp(3) with time zone NOT NULL,
    "credentialId" character varying(36),
    provider character varying(16),
    model character varying(256),
    "workflowId" character varying(36),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "agentId" uuid,
    "agentName" character varying(128),
    type character varying(16) DEFAULT 'production'::character varying NOT NULL,
    CONSTRAINT "CHK_chat_hub_sessions_type" CHECK (((type)::text = ANY (ARRAY[('production'::character varying)::text, ('manual'::character varying)::text])))
);


ALTER TABLE public.chat_hub_sessions OWNER TO n8n;

--
-- Name: chat_hub_tools; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.chat_hub_tools (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    type character varying(255) NOT NULL,
    "typeVersion" double precision NOT NULL,
    "ownerId" uuid NOT NULL,
    definition json NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.chat_hub_tools OWNER TO n8n;

--
-- Name: credential_dependency; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.credential_dependency (
    id integer NOT NULL,
    "credentialId" character varying(36) NOT NULL,
    "dependencyType" character varying(64) NOT NULL,
    "dependencyId" character varying(255) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.credential_dependency OWNER TO n8n;

--
-- Name: credential_dependency_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.credential_dependency ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.credential_dependency_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: credentials_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.credentials_entity (
    name character varying(128) NOT NULL,
    data text NOT NULL,
    type character varying(128) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    id character varying(36) NOT NULL,
    "isManaged" boolean DEFAULT false NOT NULL,
    "isGlobal" boolean DEFAULT false NOT NULL,
    "isResolvable" boolean DEFAULT false NOT NULL,
    "resolvableAllowFallback" boolean DEFAULT false NOT NULL,
    "resolverId" character varying(16),
    "usageScope" character varying(16) DEFAULT 'project'::character varying NOT NULL,
    CONSTRAINT "CHK_credentials_entity_usageScope" CHECK ((("usageScope")::text = ANY (ARRAY[('project'::character varying)::text, ('instance'::character varying)::text])))
);


ALTER TABLE public.credentials_entity OWNER TO n8n;

--
-- Name: data_table; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.data_table (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    "projectId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.data_table OWNER TO n8n;

--
-- Name: data_table_column; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.data_table_column (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    type character varying(32) NOT NULL,
    index integer NOT NULL,
    "dataTableId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.data_table_column OWNER TO n8n;

--
-- Name: deployment_key; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.deployment_key (
    id character varying(36) NOT NULL,
    type character varying(64) NOT NULL,
    value text NOT NULL,
    algorithm character varying(20),
    status character varying(20) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.deployment_key OWNER TO n8n;

--
-- Name: dynamic_credential_entry; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.dynamic_credential_entry (
    credential_id character varying(16) NOT NULL,
    subject_id character varying(2048) NOT NULL,
    resolver_id character varying(16) NOT NULL,
    data text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.dynamic_credential_entry OWNER TO n8n;

--
-- Name: dynamic_credential_resolver; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.dynamic_credential_resolver (
    id character varying(16) NOT NULL,
    name character varying(128) NOT NULL,
    type character varying(128) NOT NULL,
    config text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.dynamic_credential_resolver OWNER TO n8n;

--
-- Name: dynamic_credential_user_entry; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.dynamic_credential_user_entry (
    "credentialId" character varying(16) NOT NULL,
    "userId" uuid NOT NULL,
    "resolverId" character varying(16) NOT NULL,
    data text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.dynamic_credential_user_entry OWNER TO n8n;

--
-- Name: evaluation_collection; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.evaluation_collection (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    description text,
    "workflowId" character varying(36) NOT NULL,
    "evaluationConfigId" character varying(36) NOT NULL,
    "createdById" uuid,
    "insightsCache" json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.evaluation_collection OWNER TO n8n;

--
-- Name: evaluation_config; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.evaluation_config (
    id character varying(36) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    status character varying(16) DEFAULT 'valid'::character varying NOT NULL,
    "invalidReason" character varying(64),
    "datasetSource" character varying(32) NOT NULL,
    "datasetRef" json NOT NULL,
    "startNodeName" character varying(255) NOT NULL,
    "endNodeName" character varying(255) NOT NULL,
    metrics json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.evaluation_config OWNER TO n8n;

--
-- Name: event_destinations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.event_destinations (
    id uuid NOT NULL,
    destination jsonb NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.event_destinations OWNER TO n8n;

--
-- Name: execution_annotation_tags; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.execution_annotation_tags (
    "annotationId" integer NOT NULL,
    "tagId" character varying(24) NOT NULL
);


ALTER TABLE public.execution_annotation_tags OWNER TO n8n;

--
-- Name: execution_annotations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.execution_annotations (
    id integer NOT NULL,
    "executionId" integer NOT NULL,
    vote character varying(6),
    note text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.execution_annotations OWNER TO n8n;

--
-- Name: execution_annotations_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.execution_annotations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.execution_annotations_id_seq OWNER TO n8n;

--
-- Name: execution_annotations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.execution_annotations_id_seq OWNED BY public.execution_annotations.id;


--
-- Name: execution_data; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.execution_data (
    "executionId" integer NOT NULL,
    "workflowData" json NOT NULL,
    data text NOT NULL,
    "workflowVersionId" character varying(36)
);


ALTER TABLE public.execution_data OWNER TO n8n;

--
-- Name: execution_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.execution_entity (
    id integer NOT NULL,
    finished boolean NOT NULL,
    mode character varying NOT NULL,
    "retryOf" character varying,
    "retrySuccessId" character varying,
    "startedAt" timestamp(3) with time zone,
    "stoppedAt" timestamp(3) with time zone,
    "waitTill" timestamp(3) with time zone,
    status character varying NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "deletedAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "storedAt" character varying(2) DEFAULT 'db'::character varying NOT NULL,
    "tracingContext" json,
    "deduplicationKey" character varying(255),
    "jsonSizeBytes" bigint DEFAULT 0 NOT NULL,
    "workflowVersionId" character varying(36) DEFAULT NULL::character varying,
    "binaryDataSizeBytes" bigint DEFAULT 0 NOT NULL,
    "usedPrivateCredentials" boolean DEFAULT false NOT NULL,
    CONSTRAINT "CHK_execution_entity_storedAt" CHECK ((("storedAt")::text = ANY (ARRAY[('db'::character varying)::text, ('fs'::character varying)::text, ('s3'::character varying)::text, ('az'::character varying)::text])))
);


ALTER TABLE public.execution_entity OWNER TO n8n;

--
-- Name: execution_entity_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.execution_entity_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.execution_entity_id_seq OWNER TO n8n;

--
-- Name: execution_entity_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.execution_entity_id_seq OWNED BY public.execution_entity.id;


--
-- Name: execution_metadata; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.execution_metadata (
    id integer NOT NULL,
    "executionId" integer NOT NULL,
    key character varying(255) NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.execution_metadata OWNER TO n8n;

--
-- Name: execution_metadata_temp_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.execution_metadata_temp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.execution_metadata_temp_id_seq OWNER TO n8n;

--
-- Name: execution_metadata_temp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.execution_metadata_temp_id_seq OWNED BY public.execution_metadata.id;


--
-- Name: folder; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.folder (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    "parentFolderId" character varying(36),
    "projectId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.folder OWNER TO n8n;

--
-- Name: folder_tag; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.folder_tag (
    "folderId" character varying(36) NOT NULL,
    "tagId" character varying(36) NOT NULL
);


ALTER TABLE public.folder_tag OWNER TO n8n;

--
-- Name: insights_by_period; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.insights_by_period (
    id integer NOT NULL,
    "metaId" integer NOT NULL,
    type integer NOT NULL,
    value bigint NOT NULL,
    "periodUnit" integer NOT NULL,
    "periodStart" timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.insights_by_period OWNER TO n8n;

--
-- Name: insights_by_period_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.insights_by_period ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.insights_by_period_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: insights_metadata; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.insights_metadata (
    "metaId" integer NOT NULL,
    "workflowId" character varying(36),
    "projectId" character varying(36),
    "workflowName" character varying(128) NOT NULL,
    "projectName" character varying(255) NOT NULL
);


ALTER TABLE public.insights_metadata OWNER TO n8n;

--
-- Name: insights_metadata_metaId_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.insights_metadata ALTER COLUMN "metaId" ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public."insights_metadata_metaId_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: insights_raw; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.insights_raw (
    id integer NOT NULL,
    "metaId" integer NOT NULL,
    type integer NOT NULL,
    value bigint NOT NULL,
    "timestamp" timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.insights_raw OWNER TO n8n;

--
-- Name: insights_raw_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.insights_raw ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.insights_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: installed_nodes; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.installed_nodes (
    name character varying(200) NOT NULL,
    type character varying(200) NOT NULL,
    "latestVersion" double precision DEFAULT 1 NOT NULL,
    package character varying(241) NOT NULL
);


ALTER TABLE public.installed_nodes OWNER TO n8n;

--
-- Name: installed_packages; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.installed_packages (
    "packageName" character varying(214) NOT NULL,
    "installedVersion" character varying(50) NOT NULL,
    "authorName" character varying(70),
    "authorEmail" character varying(70),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.installed_packages OWNER TO n8n;

--
-- Name: instance_ai_checkpoints; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_checkpoints (
    key character varying(255) NOT NULL,
    "runId" character varying(255),
    "threadId" uuid NOT NULL,
    "resourceId" character varying(255),
    state json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "expiredAt" timestamp(3) with time zone,
    "hostRunId" character varying(64),
    CONSTRAINT instance_ai_checkpoints_state_tombstone_check CHECK (((("expiredAt" IS NOT NULL) AND (state IS NULL)) OR ("expiredAt" IS NULL)))
);


ALTER TABLE public.instance_ai_checkpoints OWNER TO n8n;

--
-- Name: instance_ai_events; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_events (
    "threadId" uuid NOT NULL,
    seq integer NOT NULL,
    "runId" character varying(64) NOT NULL,
    type character varying(64) NOT NULL,
    payload text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_events OWNER TO n8n;

--
-- Name: instance_ai_iteration_logs; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_iteration_logs (
    id character varying(36) NOT NULL,
    "threadId" uuid NOT NULL,
    "taskKey" character varying NOT NULL,
    entry text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_iteration_logs OWNER TO n8n;

--
-- Name: instance_ai_mcp_registry_connections; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_mcp_registry_connections (
    id uuid NOT NULL,
    "credentialId" character varying(36) NOT NULL,
    "serverSlug" character varying(255) NOT NULL,
    "toolFilter" json,
    "userId" uuid NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_mcp_registry_connections OWNER TO n8n;

--
-- Name: instance_ai_messages; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_messages (
    id character varying(36) NOT NULL,
    "threadId" uuid NOT NULL,
    content text NOT NULL,
    role character varying(16) NOT NULL,
    type character varying(32),
    "resourceId" character varying(255),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_messages OWNER TO n8n;

--
-- Name: instance_ai_observation_cursors; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_observation_cursors (
    "observationScopeId" uuid NOT NULL,
    "lastObservedMessageId" character varying(36) NOT NULL,
    "lastObservedAt" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_observation_cursors OWNER TO n8n;

--
-- Name: instance_ai_observation_locks; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_observation_locks (
    "observationScopeId" uuid NOT NULL,
    "taskKind" character varying(20) NOT NULL,
    "holderId" character varying(64) NOT NULL,
    "heldUntil" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_instance_ai_observation_locks_taskKind" CHECK ((("taskKind")::text = ANY (ARRAY[('observer'::character varying)::text, ('reflector'::character varying)::text])))
);


ALTER TABLE public.instance_ai_observation_locks OWNER TO n8n;

--
-- Name: instance_ai_observational_memory; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_observational_memory (
    id character varying(36) NOT NULL,
    "lookupKey" character varying(255) NOT NULL,
    scope character varying(16) NOT NULL,
    "threadId" uuid,
    "resourceId" character varying(255) NOT NULL,
    "activeObservations" text DEFAULT ''::text NOT NULL,
    "originType" character varying(32) NOT NULL,
    config text NOT NULL,
    "generationCount" integer DEFAULT 0 NOT NULL,
    "lastObservedAt" timestamp(3) with time zone,
    "pendingMessageTokens" integer DEFAULT 0 NOT NULL,
    "totalTokensObserved" integer DEFAULT 0 NOT NULL,
    "observationTokenCount" integer DEFAULT 0 NOT NULL,
    "isObserving" boolean DEFAULT false NOT NULL,
    "isReflecting" boolean DEFAULT false NOT NULL,
    "observedMessageIds" json,
    "observedTimezone" character varying,
    "bufferedObservations" text,
    "bufferedObservationTokens" integer,
    "bufferedMessageIds" json,
    "bufferedReflection" text,
    "bufferedReflectionTokens" integer,
    "bufferedReflectionInputTokens" integer,
    "reflectedObservationLineCount" integer,
    "bufferedObservationChunks" json,
    "isBufferingObservation" boolean DEFAULT false NOT NULL,
    "isBufferingReflection" boolean DEFAULT false NOT NULL,
    "lastBufferedAtTokens" integer DEFAULT 0 NOT NULL,
    "lastBufferedAtTime" timestamp(3) with time zone,
    metadata json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_observational_memory OWNER TO n8n;

--
-- Name: instance_ai_observations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_observations (
    id character varying(36) NOT NULL,
    "observationScopeId" uuid NOT NULL,
    marker character varying(16) NOT NULL,
    text text NOT NULL,
    "parentId" character varying(36),
    "tokenCount" integer DEFAULT 0 NOT NULL,
    status character varying(16) NOT NULL,
    "supersededBy" character varying(36),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_instance_ai_observations_marker" CHECK (((marker)::text = ANY (ARRAY[('critical'::character varying)::text, ('important'::character varying)::text, ('info'::character varying)::text, ('completion'::character varying)::text]))),
    CONSTRAINT "CHK_instance_ai_observations_status" CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('superseded'::character varying)::text, ('dropped'::character varying)::text])))
);


ALTER TABLE public.instance_ai_observations OWNER TO n8n;

--
-- Name: instance_ai_pending_confirmations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_pending_confirmations (
    "requestId" character varying(36) NOT NULL,
    "threadId" uuid NOT NULL,
    "userId" uuid NOT NULL,
    kind character varying(16) NOT NULL,
    "runId" character varying(36) NOT NULL,
    "toolCallId" character varying(64),
    "messageGroupId" character varying(36),
    "checkpointKey" character varying(255),
    "checkpointTaskId" character varying(36),
    "expiresAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_instance_ai_pending_confirmations_kind" CHECK (((kind)::text = ANY (ARRAY[('suspended'::character varying)::text, ('inline'::character varying)::text])))
);


ALTER TABLE public.instance_ai_pending_confirmations OWNER TO n8n;

--
-- Name: instance_ai_resources; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_resources (
    id character varying(255) NOT NULL,
    "workingMemory" text,
    metadata json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_resources OWNER TO n8n;

--
-- Name: instance_ai_thread_grants; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_thread_grants (
    "threadId" uuid NOT NULL,
    "userId" uuid NOT NULL,
    "grantKey" character varying(512) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_thread_grants OWNER TO n8n;

--
-- Name: instance_ai_threads; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_threads (
    id uuid NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    metadata json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "projectId" character varying(36) NOT NULL
);


ALTER TABLE public.instance_ai_threads OWNER TO n8n;

--
-- Name: instance_ai_workflow_snapshots; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_ai_workflow_snapshots (
    "runId" character varying(36) NOT NULL,
    "workflowName" character varying(255) NOT NULL,
    "resourceId" character varying(255),
    status character varying,
    snapshot text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_ai_workflow_snapshots OWNER TO n8n;

--
-- Name: instance_credential_assignment; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_credential_assignment (
    "credentialUseId" character varying(128) NOT NULL,
    "credentialId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_credential_assignment OWNER TO n8n;

--
-- Name: instance_monitoring_report; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_monitoring_report (
    id uuid NOT NULL,
    "dataPoints" json NOT NULL,
    status character varying(64) DEFAULT 'pending'::character varying NOT NULL,
    "deliveredAt" timestamp(3) with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    "lastAttemptAt" timestamp(3) with time zone,
    "lastError" text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_instance_monitoring_report_status" CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('delivered'::character varying)::text, ('skipped_after_max_retries'::character varying)::text])))
);


ALTER TABLE public.instance_monitoring_report OWNER TO n8n;

--
-- Name: instance_version_history; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.instance_version_history (
    id integer NOT NULL,
    major integer NOT NULL,
    minor integer NOT NULL,
    patch integer NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.instance_version_history OWNER TO n8n;

--
-- Name: instance_version_history_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.instance_version_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.instance_version_history_id_seq OWNER TO n8n;

--
-- Name: instance_version_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.instance_version_history_id_seq OWNED BY public.instance_version_history.id;


--
-- Name: invalid_auth_token; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.invalid_auth_token (
    token character varying(512) NOT NULL,
    "expiresAt" timestamp(3) with time zone NOT NULL
);


ALTER TABLE public.invalid_auth_token OWNER TO n8n;

--
-- Name: mcp_registry_server; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.mcp_registry_server (
    slug character varying(255) NOT NULL,
    status character varying(50) NOT NULL,
    version character varying(50) NOT NULL,
    "registryUpdatedAt" timestamp(3) without time zone NOT NULL,
    data json DEFAULT '{}'::json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_tmp_mcp_registry_server_status" CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('deprecated'::character varying)::text])))
);


ALTER TABLE public.mcp_registry_server OWNER TO n8n;

--
-- Name: migrations; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.migrations (
    id integer NOT NULL,
    "timestamp" bigint NOT NULL,
    name character varying NOT NULL
);


ALTER TABLE public.migrations OWNER TO n8n;

--
-- Name: migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.migrations_id_seq OWNER TO n8n;

--
-- Name: migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.migrations_id_seq OWNED BY public.migrations.id;


--
-- Name: oauth_access_tokens; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.oauth_access_tokens (
    token character varying NOT NULL,
    "clientId" character varying NOT NULL,
    "userId" uuid NOT NULL
);


ALTER TABLE public.oauth_access_tokens OWNER TO n8n;

--
-- Name: oauth_authorization_codes; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.oauth_authorization_codes (
    code character varying(255) NOT NULL,
    "clientId" character varying NOT NULL,
    "userId" uuid NOT NULL,
    "redirectUri" character varying NOT NULL,
    "codeChallenge" character varying NOT NULL,
    "codeChallengeMethod" character varying(255) NOT NULL,
    "expiresAt" bigint NOT NULL,
    state character varying,
    used boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    resource character varying,
    scope json DEFAULT '["tool:listWorkflows","tool:getWorkflowDetails"]'::json NOT NULL
);


ALTER TABLE public.oauth_authorization_codes OWNER TO n8n;

--
-- Name: oauth_clients; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.oauth_clients (
    id character varying NOT NULL,
    name character varying(255) NOT NULL,
    "redirectUris" json NOT NULL,
    "grantTypes" json NOT NULL,
    "clientSecret" character varying(255),
    "clientSecretExpiresAt" bigint,
    "tokenEndpointAuthMethod" character varying(255) DEFAULT 'none'::character varying NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "isFirstParty" boolean DEFAULT false NOT NULL
);


ALTER TABLE public.oauth_clients OWNER TO n8n;

--
-- Name: oauth_refresh_tokens; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.oauth_refresh_tokens (
    token character varying(255) NOT NULL,
    "clientId" character varying NOT NULL,
    "userId" uuid NOT NULL,
    "expiresAt" bigint NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    scope json DEFAULT '["tool:listWorkflows","tool:getWorkflowDetails"]'::json NOT NULL,
    resource character varying NOT NULL
);


ALTER TABLE public.oauth_refresh_tokens OWNER TO n8n;

--
-- Name: oauth_user_consents; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.oauth_user_consents (
    id integer NOT NULL,
    "userId" uuid NOT NULL,
    "clientId" character varying NOT NULL,
    "grantedAt" bigint NOT NULL,
    scope json NOT NULL
);


ALTER TABLE public.oauth_user_consents OWNER TO n8n;

--
-- Name: oauth_user_consents_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.oauth_user_consents ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.oauth_user_consents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: poller_state; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.poller_state (
    "workflowId" character varying(36) NOT NULL,
    "nodeId" character varying(36) NOT NULL,
    cursor json DEFAULT '{}'::json NOT NULL,
    "consecutiveErrors" integer DEFAULT 0 NOT NULL,
    "backoffUntil" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.poller_state OWNER TO n8n;

--
-- Name: processed_data; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.processed_data (
    "workflowId" character varying(36) NOT NULL,
    context character varying(255) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    value text NOT NULL
);


ALTER TABLE public.processed_data OWNER TO n8n;

--
-- Name: project; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.project (
    id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    type character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    icon json,
    description character varying(512),
    "creatorId" uuid,
    "customTelemetryTags" json DEFAULT '[]'::json NOT NULL
);


ALTER TABLE public.project OWNER TO n8n;

--
-- Name: project_pool_settings; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.project_pool_settings (
    "projectId" character varying(36) NOT NULL,
    "defaultPool" character varying(63),
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.project_pool_settings OWNER TO n8n;

--
-- Name: project_relation; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.project_relation (
    "projectId" character varying(36) NOT NULL,
    "userId" uuid NOT NULL,
    role character varying NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.project_relation OWNER TO n8n;

--
-- Name: project_secrets_provider_access; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.project_secrets_provider_access (
    "secretsProviderConnectionId" integer NOT NULL,
    "projectId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    role character varying(128) DEFAULT 'secretsProviderConnection:user'::character varying NOT NULL,
    CONSTRAINT "CHK_project_secrets_provider_access_role" CHECK (((role)::text = ANY (ARRAY[('secretsProviderConnection:owner'::character varying)::text, ('secretsProviderConnection:user'::character varying)::text])))
);


ALTER TABLE public.project_secrets_provider_access OWNER TO n8n;

--
-- Name: promotion_config; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.promotion_config (
    id character varying(36) NOT NULL,
    "connectionId" character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    direction character varying(16) NOT NULL,
    settings json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_promotion_config_direction" CHECK (((direction)::text = ANY (ARRAY[('apply'::character varying)::text, ('promote'::character varying)::text])))
);


ALTER TABLE public.promotion_config OWNER TO n8n;

--
-- Name: promotion_connection; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.promotion_connection (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    "providerId" character varying(36) NOT NULL,
    scope character varying(16) NOT NULL,
    target json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_promotion_connection_scope" CHECK (((scope)::text = ANY (ARRAY[('instance'::character varying)::text, ('projects'::character varying)::text])))
);


ALTER TABLE public.promotion_connection OWNER TO n8n;

--
-- Name: promotion_connection_project; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.promotion_connection_project (
    "projectId" character varying(36) NOT NULL,
    "connectionId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.promotion_connection_project OWNER TO n8n;

--
-- Name: promotion_provider; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.promotion_provider (
    id character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    type character varying(32) NOT NULL,
    "authType" character varying(32) NOT NULL,
    config json NOT NULL,
    auth text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_promotion_provider_authType" CHECK ((("authType")::text = ANY (ARRAY[('ssh-key'::character varying)::text, ('token'::character varying)::text]))),
    CONSTRAINT "CHK_promotion_provider_type" CHECK (((type)::text = 'git'::text))
);


ALTER TABLE public.promotion_provider OWNER TO n8n;

--
-- Name: role; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.role (
    slug character varying(128) NOT NULL,
    "displayName" text,
    description text,
    "roleType" text,
    "systemRole" boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.role OWNER TO n8n;

--
-- Name: role_mapping_rule; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.role_mapping_rule (
    id character varying(16) NOT NULL,
    expression text NOT NULL,
    role character varying(128) NOT NULL,
    type character varying(64) NOT NULL,
    "order" integer NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.role_mapping_rule OWNER TO n8n;

--
-- Name: role_mapping_rule_project; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.role_mapping_rule_project (
    "roleMappingRuleId" character varying(16) NOT NULL,
    "projectId" character varying(36) NOT NULL
);


ALTER TABLE public.role_mapping_rule_project OWNER TO n8n;

--
-- Name: role_scope; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.role_scope (
    "roleSlug" character varying(128) NOT NULL,
    "scopeSlug" character varying(128) NOT NULL
);


ALTER TABLE public.role_scope OWNER TO n8n;

--
-- Name: scheduled_job; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.scheduled_job (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    "taskType" character varying(128) NOT NULL,
    payload json DEFAULT '{}'::json NOT NULL,
    kind character varying(16) NOT NULL,
    "cronExpression" character varying(255),
    timezone character varying(64),
    "intervalSeconds" integer,
    "fireAt" timestamp(3) with time zone,
    enabled boolean DEFAULT true NOT NULL,
    "nextRunAt" timestamp(3) with time zone,
    "lastFiredAt" timestamp(3) with time zone,
    "maxAttempts" integer DEFAULT 1 NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "recurrenceUnit" character varying(16),
    "recurrenceSize" integer,
    "misfirePolicy" character varying(16) DEFAULT 'coalesce'::character varying NOT NULL,
    "misfireGraceSeconds" integer DEFAULT 60 NOT NULL,
    "ownerType" character varying(32) NOT NULL,
    "ownerId" character varying(255) NOT NULL,
    "ownerMemberId" character varying(36),
    "orphanedAt" timestamp(3) with time zone,
    CONSTRAINT "CHK_scheduled_job_cron_expression" CHECK ((((kind)::text <> 'cron'::text) OR ("cronExpression" IS NOT NULL))),
    CONSTRAINT "CHK_scheduled_job_fire_at" CHECK ((((kind)::text <> 'one_off'::text) OR ("fireAt" IS NOT NULL))),
    CONSTRAINT "CHK_scheduled_job_interval_seconds" CHECK ((((kind)::text <> 'interval'::text) OR ("intervalSeconds" IS NOT NULL))),
    CONSTRAINT "CHK_scheduled_job_kind" CHECK (((kind)::text = ANY (ARRAY[('cron'::character varying)::text, ('interval'::character varying)::text, ('one_off'::character varying)::text, ('recurring_cron'::character varying)::text]))),
    CONSTRAINT "CHK_scheduled_job_misfireGraceSeconds" CHECK (("misfireGraceSeconds" > 0)),
    CONSTRAINT "CHK_scheduled_job_misfirePolicy" CHECK ((("misfirePolicy")::text = ANY (ARRAY[('coalesce'::character varying)::text, ('skip'::character varying)::text, ('coalesce_owner'::character varying)::text]))),
    CONSTRAINT "CHK_scheduled_job_recurrence_size" CHECK (("recurrenceSize" >= 2)),
    CONSTRAINT "CHK_scheduled_job_recurrence_unit" CHECK ((("recurrenceUnit")::text = ANY (ARRAY[('hours'::character varying)::text, ('days'::character varying)::text, ('weeks'::character varying)::text, ('months'::character varying)::text]))),
    CONSTRAINT "CHK_scheduled_job_recurring_cron" CHECK ((((kind)::text <> 'recurring_cron'::text) OR (("cronExpression" IS NOT NULL) AND ("recurrenceUnit" IS NOT NULL) AND ("recurrenceSize" IS NOT NULL))))
);


ALTER TABLE public.scheduled_job OWNER TO n8n;

--
-- Name: scheduled_job_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.scheduled_job ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.scheduled_job_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scheduled_task; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.scheduled_task (
    id bigint NOT NULL,
    "jobId" integer NOT NULL,
    "taskType" character varying(128) NOT NULL,
    payload json DEFAULT '{}'::json NOT NULL,
    "scheduledFor" timestamp(3) with time zone NOT NULL,
    "runAt" timestamp(3) with time zone NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    "maxAttempts" integer DEFAULT 1 NOT NULL,
    "claimedBy" character varying(255),
    "leaseExpiresAt" timestamp(3) with time zone,
    "leaseEpoch" integer DEFAULT 0 NOT NULL,
    "startedAt" timestamp(3) with time zone,
    "finishedAt" timestamp(3) with time zone,
    "errorMessage" text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "dispatchedAt" timestamp(3) with time zone,
    "missedAfter" timestamp(3) with time zone,
    CONSTRAINT "CHK_scheduled_task_running_lease" CHECK ((((status)::text <> 'running'::text) OR ("leaseExpiresAt" IS NOT NULL))),
    CONSTRAINT "CHK_scheduled_task_status" CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('running'::character varying)::text, ('succeeded'::character varying)::text, ('failed'::character varying)::text, ('missed'::character varying)::text, ('cancelled'::character varying)::text])))
);


ALTER TABLE public.scheduled_task OWNER TO n8n;

--
-- Name: scheduled_task_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.scheduled_task ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.scheduled_task_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: scope; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.scope (
    slug character varying(128) NOT NULL,
    "displayName" text,
    description text
);


ALTER TABLE public.scope OWNER TO n8n;

--
-- Name: secrets_provider_connection; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.secrets_provider_connection (
    id integer NOT NULL,
    "providerKey" character varying(128) NOT NULL,
    type character varying(36) NOT NULL,
    "encryptedSettings" text NOT NULL,
    "isEnabled" boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.secrets_provider_connection OWNER TO n8n;

--
-- Name: secrets_provider_connection_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.secrets_provider_connection ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.secrets_provider_connection_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: settings; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.settings (
    key character varying(255) NOT NULL,
    value text NOT NULL,
    "loadOnStartup" boolean DEFAULT false NOT NULL
);


ALTER TABLE public.settings OWNER TO n8n;

--
-- Name: shared_credentials; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.shared_credentials (
    "credentialsId" character varying(36) NOT NULL,
    "projectId" character varying(36) NOT NULL,
    role text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.shared_credentials OWNER TO n8n;

--
-- Name: shared_workflow; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.shared_workflow (
    "workflowId" character varying(36) NOT NULL,
    "projectId" character varying(36) NOT NULL,
    role text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.shared_workflow OWNER TO n8n;

--
-- Name: tag_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.tag_entity (
    name character varying(24) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    id character varying(36) NOT NULL
);


ALTER TABLE public.tag_entity OWNER TO n8n;

--
-- Name: test_case_execution; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.test_case_execution (
    id character varying(36) NOT NULL,
    "testRunId" character varying(36) NOT NULL,
    "executionId" integer,
    status character varying NOT NULL,
    "runAt" timestamp(3) with time zone,
    "completedAt" timestamp(3) with time zone,
    "errorCode" character varying,
    "errorDetails" json,
    metrics json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    inputs json,
    outputs json,
    "runIndex" integer
);


ALTER TABLE public.test_case_execution OWNER TO n8n;

--
-- Name: test_run; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.test_run (
    id character varying(36) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    status character varying NOT NULL,
    "errorCode" character varying,
    "errorDetails" json,
    "runAt" timestamp(3) with time zone,
    "completedAt" timestamp(3) with time zone,
    metrics json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "runningInstanceId" character varying(255),
    "cancelRequested" boolean DEFAULT false NOT NULL,
    "workflowVersionId" character varying(36),
    "evaluationConfigId" character varying(36),
    "evaluationConfigSnapshot" jsonb,
    "collectionId" character varying(36)
);


ALTER TABLE public.test_run OWNER TO n8n;

--
-- Name: token_exchange_jti; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.token_exchange_jti (
    jti character varying(255) NOT NULL,
    "expiresAt" timestamp(3) with time zone NOT NULL,
    "createdAt" timestamp(3) with time zone NOT NULL
);


ALTER TABLE public.token_exchange_jti OWNER TO n8n;

--
-- Name: trusted_key; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.trusted_key (
    "sourceId" character varying(36) NOT NULL,
    kid character varying(255) NOT NULL,
    data text NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.trusted_key OWNER TO n8n;

--
-- Name: trusted_key_source; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.trusted_key_source (
    id character varying(36) NOT NULL,
    type character varying(32) NOT NULL,
    config text NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    "lastError" text,
    "lastRefreshedAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.trusted_key_source OWNER TO n8n;

--
-- Name: type_availability_policy; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.type_availability_policy (
    id character varying(36) NOT NULL,
    kind character varying(64) NOT NULL,
    rules json NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    "updatedBy" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.type_availability_policy OWNER TO n8n;

--
-- Name: type_availability_policy_attachment; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.type_availability_policy_attachment (
    "scopeId" character varying(36) NOT NULL,
    "policyId" character varying(36) NOT NULL,
    priority integer NOT NULL,
    "isFloor" boolean DEFAULT false NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.type_availability_policy_attachment OWNER TO n8n;

--
-- Name: type_availability_policy_scope; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.type_availability_policy_scope (
    id character varying(36) NOT NULL,
    kind character varying(64) NOT NULL,
    "projectId" character varying(36),
    "defaultAction" character varying(16) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    "updatedBy" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_type_availability_policy_scope_defaultAction" CHECK ((("defaultAction")::text = ANY (ARRAY[('allow'::character varying)::text, ('deny'::character varying)::text, ('delegate'::character varying)::text])))
);


ALTER TABLE public.type_availability_policy_scope OWNER TO n8n;

--
-- Name: user; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public."user" (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255),
    "firstName" character varying(32),
    "lastName" character varying(32),
    password character varying(255),
    "personalizationAnswers" json,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    settings json,
    disabled boolean DEFAULT false NOT NULL,
    "mfaEnabled" boolean DEFAULT false NOT NULL,
    "mfaSecret" text,
    "mfaRecoveryCodes" text,
    "lastActiveAt" date,
    "roleSlug" character varying(128) DEFAULT 'global:member'::character varying NOT NULL
);


ALTER TABLE public."user" OWNER TO n8n;

--
-- Name: user_api_keys; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.user_api_keys (
    id character varying(36) NOT NULL,
    "userId" uuid NOT NULL,
    label character varying(100) NOT NULL,
    "apiKey" character varying NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    scopes json,
    audience character varying DEFAULT 'public-api'::character varying NOT NULL,
    "lastUsedAt" timestamp(3) with time zone
);


ALTER TABLE public.user_api_keys OWNER TO n8n;

--
-- Name: user_favorites; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.user_favorites (
    id integer NOT NULL,
    "userId" uuid NOT NULL,
    "resourceId" character varying(255) NOT NULL,
    "resourceType" character varying(64) NOT NULL
);


ALTER TABLE public.user_favorites OWNER TO n8n;

--
-- Name: user_favorites_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.user_favorites ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.user_favorites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: variables; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.variables (
    key character varying(50) NOT NULL,
    type character varying(50) DEFAULT 'string'::character varying NOT NULL,
    value text,
    id character varying(36) NOT NULL,
    "projectId" character varying(36),
    CONSTRAINT variables_value_max_len CHECK (((value IS NULL) OR (char_length(value) <= 1000)))
);


ALTER TABLE public.variables OWNER TO n8n;

--
-- Name: webhook_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.webhook_entity (
    "webhookPath" character varying NOT NULL,
    method character varying NOT NULL,
    node character varying NOT NULL,
    "webhookId" character varying,
    "pathLength" integer,
    "workflowId" character varying(36) NOT NULL
);


ALTER TABLE public.webhook_entity OWNER TO n8n;

--
-- Name: workflow_builder_session; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_builder_session (
    id uuid NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "userId" uuid NOT NULL,
    messages json DEFAULT '[]'::json NOT NULL,
    "previousSummary" text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "activeVersionCardId" character varying(255),
    "resumeAfterRestoreMessageId" character varying(255)
);


ALTER TABLE public.workflow_builder_session OWNER TO n8n;

--
-- Name: workflow_dependency; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_dependency (
    id integer NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "workflowVersionId" integer NOT NULL,
    "dependencyType" character varying(32) NOT NULL,
    "dependencyKey" character varying(255) NOT NULL,
    "dependencyInfo" json,
    "indexVersionId" smallint DEFAULT 1 NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "publishedVersionId" character varying(36)
);


ALTER TABLE public.workflow_dependency OWNER TO n8n;

--
-- Name: workflow_dependency_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_dependency ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.workflow_dependency_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_entity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_entity (
    name character varying(128) NOT NULL,
    active boolean NOT NULL,
    nodes json NOT NULL,
    connections json NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    settings json,
    "staticData" json,
    "pinData" json,
    "versionId" character(36) NOT NULL,
    "triggerCount" integer DEFAULT 0 NOT NULL,
    id character varying(36) NOT NULL,
    meta json,
    "parentFolderId" character varying(36) DEFAULT NULL::character varying,
    "isArchived" boolean DEFAULT false NOT NULL,
    "versionCounter" integer DEFAULT 1 NOT NULL,
    description text,
    "activeVersionId" character varying(36),
    "nodeGroups" json DEFAULT '[]'::json NOT NULL,
    "sourceWorkflowId" character varying
);


ALTER TABLE public.workflow_entity OWNER TO n8n;

--
-- Name: workflow_history; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_history (
    "versionId" character varying(36) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    authors character varying(255) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    nodes json NOT NULL,
    connections json NOT NULL,
    name character varying(128),
    autosaved boolean DEFAULT false NOT NULL,
    description text,
    "nodeGroups" json DEFAULT '[]'::json NOT NULL
);


ALTER TABLE public.workflow_history OWNER TO n8n;

--
-- Name: workflow_publication_outbox; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_publication_outbox (
    id integer NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "publishedVersionId" character varying(36) NOT NULL,
    status character varying(20) NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    reason character varying(20) DEFAULT 'publish'::character varying NOT NULL,
    CONSTRAINT "CHK_workflow_publication_outbox_reason" CHECK (((reason)::text = ANY (ARRAY[('publish'::character varying)::text, ('startup'::character varying)::text, ('leadership-takeover'::character varying)::text, ('reconcile'::character varying)::text]))),
    CONSTRAINT "CHK_workflow_publication_outbox_status" CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('in_progress'::character varying)::text, ('completed'::character varying)::text, ('partial_success'::character varying)::text, ('failed'::character varying)::text])))
);


ALTER TABLE public.workflow_publication_outbox OWNER TO n8n;

--
-- Name: workflow_publication_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_publication_outbox ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.workflow_publication_outbox_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_publication_trigger_status; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_publication_trigger_status (
    "workflowId" character varying(36) NOT NULL,
    "nodeId" character varying(36) NOT NULL,
    "versionId" character varying(36) NOT NULL,
    status character varying(20) NOT NULL,
    "errorMessage" text,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "triggerKind" character varying(20) NOT NULL,
    CONSTRAINT "CHK_workflow_publication_trigger_status_status" CHECK (((status)::text = ANY (ARRAY[('activated'::character varying)::text, ('failed'::character varying)::text]))),
    CONSTRAINT "CHK_workflow_publication_trigger_status_triggerKind" CHECK ((("triggerKind")::text = ANY (ARRAY[('in-memory'::character varying)::text, ('persisted'::character varying)::text])))
);


ALTER TABLE public.workflow_publication_trigger_status OWNER TO n8n;

--
-- Name: workflow_publish_history; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_publish_history (
    id integer NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "versionId" character varying(36),
    event character varying(36) NOT NULL,
    "userId" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_workflow_publish_history_event" CHECK (((event)::text = ANY (ARRAY[('activated'::character varying)::text, ('deactivated'::character varying)::text])))
);


ALTER TABLE public.workflow_publish_history OWNER TO n8n;

--
-- Name: workflow_publish_history_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_publish_history ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.workflow_publish_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_published_version; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_published_version (
    "workflowId" character varying(36) NOT NULL,
    "publishedVersionId" character varying(36) NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.workflow_published_version OWNER TO n8n;

--
-- Name: workflow_review_activity; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_activity (
    id integer NOT NULL,
    "workflowReviewRequestId" character varying(36) NOT NULL,
    type character varying(64) NOT NULL,
    "typeVersion" integer DEFAULT 1 NOT NULL,
    data json,
    "createdById" uuid,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.workflow_review_activity OWNER TO n8n;

--
-- Name: workflow_review_activity_comment; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_activity_comment (
    id integer NOT NULL,
    "activityId" integer NOT NULL,
    "createdById" uuid,
    body text,
    history json,
    "updatedAt" timestamp(3) with time zone,
    "deletedAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL
);


ALTER TABLE public.workflow_review_activity_comment OWNER TO n8n;

--
-- Name: workflow_review_activity_comment_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_review_activity_comment ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.workflow_review_activity_comment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_review_activity_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_review_activity ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.workflow_review_activity_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_review_request; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_request (
    id character varying(36) NOT NULL,
    "projectId" character varying(36) NOT NULL,
    state character varying(16) DEFAULT 'open'::character varying NOT NULL,
    decision character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    "createdById" uuid,
    "updatedById" uuid,
    "closedById" uuid,
    "approvedAt" timestamp(3) with time zone,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    "updatedAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP(3) NOT NULL,
    CONSTRAINT "CHK_workflow_review_request_decision" CHECK (((decision)::text = ANY (ARRAY[('pending'::character varying)::text, ('changes_requested'::character varying)::text, ('approved'::character varying)::text]))),
    CONSTRAINT "CHK_workflow_review_request_state" CHECK (((state)::text = ANY (ARRAY[('open'::character varying)::text, ('closed'::character varying)::text])))
);


ALTER TABLE public.workflow_review_request OWNER TO n8n;

--
-- Name: workflow_review_request_authors; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_request_authors (
    "workflowReviewRequestId" character varying(36) NOT NULL,
    "userId" uuid NOT NULL
);


ALTER TABLE public.workflow_review_request_authors OWNER TO n8n;

--
-- Name: workflow_review_request_reviewers; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_request_reviewers (
    "workflowReviewRequestId" character varying(36) NOT NULL,
    "userId" uuid NOT NULL
);


ALTER TABLE public.workflow_review_request_reviewers OWNER TO n8n;

--
-- Name: workflow_review_request_workflow; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_review_request_workflow (
    id character varying(36) NOT NULL,
    "workflowReviewRequestId" character varying(36) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "workflowVersionId" character varying(36),
    "baselineVersionId" character varying(36)
);


ALTER TABLE public.workflow_review_request_workflow OWNER TO n8n;

--
-- Name: workflow_statistics; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_statistics (
    count bigint DEFAULT 0,
    "latestEvent" timestamp(3) with time zone,
    name character varying(128) NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    "rootCount" bigint DEFAULT 0,
    id integer NOT NULL,
    "workflowName" character varying(128)
);


ALTER TABLE public.workflow_statistics OWNER TO n8n;

--
-- Name: workflow_statistics_delta; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflow_statistics_delta (
    id bigint NOT NULL,
    "workflowId" character varying(36) NOT NULL,
    name character varying(128) NOT NULL,
    "rootCountDelta" smallint NOT NULL,
    "createdAt" timestamp(3) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "workflowName" character varying(128)
)
WITH (autovacuum_vacuum_scale_factor='0.0', autovacuum_vacuum_threshold='1000', autovacuum_vacuum_cost_delay='0');


ALTER TABLE public.workflow_statistics_delta OWNER TO n8n;

--
-- Name: workflow_statistics_delta_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

ALTER TABLE public.workflow_statistics_delta ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.workflow_statistics_delta_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: workflow_statistics_id_seq; Type: SEQUENCE; Schema: public; Owner: n8n
--

CREATE SEQUENCE public.workflow_statistics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.workflow_statistics_id_seq OWNER TO n8n;

--
-- Name: workflow_statistics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: n8n
--

ALTER SEQUENCE public.workflow_statistics_id_seq OWNED BY public.workflow_statistics.id;


--
-- Name: workflows_tags; Type: TABLE; Schema: public; Owner: n8n
--

CREATE TABLE public.workflows_tags (
    "workflowId" character varying(36) NOT NULL,
    "tagId" character varying(36) NOT NULL
);


ALTER TABLE public.workflows_tags OWNER TO n8n;

--
-- Name: ga4_event_ga4_event_id_seq; Type: SEQUENCE; Schema: raw; Owner: n8n
--

CREATE SEQUENCE raw.ga4_event_ga4_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE raw.ga4_event_ga4_event_id_seq OWNER TO n8n;

--
-- Name: ga4_event_ga4_event_id_seq; Type: SEQUENCE OWNED BY; Schema: raw; Owner: n8n
--

ALTER SEQUENCE raw.ga4_event_ga4_event_id_seq OWNED BY raw.ga4_event.ga4_event_id;


--
-- Name: geo_response; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.geo_response (
    ham_id bigint NOT NULL,
    saglayici text NOT NULL,
    yuzey text NOT NULL,
    sorgu_metni text NOT NULL,
    language text NOT NULL,
    country text NOT NULL,
    cevap_hash text NOT NULL,
    ham jsonb NOT NULL,
    cekim_at timestamp with time zone DEFAULT now() NOT NULL,
    is_id bigint,
    parser_surum text NOT NULL
);


ALTER TABLE raw.geo_response OWNER TO n8n;

--
-- Name: geo_response_ham_id_seq; Type: SEQUENCE; Schema: raw; Owner: n8n
--

CREATE SEQUENCE raw.geo_response_ham_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE raw.geo_response_ham_id_seq OWNER TO n8n;

--
-- Name: geo_response_ham_id_seq; Type: SEQUENCE OWNED BY; Schema: raw; Owner: n8n
--

ALTER SEQUENCE raw.geo_response_ham_id_seq OWNED BY raw.geo_response.ham_id;


--
-- Name: idefix_urun; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.idefix_urun (
    barkod text NOT NULL,
    stok_kodu text,
    referans bigint,
    ad text,
    durum text,
    ham jsonb NOT NULL,
    cekildi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.idefix_urun OWNER TO n8n;

--
-- Name: lead_osm; Type: TABLE; Schema: raw; Owner: n8n
--

CREATE TABLE raw.lead_osm (
    osm_tip text NOT NULL,
    osm_id bigint NOT NULL,
    segment text NOT NULL,
    il text NOT NULL,
    etiketler jsonb NOT NULL,
    enlem double precision,
    boylam double precision,
    cekildi timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE raw.lead_osm OWNER TO n8n;

--
-- Name: yukleme_log_id_seq; Type: SEQUENCE; Schema: raw; Owner: n8n
--

ALTER TABLE raw.yukleme_log ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME raw.yukleme_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: acik_soru soru_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.acik_soru ALTER COLUMN soru_id SET DEFAULT nextval('core.acik_soru_soru_id_seq'::regclass);


--
-- Name: ai_calisma_log calisma_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ai_calisma_log ALTER COLUMN calisma_id SET DEFAULT nextval('core.ai_calisma_log_calisma_id_seq'::regclass);


--
-- Name: ai_human_supersede_audit audit_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_supersede_audit ALTER COLUMN audit_id SET DEFAULT nextval('core.ai_human_supersede_audit_audit_id_seq'::regclass);


--
-- Name: ai_provider_attempt attempt_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_provider_attempt ALTER COLUMN attempt_id SET DEFAULT nextval('core.ai_provider_attempt_attempt_id_seq'::regclass);


--
-- Name: ai_red_team_attempt attempt_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_attempt ALTER COLUMN attempt_id SET DEFAULT nextval('core.ai_red_team_attempt_attempt_id_seq'::regclass);


--
-- Name: ai_red_team_job job_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_job ALTER COLUMN job_id SET DEFAULT nextval('core.ai_red_team_job_job_id_seq'::regclass);


--
-- Name: ai_task task_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_task ALTER COLUMN task_id SET DEFAULT nextval('core.ai_task_task_id_seq'::regclass);


--
-- Name: arac_envanteri arac_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arac_envanteri ALTER COLUMN arac_id SET DEFAULT nextval('core.arac_envanteri_arac_id_seq'::regclass);


--
-- Name: arastirma_plani plan_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arastirma_plani ALTER COLUMN plan_id SET DEFAULT nextval('core.arastirma_plani_plan_id_seq'::regclass);


--
-- Name: basin_bahsi bahis_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.basin_bahsi ALTER COLUMN bahis_id SET DEFAULT nextval('core.basin_bahsi_bahis_id_seq'::regclass);


--
-- Name: buyume_bulgu bulgu_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.buyume_bulgu ALTER COLUMN bulgu_id SET DEFAULT nextval('core.buyume_bulgu_bulgu_id_seq'::regclass);


--
-- Name: geo_alias alias_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_alias ALTER COLUMN alias_id SET DEFAULT nextval('core.geo_alias_alias_id_seq'::regclass);


--
-- Name: geo_brand brand_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_brand ALTER COLUMN brand_id SET DEFAULT nextval('core.geo_brand_brand_id_seq'::regclass);


--
-- Name: geo_citation citation_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation ALTER COLUMN citation_id SET DEFAULT nextval('core.geo_citation_citation_id_seq'::regclass);


--
-- Name: geo_entity_conflict conflict_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_entity_conflict ALTER COLUMN conflict_id SET DEFAULT nextval('core.geo_entity_conflict_conflict_id_seq'::regclass);


--
-- Name: geo_gap gap_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_gap ALTER COLUMN gap_id SET DEFAULT nextval('core.geo_gap_gap_id_seq'::regclass);


--
-- Name: geo_karar_kapsami kapsam_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_karar_kapsami ALTER COLUMN kapsam_id SET DEFAULT nextval('core.geo_karar_kapsami_kapsam_id_seq'::regclass);


--
-- Name: geo_mention mention_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_mention ALTER COLUMN mention_id SET DEFAULT nextval('core.geo_mention_mention_id_seq'::regclass);


--
-- Name: geo_observation observation_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_observation ALTER COLUMN observation_id SET DEFAULT nextval('core.geo_observation_observation_id_seq'::regclass);


--
-- Name: geo_query query_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_query ALTER COLUMN query_id SET DEFAULT nextval('core.geo_query_query_id_seq'::regclass);


--
-- Name: geo_source source_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_source ALTER COLUMN source_id SET DEFAULT nextval('core.geo_source_source_id_seq'::regclass);


--
-- Name: gonderi_notu not_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.gonderi_notu ALTER COLUMN not_id SET DEFAULT nextval('core.gonderi_notu_not_id_seq'::regclass);


--
-- Name: guncel_olay id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.guncel_olay ALTER COLUMN id SET DEFAULT nextval('core.guncel_olay_id_seq'::regclass);


--
-- Name: hatirlatici id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.hatirlatici ALTER COLUMN id SET DEFAULT nextval('core.hatirlatici_id_seq'::regclass);


--
-- Name: ic_mesaj mesaj_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj ALTER COLUMN mesaj_id SET DEFAULT nextval('core.ic_mesaj_mesaj_id_seq'::regclass);


--
-- Name: ig_gonderi_plani plan_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ig_gonderi_plani ALTER COLUMN plan_id SET DEFAULT nextval('core.ig_gonderi_plani_plan_id_seq'::regclass);


--
-- Name: inanc_catismasi catisma_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.inanc_catismasi ALTER COLUMN catisma_id SET DEFAULT nextval('core.inanc_catismasi_catisma_id_seq'::regclass);


--
-- Name: kademe_denemesi id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kademe_denemesi ALTER COLUMN id SET DEFAULT nextval('core.kademe_denemesi_id_seq'::regclass);


--
-- Name: kanit_anlik anlik_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kanit_anlik ALTER COLUMN anlik_id SET DEFAULT nextval('core.kanit_anlik_anlik_id_seq'::regclass);


--
-- Name: karar karar_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar ALTER COLUMN karar_id SET DEFAULT nextval('core.karar_karar_id_seq'::regclass);


--
-- Name: karar_aksiyon aksiyon_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_aksiyon ALTER COLUMN aksiyon_id SET DEFAULT nextval('core.karar_aksiyon_aksiyon_id_seq'::regclass);


--
-- Name: karar_red_team inceleme_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_red_team ALTER COLUMN inceleme_id SET DEFAULT nextval('core.karar_red_team_inceleme_id_seq'::regclass);


--
-- Name: kargo_karar karar_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kargo_karar ALTER COLUMN karar_id SET DEFAULT nextval('core.kargo_karar_karar_id_seq'::regclass);


--
-- Name: katalog_not not_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.katalog_not ALTER COLUMN not_id SET DEFAULT nextval('core.katalog_not_not_id_seq'::regclass);


--
-- Name: kreatif_itiraz itiraz_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kreatif_itiraz ALTER COLUMN itiraz_id SET DEFAULT nextval('core.kreatif_itiraz_itiraz_id_seq'::regclass);


--
-- Name: kreatif_konsept konsept_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kreatif_konsept ALTER COLUMN konsept_id SET DEFAULT nextval('core.kreatif_konsept_konsept_id_seq'::regclass);


--
-- Name: lead lead_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.lead ALTER COLUMN lead_id SET DEFAULT nextval('core.lead_lead_id_seq'::regclass);


--
-- Name: maliyet_bileseni bilesen_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.maliyet_bileseni ALTER COLUMN bilesen_id SET DEFAULT nextval('core.maliyet_bileseni_bilesen_id_seq'::regclass);


--
-- Name: medya_istegi istek_no; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.medya_istegi ALTER COLUMN istek_no SET DEFAULT nextval('core.medya_istegi_istek_no_seq'::regclass);


--
-- Name: mimari_ders ders_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.mimari_ders ALTER COLUMN ders_id SET DEFAULT nextval('core.mimari_ders_ders_id_seq'::regclass);


--
-- Name: pazaryeri_siparis id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.pazaryeri_siparis ALTER COLUMN id SET DEFAULT nextval('core.pazaryeri_siparis_id_seq'::regclass);


--
-- Name: rapor_anlik kayit_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.rapor_anlik ALTER COLUMN kayit_id SET DEFAULT nextval('core.rapor_anlik_kayit_id_seq'::regclass);


--
-- Name: saha_elle_nokta nokta_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_elle_nokta ALTER COLUMN nokta_id SET DEFAULT nextval('core.saha_elle_nokta_nokta_id_seq'::regclass);


--
-- Name: saha_konum konum_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_konum ALTER COLUMN konum_id SET DEFAULT nextval('core.saha_konum_konum_id_seq'::regclass);


--
-- Name: saha_rota rota_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_rota ALTER COLUMN rota_id SET DEFAULT nextval('core.saha_rota_rota_id_seq'::regclass);


--
-- Name: saha_ziyaret ziyaret_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ziyaret ALTER COLUMN ziyaret_id SET DEFAULT nextval('core.saha_ziyaret_ziyaret_id_seq'::regclass);


--
-- Name: saha_ziyaret_foto foto_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ziyaret_foto ALTER COLUMN foto_id SET DEFAULT nextval('core.saha_ziyaret_foto_foto_id_seq'::regclass);


--
-- Name: siparis_bildirim id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.siparis_bildirim ALTER COLUMN id SET DEFAULT nextval('core.siparis_bildirim_id_seq'::regclass);


--
-- Name: stok_sayim sayim_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.stok_sayim ALTER COLUMN sayim_id SET DEFAULT nextval('core.stok_sayim_sayim_id_seq'::regclass);


--
-- Name: tarayici_isi is_id; Type: DEFAULT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.tarayici_isi ALTER COLUMN is_id SET DEFAULT nextval('core.tarayici_isi_is_id_seq'::regclass);


--
-- Name: tasarim_isi is_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.tasarim_isi ALTER COLUMN is_id SET DEFAULT nextval('core.tasarim_isi_is_id_seq'::regclass);


--
-- Name: tasarim_sablon sablon_id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.tasarim_sablon ALTER COLUMN sablon_id SET DEFAULT nextval('core.tasarim_sablon_sablon_id_seq'::regclass);


--
-- Name: urun_platform_fiyat id; Type: DEFAULT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_platform_fiyat ALTER COLUMN id SET DEFAULT nextval('core.urun_platform_fiyat_id_seq'::regclass);


--
-- Name: kalip id; Type: DEFAULT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.kalip ALTER COLUMN id SET DEFAULT nextval('lcarlie.kalip_id_seq'::regclass);


--
-- Name: konusma id; Type: DEFAULT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.konusma ALTER COLUMN id SET DEFAULT nextval('lcarlie.konusma_id_seq'::regclass);


--
-- Name: mesaj id; Type: DEFAULT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.mesaj ALTER COLUMN id SET DEFAULT nextval('lcarlie.mesaj_id_seq'::regclass);


--
-- Name: satis_cevap id; Type: DEFAULT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_cevap ALTER COLUMN id SET DEFAULT nextval('lcarlie.satis_cevap_id_seq'::regclass);


--
-- Name: satis_yaklasim id; Type: DEFAULT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_yaklasim ALTER COLUMN id SET DEFAULT nextval('lcarlie.satis_yaklasim_id_seq'::regclass);


--
-- Name: auth_provider_sync_history id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.auth_provider_sync_history ALTER COLUMN id SET DEFAULT nextval('public.auth_provider_sync_history_id_seq'::regclass);


--
-- Name: execution_annotations id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotations ALTER COLUMN id SET DEFAULT nextval('public.execution_annotations_id_seq'::regclass);


--
-- Name: execution_entity id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_entity ALTER COLUMN id SET DEFAULT nextval('public.execution_entity_id_seq'::regclass);


--
-- Name: execution_metadata id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_metadata ALTER COLUMN id SET DEFAULT nextval('public.execution_metadata_temp_id_seq'::regclass);


--
-- Name: instance_version_history id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_version_history ALTER COLUMN id SET DEFAULT nextval('public.instance_version_history_id_seq'::regclass);


--
-- Name: migrations id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.migrations ALTER COLUMN id SET DEFAULT nextval('public.migrations_id_seq'::regclass);


--
-- Name: workflow_statistics id; Type: DEFAULT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_statistics ALTER COLUMN id SET DEFAULT nextval('public.workflow_statistics_id_seq'::regclass);


--
-- Name: ga4_event ga4_event_id; Type: DEFAULT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.ga4_event ALTER COLUMN ga4_event_id SET DEFAULT nextval('raw.ga4_event_ga4_event_id_seq'::regclass);


--
-- Name: geo_response ham_id; Type: DEFAULT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.geo_response ALTER COLUMN ham_id SET DEFAULT nextval('raw.geo_response_ham_id_seq'::regclass);


--
-- Name: memory_embedding memory_embedding_pkey; Type: CONSTRAINT; Schema: ai_semantic; Owner: n8n
--

ALTER TABLE ONLY ai_semantic.memory_embedding
    ADD CONSTRAINT memory_embedding_pkey PRIMARY KEY (embedding_id);


--
-- Name: memory_embedding memory_embedding_source_type_source_ref_content_hash_model__key; Type: CONSTRAINT; Schema: ai_semantic; Owner: n8n
--

ALTER TABLE ONLY ai_semantic.memory_embedding
    ADD CONSTRAINT memory_embedding_source_type_source_ref_content_hash_model__key UNIQUE (source_type, source_ref, content_hash, model_id, model_revision);


--
-- Name: acik_soru acik_soru_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.acik_soru
    ADD CONSTRAINT acik_soru_pkey PRIMARY KEY (soru_id);


--
-- Name: ai_action_approval ai_action_approval_action_id_approver_identity_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_approval
    ADD CONSTRAINT ai_action_approval_action_id_approver_identity_key UNIQUE (action_id, approver_identity);


--
-- Name: ai_action_approval ai_action_approval_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_approval
    ADD CONSTRAINT ai_action_approval_pkey PRIMARY KEY (approval_id);


--
-- Name: ai_action_execution ai_action_execution_action_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_execution
    ADD CONSTRAINT ai_action_execution_action_id_key UNIQUE (action_id);


--
-- Name: ai_action_execution ai_action_execution_execution_key_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_execution
    ADD CONSTRAINT ai_action_execution_execution_key_key UNIQUE (execution_key);


--
-- Name: ai_action_execution ai_action_execution_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_execution
    ADD CONSTRAINT ai_action_execution_pkey PRIMARY KEY (execution_id);


--
-- Name: ai_action_proposal ai_action_proposal_idempotency_key_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_proposal
    ADD CONSTRAINT ai_action_proposal_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: ai_action_proposal ai_action_proposal_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_proposal
    ADD CONSTRAINT ai_action_proposal_pkey PRIMARY KEY (action_id);


--
-- Name: ai_action_type ai_action_type_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_type
    ADD CONSTRAINT ai_action_type_pkey PRIMARY KEY (action_type);


--
-- Name: ai_calisma_log ai_calisma_log_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ai_calisma_log
    ADD CONSTRAINT ai_calisma_log_pkey PRIMARY KEY (calisma_id);


--
-- Name: ai_evidence_followup ai_evidence_followup_decision_id_question_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_evidence_followup
    ADD CONSTRAINT ai_evidence_followup_decision_id_question_id_key UNIQUE (decision_id, question_id);


--
-- Name: ai_evidence_followup ai_evidence_followup_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_evidence_followup
    ADD CONSTRAINT ai_evidence_followup_pkey PRIMARY KEY (followup_id);


--
-- Name: ai_executive_brief ai_executive_brief_message_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_executive_brief
    ADD CONSTRAINT ai_executive_brief_message_id_key UNIQUE (message_id);


--
-- Name: ai_executive_brief ai_executive_brief_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_executive_brief
    ADD CONSTRAINT ai_executive_brief_pkey PRIMARY KEY (brief_key);


--
-- Name: ai_generated_question ai_generated_question_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_generated_question
    ADD CONSTRAINT ai_generated_question_pkey PRIMARY KEY (question_key);


--
-- Name: ai_generated_question ai_generated_question_soru_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_generated_question
    ADD CONSTRAINT ai_generated_question_soru_id_key UNIQUE (soru_id);


--
-- Name: ai_human_data_attestation ai_human_data_attestation_attestation_type_scope_active_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_data_attestation
    ADD CONSTRAINT ai_human_data_attestation_attestation_type_scope_active_key UNIQUE (attestation_type, scope, active);


--
-- Name: ai_human_data_attestation ai_human_data_attestation_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_data_attestation
    ADD CONSTRAINT ai_human_data_attestation_pkey PRIMARY KEY (attestation_id);


--
-- Name: ai_human_supersede_audit ai_human_supersede_audit_old_karar_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_supersede_audit
    ADD CONSTRAINT ai_human_supersede_audit_old_karar_id_key UNIQUE (old_karar_id);


--
-- Name: ai_human_supersede_audit ai_human_supersede_audit_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_supersede_audit
    ADD CONSTRAINT ai_human_supersede_audit_pkey PRIMARY KEY (audit_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_data_message_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_data_message_id_key UNIQUE (data_message_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_experiment_message_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_experiment_message_id_key UNIQUE (experiment_message_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_pkey PRIMARY KEY (karar_id);


--
-- Name: ai_model_policy ai_model_policy_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_model_policy
    ADD CONSTRAINT ai_model_policy_pkey PRIMARY KEY (policy_name);


--
-- Name: ai_orchestrator_config ai_orchestrator_config_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_orchestrator_config
    ADD CONSTRAINT ai_orchestrator_config_pkey PRIMARY KEY (config_key);


--
-- Name: ai_provider_attempt ai_provider_attempt_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_provider_attempt
    ADD CONSTRAINT ai_provider_attempt_pkey PRIMARY KEY (attempt_id);


--
-- Name: ai_provider_budget ai_provider_budget_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_provider_budget
    ADD CONSTRAINT ai_provider_budget_pkey PRIMARY KEY (provider);


--
-- Name: ai_provider_price_config ai_provider_price_config_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_provider_price_config
    ADD CONSTRAINT ai_provider_price_config_pkey PRIMARY KEY (provider);


--
-- Name: ai_question_route ai_question_route_mesaj_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_question_route
    ADD CONSTRAINT ai_question_route_mesaj_id_key UNIQUE (mesaj_id);


--
-- Name: ai_question_route ai_question_route_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_question_route
    ADD CONSTRAINT ai_question_route_pkey PRIMARY KEY (soru_id, departman);


--
-- Name: ai_red_team_attempt ai_red_team_attempt_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_attempt
    ADD CONSTRAINT ai_red_team_attempt_pkey PRIMARY KEY (attempt_id);


--
-- Name: ai_red_team_job ai_red_team_job_karar_id_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_job
    ADD CONSTRAINT ai_red_team_job_karar_id_key UNIQUE (karar_id);


--
-- Name: ai_red_team_job ai_red_team_job_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_job
    ADD CONSTRAINT ai_red_team_job_pkey PRIMARY KEY (job_id);


--
-- Name: ai_task ai_task_idempotency_key_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_task
    ADD CONSTRAINT ai_task_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: ai_task ai_task_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_task
    ADD CONSTRAINT ai_task_pkey PRIMARY KEY (task_id);


--
-- Name: anayasa anayasa_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.anayasa
    ADD CONSTRAINT anayasa_pkey PRIMARY KEY (kural_kod);


--
-- Name: arac_envanteri arac_envanteri_ad_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arac_envanteri
    ADD CONSTRAINT arac_envanteri_ad_key UNIQUE (ad);


--
-- Name: arac_envanteri arac_envanteri_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arac_envanteri
    ADD CONSTRAINT arac_envanteri_pkey PRIMARY KEY (arac_id);


--
-- Name: arastirma_plani arastirma_plani_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arastirma_plani
    ADD CONSTRAINT arastirma_plani_pkey PRIMARY KEY (plan_id);


--
-- Name: arastirma_plani arastirma_plani_tekil; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.arastirma_plani
    ADD CONSTRAINT arastirma_plani_tekil UNIQUE (kapsam, hedef, konu);


--
-- Name: ayar ayar_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ayar
    ADD CONSTRAINT ayar_pkey PRIMARY KEY (anahtar);


--
-- Name: basin_bahsi basin_bahsi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.basin_bahsi
    ADD CONSTRAINT basin_bahsi_pkey PRIMARY KEY (bahis_id);


--
-- Name: basin_bahsi basin_bahsi_tekil; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.basin_bahsi
    ADD CONSTRAINT basin_bahsi_tekil UNIQUE (baslik, kaynak_site);


--
-- Name: bayi_kampanya bayi_kampanya_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.bayi_kampanya
    ADD CONSTRAINT bayi_kampanya_pkey PRIMARY KEY (sira);


--
-- Name: birlestirme_karari birlestirme_karari_kaynak_kimlik_tipi_source_id_a_source_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.birlestirme_karari
    ADD CONSTRAINT birlestirme_karari_kaynak_kimlik_tipi_source_id_a_source_id_key UNIQUE (kaynak, kimlik_tipi, source_id_a, source_id_b);


--
-- Name: birlestirme_karari birlestirme_karari_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.birlestirme_karari
    ADD CONSTRAINT birlestirme_karari_pkey PRIMARY KEY (karar_id);


--
-- Name: buyume_bulgu buyume_bulgu_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.buyume_bulgu
    ADD CONSTRAINT buyume_bulgu_pkey PRIMARY KEY (bulgu_id);


--
-- Name: customer_identity customer_identity_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.customer_identity
    ADD CONSTRAINT customer_identity_pkey PRIMARY KEY (identity_id);


--
-- Name: customer customer_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.customer
    ADD CONSTRAINT customer_pkey PRIMARY KEY (customer_id);


--
-- Name: departman departman_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.departman
    ADD CONSTRAINT departman_pkey PRIMARY KEY (kod);


--
-- Name: funnel_adim funnel_adim_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.funnel_adim
    ADD CONSTRAINT funnel_adim_pkey PRIMARY KEY (adim_kod);


--
-- Name: funnel_sayfa_kapsama funnel_sayfa_kapsama_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.funnel_sayfa_kapsama
    ADD CONSTRAINT funnel_sayfa_kapsama_pkey PRIMARY KEY (adim_kod, sayfa);


--
-- Name: geo_alias geo_alias_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_alias
    ADD CONSTRAINT geo_alias_pkey PRIMARY KEY (alias_id);


--
-- Name: geo_brand geo_brand_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_brand
    ADD CONSTRAINT geo_brand_pkey PRIMARY KEY (brand_id);


--
-- Name: geo_citation_mention geo_citation_mention_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation_mention
    ADD CONSTRAINT geo_citation_mention_pkey PRIMARY KEY (citation_id, mention_id);


--
-- Name: geo_citation geo_citation_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation
    ADD CONSTRAINT geo_citation_pkey PRIMARY KEY (citation_id);


--
-- Name: geo_entity_conflict geo_entity_conflict_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_entity_conflict
    ADD CONSTRAINT geo_entity_conflict_pkey PRIMARY KEY (conflict_id);


--
-- Name: geo_gap geo_gap_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_gap
    ADD CONSTRAINT geo_gap_pkey PRIMARY KEY (gap_id);


--
-- Name: geo_karar_kapsami geo_karar_kapsami_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_karar_kapsami
    ADD CONSTRAINT geo_karar_kapsami_pkey PRIMARY KEY (kapsam_id);


--
-- Name: geo_mention geo_mention_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_mention
    ADD CONSTRAINT geo_mention_pkey PRIMARY KEY (mention_id);


--
-- Name: geo_observation geo_observation_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_observation
    ADD CONSTRAINT geo_observation_pkey PRIMARY KEY (observation_id);


--
-- Name: geo_query geo_query_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_query
    ADD CONSTRAINT geo_query_pkey PRIMARY KEY (query_id);


--
-- Name: geo_source geo_source_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_source
    ADD CONSTRAINT geo_source_pkey PRIMARY KEY (source_id);


--
-- Name: gonderi_notu gonderi_notu_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.gonderi_notu
    ADD CONSTRAINT gonderi_notu_pkey PRIMARY KEY (not_id);


--
-- Name: gonderi_sinif_beyani gonderi_sinif_beyani_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.gonderi_sinif_beyani
    ADD CONSTRAINT gonderi_sinif_beyani_pkey PRIMARY KEY (gonderi_id);


--
-- Name: guncel_olay_kosu guncel_olay_kosu_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.guncel_olay_kosu
    ADD CONSTRAINT guncel_olay_kosu_pkey PRIMARY KEY (gun);


--
-- Name: guncel_olay guncel_olay_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.guncel_olay
    ADD CONSTRAINT guncel_olay_pkey PRIMARY KEY (id);


--
-- Name: guncel_olay guncel_olay_tekil; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.guncel_olay
    ADD CONSTRAINT guncel_olay_tekil UNIQUE (gun, kaynak_url);


--
-- Name: hatirlatici hatirlatici_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.hatirlatici
    ADD CONSTRAINT hatirlatici_pkey PRIMARY KEY (id);


--
-- Name: ic_mesaj ic_mesaj_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_pkey PRIMARY KEY (mesaj_id);


--
-- Name: identity_conflict identity_conflict_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.identity_conflict
    ADD CONSTRAINT identity_conflict_pkey PRIMARY KEY (conflict_id);


--
-- Name: ig_gonderi_plani ig_gonderi_plani_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ig_gonderi_plani
    ADD CONSTRAINT ig_gonderi_plani_pkey PRIMARY KEY (plan_id);


--
-- Name: inanc_catismasi inanc_catismasi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.inanc_catismasi
    ADD CONSTRAINT inanc_catismasi_pkey PRIMARY KEY (catisma_id);


--
-- Name: jarvis_action_registry_event jarvis_action_registry_event_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_action_registry_event
    ADD CONSTRAINT jarvis_action_registry_event_pkey PRIMARY KEY (event_id);


--
-- Name: jarvis_action_registry jarvis_action_registry_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_action_registry
    ADD CONSTRAINT jarvis_action_registry_pkey PRIMARY KEY (action_key);


--
-- Name: jarvis_action_registry jarvis_action_registry_source_source_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_action_registry
    ADD CONSTRAINT jarvis_action_registry_source_source_id_key UNIQUE (source, source_id);


--
-- Name: jarvis_cari_account jarvis_cari_account_owner_account_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_account
    ADD CONSTRAINT jarvis_cari_account_owner_account_id_key UNIQUE (owner, account_id);


--
-- Name: jarvis_cari_account jarvis_cari_account_owner_name_key_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_account
    ADD CONSTRAINT jarvis_cari_account_owner_name_key_key UNIQUE (owner, name_key);


--
-- Name: jarvis_cari_account jarvis_cari_account_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_account
    ADD CONSTRAINT jarvis_cari_account_pkey PRIMARY KEY (account_id);


--
-- Name: jarvis_cari_document jarvis_cari_document_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_document
    ADD CONSTRAINT jarvis_cari_document_pkey PRIMARY KEY (document_id);


--
-- Name: jarvis_cari_draft jarvis_cari_draft_owner_account_id_draft_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_draft
    ADD CONSTRAINT jarvis_cari_draft_owner_account_id_draft_id_key UNIQUE (owner, account_id, draft_id);


--
-- Name: jarvis_cari_draft jarvis_cari_draft_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_draft
    ADD CONSTRAINT jarvis_cari_draft_pkey PRIMARY KEY (draft_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_owner_account_id_entry_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_owner_account_id_entry_id_key UNIQUE (owner, account_id, entry_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_owner_account_id_request_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_owner_account_id_request_id_key UNIQUE (owner, account_id, request_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_pkey PRIMARY KEY (entry_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_reverses_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_reverses_key UNIQUE (reverses);


--
-- Name: jarvis_cari_source_event jarvis_cari_source_event_owner_source_store_id_event_key_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_source_event
    ADD CONSTRAINT jarvis_cari_source_event_owner_source_store_id_event_key_key UNIQUE (owner, source, store_id, event_key);


--
-- Name: jarvis_cari_source_event jarvis_cari_source_event_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_source_event
    ADD CONSTRAINT jarvis_cari_source_event_pkey PRIMARY KEY (event_id);


--
-- Name: jarvis_expense_dispatch jarvis_expense_dispatch_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_expense_dispatch
    ADD CONSTRAINT jarvis_expense_dispatch_pkey PRIMARY KEY (owner, period, part);


--
-- Name: jarvis_expense_document jarvis_expense_document_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_expense_document
    ADD CONSTRAINT jarvis_expense_document_pkey PRIMARY KEY (document_id);


--
-- Name: jarvis_personal_action_event jarvis_personal_action_event_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_personal_action_event
    ADD CONSTRAINT jarvis_personal_action_event_pkey PRIMARY KEY (event_id);


--
-- Name: jarvis_personal_action jarvis_personal_action_owner_idempotency_key_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_personal_action
    ADD CONSTRAINT jarvis_personal_action_owner_idempotency_key_key UNIQUE (owner, idempotency_key);


--
-- Name: jarvis_personal_action jarvis_personal_action_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_personal_action
    ADD CONSTRAINT jarvis_personal_action_pkey PRIMARY KEY (action_id);


--
-- Name: jarvis_task_state jarvis_task_state_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.jarvis_task_state
    ADD CONSTRAINT jarvis_task_state_pkey PRIMARY KEY (task_id);


--
-- Name: jeton_otorite jeton_otorite_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jeton_otorite
    ADD CONSTRAINT jeton_otorite_pkey PRIMARY KEY (jeton_adi);


--
-- Name: kademe_denemesi kademe_denemesi_kayit_hash_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kademe_denemesi
    ADD CONSTRAINT kademe_denemesi_kayit_hash_key UNIQUE (kayit_hash);


--
-- Name: kademe_denemesi kademe_denemesi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kademe_denemesi
    ADD CONSTRAINT kademe_denemesi_pkey PRIMARY KEY (id);


--
-- Name: kanal_nabiz kanal_nabiz_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kanal_nabiz
    ADD CONSTRAINT kanal_nabiz_pkey PRIMARY KEY (kanal);


--
-- Name: kanit_anlik kanit_anlik_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kanit_anlik
    ADD CONSTRAINT kanit_anlik_pkey PRIMARY KEY (anlik_id);


--
-- Name: karar_aksiyon karar_aksiyon_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_aksiyon
    ADD CONSTRAINT karar_aksiyon_pkey PRIMARY KEY (aksiyon_id);


--
-- Name: karar_insan karar_insan_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_insan
    ADD CONSTRAINT karar_insan_pkey PRIMARY KEY (karar_id);


--
-- Name: karar_kanit karar_kanit_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_kanit
    ADD CONSTRAINT karar_kanit_pkey PRIMARY KEY (karar_id, bulgu_id);


--
-- Name: karar karar_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar
    ADD CONSTRAINT karar_pkey PRIMARY KEY (karar_id);


--
-- Name: karar_red_team karar_red_team_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_red_team
    ADD CONSTRAINT karar_red_team_pkey PRIMARY KEY (inceleme_id);


--
-- Name: karar_sonuc karar_sonuc_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_sonuc
    ADD CONSTRAINT karar_sonuc_pkey PRIMARY KEY (karar_id);


--
-- Name: kargo_karar kargo_karar_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kargo_karar
    ADD CONSTRAINT kargo_karar_pkey PRIMARY KEY (karar_id);


--
-- Name: katalog_not katalog_not_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.katalog_not
    ADD CONSTRAINT katalog_not_pkey PRIMARY KEY (not_id);


--
-- Name: kreatif_itiraz kreatif_itiraz_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kreatif_itiraz
    ADD CONSTRAINT kreatif_itiraz_pkey PRIMARY KEY (itiraz_id);


--
-- Name: kreatif_konsept kreatif_konsept_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kreatif_konsept
    ADD CONSTRAINT kreatif_konsept_pkey PRIMARY KEY (konsept_id);


--
-- Name: lead lead_kaynak_kaynak_kimlik_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.lead
    ADD CONSTRAINT lead_kaynak_kaynak_kimlik_key UNIQUE (kaynak, kaynak_kimlik);


--
-- Name: lead lead_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.lead
    ADD CONSTRAINT lead_pkey PRIMARY KEY (lead_id);


--
-- Name: maliyet_bileseni maliyet_bileseni_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.maliyet_bileseni
    ADD CONSTRAINT maliyet_bileseni_pkey PRIMARY KEY (bilesen_id);


--
-- Name: medya_istegi medya_istegi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.medya_istegi
    ADD CONSTRAINT medya_istegi_pkey PRIMARY KEY (istek_no);


--
-- Name: medya_istegi medya_istegi_request_id_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.medya_istegi
    ADD CONSTRAINT medya_istegi_request_id_key UNIQUE (request_id);


--
-- Name: meta_hesap_kayit meta_hesap_kayit_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.meta_hesap_kayit
    ADD CONSTRAINT meta_hesap_kayit_pkey PRIMARY KEY (hesap_id);


--
-- Name: mimari_ders mimari_ders_kod_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.mimari_ders
    ADD CONSTRAINT mimari_ders_kod_key UNIQUE (kod);


--
-- Name: mimari_ders mimari_ders_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.mimari_ders
    ADD CONSTRAINT mimari_ders_pkey PRIMARY KEY (ders_id);


--
-- Name: model_kademe model_kademe_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.model_kademe
    ADD CONSTRAINT model_kademe_pkey PRIMARY KEY (is_anahtari);


--
-- Name: pazar_bulgu pazar_bulgu_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.pazar_bulgu
    ADD CONSTRAINT pazar_bulgu_pkey PRIMARY KEY (bulgu_id);


--
-- Name: pazaryeri_siparis pazaryeri_siparis_kanal_siparis_no_paket_no_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.pazaryeri_siparis
    ADD CONSTRAINT pazaryeri_siparis_kanal_siparis_no_paket_no_key UNIQUE (kanal, siparis_no, paket_no);


--
-- Name: pazaryeri_siparis pazaryeri_siparis_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.pazaryeri_siparis
    ADD CONSTRAINT pazaryeri_siparis_pkey PRIMARY KEY (id);


--
-- Name: platform platform_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.platform
    ADD CONSTRAINT platform_pkey PRIMARY KEY (kod);


--
-- Name: rapor_anlik rapor_anlik_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.rapor_anlik
    ADD CONSTRAINT rapor_anlik_pkey PRIMARY KEY (kayit_id);


--
-- Name: rapor_anlik rapor_anlik_rapor_gunu_calisma_no_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.rapor_anlik
    ADD CONSTRAINT rapor_anlik_rapor_gunu_calisma_no_key UNIQUE (rapor_gunu, calisma_no);


--
-- Name: reklam_urun reklam_urun_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.reklam_urun
    ADD CONSTRAINT reklam_urun_pkey PRIMARY KEY (ad_id);


--
-- Name: saha_bilgi saha_bilgi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_bilgi
    ADD CONSTRAINT saha_bilgi_pkey PRIMARY KEY (hedef_anahtari);


--
-- Name: saha_brans_esleme saha_brans_esleme_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_brans_esleme
    ADD CONSTRAINT saha_brans_esleme_pkey PRIMARY KEY (kategori);


--
-- Name: saha_disla_kalip saha_disla_kalip_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_disla_kalip
    ADD CONSTRAINT saha_disla_kalip_pkey PRIMARY KEY (kalip);


--
-- Name: saha_elle_nokta saha_elle_nokta_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_elle_nokta
    ADD CONSTRAINT saha_elle_nokta_pkey PRIMARY KEY (nokta_id);


--
-- Name: saha_ilce_esleme saha_ilce_esleme_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ilce_esleme
    ADD CONSTRAINT saha_ilce_esleme_pkey PRIMARY KEY (ham);


--
-- Name: saha_konum saha_konum_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_konum
    ADD CONSTRAINT saha_konum_pkey PRIMARY KEY (konum_id);


--
-- Name: saha_rota_durak saha_rota_durak_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_rota_durak
    ADD CONSTRAINT saha_rota_durak_pkey PRIMARY KEY (rota_id, sira);


--
-- Name: saha_rota saha_rota_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_rota
    ADD CONSTRAINT saha_rota_pkey PRIMARY KEY (rota_id);


--
-- Name: saha_ziyaret_foto saha_ziyaret_foto_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ziyaret_foto
    ADD CONSTRAINT saha_ziyaret_foto_pkey PRIMARY KEY (foto_id);


--
-- Name: saha_ziyaret saha_ziyaret_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ziyaret
    ADD CONSTRAINT saha_ziyaret_pkey PRIMARY KEY (ziyaret_id);


--
-- Name: sayfa_olcum sayfa_olcum_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.sayfa_olcum
    ADD CONSTRAINT sayfa_olcum_pkey PRIMARY KEY (url);


--
-- Name: sayfa_urun sayfa_urun_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.sayfa_urun
    ADD CONSTRAINT sayfa_urun_pkey PRIMARY KEY (sayfa_yolu);


--
-- Name: siparis_bildirim siparis_bildirim_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.siparis_bildirim
    ADD CONSTRAINT siparis_bildirim_pkey PRIMARY KEY (id);


--
-- Name: siparis_bildirim siparis_bildirim_siparis_id_yol_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.siparis_bildirim
    ADD CONSTRAINT siparis_bildirim_siparis_id_yol_key UNIQUE (siparis_id, yol);


--
-- Name: siparis_teyit siparis_teyit_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.siparis_teyit
    ADD CONSTRAINT siparis_teyit_pkey PRIMARY KEY (siparis_no);


--
-- Name: source_authority source_authority_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.source_authority
    ADD CONSTRAINT source_authority_pkey PRIMARY KEY (alan);


--
-- Name: stok_sayim stok_sayim_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.stok_sayim
    ADD CONSTRAINT stok_sayim_pkey PRIMARY KEY (sayim_id);


--
-- Name: tarayici_isi tarayici_isi_idempotency_key_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.tarayici_isi
    ADD CONSTRAINT tarayici_isi_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: tarayici_isi tarayici_isi_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.tarayici_isi
    ADD CONSTRAINT tarayici_isi_pkey PRIMARY KEY (is_id);


--
-- Name: tarayici_isi tarayici_isi_slug_key; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.tarayici_isi
    ADD CONSTRAINT tarayici_isi_slug_key UNIQUE (slug);


--
-- Name: tarayici_nabiz tarayici_nabiz_pkey; Type: CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.tarayici_nabiz
    ADD CONSTRAINT tarayici_nabiz_pkey PRIMARY KEY (worker);


--
-- Name: tasarim_isi tasarim_isi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.tasarim_isi
    ADD CONSTRAINT tasarim_isi_pkey PRIMARY KEY (is_id);


--
-- Name: tasarim_sablon tasarim_sablon_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.tasarim_sablon
    ADD CONSTRAINT tasarim_sablon_pkey PRIMARY KEY (sablon_id);


--
-- Name: urun_bayi_fiyat urun_bayi_fiyat_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_bayi_fiyat
    ADD CONSTRAINT urun_bayi_fiyat_pkey PRIMARY KEY (urun_slug);


--
-- Name: urun_fiyat_gercegi urun_fiyat_gercegi_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_fiyat_gercegi
    ADD CONSTRAINT urun_fiyat_gercegi_pkey PRIMARY KEY (urun_id);


--
-- Name: urun_inci urun_inci_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_inci
    ADD CONSTRAINT urun_inci_pkey PRIMARY KEY (urun_anahtari);


--
-- Name: urun_maliyet urun_maliyet_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_maliyet
    ADD CONSTRAINT urun_maliyet_pkey PRIMARY KEY (maliyet_id);


--
-- Name: urun_maliyet urun_maliyet_urun_id_gecerli_baslangic_key; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_maliyet
    ADD CONSTRAINT urun_maliyet_urun_id_gecerli_baslangic_key UNIQUE (urun_id, gecerli_baslangic);


--
-- Name: urun_platform_fiyat urun_platform_fiyat_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_platform_fiyat
    ADD CONSTRAINT urun_platform_fiyat_pkey PRIMARY KEY (id);


--
-- Name: urun_platform_komisyon urun_platform_komisyon_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_platform_komisyon
    ADD CONSTRAINT urun_platform_komisyon_pkey PRIMARY KEY (urun_id, platform_kod);


--
-- Name: urun_seo urun_seo_pkey; Type: CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_seo
    ADD CONSTRAINT urun_seo_pkey PRIMARY KEY (urun_id);


--
-- Name: hiz hiz_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.hiz
    ADD CONSTRAINT hiz_pkey PRIMARY KEY (kova, pencere_bas);


--
-- Name: kalip kalip_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.kalip
    ADD CONSTRAINT kalip_pkey PRIMARY KEY (id);


--
-- Name: kalip kalip_soru_norm_cevap_imza_key; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.kalip
    ADD CONSTRAINT kalip_soru_norm_cevap_imza_key UNIQUE (soru_norm, cevap_imza);


--
-- Name: konusma konusma_kanal_harici_tekil; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.konusma
    ADD CONSTRAINT konusma_kanal_harici_tekil UNIQUE (kanal, harici_id);


--
-- Name: konusma konusma_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.konusma
    ADD CONSTRAINT konusma_pkey PRIMARY KEY (id);


--
-- Name: mesaj mesaj_konusma_harici_tekil; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.mesaj
    ADD CONSTRAINT mesaj_konusma_harici_tekil UNIQUE (konusma_id, harici_id);


--
-- Name: mesaj mesaj_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.mesaj
    ADD CONSTRAINT mesaj_pkey PRIMARY KEY (id);


--
-- Name: satis_cevap satis_cevap_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_cevap
    ADD CONSTRAINT satis_cevap_pkey PRIMARY KEY (id);


--
-- Name: satis_yaklasim satis_yaklasim_pkey; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_yaklasim
    ADD CONSTRAINT satis_yaklasim_pkey PRIMARY KEY (id);


--
-- Name: satis_yaklasim satis_yaklasim_surum_benzersiz; Type: CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_yaklasim
    ADD CONSTRAINT satis_yaklasim_surum_benzersiz UNIQUE (surum, urun, soru_tipi);


--
-- Name: hatira hatira_pkey; Type: CONSTRAINT; Schema: mem0; Owner: mem0_writer
--

ALTER TABLE ONLY mem0.hatira
    ADD CONSTRAINT hatira_pkey PRIMARY KEY (id);


--
-- Name: test_run PK_011c050f566e9db509a0fadb9b9; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_run
    ADD CONSTRAINT "PK_011c050f566e9db509a0fadb9b9" PRIMARY KEY (id);


--
-- Name: project_secrets_provider_access PK_0402b7fcec5415246656f102f83; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_secrets_provider_access
    ADD CONSTRAINT "PK_0402b7fcec5415246656f102f83" PRIMARY KEY ("secretsProviderConnectionId", "projectId");


--
-- Name: agent_eval_rating PK_04b7709a435e0c07520ceb37393; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_rating
    ADD CONSTRAINT "PK_04b7709a435e0c07520ceb37393" PRIMARY KEY (id);


--
-- Name: installed_packages PK_08cc9197c39b028c1e9beca225940576fd1a5804; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.installed_packages
    ADD CONSTRAINT "PK_08cc9197c39b028c1e9beca225940576fd1a5804" PRIMARY KEY ("packageName");


--
-- Name: promotion_connection_project PK_0c63d9094bf8ca78349ba860147; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_connection_project
    ADD CONSTRAINT "PK_0c63d9094bf8ca78349ba860147" PRIMARY KEY ("projectId");


--
-- Name: instance_ai_events PK_12489cd6197feeac2089acc7ef6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_events
    ADD CONSTRAINT "PK_12489cd6197feeac2089acc7ef6" PRIMARY KEY ("threadId", seq);


--
-- Name: mcp_registry_server PK_12fd89a1fb8489513b0a91f5d31; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.mcp_registry_server
    ADD CONSTRAINT "PK_12fd89a1fb8489513b0a91f5d31" PRIMARY KEY (slug);


--
-- Name: workflow_publication_trigger_status PK_14aa18b83513fb92d7523909e02; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publication_trigger_status
    ADD CONSTRAINT "PK_14aa18b83513fb92d7523909e02" PRIMARY KEY ("workflowId", "nodeId");


--
-- Name: instance_ai_messages PK_156c6f287225e9befe0181bb02b; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_messages
    ADD CONSTRAINT "PK_156c6f287225e9befe0181bb02b" PRIMARY KEY (id);


--
-- Name: agent_task_definition PK_1756c11c637903e97629a7a784a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_definition
    ADD CONSTRAINT "PK_1756c11c637903e97629a7a784a" PRIMARY KEY (id);


--
-- Name: execution_metadata PK_17a0b6284f8d626aae88e1c16e4; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_metadata
    ADD CONSTRAINT "PK_17a0b6284f8d626aae88e1c16e4" PRIMARY KEY (id);


--
-- Name: role_mapping_rule_project PK_198c5b5aea509d139274efcaf9a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule_project
    ADD CONSTRAINT "PK_198c5b5aea509d139274efcaf9a" PRIMARY KEY ("roleMappingRuleId", "projectId");


--
-- Name: project_relation PK_1caaa312a5d7184a003be0f0cb6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_relation
    ADD CONSTRAINT "PK_1caaa312a5d7184a003be0f0cb6" PRIMARY KEY ("projectId", "userId");


--
-- Name: chat_hub_sessions PK_1eafef1273c70e4464fec703412; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_sessions
    ADD CONSTRAINT "PK_1eafef1273c70e4464fec703412" PRIMARY KEY (id);


--
-- Name: agent_task_snapshot PK_2142a8bcda2360c3c5e34f82640; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_snapshot
    ADD CONSTRAINT "PK_2142a8bcda2360c3c5e34f82640" PRIMARY KEY ("versionId", "taskId");


--
-- Name: instance_ai_iteration_logs PK_21c2b214b44bc6c34a6d3551c90; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_iteration_logs
    ADD CONSTRAINT "PK_21c2b214b44bc6c34a6d3551c90" PRIMARY KEY (id);


--
-- Name: agent_execution_threads PK_22373dbf6ba6929d8ac50093309; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution_threads
    ADD CONSTRAINT "PK_22373dbf6ba6929d8ac50093309" PRIMARY KEY (id);


--
-- Name: instance_ai_pending_confirmations PK_25c38179c8d45095b168adfff80; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_pending_confirmations
    ADD CONSTRAINT "PK_25c38179c8d45095b168adfff80" PRIMARY KEY ("requestId");


--
-- Name: type_availability_policy_scope PK_26178b723c376150b45eabdb8e7; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy_scope
    ADD CONSTRAINT "PK_26178b723c376150b45eabdb8e7" PRIMARY KEY (id);


--
-- Name: agents_memory_entry_sources PK_278f05e98e74baaaa93f52b4bab; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "PK_278f05e98e74baaaa93f52b4bab" PRIMARY KEY (id);


--
-- Name: folder_tag PK_27e4e00852f6b06a925a4d83a3e; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder_tag
    ADD CONSTRAINT "PK_27e4e00852f6b06a925a4d83a3e" PRIMARY KEY ("folderId", "tagId");


--
-- Name: agent_eval_run PK_280832ca3f1b43663cc0e25e77f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_run
    ADD CONSTRAINT "PK_280832ca3f1b43663cc0e25e77f" PRIMARY KEY (id);


--
-- Name: instance_ai_threads PK_35575100e45cdedeb89ae0643e9; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_threads
    ADD CONSTRAINT "PK_35575100e45cdedeb89ae0643e9" PRIMARY KEY (id);


--
-- Name: role PK_35c9b140caaf6da09cfabb0d675; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role
    ADD CONSTRAINT "PK_35c9b140caaf6da09cfabb0d675" PRIMARY KEY (slug);


--
-- Name: secrets_provider_connection PK_4350ae85e76f9ba7df1370acb5d; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.secrets_provider_connection
    ADD CONSTRAINT "PK_4350ae85e76f9ba7df1370acb5d" PRIMARY KEY (id);


--
-- Name: instance_ai_resources PK_45b5b0b6f715dae4292b86603d8; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_resources
    ADD CONSTRAINT "PK_45b5b0b6f715dae4292b86603d8" PRIMARY KEY (id);


--
-- Name: workflow_review_request_reviewers PK_4715c6035e0ebc4f3e8716f1e34; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_reviewers
    ADD CONSTRAINT "PK_4715c6035e0ebc4f3e8716f1e34" PRIMARY KEY ("workflowReviewRequestId", "userId");


--
-- Name: agents_threads PK_4a3feb0a13ffe315c009cce64e5; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_threads
    ADD CONSTRAINT "PK_4a3feb0a13ffe315c009cce64e5" PRIMARY KEY (id);


--
-- Name: instance_monitoring_report PK_4a5cb8aa51c67e4f5a7eb0f9509; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_monitoring_report
    ADD CONSTRAINT "PK_4a5cb8aa51c67e4f5a7eb0f9509" PRIMARY KEY (id);


--
-- Name: agent_workflow_dependency PK_4b9cb5e8db0dd16bb843b76465a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_workflow_dependency
    ADD CONSTRAINT "PK_4b9cb5e8db0dd16bb843b76465a" PRIMARY KEY ("agentId", "workflowId");


--
-- Name: project PK_4d68b1358bb5b766d3e78f32f57; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project
    ADD CONSTRAINT "PK_4d68b1358bb5b766d3e78f32f57" PRIMARY KEY (id);


--
-- Name: instance_ai_observations PK_4d9b514cdf0f0b577650caf2ac2; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observations
    ADD CONSTRAINT "PK_4d9b514cdf0f0b577650caf2ac2" PRIMARY KEY (id);


--
-- Name: agent_channel_status PK_4e1ca943734d575679a56f4da90; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_channel_status
    ADD CONSTRAINT "PK_4e1ca943734d575679a56f4da90" PRIMARY KEY ("agentId", "integrationType", "credentialId", "hostId");


--
-- Name: agent_checkpoints PK_50a27cbafa6806c9b162304b5fd; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_checkpoints
    ADD CONSTRAINT "PK_50a27cbafa6806c9b162304b5fd" PRIMARY KEY ("runId");


--
-- Name: dynamic_credential_entry PK_5135ffcabecad4727ff6b9b803d; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_entry
    ADD CONSTRAINT "PK_5135ffcabecad4727ff6b9b803d" PRIMARY KEY (credential_id, subject_id, resolver_id);


--
-- Name: workflow_dependency PK_52325e34cd7a2f0f67b0f3cad65; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_dependency
    ADD CONSTRAINT "PK_52325e34cd7a2f0f67b0f3cad65" PRIMARY KEY (id);


--
-- Name: instance_ai_checkpoints PK_5315a45f0846d1f9d128c18a2ed; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_checkpoints
    ADD CONSTRAINT "PK_5315a45f0846d1f9d128c18a2ed" PRIMARY KEY (key);


--
-- Name: agent_credential_dependency PK_546f5d9cfaf5ea78efcc6f5d0a2; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_credential_dependency
    ADD CONSTRAINT "PK_546f5d9cfaf5ea78efcc6f5d0a2" PRIMARY KEY ("agentId", "credentialId");


--
-- Name: instance_ai_thread_grants PK_56107d26ebeabf780c5cf311d66; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_thread_grants
    ADD CONSTRAINT "PK_56107d26ebeabf780c5cf311d66" PRIMARY KEY ("threadId", "userId", "grantKey");


--
-- Name: invalid_auth_token PK_5779069b7235b256d91f7af1a15; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.invalid_auth_token
    ADD CONSTRAINT "PK_5779069b7235b256d91f7af1a15" PRIMARY KEY (token);


--
-- Name: evaluation_config PK_59c14dccf8989df94070c2dcfda; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_config
    ADD CONSTRAINT "PK_59c14dccf8989df94070c2dcfda" PRIMARY KEY (id);


--
-- Name: workflow_review_activity_comment PK_5a2a7dea8b7e6afa1001129da27; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity_comment
    ADD CONSTRAINT "PK_5a2a7dea8b7e6afa1001129da27" PRIMARY KEY (id);


--
-- Name: instance_ai_observation_cursors PK_5b6319b2e9a37c1064a72428f9a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observation_cursors
    ADD CONSTRAINT "PK_5b6319b2e9a37c1064a72428f9a" PRIMARY KEY ("observationScopeId");


--
-- Name: shared_workflow PK_5ba87620386b847201c9531c58f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_workflow
    ADD CONSTRAINT "PK_5ba87620386b847201c9531c58f" PRIMARY KEY ("workflowId", "projectId");


--
-- Name: workflow_published_version PK_5c76fb7ee939fe2530374d3f75a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_published_version
    ADD CONSTRAINT "PK_5c76fb7ee939fe2530374d3f75a" PRIMARY KEY ("workflowId");


--
-- Name: folder PK_6278a41a706740c94c02e288df8; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder
    ADD CONSTRAINT "PK_6278a41a706740c94c02e288df8" PRIMARY KEY (id);


--
-- Name: promotion_connection PK_65cec79aba16950b45592335204; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_connection
    ADD CONSTRAINT "PK_65cec79aba16950b45592335204" PRIMARY KEY (id);


--
-- Name: agent_history PK_65ffcfe7a8e112fb826311fb092; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_history
    ADD CONSTRAINT "PK_65ffcfe7a8e112fb826311fb092" PRIMARY KEY ("versionId");


--
-- Name: data_table_column PK_673cb121ee4a8a5e27850c72c51; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table_column
    ADD CONSTRAINT "PK_673cb121ee4a8a5e27850c72c51" PRIMARY KEY (id);


--
-- Name: agent_files PK_692920e59217af7d124cd95106f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_files
    ADD CONSTRAINT "PK_692920e59217af7d124cd95106f" PRIMARY KEY (id);


--
-- Name: chat_hub_tools PK_696d26426c704fba79b2c195ef5; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_tools
    ADD CONSTRAINT "PK_696d26426c704fba79b2c195ef5" PRIMARY KEY (id);


--
-- Name: annotation_tag_entity PK_69dfa041592c30bbc0d4b84aa00; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.annotation_tag_entity
    ADD CONSTRAINT "PK_69dfa041592c30bbc0d4b84aa00" PRIMARY KEY (id);


--
-- Name: user_favorites PK_6c472a19a7423cfbbf6b7c75939; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT "PK_6c472a19a7423cfbbf6b7c75939" PRIMARY KEY (id);


--
-- Name: agent_background_job PK_6e0db58281aa2b4c956dc0d58e9; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_background_job
    ADD CONSTRAINT "PK_6e0db58281aa2b4c956dc0d58e9" PRIMARY KEY (id);


--
-- Name: promotion_provider PK_6e968555ff44699f59ad10be765; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_provider
    ADD CONSTRAINT "PK_6e968555ff44699f59ad10be765" PRIMARY KEY (id);


--
-- Name: project_pool_settings PK_6f5617b5fb0db43f92e39f5b626; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_pool_settings
    ADD CONSTRAINT "PK_6f5617b5fb0db43f92e39f5b626" PRIMARY KEY ("projectId");


--
-- Name: instance_ai_observational_memory PK_7192dd00cddba039bf1d3e6a098; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observational_memory
    ADD CONSTRAINT "PK_7192dd00cddba039bf1d3e6a098" PRIMARY KEY (id);


--
-- Name: oauth_refresh_tokens PK_74abaed0b30711b6532598b0392; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT "PK_74abaed0b30711b6532598b0392" PRIMARY KEY (token);


--
-- Name: dynamic_credential_user_entry PK_74f548e633abc66dc27c8f0ca77; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_user_entry
    ADD CONSTRAINT "PK_74f548e633abc66dc27c8f0ca77" PRIMARY KEY ("credentialId", "userId", "resolverId");


--
-- Name: agent_chat_subscriptions PK_76598cf91038bee1f3ac94c94bc; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_chat_subscriptions
    ADD CONSTRAINT "PK_76598cf91038bee1f3ac94c94bc" PRIMARY KEY ("agentId", "integrationType", "credentialId", "threadId");


--
-- Name: chat_hub_messages PK_7704a5add6baed43eef835f0bfb; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "PK_7704a5add6baed43eef835f0bfb" PRIMARY KEY (id);


--
-- Name: execution_annotations PK_7afcf93ffa20c4252869a7c6a23; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotations
    ADD CONSTRAINT "PK_7afcf93ffa20c4252869a7c6a23" PRIMARY KEY (id);


--
-- Name: type_availability_policy PK_7dc9809c6d53a6b8b8a62cd7798; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy
    ADD CONSTRAINT "PK_7dc9809c6d53a6b8b8a62cd7798" PRIMARY KEY (id);


--
-- Name: agents_observation_locks PK_7e2e315162ac3d80587e15ac2c3; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_locks
    ADD CONSTRAINT "PK_7e2e315162ac3d80587e15ac2c3" PRIMARY KEY ("agentId", "observationScopeId", "taskKind");


--
-- Name: credential_dependency PK_80212729ed0ffa0709417ab28f4; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.credential_dependency
    ADD CONSTRAINT "PK_80212729ed0ffa0709417ab28f4" PRIMARY KEY (id);


--
-- Name: agents_messages PK_81020dc608dfb0af1ede386d907; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_messages
    ADD CONSTRAINT "PK_81020dc608dfb0af1ede386d907" PRIMARY KEY (id);


--
-- Name: ai_builder_temporary_workflow PK_85a87a1ba0f61999fe11dc56325; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_builder_temporary_workflow
    ADD CONSTRAINT "PK_85a87a1ba0f61999fe11dc56325" PRIMARY KEY ("workflowId");


--
-- Name: oauth_user_consents PK_85b9ada746802c8993103470f05; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_user_consents
    ADD CONSTRAINT "PK_85b9ada746802c8993103470f05" PRIMARY KEY (id);


--
-- Name: instance_version_history PK_874f58cb616935bf49d9dbd67e9; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_version_history
    ADD CONSTRAINT "PK_874f58cb616935bf49d9dbd67e9" PRIMARY KEY (id);


--
-- Name: chat_hub_session_tools PK_87aea76ff4c274c4a5ac838ebe3; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_session_tools
    ADD CONSTRAINT "PK_87aea76ff4c274c4a5ac838ebe3" PRIMARY KEY ("sessionId", "toolId");


--
-- Name: scheduled_job PK_893185383f029ca8d57bb781fa8; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.scheduled_job
    ADD CONSTRAINT "PK_893185383f029ca8d57bb781fa8" PRIMARY KEY (id);


--
-- Name: migrations PK_8c82d7f526340ab734260ea46be; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.migrations
    ADD CONSTRAINT "PK_8c82d7f526340ab734260ea46be" PRIMARY KEY (id);


--
-- Name: installed_nodes PK_8ebd28194e4f792f96b5933423fc439df97d9689; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.installed_nodes
    ADD CONSTRAINT "PK_8ebd28194e4f792f96b5933423fc439df97d9689" PRIMARY KEY (name);


--
-- Name: shared_credentials PK_8ef3a59796a228913f251779cff; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_credentials
    ADD CONSTRAINT "PK_8ef3a59796a228913f251779cff" PRIMARY KEY ("credentialsId", "projectId");


--
-- Name: test_case_execution PK_90c121f77a78a6580e94b794bce; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_case_execution
    ADD CONSTRAINT "PK_90c121f77a78a6580e94b794bce" PRIMARY KEY (id);


--
-- Name: instance_ai_workflow_snapshots PK_93f2696eb321dfe1d7defe7073f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_workflow_snapshots
    ADD CONSTRAINT "PK_93f2696eb321dfe1d7defe7073f" PRIMARY KEY ("runId", "workflowName");


--
-- Name: deployment_key PK_94bb7aeb5def5a0284a5fe9f9a0; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.deployment_key
    ADD CONSTRAINT "PK_94bb7aeb5def5a0284a5fe9f9a0" PRIMARY KEY (id);


--
-- Name: type_availability_policy_attachment PK_96c1ba2b399ed0aabb047d04f07; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy_attachment
    ADD CONSTRAINT "PK_96c1ba2b399ed0aabb047d04f07" PRIMARY KEY ("scopeId", "policyId");


--
-- Name: user_api_keys PK_978fa5caa3468f463dac9d92e69; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.user_api_keys
    ADD CONSTRAINT "PK_978fa5caa3468f463dac9d92e69" PRIMARY KEY (id);


--
-- Name: execution_annotation_tags PK_979ec03d31294cca484be65d11f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotation_tags
    ADD CONSTRAINT "PK_979ec03d31294cca484be65d11f" PRIMARY KEY ("annotationId", "tagId");


--
-- Name: instance_credential_assignment PK_984b0a98726485c9a330cde6b2f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_credential_assignment
    ADD CONSTRAINT "PK_984b0a98726485c9a330cde6b2f" PRIMARY KEY ("credentialUseId");


--
-- Name: trusted_key_source PK_99e8908ce2c2cdccce487db7fc6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.trusted_key_source
    ADD CONSTRAINT "PK_99e8908ce2c2cdccce487db7fc6" PRIMARY KEY (id);


--
-- Name: agents_observations PK_9ad319654d12c2649f7caf27135; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observations
    ADD CONSTRAINT "PK_9ad319654d12c2649f7caf27135" PRIMARY KEY (id);


--
-- Name: agent_chat_attachments PK_9c1250f77b41d1a0e71a3f1414a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_chat_attachments
    ADD CONSTRAINT "PK_9c1250f77b41d1a0e71a3f1414a" PRIMARY KEY (id);


--
-- Name: agents PK_9c653f28ae19c5884d5baf6a1d9; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT "PK_9c653f28ae19c5884d5baf6a1d9" PRIMARY KEY (id);


--
-- Name: agents_memory_entry_locks PK_a8e0f570d04a174292bea104ae6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_locks
    ADD CONSTRAINT "PK_a8e0f570d04a174292bea104ae6" PRIMARY KEY ("agentId", "resourceId");


--
-- Name: agent_eval_dataset PK_ac887efbb3580a577f1442cfa89; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_dataset
    ADD CONSTRAINT "PK_ac887efbb3580a577f1442cfa89" PRIMARY KEY (id);


--
-- Name: workflow_review_request PK_ae17b90023bcd05e003cd8f64dc; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request
    ADD CONSTRAINT "PK_ae17b90023bcd05e003cd8f64dc" PRIMARY KEY (id);


--
-- Name: workflow_review_request_authors PK_ae197bb5135d422f6392a879e0c; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_authors
    ADD CONSTRAINT "PK_ae197bb5135d422f6392a879e0c" PRIMARY KEY ("workflowReviewRequestId", "userId");


--
-- Name: webhook_entity PK_b21ace2e13596ccd87dc9bf4ea6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.webhook_entity
    ADD CONSTRAINT "PK_b21ace2e13596ccd87dc9bf4ea6" PRIMARY KEY ("webhookPath", method);


--
-- Name: workflow_publication_outbox PK_b3e2eeee36a4bd044d56468d311; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publication_outbox
    ADD CONSTRAINT "PK_b3e2eeee36a4bd044d56468d311" PRIMARY KEY (id);


--
-- Name: promotion_config PK_b4d534111f62d31699e6ceb544f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_config
    ADD CONSTRAINT "PK_b4d534111f62d31699e6ceb544f" PRIMARY KEY (id);


--
-- Name: insights_by_period PK_b606942249b90cc39b0265f0575; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_by_period
    ADD CONSTRAINT "PK_b606942249b90cc39b0265f0575" PRIMARY KEY (id);


--
-- Name: workflow_history PK_b6572dd6173e4cd06fe79937b58; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_history
    ADD CONSTRAINT "PK_b6572dd6173e4cd06fe79937b58" PRIMARY KEY ("versionId");


--
-- Name: dynamic_credential_resolver PK_b76cfb088dcdaf5275e9980bb64; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_resolver
    ADD CONSTRAINT "PK_b76cfb088dcdaf5275e9980bb64" PRIMARY KEY (id);


--
-- Name: agent_execution PK_ba438acc8532addc12d1ef17049; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution
    ADD CONSTRAINT "PK_ba438acc8532addc12d1ef17049" PRIMARY KEY (id);


--
-- Name: workflow_review_request_workflow PK_be3bf4facb054cf2b2b116b3b9c; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_workflow
    ADD CONSTRAINT "PK_be3bf4facb054cf2b2b116b3b9c" PRIMARY KEY (id);


--
-- Name: agents_memory_entries PK_bfbc45dc88f66fae4e4b4a15fec; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entries
    ADD CONSTRAINT "PK_bfbc45dc88f66fae4e4b4a15fec" PRIMARY KEY (id);


--
-- Name: scope PK_bfc45df0481abd7f355d6187da1; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.scope
    ADD CONSTRAINT "PK_bfc45df0481abd7f355d6187da1" PRIMARY KEY (slug);


--
-- Name: activity_event PK_c2c1e9fdda754a6bf7f664d7e04; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.activity_event
    ADD CONSTRAINT "PK_c2c1e9fdda754a6bf7f664d7e04" PRIMARY KEY (id);


--
-- Name: oauth_clients PK_c4759172d3431bae6f04e678e0d; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT "PK_c4759172d3431bae6f04e678e0d" PRIMARY KEY (id);


--
-- Name: workflow_publish_history PK_c788f7caf88e91e365c97d6d04a; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publish_history
    ADD CONSTRAINT "PK_c788f7caf88e91e365c97d6d04a" PRIMARY KEY (id);


--
-- Name: processed_data PK_ca04b9d8dc72de268fe07a65773; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.processed_data
    ADD CONSTRAINT "PK_ca04b9d8dc72de268fe07a65773" PRIMARY KEY ("workflowId", context);


--
-- Name: chat_hub_agent_tools PK_cc8806fdea48297a7d497035d72; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agent_tools
    ADD CONSTRAINT "PK_cc8806fdea48297a7d497035d72" PRIMARY KEY ("agentId", "toolId");


--
-- Name: agent_eval_result PK_d40a22dc56dc200313c1f0e41ac; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_result
    ADD CONSTRAINT "PK_d40a22dc56dc200313c1f0e41ac" PRIMARY KEY (id);


--
-- Name: agents_memory_entry_candidates PK_d5c36484cafd23222df4c564159; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_candidates
    ADD CONSTRAINT "PK_d5c36484cafd23222df4c564159" PRIMARY KEY (id);


--
-- Name: scheduled_task PK_d690af24e57e30594c1948af1e6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.scheduled_task
    ADD CONSTRAINT "PK_d690af24e57e30594c1948af1e6" PRIMARY KEY (id);


--
-- Name: role_mapping_rule PK_d772c8ec1a89b52d31c882bc560; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule
    ADD CONSTRAINT "PK_d772c8ec1a89b52d31c882bc560" PRIMARY KEY (id);


--
-- Name: token_exchange_jti PK_d8e8a6f737d530fdd2dd716e89c; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.token_exchange_jti
    ADD CONSTRAINT "PK_d8e8a6f737d530fdd2dd716e89c" PRIMARY KEY (jti);


--
-- Name: settings PK_dc0fe14e6d9943f268e7b119f69ab8bd; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT "PK_dc0fe14e6d9943f268e7b119f69ab8bd" PRIMARY KEY (key);


--
-- Name: trusted_key PK_dc7d93798f3dbb6959f974c97e1; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.trusted_key
    ADD CONSTRAINT "PK_dc7d93798f3dbb6959f974c97e1" PRIMARY KEY ("sourceId", kid);


--
-- Name: oauth_access_tokens PK_dcd71f96a5d5f4bf79e67d322bf; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_access_tokens
    ADD CONSTRAINT "PK_dcd71f96a5d5f4bf79e67d322bf" PRIMARY KEY (token);


--
-- Name: data_table PK_e226d0001b9e6097cbfe70617cb; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table
    ADD CONSTRAINT "PK_e226d0001b9e6097cbfe70617cb" PRIMARY KEY (id);


--
-- Name: instance_ai_mcp_registry_connections PK_e34e4d15d78eabbe8217e33ef03; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_mcp_registry_connections
    ADD CONSTRAINT "PK_e34e4d15d78eabbe8217e33ef03" PRIMARY KEY (id);


--
-- Name: workflow_builder_session PK_e69ef0d385986e273423b0e8695; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_builder_session
    ADD CONSTRAINT "PK_e69ef0d385986e273423b0e8695" PRIMARY KEY (id);


--
-- Name: evaluation_collection PK_e720b6efc1e45b878ebb0b2ca30; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_collection
    ADD CONSTRAINT "PK_e720b6efc1e45b878ebb0b2ca30" PRIMARY KEY (id);


--
-- Name: ai_preference PK_e7dbbeec9da3e06f6a20669e6e7; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_preference
    ADD CONSTRAINT "PK_e7dbbeec9da3e06f6a20669e6e7" PRIMARY KEY (id);


--
-- Name: user PK_ea8f538c94b6e352418254ed6474a81f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT "PK_ea8f538c94b6e352418254ed6474a81f" PRIMARY KEY (id);


--
-- Name: agents_observation_cursors PK_eb777ac57ab872d38f8ebd19317; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_cursors
    ADD CONSTRAINT "PK_eb777ac57ab872d38f8ebd19317" PRIMARY KEY ("agentId", "observationScopeId");


--
-- Name: insights_raw PK_ec15125755151e3a7e00e00014f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_raw
    ADD CONSTRAINT "PK_ec15125755151e3a7e00e00014f" PRIMARY KEY (id);


--
-- Name: poller_state PK_eda59336a5dd1e6a12f4d4b7287; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.poller_state
    ADD CONSTRAINT "PK_eda59336a5dd1e6a12f4d4b7287" PRIMARY KEY ("workflowId", "nodeId");


--
-- Name: workflow_review_activity PK_f1e66ba0b645dec566057ad21e6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity
    ADD CONSTRAINT "PK_f1e66ba0b645dec566057ad21e6" PRIMARY KEY (id);


--
-- Name: chat_hub_agents PK_f39a3b36bbdf0e2979ddb21cf78; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agents
    ADD CONSTRAINT "PK_f39a3b36bbdf0e2979ddb21cf78" PRIMARY KEY (id);


--
-- Name: insights_metadata PK_f448a94c35218b6208ce20cf5a1; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_metadata
    ADD CONSTRAINT "PK_f448a94c35218b6208ce20cf5a1" PRIMARY KEY ("metaId");


--
-- Name: agent_task_run_lock PK_f593adaf7230e964d3c25deda64; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_run_lock
    ADD CONSTRAINT "PK_f593adaf7230e964d3c25deda64" PRIMARY KEY ("agentId", "taskId");


--
-- Name: agents_resources PK_fa6b20b2d31a9991529dbf8ef7d; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_resources
    ADD CONSTRAINT "PK_fa6b20b2d31a9991529dbf8ef7d" PRIMARY KEY (id);


--
-- Name: oauth_authorization_codes PK_fb91ab932cfbd694061501cc20f; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT "PK_fb91ab932cfbd694061501cc20f" PRIMARY KEY (code);


--
-- Name: binary_data PK_fc3691585b39408bb0551122af6; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.binary_data
    ADD CONSTRAINT "PK_fc3691585b39408bb0551122af6" PRIMARY KEY ("fileId");


--
-- Name: instance_ai_observation_locks PK_fc491dd378b9448655c3c683f85; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observation_locks
    ADD CONSTRAINT "PK_fc491dd378b9448655c3c683f85" PRIMARY KEY ("observationScopeId", "taskKind");


--
-- Name: role_scope PK_role_scope; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_scope
    ADD CONSTRAINT "PK_role_scope" PRIMARY KEY ("roleSlug", "scopeSlug");


--
-- Name: oauth_user_consents UQ_083721d99ce8db4033e2958ebb4; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_user_consents
    ADD CONSTRAINT "UQ_083721d99ce8db4033e2958ebb4" UNIQUE ("userId", "clientId");


--
-- Name: evaluation_config UQ_3c3c99a712e971835c52292e44c; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_config
    ADD CONSTRAINT "UQ_3c3c99a712e971835c52292e44c" UNIQUE ("workflowId", name);


--
-- Name: data_table_column UQ_8082ec4890f892f0bc77473a123; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table_column
    ADD CONSTRAINT "UQ_8082ec4890f892f0bc77473a123" UNIQUE ("dataTableId", name);


--
-- Name: data_table UQ_b23096ef747281ac944d28e8b0d; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table
    ADD CONSTRAINT "UQ_b23096ef747281ac944d28e8b0d" UNIQUE ("projectId", name);


--
-- Name: role_mapping_rule UQ_b33ac896ad3099fc8de36fdc1c4; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule
    ADD CONSTRAINT "UQ_b33ac896ad3099fc8de36fdc1c4" UNIQUE (type, "order");


--
-- Name: user_favorites UQ_cf6ae658ead9ffc124723413c65; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT "UQ_cf6ae658ead9ffc124723413c65" UNIQUE ("userId", "resourceId", "resourceType");


--
-- Name: user UQ_e12875dfb3b1d92d7d7c5377e2; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT "UQ_e12875dfb3b1d92d7d7c5377e2" UNIQUE (email);


--
-- Name: workflow_builder_session UQ_ec2aa73632932d485a1d5192ce1; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_builder_session
    ADD CONSTRAINT "UQ_ec2aa73632932d485a1d5192ce1" UNIQUE ("workflowId", "userId");


--
-- Name: auth_identity auth_identity_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.auth_identity
    ADD CONSTRAINT auth_identity_pkey PRIMARY KEY ("providerId", "providerType");


--
-- Name: auth_provider_sync_history auth_provider_sync_history_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.auth_provider_sync_history
    ADD CONSTRAINT auth_provider_sync_history_pkey PRIMARY KEY (id);


--
-- Name: credentials_entity credentials_entity_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.credentials_entity
    ADD CONSTRAINT credentials_entity_pkey PRIMARY KEY (id);


--
-- Name: event_destinations event_destinations_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.event_destinations
    ADD CONSTRAINT event_destinations_pkey PRIMARY KEY (id);


--
-- Name: execution_data execution_data_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_data
    ADD CONSTRAINT execution_data_pkey PRIMARY KEY ("executionId");


--
-- Name: execution_entity pk_e3e63bbf986767844bbe1166d4e; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_entity
    ADD CONSTRAINT pk_e3e63bbf986767844bbe1166d4e PRIMARY KEY (id);


--
-- Name: workflows_tags pk_workflows_tags; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflows_tags
    ADD CONSTRAINT pk_workflows_tags PRIMARY KEY ("workflowId", "tagId");


--
-- Name: tag_entity tag_entity_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.tag_entity
    ADD CONSTRAINT tag_entity_pkey PRIMARY KEY (id);


--
-- Name: variables variables_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.variables
    ADD CONSTRAINT variables_pkey PRIMARY KEY (id);


--
-- Name: workflow_entity workflow_entity_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_entity
    ADD CONSTRAINT workflow_entity_pkey PRIMARY KEY (id);


--
-- Name: workflow_statistics_delta workflow_statistics_delta_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_statistics_delta
    ADD CONSTRAINT workflow_statistics_delta_pkey PRIMARY KEY (id);


--
-- Name: workflow_statistics workflow_statistics_pkey; Type: CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_statistics
    ADD CONSTRAINT workflow_statistics_pkey PRIMARY KEY (id);


--
-- Name: bk_shipment bk_shipment_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.bk_shipment
    ADD CONSTRAINT bk_shipment_pkey PRIMARY KEY (gonderi_id);


--
-- Name: ga4_event ga4_event_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.ga4_event
    ADD CONSTRAINT ga4_event_pkey PRIMARY KEY (ga4_event_id);


--
-- Name: geo_response geo_response_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.geo_response
    ADD CONSTRAINT geo_response_pkey PRIMARY KEY (ham_id);


--
-- Name: idefix_urun idefix_urun_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.idefix_urun
    ADD CONSTRAINT idefix_urun_pkey PRIMARY KEY (barkod);


--
-- Name: ig_medya ig_medya_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.ig_medya
    ADD CONSTRAINT ig_medya_pkey PRIMARY KEY (medya_id);


--
-- Name: lead_osm lead_osm_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.lead_osm
    ADD CONSTRAINT lead_osm_pkey PRIMARY KEY (osm_tip, osm_id);


--
-- Name: meta_harcama meta_harcama_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.meta_harcama
    ADD CONSTRAINT meta_harcama_pkey PRIMARY KEY (gun, hesap_id, kampanya_id, kaynak);


--
-- Name: meta_hesap meta_hesap_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.meta_hesap
    ADD CONSTRAINT meta_hesap_pkey PRIMARY KEY (hesap_id);


--
-- Name: meta_kreatif meta_kreatif_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.meta_kreatif
    ADD CONSTRAINT meta_kreatif_pkey PRIMARY KEY (ad_id);


--
-- Name: meta_reklam meta_reklam_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.meta_reklam
    ADD CONSTRAINT meta_reklam_pkey PRIMARY KEY (hesap_id, gun, ad_id);


--
-- Name: osm_poi osm_poi_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.osm_poi
    ADD CONSTRAINT osm_poi_pkey PRIMARY KEY (osm_tur, osm_id);


--
-- Name: overture_poi overture_poi_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.overture_poi
    ADD CONSTRAINT overture_poi_pkey PRIMARY KEY (overture_id);


--
-- Name: trendyol_urun trendyol_urun_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.trendyol_urun
    ADD CONSTRAINT trendyol_urun_pkey PRIMARY KEY (barkod);


--
-- Name: wix_order_item wix_order_item_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.wix_order_item
    ADD CONSTRAINT wix_order_item_pkey PRIMARY KEY (siparis_id, sira);


--
-- Name: wix_order wix_order_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.wix_order
    ADD CONSTRAINT wix_order_pkey PRIMARY KEY (siparis_id);


--
-- Name: wix_urun wix_urun_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.wix_urun
    ADD CONSTRAINT wix_urun_pkey PRIMARY KEY (urun_id);


--
-- Name: yukleme_log yukleme_log_pkey; Type: CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.yukleme_log
    ADD CONSTRAINT yukleme_log_pkey PRIMARY KEY (id);


--
-- Name: memory_embedding_cosine_idx; Type: INDEX; Schema: ai_semantic; Owner: n8n
--

CREATE INDEX memory_embedding_cosine_idx ON ai_semantic.memory_embedding USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: acik_soru_durum_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX acik_soru_durum_idx ON core.acik_soru USING btree (durum, beklenen_bilgi_degeri);


--
-- Name: acik_soru_hedef_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX acik_soru_hedef_idx ON core.acik_soru USING btree (hedef, durum);


--
-- Name: ai_provider_attempt_task_idx; Type: INDEX; Schema: core; Owner: function_owner
--

CREATE INDEX ai_provider_attempt_task_idx ON core.ai_provider_attempt USING btree (task_id, attempt);


--
-- Name: ai_task_claim_idx; Type: INDEX; Schema: core; Owner: function_owner
--

CREATE INDEX ai_task_claim_idx ON core.ai_task USING btree (state, eligible_after, priority, task_id);


--
-- Name: ai_task_lease_idx; Type: INDEX; Schema: core; Owner: function_owner
--

CREATE INDEX ai_task_lease_idx ON core.ai_task USING btree (lease_until) WHERE (state = ANY (ARRAY['LEASED'::text, 'RUNNING'::text]));


--
-- Name: basin_bahsi_bulundu_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX basin_bahsi_bulundu_idx ON core.basin_bahsi USING btree (bulundu DESC);


--
-- Name: basin_bahsi_risk_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX basin_bahsi_risk_idx ON core.basin_bahsi USING btree (mevzuat_durumu) WHERE (mevzuat_durumu = 'RISKLI'::text);


--
-- Name: buyume_bulgu_anlik_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX buyume_bulgu_anlik_idx ON core.buyume_bulgu USING btree (anlik_id, modul);


--
-- Name: customer_email_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX customer_email_idx ON core.customer USING btree (email_normalized) WHERE (email_normalized IS NOT NULL);


--
-- Name: customer_identity_musteri_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX customer_identity_musteri_idx ON core.customer_identity USING btree (customer_id);


--
-- Name: customer_identity_normal_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX customer_identity_normal_idx ON core.customer_identity USING btree (kimlik_tipi, deger_normal) WHERE (deger_normal IS NOT NULL);


--
-- Name: customer_identity_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX customer_identity_tekil ON core.customer_identity USING btree (kaynak, kimlik_tipi, deger_ham, COALESCE(source_customer_id, ''::text));


--
-- Name: customer_phone_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX customer_phone_idx ON core.customer USING btree (phone_normalized) WHERE (phone_normalized IS NOT NULL);


--
-- Name: customer_status_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX customer_status_idx ON core.customer USING btree (identity_status);


--
-- Name: gonderi_notu_ref; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX gonderi_notu_ref ON core.gonderi_notu USING btree (siparis_ref);


--
-- Name: gonderi_notu_urun; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX gonderi_notu_urun ON core.gonderi_notu USING btree (urun_adi);


--
-- Name: hatirlatici_acik_zaman; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX hatirlatici_acik_zaman ON core.hatirlatici USING btree (zaman) WHERE (durum = 'ACIK'::text);


--
-- Name: ic_mesaj_durum_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ic_mesaj_durum_idx ON core.ic_mesaj USING btree (durum, zaman DESC);


--
-- Name: ic_mesaj_kime_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ic_mesaj_kime_idx ON core.ic_mesaj USING btree (kime, durum);


--
-- Name: identity_conflict_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX identity_conflict_tekil ON core.identity_conflict USING btree (kimlik_tipi, deger_normal) WHERE (durum = 'ACIK'::text);


--
-- Name: ig_plan_durum_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ig_plan_durum_idx ON core.ig_gonderi_plani USING btree (durum, uretim_at DESC);


--
-- Name: ig_plan_urun_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ig_plan_urun_idx ON core.ig_gonderi_plani USING btree (urun_slug);


--
-- Name: ix_geo_alias_brand; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_alias_brand ON core.geo_alias USING btree (canonical_brand_id);


--
-- Name: ix_geo_citation_source; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_citation_source ON core.geo_citation USING btree (source_id);


--
-- Name: ix_geo_kk_query; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_kk_query ON core.geo_karar_kapsami USING btree (query_id);


--
-- Name: ix_geo_mention_brand; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_mention_brand ON core.geo_mention USING btree (brand_id);


--
-- Name: ix_geo_obs_durum; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_obs_durum ON core.geo_observation USING btree (durum);


--
-- Name: ix_geo_obs_zaman; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX ix_geo_obs_zaman ON core.geo_observation USING btree (gozlem_at DESC);


--
-- Name: jarvis_action_registry_owner_status; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_action_registry_owner_status ON core.jarvis_action_registry USING btree (owner, status, created_at DESC);


--
-- Name: jarvis_cari_account_entries; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_cari_account_entries ON core.jarvis_cari_entry USING btree (owner, account_id, document_date, created_at);


--
-- Name: jarvis_cari_document_lookup; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_cari_document_lookup ON core.jarvis_cari_document USING btree (owner, account_id, created_at DESC);


--
-- Name: jarvis_cari_draft_open; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_cari_draft_open ON core.jarvis_cari_draft USING btree (owner, account_id, created_at DESC) WHERE (status = 'draft'::text);


--
-- Name: jarvis_cari_entry_applies_to; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_cari_entry_applies_to ON core.jarvis_cari_entry USING btree (owner, account_id, ((payload ->> 'applies_to'::text))) WHERE (payload ? 'applies_to'::text);


--
-- Name: jarvis_cari_invoice_hash; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX jarvis_cari_invoice_hash ON core.jarvis_cari_document USING btree (owner, sha256) WHERE (source = 'invoice'::text);


--
-- Name: jarvis_cari_owner_tax_id; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX jarvis_cari_owner_tax_id ON core.jarvis_cari_account USING btree (owner, tax_id) WHERE (tax_id <> ''::text);


--
-- Name: jarvis_cari_source_current; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_cari_source_current ON core.jarvis_cari_source_event USING btree (owner, source, store_id, object_id, source_updated_at DESC);


--
-- Name: jarvis_expense_gmail_source; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX jarvis_expense_gmail_source ON core.jarvis_expense_document USING btree (owner, source_message_id, source_attachment_id) WHERE (origin = 'gmail'::text);


--
-- Name: jarvis_expense_month; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_expense_month ON core.jarvis_expense_document USING btree (owner, created_at DESC);


--
-- Name: jarvis_expense_owner_sha; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX jarvis_expense_owner_sha ON core.jarvis_expense_document USING btree (owner, sha256);


--
-- Name: jarvis_personal_action_owner_recent; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX jarvis_personal_action_owner_recent ON core.jarvis_personal_action USING btree (owner, created_at DESC);


--
-- Name: kademe_denemesi_ts_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kademe_denemesi_ts_idx ON core.kademe_denemesi USING btree (ts DESC);


--
-- Name: kademe_denemesi_uc_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kademe_denemesi_uc_idx ON core.kademe_denemesi USING btree (uc, sonuc);


--
-- Name: karar_acik_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX karar_acik_tekil ON core.karar USING btree (idempotency_key) WHERE ((durum = ANY (ARRAY['PROPOSED'::text, 'DEFERRED'::text])) AND (NOT fixture));


--
-- Name: karar_ai_idempotency_key_uniq; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX karar_ai_idempotency_key_uniq ON core.karar USING btree (idempotency_key) WHERE ((idempotency_key ~~ 'ai:%'::text) AND (NOT fixture));


--
-- Name: karar_aksiyon_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX karar_aksiyon_idx ON core.karar_aksiyon USING btree (karar_id);


--
-- Name: karar_durum_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX karar_durum_idx ON core.karar USING btree (durum, fixture);


--
-- Name: karar_rt_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX karar_rt_idx ON core.karar_red_team USING btree (karar_id, sonuc);


--
-- Name: kargo_karar_tek_acik; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX kargo_karar_tek_acik ON core.kargo_karar USING btree (siparis_id) WHERE (karar = ANY (ARRAY['ISTENDI'::text, 'ONAYLANDI'::text]));


--
-- Name: kargo_karar_zaman; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kargo_karar_zaman ON core.kargo_karar USING btree (verildi DESC);


--
-- Name: katalog_not_hedef_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX katalog_not_hedef_idx ON core.katalog_not USING btree (hedef_anahtari, girildi DESC);


--
-- Name: katalog_not_urun_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX katalog_not_urun_idx ON core.katalog_not USING btree (urun_slug, girildi DESC);


--
-- Name: kreatif_itiraz_acik; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kreatif_itiraz_acik ON core.kreatif_itiraz USING btree (muhatap) WHERE (durum = ANY (ARRAY['ACIK'::text, 'TEKRAR_ACILDI'::text]));


--
-- Name: kreatif_itiraz_parti; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kreatif_itiraz_parti ON core.kreatif_itiraz USING btree (parti);


--
-- Name: kreatif_konsept_plan_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX kreatif_konsept_plan_idx ON core.kreatif_konsept USING btree (plan_id, secildi);


--
-- Name: kreatif_konsept_tek_secim; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX kreatif_konsept_tek_secim ON core.kreatif_konsept USING btree (plan_id) WHERE secildi;


--
-- Name: lead_saklama_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX lead_saklama_idx ON core.lead USING btree (saklama_sonu);


--
-- Name: lead_segment_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX lead_segment_idx ON core.lead USING btree (il, segment);


--
-- Name: lead_temas_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX lead_temas_idx ON core.lead USING btree (temas_edilebilir) WHERE temas_edilebilir;


--
-- Name: maliyet_bileseni_acik_tek; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX maliyet_bileseni_acik_tek ON core.maliyet_bileseni USING btree (bilesen) WHERE (gecerli_bitis IS NULL);


--
-- Name: medya_istegi_acik; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX medya_istegi_acik ON core.medya_istegi USING btree (durum, olusturuldu DESC) WHERE (durum = ANY (ARRAY['GONDERILIYOR'::text, 'queued'::text, 'in_progress'::text, 'BEKLEME_ASILDI'::text]));


--
-- Name: medya_istegi_imza_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX medya_istegi_imza_tekil ON core.medya_istegi USING btree (istek_imzasi) WHERE (durum <> ALL (ARRAY['REDDEDILDI'::text, 'canceled'::text]));


--
-- Name: medya_istegi_parti; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX medya_istegi_parti ON core.medya_istegi USING btree (parti, olusturuldu DESC);


--
-- Name: medya_istegi_sahip; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX medya_istegi_sahip ON core.medya_istegi USING btree (talep_eden, olusturuldu DESC);


--
-- Name: pazar_bulgu_kod_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX pazar_bulgu_kod_idx ON core.pazar_bulgu USING btree (kod, olusturma DESC);


--
-- Name: pazaryeri_siparis_tekil_paketsiz; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX pazaryeri_siparis_tekil_paketsiz ON core.pazaryeri_siparis USING btree (kanal, siparis_no) WHERE (paket_no IS NULL);


--
-- Name: pazaryeri_siparis_zaman; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX pazaryeri_siparis_zaman ON core.pazaryeri_siparis USING btree (ilk_gorulme DESC);


--
-- Name: saha_elle_konum_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_elle_konum_idx ON core.saha_elle_nokta USING btree (enlem, boylam);


--
-- Name: saha_foto_ziyaret_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_foto_ziyaret_idx ON core.saha_ziyaret_foto USING btree (ziyaret_id);


--
-- Name: saha_konum_kullanici_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_konum_kullanici_idx ON core.saha_konum USING btree (kullanici, ts DESC);


--
-- Name: saha_konum_ts_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_konum_ts_idx ON core.saha_konum USING btree (ts);


--
-- Name: saha_ziyaret_anahtar_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_ziyaret_anahtar_idx ON core.saha_ziyaret USING btree (hedef_anahtari, ziyaret_at DESC);


--
-- Name: saha_ziyaret_hedef_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX saha_ziyaret_hedef_idx ON core.saha_ziyaret USING btree (osm_tur, osm_id, ziyaret_at DESC);


--
-- Name: tarayici_isi_bekleyen_ix; Type: INDEX; Schema: core; Owner: function_owner
--

CREATE INDEX tarayici_isi_bekleyen_ix ON core.tarayici_isi USING btree (durum, is_id) WHERE (durum = ANY (ARRAY['BEKLIYOR'::text, 'CALISIYOR'::text]));


--
-- Name: tarayici_isi_sunulacak_ix; Type: INDEX; Schema: core; Owner: function_owner
--

CREATE INDEX tarayici_isi_sunulacak_ix ON core.tarayici_isi USING btree (durum, is_id) WHERE (durum = ANY (ARRAY['BITTI'::text, 'HATA'::text, 'INSAN_GEREKLI'::text]));


--
-- Name: tasarim_isi_onaysiz; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX tasarim_isi_onaysiz ON core.tasarim_isi USING btree (uretildi DESC) WHERE (onay IS NULL);


--
-- Name: tasarim_isi_zaman; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX tasarim_isi_zaman ON core.tasarim_isi USING btree (uretildi DESC);


--
-- Name: tasarim_sablon_kodu_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX tasarim_sablon_kodu_tekil ON core.tasarim_sablon USING btree (sablon_kodu) WHERE (sablon_kodu IS NOT NULL);


--
-- Name: tasarim_sablon_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX tasarim_sablon_tekil ON core.tasarim_sablon USING btree (is_turu, canva_id);


--
-- Name: urun_maliyet_aktif_idx; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX urun_maliyet_aktif_idx ON core.urun_maliyet USING btree (urun_id) WHERE (gecerli_bitis IS NULL);


--
-- Name: urun_platform_fiyat_acik; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX urun_platform_fiyat_acik ON core.urun_platform_fiyat USING btree (urun_id, platform_kod) WHERE (gecerli_bitis IS NULL);


--
-- Name: urun_platform_fiyat_toplu; Type: INDEX; Schema: core; Owner: n8n
--

CREATE INDEX urun_platform_fiyat_toplu ON core.urun_platform_fiyat USING btree (toplu_islem_id) WHERE (toplu_islem_id IS NOT NULL);


--
-- Name: ux_geo_alias_normal; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_alias_normal ON core.geo_alias USING btree (normalized_alias) WHERE active;


--
-- Name: ux_geo_brand_ad; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_brand_ad ON core.geo_brand USING btree (lower(canonical_name));


--
-- Name: ux_geo_citation_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_citation_tekil ON core.geo_citation USING btree (observation_id, url_hash);


--
-- Name: ux_geo_conflict_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_conflict_tekil ON core.geo_entity_conflict USING btree (urun, alan, gozlenen, COALESCE(kaynak_url, ''::text));


--
-- Name: ux_geo_gap_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_gap_tekil ON core.geo_gap USING btree (tip, COALESCE(urun, ''::text), COALESCE(query_id, (0)::bigint), COALESCE(source_id, (0)::bigint));


--
-- Name: ux_geo_kk_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_kk_tekil ON core.geo_karar_kapsami USING btree (karar_id, COALESCE(query_id, (0)::bigint), COALESCE(kume_anahtari, ''::text), COALESCE(urun, ''::text));


--
-- Name: ux_geo_mention_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_mention_tekil ON core.geo_mention USING btree (observation_id, brand_id, COALESCE(urun, ''::text), tip);


--
-- Name: ux_geo_obs_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_obs_tekil ON core.geo_observation USING btree (query_id, yuzey, language, country, gozlem_at);


--
-- Name: ux_geo_query_tekil; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_query_tekil ON core.geo_query USING btree (lower(sorgu_metni), language, country, set_surum);


--
-- Name: ux_geo_source_domain; Type: INDEX; Schema: core; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_source_domain ON core.geo_source USING btree (domain);


--
-- Name: konusma_devir_bekleyen; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX konusma_devir_bekleyen ON lcarlie.konusma USING btree (devir_durumu, son_mesaj DESC);


--
-- Name: konusma_kanal_zaman; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX konusma_kanal_zaman ON lcarlie.konusma USING btree (kanal, son_mesaj DESC);


--
-- Name: konusma_musteri; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX konusma_musteri ON lcarlie.konusma USING btree (musteri_ref);


--
-- Name: konusma_sonuc; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX konusma_sonuc ON lcarlie.konusma USING btree (sonuc, son_mesaj DESC);


--
-- Name: mesaj_gonderen; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX mesaj_gonderen ON lcarlie.mesaj USING btree (gonderen, zaman DESC);


--
-- Name: mesaj_konusma_zaman; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX mesaj_konusma_zaman ON lcarlie.mesaj USING btree (konusma_id, zaman);


--
-- Name: mesaj_metin_fts; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX mesaj_metin_fts ON lcarlie.mesaj USING gin (to_tsvector('simple'::regconfig, metin));


--
-- Name: mesaj_mevzuat; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX mesaj_mevzuat ON lcarlie.mesaj USING btree (mevzuat) WHERE (mevzuat IS NOT NULL);


--
-- Name: satis_cevap_kohort; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX satis_cevap_kohort ON lcarlie.satis_cevap USING btree (yaklasim_id, urun, soru_tipi) WHERE gonderildi;


--
-- Name: satis_cevap_konusma; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE INDEX satis_cevap_konusma ON lcarlie.satis_cevap USING btree (konusma_id);


--
-- Name: satis_yaklasim_tek_onayli; Type: INDEX; Schema: lcarlie; Owner: n8n
--

CREATE UNIQUE INDEX satis_yaklasim_tek_onayli ON lcarlie.satis_yaklasim USING btree (COALESCE(urun, ''::text), COALESCE(soru_tipi, ''::text)) WHERE (durum = 'ONAYLI'::text);


--
-- Name: saha_kaynak_anahtar_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE UNIQUE INDEX saha_kaynak_anahtar_idx ON mart.saha_kaynak USING btree (hedef_anahtari);


--
-- Name: saha_kaynak_ara_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_kaynak_ara_idx ON mart.saha_kaynak USING btree (ad_ara);


--
-- Name: saha_kaynak_brans_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_kaynak_brans_idx ON mart.saha_kaynak USING btree (brans);


--
-- Name: saha_kaynak_grup_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE UNIQUE INDEX saha_kaynak_grup_idx ON mart.saha_kaynak USING btree (grup);


--
-- Name: saha_kaynak_ilce_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_kaynak_ilce_idx ON mart.saha_kaynak USING btree (ilce);


--
-- Name: saha_kaynak_konum_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_kaynak_konum_idx ON mart.saha_kaynak USING btree (enlem, boylam);


--
-- Name: saha_kaynak_tur_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_kaynak_tur_idx ON mart.saha_kaynak USING btree (tur);


--
-- Name: saha_tum_anahtar_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE UNIQUE INDEX saha_tum_anahtar_idx ON mart.saha_tum USING btree (hedef_anahtari);


--
-- Name: saha_tum_grup_idx; Type: INDEX; Schema: mart; Owner: n8n
--

CREATE INDEX saha_tum_grup_idx ON mart.saha_tum USING btree (grup);


--
-- Name: hatira_hnsw_idx; Type: INDEX; Schema: mem0; Owner: mem0_writer
--

CREATE INDEX hatira_hnsw_idx ON mem0.hatira USING hnsw (vector public.vector_cosine_ops);


--
-- Name: hatira_text_lemmatized_idx; Type: INDEX; Schema: mem0; Owner: mem0_writer
--

CREATE INDEX hatira_text_lemmatized_idx ON mem0.hatira USING gin (to_tsvector('simple'::regconfig, (payload ->> 'text_lemmatized'::text)));


--
-- Name: IDX_02751202c9a2ad75f2d8e14f5e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_02751202c9a2ad75f2d8e14f5e" ON public.instance_ai_iteration_logs USING btree ("threadId", "taskKey", "createdAt");


--
-- Name: IDX_0468a9dc35597314e641d4722a; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_0468a9dc35597314e641d4722a" ON public.agent_execution_threads USING btree ("agentId");


--
-- Name: IDX_070b5de842ece9ccdda0d9738b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_070b5de842ece9ccdda0d9738b" ON public.workflow_publish_history USING btree ("workflowId", "versionId");


--
-- Name: IDX_07cb1e4a302629c5fa5d74d2bb; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_07cb1e4a302629c5fa5d74d2bb" ON public.agents_observations USING btree ("agentId", "observationScopeId", status);


--
-- Name: IDX_0babdf6e3b897a86fe4678355e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_0babdf6e3b897a86fe4678355e" ON public.instance_ai_pending_confirmations USING btree ("checkpointKey");


--
-- Name: IDX_0d5db648188d338df7fb2a8064; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_0d5db648188d338df7fb2a8064" ON public.instance_ai_observations USING btree ("observationScopeId", status, "createdAt", id);


--
-- Name: IDX_0e2f8bf92a7a9c88b89670f701; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_0e2f8bf92a7a9c88b89670f701" ON public.agent_execution_threads USING btree ("projectId");


--
-- Name: IDX_0edf1226b77ddc525eae493807; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_0edf1226b77ddc525eae493807" ON public.agents_memory_entries USING btree ("supersededBy");


--
-- Name: IDX_127ee1078ffa952bb37b511efa; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_127ee1078ffa952bb37b511efa" ON public.agents_observations USING btree ("supersededBy");


--
-- Name: IDX_1443a75e59adbfb796071d6639; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_1443a75e59adbfb796071d6639" ON public.agents_memory_entries USING btree ("resourceId");


--
-- Name: IDX_14f68deffaf858465715995508; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_14f68deffaf858465715995508" ON public.folder USING btree ("projectId", id);


--
-- Name: IDX_16db3adb7b19df1ee55ff06b27; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_16db3adb7b19df1ee55ff06b27" ON public.instance_ai_mcp_registry_connections USING btree ("userId", "serverSlug", "credentialId");


--
-- Name: IDX_1d11050a381548c42c32cc25c4; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_1d11050a381548c42c32cc25c4" ON public.user_favorites USING btree ("resourceType", "resourceId");


--
-- Name: IDX_1d8ab99d5861c9388d2dc1cf73; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_1d8ab99d5861c9388d2dc1cf73" ON public.insights_metadata USING btree ("workflowId");


--
-- Name: IDX_1dd5c393ad0517be3c31a7af83; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_1dd5c393ad0517be3c31a7af83" ON public.user_favorites USING btree ("userId");


--
-- Name: IDX_1e31657f5fe46816c34be7c1b4; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_1e31657f5fe46816c34be7c1b4" ON public.workflow_history USING btree ("workflowId");


--
-- Name: IDX_1eeb64cb9d66a927988de759e6; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_1eeb64cb9d66a927988de759e6" ON public.instance_ai_messages USING btree ("threadId");


--
-- Name: IDX_1ef35bac35d20bdae979d917a3; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_1ef35bac35d20bdae979d917a3" ON public.user_api_keys USING btree ("apiKey");


--
-- Name: IDX_2b23f3f24a70bebb990203b011; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_2b23f3f24a70bebb990203b011" ON public.instance_ai_checkpoints USING btree ("threadId");


--
-- Name: IDX_2c579b1068b66359de1b4d2de5; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_2c579b1068b66359de1b4d2de5" ON public.promotion_connection_project USING btree ("connectionId");


--
-- Name: IDX_32cdd799675715fb1d2a8683e9; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_32cdd799675715fb1d2a8683e9" ON public.instance_ai_events USING btree ("threadId", "runId");


--
-- Name: IDX_35a78869286c65d9330d02b88f; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_35a78869286c65d9330d02b88f" ON public.role_mapping_rule_project USING btree ("projectId");


--
-- Name: IDX_39b07732e819fb561d74c38763; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_39b07732e819fb561d74c38763" ON public.ai_builder_temporary_workflow USING btree ("threadId");


--
-- Name: IDX_39ca447735d378e365f4227abf; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_39ca447735d378e365f4227abf" ON public.agent_eval_run USING btree ("datasetId");


--
-- Name: IDX_401b94abf83d1ac7a841f31330; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_401b94abf83d1ac7a841f31330" ON public.instance_ai_thread_grants USING btree ("userId");


--
-- Name: IDX_40a2d1248a6d984f442de2fac1; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_40a2d1248a6d984f442de2fac1" ON public.agent_eval_result USING btree ("runId");


--
-- Name: IDX_451d387a182fa8dd8002dfc3a7; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_451d387a182fa8dd8002dfc3a7" ON public.agents_memory_entry_sources USING btree ("threadId");


--
-- Name: IDX_45dafc48fe2ce95eac30fc8ffd; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_45dafc48fe2ce95eac30fc8ffd" ON public.agent_files USING btree ("agentId", "createdAt");


--
-- Name: IDX_4c72ebdb265d1775bf61147af0; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_4c72ebdb265d1775bf61147af0" ON public.chat_hub_tools USING btree ("ownerId", name);


--
-- Name: IDX_4cfd8a70ebb0a5b0cf047dca3c; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_4cfd8a70ebb0a5b0cf047dca3c" ON public.agents_observations USING btree ("observationScopeId");


--
-- Name: IDX_4ea340a1847ad0e40a0b0360fe; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_4ea340a1847ad0e40a0b0360fe" ON public.ai_preference USING btree ("projectId");


--
-- Name: IDX_501e2d1701a10e24fb69ab5fc5; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_501e2d1701a10e24fb69ab5fc5" ON public.agents_observations USING btree ("parentId");


--
-- Name: IDX_5123f71435736664d2676084a8; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_5123f71435736664d2676084a8" ON public.agents_memory_entry_candidates USING btree ("resourceId");


--
-- Name: IDX_54fa1b94f34a409beafae567a4; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_54fa1b94f34a409beafae567a4" ON public.agents_threads USING btree ("resourceId");


--
-- Name: IDX_56900edc3cfd16612e2ef2c6a8; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_56900edc3cfd16612e2ef2c6a8" ON public.binary_data USING btree ("sourceType", "sourceId");


--
-- Name: IDX_5e31c210f896d539964bf99fe3; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_5e31c210f896d539964bf99fe3" ON public.agent_checkpoints USING btree ("agentId");


--
-- Name: IDX_5ec8e8c8d3539f3696cf73b43b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_5ec8e8c8d3539f3696cf73b43b" ON public.credential_dependency USING btree ("credentialId");


--
-- Name: IDX_5f0643f6717905a05164090dde; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_5f0643f6717905a05164090dde" ON public.project_relation USING btree ("userId");


--
-- Name: IDX_60b6a84299eeb3f671dfec7693; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_60b6a84299eeb3f671dfec7693" ON public.insights_by_period USING btree ("periodStart", type, "periodUnit", "metaId");


--
-- Name: IDX_61448d56d61802b5dfde5cdb00; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_61448d56d61802b5dfde5cdb00" ON public.project_relation USING btree ("projectId");


--
-- Name: IDX_62476b94b56d9dc7ed9ed75d3d; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_62476b94b56d9dc7ed9ed75d3d" ON public.dynamic_credential_entry USING btree (subject_id);


--
-- Name: IDX_63d3c3a68b9cebf05f967f0b1c; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_63d3c3a68b9cebf05f967f0b1c" ON public.agent_execution USING btree ("threadId", "createdAt");


--
-- Name: IDX_63d7bbae72c767cf162d459fcc; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_63d7bbae72c767cf162d459fcc" ON public.user_api_keys USING btree ("userId", label);


--
-- Name: IDX_674705e4c8a3d3eb0736f8e8ee; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_674705e4c8a3d3eb0736f8e8ee" ON public.type_availability_policy_attachment USING btree ("policyId");


--
-- Name: IDX_6806b43c8a0d11460f0c2552eb; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_6806b43c8a0d11460f0c2552eb" ON public.agent_chat_attachments USING btree ("projectId", "threadId");


--
-- Name: IDX_6b55089892e447c2f82e5ec60e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_6b55089892e447c2f82e5ec60e" ON public.agents_observation_locks USING btree ("observationScopeId");


--
-- Name: IDX_6dc22e132cf1a34e5bca672b99; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_6dc22e132cf1a34e5bca672b99" ON public.agents_memory_entry_candidates USING btree ("agentId", "resourceId", status, "createdAt", id);


--
-- Name: IDX_6edec973a6450990977bb854c3; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_6edec973a6450990977bb854c3" ON public.dynamic_credential_user_entry USING btree ("resolverId");


--
-- Name: IDX_768189b506cc26c4fe878b87cb; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_768189b506cc26c4fe878b87cb" ON public.instance_ai_checkpoints USING btree ("runId");


--
-- Name: IDX_76e212c6867fbaa06bf0decd6f; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_76e212c6867fbaa06bf0decd6f" ON public.instance_ai_messages USING btree ("resourceId");


--
-- Name: IDX_7e9556f25f995653997be3322b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_7e9556f25f995653997be3322b" ON public.agent_chat_attachments USING btree ("agentId", "threadId");


--
-- Name: IDX_87aa187d27ea67eafd16490515; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_87aa187d27ea67eafd16490515" ON public.agents_observation_cursors USING btree ("observationScopeId");


--
-- Name: IDX_87cd5a8da20304b089ea2f83fe; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_87cd5a8da20304b089ea2f83fe" ON public.agent_history USING btree ("agentId");


--
-- Name: IDX_8e4b4774db42f1e6dda3452b2a; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_8e4b4774db42f1e6dda3452b2a" ON public.test_case_execution USING btree ("testRunId");


--
-- Name: IDX_91ee85fa9619dd6776725e117b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_91ee85fa9619dd6776725e117b" ON public.credential_dependency USING btree ("dependencyType", "dependencyId");


--
-- Name: IDX_92f13cb6bc694227e069447f7b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_92f13cb6bc694227e069447f7b" ON public.instance_ai_observational_memory USING btree ("lookupKey");


--
-- Name: IDX_93d62baabe9858816b5adafb44; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_93d62baabe9858816b5adafb44" ON public.agent_background_job USING btree ("parentThreadId", status);


--
-- Name: IDX_9594c0983cfee1c8ff49b05848; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9594c0983cfee1c8ff49b05848" ON public.agents_memory_entry_locks USING btree ("resourceId");


--
-- Name: IDX_9626b8dc1bee96a86a3ee09d73; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9626b8dc1bee96a86a3ee09d73" ON public.instance_credential_assignment USING btree ("credentialId");


--
-- Name: IDX_97f863fa83c4786f1956508496; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_97f863fa83c4786f1956508496" ON public.execution_annotations USING btree ("executionId");


--
-- Name: IDX_9917feaa6ed5705046432b117f; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9917feaa6ed5705046432b117f" ON public.promotion_connection USING btree ("providerId");


--
-- Name: IDX_9c9ee9df586e60bb723234e499; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9c9ee9df586e60bb723234e499" ON public.dynamic_credential_resolver USING btree (type);


--
-- Name: IDX_9cadae6591c64498f1b58a2cef; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9cadae6591c64498f1b58a2cef" ON public.agent_eval_rating USING btree ("resultId");


--
-- Name: IDX_9d3a6fd750f7746de453cf4d5e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_9d3a6fd750f7746de453cf4d5e" ON public.agent_eval_dataset USING btree ("agentId");


--
-- Name: IDX_UniqueRoleDisplayName; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_UniqueRoleDisplayName" ON public.role USING btree ("displayName");


--
-- Name: IDX_a03e04e94bea8439dd166d4b52; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_a03e04e94bea8439dd166d4b52" ON public.agents_memory_entries USING btree ("agentId", "resourceId", "contentHash");


--
-- Name: IDX_a2694df196a66064edbdbe38b9; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a2694df196a66064edbdbe38b9" ON public.agent_workflow_dependency USING btree ("workflowId");


--
-- Name: IDX_a30d560207c4071d98aa03c179; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a30d560207c4071d98aa03c179" ON public.agents USING btree ("projectId");


--
-- Name: IDX_a353ac251315ef0af6ad3c9f0a; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_a353ac251315ef0af6ad3c9f0a" ON public.agents_memory_entry_sources USING btree ("memoryEntryId", "observationId", "evidenceHash");


--
-- Name: IDX_a3697779b366e131b2bbdae297; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a3697779b366e131b2bbdae297" ON public.execution_annotation_tags USING btree ("tagId");


--
-- Name: IDX_a36dc616fabc3f736bb82410a2; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a36dc616fabc3f736bb82410a2" ON public.dynamic_credential_user_entry USING btree ("userId");


--
-- Name: IDX_a371ee6b8e0ebb5635f8baa46d; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a371ee6b8e0ebb5635f8baa46d" ON public.instance_ai_workflow_snapshots USING btree ("workflowName", status);


--
-- Name: IDX_a48ce930c3bc7604894b8f0eaa; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a48ce930c3bc7604894b8f0eaa" ON public.evaluation_collection USING btree ("workflowId");


--
-- Name: IDX_a4ff2d9b9628ea988fa9e7d0bf; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a4ff2d9b9628ea988fa9e7d0bf" ON public.workflow_dependency USING btree ("workflowId");


--
-- Name: IDX_a680ac96aae02dc887bbaac512; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_a680ac96aae02dc887bbaac512" ON public.instance_ai_observational_memory USING btree (scope, "threadId", "resourceId");


--
-- Name: IDX_a7c67724df9ef3d12f6da773c1; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a7c67724df9ef3d12f6da773c1" ON public.agent_channel_status USING btree ("expiresAt");


--
-- Name: IDX_a80e0ee839a2f10ba4b86e1999; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_a80e0ee839a2f10ba4b86e1999" ON public.instance_ai_observations USING btree ("supersededBy");


--
-- Name: IDX_ac7ada75df7cc8ced228921d5a; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_ac7ada75df7cc8ced228921d5a" ON public.agents_memory_entry_candidates USING btree ("threadId");


--
-- Name: IDX_activity_event_project; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_activity_event_project" ON public.activity_event USING btree ("projectId", id);


--
-- Name: IDX_activity_event_user; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_activity_event_user" ON public.activity_event USING btree ("userId", id);


--
-- Name: IDX_ae51b54c4bb430cf92f48b623f; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_ae51b54c4bb430cf92f48b623f" ON public.annotation_tag_entity USING btree (name);


--
-- Name: IDX_aff2807b31eccbafe59d0474f0; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_aff2807b31eccbafe59d0474f0" ON public.agents_memory_entries USING btree ("agentId", "resourceId", status, "createdAt", id);


--
-- Name: IDX_agent_background_job_childExecutionId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_agent_background_job_childExecutionId" ON public.agent_background_job USING btree ("childExecutionId") WHERE ("childExecutionId" IS NOT NULL);


--
-- Name: IDX_agent_background_job_parentThreadId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agent_background_job_parentThreadId" ON public.agent_background_job USING btree ("parentThreadId") WHERE (("settledAt" IS NOT NULL) AND ("notifiedAt" IS NULL));


--
-- Name: IDX_agent_background_job_timeoutAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agent_background_job_timeoutAt" ON public.agent_background_job USING btree ("timeoutAt") WHERE ((status)::text = 'running'::text);


--
-- Name: IDX_agent_execution_status; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agent_execution_status" ON public.agent_execution USING btree (status) WHERE ((status)::text = 'running'::text);


--
-- Name: IDX_agent_execution_threads_taskVersionId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agent_execution_threads_taskVersionId" ON public.agent_execution_threads USING btree ("taskVersionId");


--
-- Name: IDX_agent_files_agentId_binaryDataId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_agent_files_agentId_binaryDataId" ON public.agent_files USING btree ("agentId", "binaryDataId");


--
-- Name: IDX_agent_files_agentId_fileName; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_agent_files_agentId_fileName" ON public.agent_files USING btree ("agentId", "fileName");


--
-- Name: IDX_agents_mem_src_candidate_unique; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_agents_mem_src_candidate_unique" ON public.agents_memory_entry_sources USING btree ("memoryEntryId", "candidateId", "evidenceHash") WHERE ("candidateId" IS NOT NULL);


--
-- Name: IDX_agents_memory_entry_sources_candidateId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agents_memory_entry_sources_candidateId" ON public.agents_memory_entry_sources USING btree ("candidateId");


--
-- Name: IDX_agents_messages_resourceId_threadId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agents_messages_resourceId_threadId" ON public.agents_messages USING btree ("resourceId", "threadId");


--
-- Name: IDX_agents_messages_threadId_createdAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agents_messages_threadId_createdAt" ON public.agents_messages USING btree ("threadId", "createdAt");


--
-- Name: IDX_agents_projectId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_agents_projectId" ON public.agents USING btree ("projectId");


--
-- Name: IDX_ba67ee8dc311830a2eea89b6e9; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_ba67ee8dc311830a2eea89b6e9" ON public.instance_ai_pending_confirmations USING btree ("threadId");


--
-- Name: IDX_bb66e404c35996b0d694617750; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_bb66e404c35996b0d694617750" ON public.role_mapping_rule USING btree (role);


--
-- Name: IDX_be9d0eca0b19fb93d4eb74b327; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_be9d0eca0b19fb93d4eb74b327" ON public.instance_ai_checkpoints USING btree ("resourceId");


--
-- Name: IDX_c1519757391996eb06064f0e7c; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_c1519757391996eb06064f0e7c" ON public.execution_annotation_tags USING btree ("annotationId");


--
-- Name: IDX_c75ec632fe0b5b1905edb9cd7f; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_c75ec632fe0b5b1905edb9cd7f" ON public.agent_channel_status USING btree ("hostId");


--
-- Name: IDX_cb7c15d22fd068a0806aa57fc0; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_cb7c15d22fd068a0806aa57fc0" ON public.agents_memory_entry_sources USING btree ("observationId");


--
-- Name: IDX_cec8eea3bf49551482ccb4933e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_cec8eea3bf49551482ccb4933e" ON public.execution_metadata USING btree ("executionId", key);


--
-- Name: IDX_chat_hub_messages_sessionId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_chat_hub_messages_sessionId" ON public.chat_hub_messages USING btree ("sessionId");


--
-- Name: IDX_chat_hub_sessions_owner_lastmsg_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_chat_hub_sessions_owner_lastmsg_id" ON public.chat_hub_sessions USING btree ("ownerId", "lastMessageAt" DESC, id);


--
-- Name: IDX_credential_dependency_credentialId_dependencyType_dependenc; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_credential_dependency_credentialId_dependencyType_dependenc" ON public.credential_dependency USING btree ("credentialId", "dependencyType", "dependencyId");


--
-- Name: IDX_credentials_entity_is_global; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_credentials_entity_is_global" ON public.credentials_entity USING btree (id) WHERE ("isGlobal" = true);


--
-- Name: IDX_d46c6f00730c2ef8bcb6ee24b6; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_d46c6f00730c2ef8bcb6ee24b6" ON public.agent_background_job USING btree ("parentAgentId");


--
-- Name: IDX_d61a12235d268a49af6a3c09c1; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_d61a12235d268a49af6a3c09c1" ON public.dynamic_credential_entry USING btree (resolver_id);


--
-- Name: IDX_d634a0c93fd7de68a87eab951b; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_d634a0c93fd7de68a87eab951b" ON public.evaluation_collection USING btree ("evaluationConfigId");


--
-- Name: IDX_d6870d3b6e4c185d33926f423c; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_d6870d3b6e4c185d33926f423c" ON public.test_run USING btree ("workflowId");


--
-- Name: IDX_d7a4aba7440449865e2b924377; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_d7a4aba7440449865e2b924377" ON public.instance_ai_pending_confirmations USING btree ("expiresAt");


--
-- Name: IDX_daef2195a4a846eb70eed15e03; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_daef2195a4a846eb70eed15e03" ON public.instance_ai_observations USING btree ("parentId");


--
-- Name: IDX_deployment_key_data_encryption_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_data_encryption_active" ON public.deployment_key USING btree (type) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'data_encryption'::text));


--
-- Name: IDX_deployment_key_instance_id_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_instance_id_active" ON public.deployment_key USING btree (type) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'instance.id'::text));


--
-- Name: IDX_deployment_key_jwe_private_key_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_jwe_private_key_active" ON public.deployment_key USING btree (type, algorithm) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'jwe.private-key'::text));


--
-- Name: IDX_deployment_key_signing_binary_data_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_signing_binary_data_active" ON public.deployment_key USING btree (type) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'signing.binary_data'::text));


--
-- Name: IDX_deployment_key_signing_hmac_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_signing_hmac_active" ON public.deployment_key USING btree (type) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'signing.hmac'::text));


--
-- Name: IDX_deployment_key_signing_jwt_active; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_deployment_key_signing_jwt_active" ON public.deployment_key USING btree (type) WHERE (((status)::text = 'active'::text) AND ((type)::text = 'signing.jwt'::text));


--
-- Name: IDX_df5fd25c8bbfd2b042602600d8; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_df5fd25c8bbfd2b042602600d8" ON public.instance_ai_pending_confirmations USING btree ("userId");


--
-- Name: IDX_e3e49861a5452db63b036a2561; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_e3e49861a5452db63b036a2561" ON public.agents_memory_entry_candidates USING btree ("agentId", "runId", "toolCallId");


--
-- Name: IDX_e43e630272995a93dfeb94ab3e; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_e43e630272995a93dfeb94ab3e" ON public.agent_background_job USING btree ("settledAt");


--
-- Name: IDX_e48a201071ab85d9d09119d640; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_e48a201071ab85d9d09119d640" ON public.workflow_dependency USING btree ("dependencyKey");


--
-- Name: IDX_e7fe1cfda990c14a445937d0b9; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_e7fe1cfda990c14a445937d0b9" ON public.workflow_dependency USING btree ("dependencyType");


--
-- Name: IDX_e9059770c01bfda6062d78d9f8; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_e9059770c01bfda6062d78d9f8" ON public.ai_preference USING btree ("userId");


--
-- Name: IDX_execution_entity_deduplicationKey; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_execution_entity_deduplicationKey" ON public.execution_entity USING btree ("deduplicationKey") WHERE ("deduplicationKey" IS NOT NULL);


--
-- Name: IDX_execution_entity_deletedAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_execution_entity_deletedAt" ON public.execution_entity USING btree ("deletedAt");


--
-- Name: IDX_execution_entity_workflowId_status_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_execution_entity_workflowId_status_id" ON public.execution_entity USING btree ("workflowId", status, id) WHERE ("deletedAt" IS NULL);


--
-- Name: IDX_f1857f6716aa258393dd6f3324; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_f1857f6716aa258393dd6f3324" ON public.agents_memory_entry_candidates USING btree ("sourceMessageId");


--
-- Name: IDX_f36dea4d38fe92e0e8f44d5a56; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_f36dea4d38fe92e0e8f44d5a56" ON public.instance_ai_threads USING btree ("resourceId");


--
-- Name: IDX_f45d0535a2ed59b6c2dd6da98a; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_f45d0535a2ed59b6c2dd6da98a" ON public.agent_task_definition USING btree ("agentId");


--
-- Name: IDX_f9573af4ed653f13b0ba1f7b12; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_f9573af4ed653f13b0ba1f7b12" ON public.agents_memory_entry_sources USING btree ("agentId", "threadId");


--
-- Name: IDX_fc7bf858660bfafd19181e8e35; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_fc7bf858660bfafd19181e8e35" ON public.agents_messages USING btree ("threadId", "createdAt");


--
-- Name: IDX_fd7542bb123074760285dc1bbf; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_fd7542bb123074760285dc1bbf" ON public.evaluation_config USING btree ("workflowId");


--
-- Name: IDX_fec7ee37062350d6a4a2979327; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_fec7ee37062350d6a4a2979327" ON public.agent_credential_dependency USING btree ("credentialId");


--
-- Name: IDX_insights_raw_timestamp_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_insights_raw_timestamp_id" ON public.insights_raw USING btree ("timestamp", id);


--
-- Name: IDX_instance_ai_threads_projectId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_instance_ai_threads_projectId" ON public.instance_ai_threads USING btree ("projectId");


--
-- Name: IDX_instance_ai_threads_resourceId_updatedAt_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_instance_ai_threads_resourceId_updatedAt_id" ON public.instance_ai_threads USING btree ("resourceId", "updatedAt", id);


--
-- Name: IDX_promotion_config_connectionId_direction; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_promotion_config_connectionId_direction" ON public.promotion_config USING btree ("connectionId", direction);


--
-- Name: IDX_promotion_connection_scope; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_promotion_connection_scope" ON public.promotion_connection USING btree (scope) WHERE ((scope)::text = 'instance'::text);


--
-- Name: IDX_role_scope_scopeSlug; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_role_scope_scopeSlug" ON public.role_scope USING btree ("scopeSlug");


--
-- Name: IDX_scheduled_job_name; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_scheduled_job_name" ON public.scheduled_job USING btree (name);


--
-- Name: IDX_scheduled_job_nextRunAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_job_nextRunAt" ON public.scheduled_job USING btree ("nextRunAt") WHERE ((enabled = true) AND ("nextRunAt" IS NOT NULL));


--
-- Name: IDX_scheduled_job_ownerType_ownerId_ownerMemberId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_job_ownerType_ownerId_ownerMemberId" ON public.scheduled_job USING btree ("ownerType", "ownerId", "ownerMemberId");


--
-- Name: IDX_scheduled_task_finishedAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_task_finishedAt" ON public.scheduled_task USING btree ("finishedAt") WHERE ("finishedAt" IS NOT NULL);


--
-- Name: IDX_scheduled_task_jobId_scheduledFor; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_scheduled_task_jobId_scheduledFor" ON public.scheduled_task USING btree ("jobId", "scheduledFor");


--
-- Name: IDX_scheduled_task_leaseExpiresAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_task_leaseExpiresAt" ON public.scheduled_task USING btree ("leaseExpiresAt") WHERE ((status)::text = 'running'::text);


--
-- Name: IDX_scheduled_task_missedAfter; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_task_missedAfter" ON public.scheduled_task USING btree ("missedAfter") WHERE (((status)::text = 'pending'::text) AND ("missedAfter" IS NOT NULL));


--
-- Name: IDX_scheduled_task_runAt; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_scheduled_task_runAt" ON public.scheduled_task USING btree ("runAt") WHERE ((status)::text = 'pending'::text);


--
-- Name: IDX_secrets_provider_connection_providerKey; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_secrets_provider_connection_providerKey" ON public.secrets_provider_connection USING btree ("providerKey");


--
-- Name: IDX_shared_workflow_projectId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_shared_workflow_projectId" ON public.shared_workflow USING btree ("projectId");


--
-- Name: IDX_test_run_collectionId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_test_run_collectionId" ON public.test_run USING btree ("collectionId");


--
-- Name: IDX_test_run_evaluationConfigId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_test_run_evaluationConfigId" ON public.test_run USING btree ("evaluationConfigId");


--
-- Name: IDX_workflow_dependency_publishedVersionId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_dependency_publishedVersionId" ON public.workflow_dependency USING btree ("publishedVersionId");


--
-- Name: IDX_workflow_entity_name; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_entity_name" ON public.workflow_entity USING btree (name);


--
-- Name: IDX_workflow_entity_sourceWorkflowId; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_entity_sourceWorkflowId" ON public.workflow_entity USING btree ("sourceWorkflowId") WHERE ("sourceWorkflowId" IS NOT NULL);


--
-- Name: IDX_workflow_publication_outbox_active_workflow_status; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_workflow_publication_outbox_active_workflow_status" ON public.workflow_publication_outbox USING btree ("workflowId", status) WHERE ((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('in_progress'::character varying)::text]));


--
-- Name: IDX_workflow_review_activity_comment_activity; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_activity_comment_activity" ON public.workflow_review_activity_comment USING btree ("activityId", id);


--
-- Name: IDX_workflow_review_activity_request; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_activity_request" ON public.workflow_review_activity USING btree ("workflowReviewRequestId", id);


--
-- Name: IDX_workflow_review_request_authors_user; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_request_authors_user" ON public.workflow_review_request_authors USING btree ("userId", "workflowReviewRequestId");


--
-- Name: IDX_workflow_review_request_project_state; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_request_project_state" ON public.workflow_review_request USING btree ("projectId", state);


--
-- Name: IDX_workflow_review_request_reviewers_user; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_request_reviewers_user" ON public.workflow_review_request_reviewers USING btree ("userId", "workflowReviewRequestId");


--
-- Name: IDX_workflow_review_request_workflow_workflow_request; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX "IDX_workflow_review_request_workflow_workflow_request" ON public.workflow_review_request_workflow USING btree ("workflowId", "workflowReviewRequestId");


--
-- Name: IDX_workflow_statistics_workflow_name; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "IDX_workflow_statistics_workflow_name" ON public.workflow_statistics USING btree ("workflowId", name);


--
-- Name: UQ_workflow_review_request_workflow_request_workflow; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX "UQ_workflow_review_request_workflow_request_workflow" ON public.workflow_review_request_workflow USING btree ("workflowReviewRequestId", "workflowId");


--
-- Name: idx_07fde106c0b471d8cc80a64fc8; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_07fde106c0b471d8cc80a64fc8 ON public.credentials_entity USING btree (type);


--
-- Name: idx_16f4436789e804e3e1c9eeb240; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_16f4436789e804e3e1c9eeb240 ON public.webhook_entity USING btree ("webhookId", method, "pathLength");


--
-- Name: idx_812eb05f7451ca757fb98444ce; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX idx_812eb05f7451ca757fb98444ce ON public.tag_entity USING btree (name);


--
-- Name: idx_execution_entity_stopped_at_status_deleted_at; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_execution_entity_stopped_at_status_deleted_at ON public.execution_entity USING btree ("stoppedAt", status, "deletedAt") WHERE (("stoppedAt" IS NOT NULL) AND ("deletedAt" IS NULL));


--
-- Name: idx_execution_entity_wait_till_status_deleted_at; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_execution_entity_wait_till_status_deleted_at ON public.execution_entity USING btree ("waitTill", status, "deletedAt") WHERE (("waitTill" IS NOT NULL) AND ("deletedAt" IS NULL));


--
-- Name: idx_execution_entity_workflow_id_started_at; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_execution_entity_workflow_id_started_at ON public.execution_entity USING btree ("workflowId", "startedAt") WHERE (("startedAt" IS NOT NULL) AND ("deletedAt" IS NULL));


--
-- Name: idx_workflows_tags_workflow_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX idx_workflows_tags_workflow_id ON public.workflows_tags USING btree ("workflowId");


--
-- Name: pk_credentials_entity_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX pk_credentials_entity_id ON public.credentials_entity USING btree (id);


--
-- Name: pk_tag_entity_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX pk_tag_entity_id ON public.tag_entity USING btree (id);


--
-- Name: pk_workflow_entity_id; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX pk_workflow_entity_id ON public.workflow_entity USING btree (id);


--
-- Name: project_relation_role_idx; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX project_relation_role_idx ON public.project_relation USING btree (role);


--
-- Name: project_relation_role_project_idx; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX project_relation_role_project_idx ON public.project_relation USING btree ("projectId", role);


--
-- Name: uq_type_availability_attachment_slot; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX uq_type_availability_attachment_slot ON public.type_availability_policy_attachment USING btree ("scopeId", "isFloor", priority);


--
-- Name: uq_type_availability_policy_scope_instance; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX uq_type_availability_policy_scope_instance ON public.type_availability_policy_scope USING btree (kind) WHERE ("projectId" IS NULL);


--
-- Name: uq_type_availability_policy_scope_project; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX uq_type_availability_policy_scope_project ON public.type_availability_policy_scope USING btree (kind, "projectId") WHERE ("projectId" IS NOT NULL);


--
-- Name: user_role_idx; Type: INDEX; Schema: public; Owner: n8n
--

CREATE INDEX user_role_idx ON public."user" USING btree ("roleSlug");


--
-- Name: variables_global_key_unique; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX variables_global_key_unique ON public.variables USING btree (key) WHERE ("projectId" IS NULL);


--
-- Name: variables_project_key_unique; Type: INDEX; Schema: public; Owner: n8n
--

CREATE UNIQUE INDEX variables_project_key_unique ON public.variables USING btree ("projectId", key) WHERE ("projectId" IS NOT NULL);


--
-- Name: bk_cod_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX bk_cod_idx ON raw.bk_shipment USING btree (cod_durum) WHERE cod_var;


--
-- Name: bk_foreign_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX bk_foreign_idx ON raw.bk_shipment USING btree (foreign_code) WHERE (foreign_code IS NOT NULL);


--
-- Name: bk_olusturma_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX bk_olusturma_idx ON raw.bk_shipment USING btree (olusturma);


--
-- Name: ga4_event_tekil; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE UNIQUE INDEX ga4_event_tekil ON raw.ga4_event USING btree (event_name, event_timestamp, COALESCE(user_pseudo_id, ''::text), COALESCE(session_id, ''::text), COALESCE(item_id, ''::text), COALESCE(transaction_id, ''::text));


--
-- Name: ga4_event_toplu_tekil; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE UNIQUE INDEX ga4_event_toplu_tekil ON raw.ga4_event USING btree (event_name, event_date) WHERE ((granulerlik = 'GUNLUK_TOPLAM'::text) AND (transaction_id IS NULL));


--
-- Name: ga4_purchase_tekil; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE UNIQUE INDEX ga4_purchase_tekil ON raw.ga4_event USING btree (transaction_id) WHERE ((event_name = 'purchase'::text) AND (transaction_id IS NOT NULL));


--
-- Name: idefix_urun_stok_kodu; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX idefix_urun_stok_kodu ON raw.idefix_urun USING btree (stok_kodu);


--
-- Name: ig_medya_tur_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX ig_medya_tur_idx ON raw.ig_medya USING btree (urun_tipi, zaman DESC);


--
-- Name: ig_medya_zaman_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX ig_medya_zaman_idx ON raw.ig_medya USING btree (zaman DESC);


--
-- Name: meta_harcama_gun_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX meta_harcama_gun_idx ON raw.meta_harcama USING btree (gun);


--
-- Name: meta_kreatif_kid_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX meta_kreatif_kid_idx ON raw.meta_kreatif USING btree (kreatif_id);


--
-- Name: meta_reklam_ad_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX meta_reklam_ad_idx ON raw.meta_reklam USING btree (ad_id);


--
-- Name: meta_reklam_gun_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX meta_reklam_gun_idx ON raw.meta_reklam USING btree (gun);


--
-- Name: osm_poi_konum_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX osm_poi_konum_idx ON raw.osm_poi USING btree (enlem, boylam);


--
-- Name: osm_poi_tur_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX osm_poi_tur_idx ON raw.osm_poi USING btree (tur);


--
-- Name: overture_poi_konum_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX overture_poi_konum_idx ON raw.overture_poi USING btree (enlem, boylam);


--
-- Name: overture_poi_tur_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX overture_poi_tur_idx ON raw.overture_poi USING btree (tur);


--
-- Name: trendyol_urun_content; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX trendyol_urun_content ON raw.trendyol_urun USING btree (content_id);


--
-- Name: ux_geo_response_tekil; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE UNIQUE INDEX ux_geo_response_tekil ON raw.geo_response USING btree (saglayici, yuzey, language, country, cevap_hash, cekim_at);


--
-- Name: wix_item_urun_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX wix_item_urun_idx ON raw.wix_order_item USING btree (urun_id);


--
-- Name: wix_order_buyer_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX wix_order_buyer_idx ON raw.wix_order USING btree (buyer_id);


--
-- Name: wix_order_olusturma_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX wix_order_olusturma_idx ON raw.wix_order USING btree (olusturma);


--
-- Name: wix_urun_sku_idx; Type: INDEX; Schema: raw; Owner: n8n
--

CREATE INDEX wix_urun_sku_idx ON raw.wix_urun USING btree (sku);


--
-- Name: buyume_bulgu bulgu_hipotez_kapisi; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER bulgu_hipotez_kapisi BEFORE INSERT OR UPDATE ON core.buyume_bulgu FOR EACH ROW EXECUTE FUNCTION core.bulgu_hipotez_kontrol();


--
-- Name: ai_action_proposal jarvis_company_action_registry; Type: TRIGGER; Schema: core; Owner: function_owner
--

CREATE TRIGGER jarvis_company_action_registry AFTER INSERT OR UPDATE ON core.ai_action_proposal FOR EACH ROW EXECUTE FUNCTION core.jarvis_sync_company_action();


--
-- Name: ai_action_approval jarvis_company_vote_registry; Type: TRIGGER; Schema: core; Owner: function_owner
--

CREATE TRIGGER jarvis_company_vote_registry AFTER INSERT ON core.ai_action_approval FOR EACH ROW EXECUTE FUNCTION core.jarvis_record_company_vote();


--
-- Name: jarvis_personal_action jarvis_personal_action_registry; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER jarvis_personal_action_registry AFTER INSERT OR UPDATE ON core.jarvis_personal_action FOR EACH ROW EXECUTE FUNCTION core.jarvis_sync_personal_action();


--
-- Name: karar karar_gecis; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER karar_gecis BEFORE UPDATE ON core.karar FOR EACH ROW EXECUTE FUNCTION core.karar_gecis_kontrol();


--
-- Name: kreatif_itiraz kreatif_itiraz_kapatma; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER kreatif_itiraz_kapatma BEFORE UPDATE ON core.kreatif_itiraz FOR EACH ROW EXECUTE FUNCTION core.kreatif_itiraz_kapatma_kontrol();


--
-- Name: medya_istegi medya_istegi_dokun; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER medya_istegi_dokun BEFORE UPDATE ON core.medya_istegi FOR EACH ROW EXECUTE FUNCTION core.medya_istegi_dokun();


--
-- Name: medya_istegi medya_istegi_onay_kapisi; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER medya_istegi_onay_kapisi BEFORE UPDATE ON core.medya_istegi FOR EACH ROW EXECUTE FUNCTION core.medya_istegi_onay_kapisi();


--
-- Name: tasarim_isi tasarim_isi_onay; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER tasarim_isi_onay BEFORE UPDATE ON core.tasarim_isi FOR EACH ROW EXECUTE FUNCTION core.tasarim_isi_onay_kontrol();


--
-- Name: geo_observation tg_geo_obs_immutable; Type: TRIGGER; Schema: core; Owner: n8n
--

CREATE TRIGGER tg_geo_obs_immutable BEFORE UPDATE ON core.geo_observation FOR EACH ROW EXECUTE FUNCTION core.geo_obs_immutable();


--
-- Name: mesaj mesaj_sonrasi; Type: TRIGGER; Schema: lcarlie; Owner: n8n
--

CREATE TRIGGER mesaj_sonrasi AFTER INSERT OR DELETE OR UPDATE ON lcarlie.mesaj FOR EACH ROW EXECUTE FUNCTION lcarlie.konusma_tazele();


--
-- Name: workflow_entity workflow_version_increment; Type: TRIGGER; Schema: public; Owner: n8n
--

CREATE TRIGGER workflow_version_increment BEFORE UPDATE ON public.workflow_entity FOR EACH ROW EXECUTE FUNCTION public.increment_workflow_version();


--
-- Name: acik_soru acik_soru_bagli_bulgu_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.acik_soru
    ADD CONSTRAINT acik_soru_bagli_bulgu_fkey FOREIGN KEY (bagli_bulgu) REFERENCES core.buyume_bulgu(bulgu_id);


--
-- Name: ai_action_approval ai_action_approval_action_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_approval
    ADD CONSTRAINT ai_action_approval_action_id_fkey FOREIGN KEY (action_id) REFERENCES core.ai_action_proposal(action_id) ON DELETE CASCADE;


--
-- Name: ai_action_execution ai_action_execution_action_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_execution
    ADD CONSTRAINT ai_action_execution_action_id_fkey FOREIGN KEY (action_id) REFERENCES core.ai_action_proposal(action_id) ON DELETE CASCADE;


--
-- Name: ai_action_proposal ai_action_proposal_action_type_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_proposal
    ADD CONSTRAINT ai_action_proposal_action_type_fkey FOREIGN KEY (action_type) REFERENCES core.ai_action_type(action_type);


--
-- Name: ai_action_proposal ai_action_proposal_task_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_action_proposal
    ADD CONSTRAINT ai_action_proposal_task_id_fkey FOREIGN KEY (task_id) REFERENCES core.ai_task(task_id);


--
-- Name: ai_calisma_log ai_calisma_log_anlik_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ai_calisma_log
    ADD CONSTRAINT ai_calisma_log_anlik_id_fkey FOREIGN KEY (anlik_id) REFERENCES core.kanit_anlik(anlik_id);


--
-- Name: ai_evidence_followup ai_evidence_followup_decision_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_evidence_followup
    ADD CONSTRAINT ai_evidence_followup_decision_id_fkey FOREIGN KEY (decision_id) REFERENCES core.karar(karar_id);


--
-- Name: ai_evidence_followup ai_evidence_followup_enqueued_task_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_evidence_followup
    ADD CONSTRAINT ai_evidence_followup_enqueued_task_id_fkey FOREIGN KEY (enqueued_task_id) REFERENCES core.ai_task(task_id);


--
-- Name: ai_evidence_followup ai_evidence_followup_question_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_evidence_followup
    ADD CONSTRAINT ai_evidence_followup_question_id_fkey FOREIGN KEY (question_id) REFERENCES core.acik_soru(soru_id);


--
-- Name: ai_executive_brief ai_executive_brief_message_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_executive_brief
    ADD CONSTRAINT ai_executive_brief_message_id_fkey FOREIGN KEY (message_id) REFERENCES core.ic_mesaj(mesaj_id);


--
-- Name: ai_generated_question ai_generated_question_soru_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_generated_question
    ADD CONSTRAINT ai_generated_question_soru_id_fkey FOREIGN KEY (soru_id) REFERENCES core.acik_soru(soru_id);


--
-- Name: ai_human_supersede_audit ai_human_supersede_audit_canonical_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_supersede_audit
    ADD CONSTRAINT ai_human_supersede_audit_canonical_karar_id_fkey FOREIGN KEY (canonical_karar_id) REFERENCES core.karar(karar_id);


--
-- Name: ai_human_supersede_audit ai_human_supersede_audit_old_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_human_supersede_audit
    ADD CONSTRAINT ai_human_supersede_audit_old_karar_id_fkey FOREIGN KEY (old_karar_id) REFERENCES core.karar(karar_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_data_message_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_data_message_id_fkey FOREIGN KEY (data_message_id) REFERENCES core.ic_mesaj(mesaj_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_experiment_message_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_experiment_message_id_fkey FOREIGN KEY (experiment_message_id) REFERENCES core.ic_mesaj(mesaj_id);


--
-- Name: ai_measurement_plan ai_measurement_plan_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_measurement_plan
    ADD CONSTRAINT ai_measurement_plan_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id);


--
-- Name: ai_provider_attempt ai_provider_attempt_task_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_provider_attempt
    ADD CONSTRAINT ai_provider_attempt_task_id_fkey FOREIGN KEY (task_id) REFERENCES core.ai_task(task_id);


--
-- Name: ai_question_route ai_question_route_departman_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_question_route
    ADD CONSTRAINT ai_question_route_departman_fkey FOREIGN KEY (departman) REFERENCES core.departman(kod);


--
-- Name: ai_question_route ai_question_route_mesaj_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_question_route
    ADD CONSTRAINT ai_question_route_mesaj_id_fkey FOREIGN KEY (mesaj_id) REFERENCES core.ic_mesaj(mesaj_id);


--
-- Name: ai_question_route ai_question_route_soru_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_question_route
    ADD CONSTRAINT ai_question_route_soru_id_fkey FOREIGN KEY (soru_id) REFERENCES core.acik_soru(soru_id);


--
-- Name: ai_red_team_attempt ai_red_team_attempt_job_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_attempt
    ADD CONSTRAINT ai_red_team_attempt_job_id_fkey FOREIGN KEY (job_id) REFERENCES core.ai_red_team_job(job_id);


--
-- Name: ai_red_team_job ai_red_team_job_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.ai_red_team_job
    ADD CONSTRAINT ai_red_team_job_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id);


--
-- Name: buyume_bulgu buyume_bulgu_anlik_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.buyume_bulgu
    ADD CONSTRAINT buyume_bulgu_anlik_id_fkey FOREIGN KEY (anlik_id) REFERENCES core.kanit_anlik(anlik_id) ON DELETE CASCADE;


--
-- Name: buyume_bulgu buyume_bulgu_ustunu_alan_fk; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.buyume_bulgu
    ADD CONSTRAINT buyume_bulgu_ustunu_alan_fk FOREIGN KEY (ustunu_alan) REFERENCES core.buyume_bulgu(bulgu_id);


--
-- Name: customer_identity customer_identity_customer_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.customer_identity
    ADD CONSTRAINT customer_identity_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES core.customer(customer_id) ON DELETE RESTRICT;


--
-- Name: funnel_sayfa_kapsama funnel_sayfa_kapsama_adim_kod_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.funnel_sayfa_kapsama
    ADD CONSTRAINT funnel_sayfa_kapsama_adim_kod_fkey FOREIGN KEY (adim_kod) REFERENCES core.funnel_adim(adim_kod);


--
-- Name: geo_alias geo_alias_canonical_brand_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_alias
    ADD CONSTRAINT geo_alias_canonical_brand_id_fkey FOREIGN KEY (canonical_brand_id) REFERENCES core.geo_brand(brand_id) ON DELETE CASCADE;


--
-- Name: geo_citation_mention geo_citation_mention_citation_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation_mention
    ADD CONSTRAINT geo_citation_mention_citation_id_fkey FOREIGN KEY (citation_id) REFERENCES core.geo_citation(citation_id) ON DELETE CASCADE;


--
-- Name: geo_citation_mention geo_citation_mention_mention_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation_mention
    ADD CONSTRAINT geo_citation_mention_mention_id_fkey FOREIGN KEY (mention_id) REFERENCES core.geo_mention(mention_id) ON DELETE CASCADE;


--
-- Name: geo_citation geo_citation_observation_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation
    ADD CONSTRAINT geo_citation_observation_id_fkey FOREIGN KEY (observation_id) REFERENCES core.geo_observation(observation_id) ON DELETE CASCADE;


--
-- Name: geo_citation geo_citation_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_citation
    ADD CONSTRAINT geo_citation_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.geo_source(source_id);


--
-- Name: geo_entity_conflict geo_entity_conflict_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_entity_conflict
    ADD CONSTRAINT geo_entity_conflict_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.geo_source(source_id);


--
-- Name: geo_gap geo_gap_action_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_gap
    ADD CONSTRAINT geo_gap_action_id_fkey FOREIGN KEY (action_id) REFERENCES core.ai_action_proposal(action_id);


--
-- Name: geo_gap geo_gap_query_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_gap
    ADD CONSTRAINT geo_gap_query_id_fkey FOREIGN KEY (query_id) REFERENCES core.geo_query(query_id);


--
-- Name: geo_gap geo_gap_source_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_gap
    ADD CONSTRAINT geo_gap_source_id_fkey FOREIGN KEY (source_id) REFERENCES core.geo_source(source_id);


--
-- Name: geo_karar_kapsami geo_karar_kapsami_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_karar_kapsami
    ADD CONSTRAINT geo_karar_kapsami_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: geo_karar_kapsami geo_karar_kapsami_query_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_karar_kapsami
    ADD CONSTRAINT geo_karar_kapsami_query_id_fkey FOREIGN KEY (query_id) REFERENCES core.geo_query(query_id);


--
-- Name: geo_mention geo_mention_brand_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_mention
    ADD CONSTRAINT geo_mention_brand_id_fkey FOREIGN KEY (brand_id) REFERENCES core.geo_brand(brand_id);


--
-- Name: geo_mention geo_mention_observation_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_mention
    ADD CONSTRAINT geo_mention_observation_id_fkey FOREIGN KEY (observation_id) REFERENCES core.geo_observation(observation_id) ON DELETE CASCADE;


--
-- Name: geo_observation geo_observation_ham_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_observation
    ADD CONSTRAINT geo_observation_ham_id_fkey FOREIGN KEY (ham_id) REFERENCES raw.geo_response(ham_id);


--
-- Name: geo_observation geo_observation_query_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.geo_observation
    ADD CONSTRAINT geo_observation_query_id_fkey FOREIGN KEY (query_id) REFERENCES core.geo_query(query_id);


--
-- Name: ic_mesaj ic_mesaj_bagli_bulgu_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_bagli_bulgu_fkey FOREIGN KEY (bagli_bulgu) REFERENCES core.buyume_bulgu(bulgu_id);


--
-- Name: ic_mesaj ic_mesaj_bagli_karar_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_bagli_karar_fkey FOREIGN KEY (bagli_karar) REFERENCES core.karar(karar_id);


--
-- Name: ic_mesaj ic_mesaj_bagli_soru_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_bagli_soru_fkey FOREIGN KEY (bagli_soru) REFERENCES core.acik_soru(soru_id);


--
-- Name: ic_mesaj ic_mesaj_kimden_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_kimden_fkey FOREIGN KEY (kimden) REFERENCES core.departman(kod);


--
-- Name: ic_mesaj ic_mesaj_kime_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_kime_fkey FOREIGN KEY (kime) REFERENCES core.departman(kod);


--
-- Name: ic_mesaj ic_mesaj_yanit_veren_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ic_mesaj
    ADD CONSTRAINT ic_mesaj_yanit_veren_fkey FOREIGN KEY (yanit_veren) REFERENCES core.departman(kod);


--
-- Name: ig_gonderi_plani ig_gonderi_plani_konsept_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.ig_gonderi_plani
    ADD CONSTRAINT ig_gonderi_plani_konsept_id_fkey FOREIGN KEY (konsept_id) REFERENCES core.kreatif_konsept(konsept_id);


--
-- Name: inanc_catismasi inanc_catismasi_bulgu_a_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.inanc_catismasi
    ADD CONSTRAINT inanc_catismasi_bulgu_a_fkey FOREIGN KEY (bulgu_a) REFERENCES core.buyume_bulgu(bulgu_id);


--
-- Name: inanc_catismasi inanc_catismasi_bulgu_b_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.inanc_catismasi
    ADD CONSTRAINT inanc_catismasi_bulgu_b_fkey FOREIGN KEY (bulgu_b) REFERENCES core.buyume_bulgu(bulgu_id);


--
-- Name: jarvis_action_registry_event jarvis_action_registry_event_action_key_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_action_registry_event
    ADD CONSTRAINT jarvis_action_registry_event_action_key_fkey FOREIGN KEY (action_key) REFERENCES core.jarvis_action_registry(action_key);


--
-- Name: jarvis_cari_document jarvis_cari_document_owner_account_id_entry_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_document
    ADD CONSTRAINT jarvis_cari_document_owner_account_id_entry_id_fkey FOREIGN KEY (owner, account_id, entry_id) REFERENCES core.jarvis_cari_entry(owner, account_id, entry_id);


--
-- Name: jarvis_cari_document jarvis_cari_document_owner_account_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_document
    ADD CONSTRAINT jarvis_cari_document_owner_account_id_fkey FOREIGN KEY (owner, account_id) REFERENCES core.jarvis_cari_account(owner, account_id);


--
-- Name: jarvis_cari_draft jarvis_cari_draft_owner_account_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_draft
    ADD CONSTRAINT jarvis_cari_draft_owner_account_id_fkey FOREIGN KEY (owner, account_id) REFERENCES core.jarvis_cari_account(owner, account_id);


--
-- Name: jarvis_cari_draft jarvis_cari_draft_owner_account_id_posted_entry_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_draft
    ADD CONSTRAINT jarvis_cari_draft_owner_account_id_posted_entry_id_fkey FOREIGN KEY (owner, account_id, posted_entry_id) REFERENCES core.jarvis_cari_entry(owner, account_id, entry_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_owner_account_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_owner_account_id_fkey FOREIGN KEY (owner, account_id) REFERENCES core.jarvis_cari_account(owner, account_id);


--
-- Name: jarvis_cari_entry jarvis_cari_entry_owner_account_id_reverses_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_cari_entry
    ADD CONSTRAINT jarvis_cari_entry_owner_account_id_reverses_fkey FOREIGN KEY (owner, account_id, reverses) REFERENCES core.jarvis_cari_entry(owner, account_id, entry_id);


--
-- Name: jarvis_personal_action_event jarvis_personal_action_event_action_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.jarvis_personal_action_event
    ADD CONSTRAINT jarvis_personal_action_event_action_id_fkey FOREIGN KEY (action_id) REFERENCES core.jarvis_personal_action(action_id);


--
-- Name: jarvis_task_state jarvis_task_state_task_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: function_owner
--

ALTER TABLE ONLY core.jarvis_task_state
    ADD CONSTRAINT jarvis_task_state_task_id_fkey FOREIGN KEY (task_id) REFERENCES core.ai_task(task_id) ON DELETE CASCADE;


--
-- Name: karar_aksiyon karar_aksiyon_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_aksiyon
    ADD CONSTRAINT karar_aksiyon_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: karar karar_anlik_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar
    ADD CONSTRAINT karar_anlik_id_fkey FOREIGN KEY (anlik_id) REFERENCES core.kanit_anlik(anlik_id);


--
-- Name: karar_insan karar_insan_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_insan
    ADD CONSTRAINT karar_insan_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: karar_kanit karar_kanit_bulgu_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_kanit
    ADD CONSTRAINT karar_kanit_bulgu_id_fkey FOREIGN KEY (bulgu_id) REFERENCES core.buyume_bulgu(bulgu_id) ON DELETE RESTRICT;


--
-- Name: karar_kanit karar_kanit_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_kanit
    ADD CONSTRAINT karar_kanit_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: karar_red_team karar_red_team_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_red_team
    ADD CONSTRAINT karar_red_team_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: karar_sonuc karar_sonuc_karar_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar_sonuc
    ADD CONSTRAINT karar_sonuc_karar_id_fkey FOREIGN KEY (karar_id) REFERENCES core.karar(karar_id) ON DELETE CASCADE;


--
-- Name: karar karar_ustunu_alan_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.karar
    ADD CONSTRAINT karar_ustunu_alan_fkey FOREIGN KEY (ustunu_alan) REFERENCES core.karar(karar_id);


--
-- Name: katalog_not katalog_not_ziyaret_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.katalog_not
    ADD CONSTRAINT katalog_not_ziyaret_id_fkey FOREIGN KEY (ziyaret_id) REFERENCES core.saha_ziyaret(ziyaret_id);


--
-- Name: kreatif_konsept kreatif_konsept_plan_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.kreatif_konsept
    ADD CONSTRAINT kreatif_konsept_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES core.ig_gonderi_plani(plan_id) ON DELETE CASCADE;


--
-- Name: mimari_ders mimari_ders_gecersiz_kilan_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.mimari_ders
    ADD CONSTRAINT mimari_ders_gecersiz_kilan_fkey FOREIGN KEY (gecersiz_kilan) REFERENCES core.mimari_ders(ders_id);


--
-- Name: saha_konum saha_konum_rota_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_konum
    ADD CONSTRAINT saha_konum_rota_id_fkey FOREIGN KEY (rota_id) REFERENCES core.saha_rota(rota_id) ON DELETE SET NULL;


--
-- Name: saha_rota_durak saha_rota_durak_rota_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_rota_durak
    ADD CONSTRAINT saha_rota_durak_rota_id_fkey FOREIGN KEY (rota_id) REFERENCES core.saha_rota(rota_id) ON DELETE CASCADE;


--
-- Name: saha_ziyaret_foto saha_ziyaret_foto_ziyaret_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.saha_ziyaret_foto
    ADD CONSTRAINT saha_ziyaret_foto_ziyaret_id_fkey FOREIGN KEY (ziyaret_id) REFERENCES core.saha_ziyaret(ziyaret_id) ON DELETE CASCADE;


--
-- Name: siparis_bildirim siparis_bildirim_siparis_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.siparis_bildirim
    ADD CONSTRAINT siparis_bildirim_siparis_id_fkey FOREIGN KEY (siparis_id) REFERENCES core.pazaryeri_siparis(id) ON DELETE CASCADE;


--
-- Name: tasarim_isi tasarim_isi_sablon_id_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.tasarim_isi
    ADD CONSTRAINT tasarim_isi_sablon_id_fkey FOREIGN KEY (sablon_id) REFERENCES core.tasarim_sablon(sablon_id);


--
-- Name: urun_platform_fiyat urun_platform_fiyat_platform_kod_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_platform_fiyat
    ADD CONSTRAINT urun_platform_fiyat_platform_kod_fkey FOREIGN KEY (platform_kod) REFERENCES core.platform(kod);


--
-- Name: urun_platform_komisyon urun_platform_komisyon_platform_kod_fkey; Type: FK CONSTRAINT; Schema: core; Owner: n8n
--

ALTER TABLE ONLY core.urun_platform_komisyon
    ADD CONSTRAINT urun_platform_komisyon_platform_kod_fkey FOREIGN KEY (platform_kod) REFERENCES core.platform(kod);


--
-- Name: mesaj mesaj_konusma_id_fkey; Type: FK CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.mesaj
    ADD CONSTRAINT mesaj_konusma_id_fkey FOREIGN KEY (konusma_id) REFERENCES lcarlie.konusma(id) ON DELETE CASCADE;


--
-- Name: satis_cevap satis_cevap_konusma_id_fkey; Type: FK CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_cevap
    ADD CONSTRAINT satis_cevap_konusma_id_fkey FOREIGN KEY (konusma_id) REFERENCES lcarlie.konusma(id) ON DELETE CASCADE;


--
-- Name: satis_cevap satis_cevap_tetik_mesaj_id_fkey; Type: FK CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_cevap
    ADD CONSTRAINT satis_cevap_tetik_mesaj_id_fkey FOREIGN KEY (tetik_mesaj_id) REFERENCES lcarlie.mesaj(id) ON DELETE SET NULL;


--
-- Name: satis_cevap satis_cevap_yaklasim_id_fkey; Type: FK CONSTRAINT; Schema: lcarlie; Owner: n8n
--

ALTER TABLE ONLY lcarlie.satis_cevap
    ADD CONSTRAINT satis_cevap_yaklasim_id_fkey FOREIGN KEY (yaklasim_id) REFERENCES lcarlie.satis_yaklasim(id);


--
-- Name: workflow_builder_session FK_00290cdeee4d4d7db84709be936; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_builder_session
    ADD CONSTRAINT "FK_00290cdeee4d4d7db84709be936" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: agent_execution_threads FK_0468a9dc35597314e641d4722aa; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution_threads
    ADD CONSTRAINT "FK_0468a9dc35597314e641d4722aa" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: processed_data FK_06a69a7032c97a763c2c7599464; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.processed_data
    ADD CONSTRAINT "FK_06a69a7032c97a763c2c7599464" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: workflow_entity FK_08d6c67b7f722b0039d9d5ed620; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_entity
    ADD CONSTRAINT "FK_08d6c67b7f722b0039d9d5ed620" FOREIGN KEY ("activeVersionId") REFERENCES public.workflow_history("versionId") ON DELETE RESTRICT;


--
-- Name: agents_observation_locks FK_093e44ae20f2518e97d83a95433; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_locks
    ADD CONSTRAINT "FK_093e44ae20f2518e97d83a95433" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: agents_messages FK_0a8057a61afabd2999608ffd0d9; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_messages
    ADD CONSTRAINT "FK_0a8057a61afabd2999608ffd0d9" FOREIGN KEY ("threadId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: instance_ai_pending_confirmations FK_0babdf6e3b897a86fe4678355eb; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_pending_confirmations
    ADD CONSTRAINT "FK_0babdf6e3b897a86fe4678355eb" FOREIGN KEY ("checkpointKey") REFERENCES public.instance_ai_checkpoints(key) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_locks FK_0ccf6d9ea6f44fa1c264fc2f795; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_locks
    ADD CONSTRAINT "FK_0ccf6d9ea6f44fa1c264fc2f795" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: agent_execution_threads FK_0e2f8bf92a7a9c88b89670f701c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution_threads
    ADD CONSTRAINT "FK_0e2f8bf92a7a9c88b89670f701c" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entries FK_0edf1226b77ddc525eae4938079; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entries
    ADD CONSTRAINT "FK_0edf1226b77ddc525eae4938079" FOREIGN KEY ("supersededBy") REFERENCES public.agents_memory_entries(id);


--
-- Name: workflow_review_request_workflow FK_0f6f0f2c6d46b806fee02962ac2; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_workflow
    ADD CONSTRAINT "FK_0f6f0f2c6d46b806fee02962ac2" FOREIGN KEY ("workflowVersionId") REFERENCES public.workflow_history("versionId") ON DELETE SET NULL;


--
-- Name: instance_ai_observation_locks FK_103e2e5f454860b28ea05a82c74; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observation_locks
    ADD CONSTRAINT "FK_103e2e5f454860b28ea05a82c74" FOREIGN KEY ("observationScopeId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: type_availability_policy_attachment FK_118709fc9fe21d3406f81665a53; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy_attachment
    ADD CONSTRAINT "FK_118709fc9fe21d3406f81665a53" FOREIGN KEY ("scopeId") REFERENCES public.type_availability_policy_scope(id) ON DELETE CASCADE;


--
-- Name: agents_observations FK_127ee1078ffa952bb37b511efad; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observations
    ADD CONSTRAINT "FK_127ee1078ffa952bb37b511efad" FOREIGN KEY ("supersededBy") REFERENCES public.agents_observations(id);


--
-- Name: agents_memory_entries FK_1443a75e59adbfb796071d66393; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entries
    ADD CONSTRAINT "FK_1443a75e59adbfb796071d66393" FOREIGN KEY ("resourceId") REFERENCES public.agents_resources(id) ON DELETE CASCADE;


--
-- Name: project_secrets_provider_access FK_18e5c27d2524b1638b292904e48; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_secrets_provider_access
    ADD CONSTRAINT "FK_18e5c27d2524b1638b292904e48" FOREIGN KEY ("secretsProviderConnectionId") REFERENCES public.secrets_provider_connection(id) ON DELETE CASCADE;


--
-- Name: agent_task_snapshot FK_1acedce6690392ef1611cca8b88; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_snapshot
    ADD CONSTRAINT "FK_1acedce6690392ef1611cca8b88" FOREIGN KEY ("versionId") REFERENCES public.agent_history("versionId") ON DELETE CASCADE;


--
-- Name: instance_ai_mcp_registry_connections FK_1d25707354d2012da256eb2ec0a; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_mcp_registry_connections
    ADD CONSTRAINT "FK_1d25707354d2012da256eb2ec0a" FOREIGN KEY ("serverSlug") REFERENCES public.mcp_registry_server(slug) ON DELETE CASCADE;


--
-- Name: insights_metadata FK_1d8ab99d5861c9388d2dc1cf733; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_metadata
    ADD CONSTRAINT "FK_1d8ab99d5861c9388d2dc1cf733" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE SET NULL;


--
-- Name: user_favorites FK_1dd5c393ad0517be3c31a7af836; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.user_favorites
    ADD CONSTRAINT "FK_1dd5c393ad0517be3c31a7af836" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: workflow_history FK_1e31657f5fe46816c34be7c1b4b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_history
    ADD CONSTRAINT "FK_1e31657f5fe46816c34be7c1b4b" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_mcp_registry_connections FK_1e826120e7e53ebc4681f026de8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_mcp_registry_connections
    ADD CONSTRAINT "FK_1e826120e7e53ebc4681f026de8" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_messages FK_1eeb64cb9d66a927988de759e6e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_messages
    ADD CONSTRAINT "FK_1eeb64cb9d66a927988de759e6e" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_1f4998c8a7dec9e00a9ab15550e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_1f4998c8a7dec9e00a9ab15550e" FOREIGN KEY ("revisionOfMessageId") REFERENCES public.chat_hub_messages(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request FK_21d5f5a831d2e38960030bb4f60; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request
    ADD CONSTRAINT "FK_21d5f5a831d2e38960030bb4f60" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: oauth_user_consents FK_21e6c3c2d78a097478fae6aaefa; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_user_consents
    ADD CONSTRAINT "FK_21e6c3c2d78a097478fae6aaefa" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: insights_metadata FK_2375a1eda085adb16b24615b69c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_metadata
    ADD CONSTRAINT "FK_2375a1eda085adb16b24615b69c" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE SET NULL;


--
-- Name: chat_hub_messages FK_25c9736e7f769f3a005eef4b372; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_25c9736e7f769f3a005eef4b372" FOREIGN KEY ("retryOfMessageId") REFERENCES public.chat_hub_messages(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request FK_2817c3a0245197b498818c447cb; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request
    ADD CONSTRAINT "FK_2817c3a0245197b498818c447cb" FOREIGN KEY ("updatedById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: agents_memory_entries FK_28e981fb675e9b44ce02f0ec1dd; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entries
    ADD CONSTRAINT "FK_28e981fb675e9b44ce02f0ec1dd" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: activity_event FK_29654477f37189453b353d3f46a; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.activity_event
    ADD CONSTRAINT "FK_29654477f37189453b353d3f46a" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: instance_ai_checkpoints FK_2b23f3f24a70bebb990203b011e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_checkpoints
    ADD CONSTRAINT "FK_2b23f3f24a70bebb990203b011e" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: chat_hub_agent_tools FK_2b53d796b3dbae91b1a9553c048; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agent_tools
    ADD CONSTRAINT "FK_2b53d796b3dbae91b1a9553c048" FOREIGN KEY ("agentId") REFERENCES public.chat_hub_agents(id) ON DELETE CASCADE;


--
-- Name: execution_metadata FK_31d0b4c93fb85ced26f6005cda3; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_metadata
    ADD CONSTRAINT "FK_31d0b4c93fb85ced26f6005cda3" FOREIGN KEY ("executionId") REFERENCES public.execution_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_observational_memory FK_34018c303885cd37093458e6409; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observational_memory
    ADD CONSTRAINT "FK_34018c303885cd37093458e6409" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE SET NULL;


--
-- Name: instance_ai_events FK_35909c5576a4a6c1d6a6fb71caa; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_events
    ADD CONSTRAINT "FK_35909c5576a4a6c1d6a6fb71caa" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: role_mapping_rule_project FK_35a78869286c65d9330d02b88f5; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule_project
    ADD CONSTRAINT "FK_35a78869286c65d9330d02b88f5" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: ai_builder_temporary_workflow FK_39b07732e819fb561d74c38763f; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_builder_temporary_workflow
    ADD CONSTRAINT "FK_39b07732e819fb561d74c38763f" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: agent_eval_run FK_39ca447735d378e365f4227abff; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_run
    ADD CONSTRAINT "FK_39ca447735d378e365f4227abff" FOREIGN KEY ("datasetId") REFERENCES public.agent_eval_dataset(id) ON DELETE CASCADE;


--
-- Name: workflow_review_activity_comment FK_3cd755e8ce44ee49bdf7e9222ec; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity_comment
    ADD CONSTRAINT "FK_3cd755e8ce44ee49bdf7e9222ec" FOREIGN KEY ("activityId") REFERENCES public.workflow_review_activity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_thread_grants FK_401b94abf83d1ac7a841f31330e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_thread_grants
    ADD CONSTRAINT "FK_401b94abf83d1ac7a841f31330e" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: agent_eval_result FK_40a2d1248a6d984f442de2fac1b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_result
    ADD CONSTRAINT "FK_40a2d1248a6d984f442de2fac1b" FOREIGN KEY ("runId") REFERENCES public.agent_eval_run(id) ON DELETE CASCADE;


--
-- Name: shared_credentials FK_416f66fc846c7c442970c094ccf; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_credentials
    ADD CONSTRAINT "FK_416f66fc846c7c442970c094ccf" FOREIGN KEY ("credentialsId") REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: agent_chat_attachments FK_41c246c30af3d2108d93e15dd5e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_chat_attachments
    ADD CONSTRAINT "FK_41c246c30af3d2108d93e15dd5e" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: variables FK_42f6c766f9f9d2edcc15bdd6e9b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.variables
    ADD CONSTRAINT "FK_42f6c766f9f9d2edcc15bdd6e9b" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: chat_hub_agent_tools FK_43e70f04c53344f82483d0570f6; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agent_tools
    ADD CONSTRAINT "FK_43e70f04c53344f82483d0570f6" FOREIGN KEY ("toolId") REFERENCES public.chat_hub_tools(id) ON DELETE CASCADE;


--
-- Name: chat_hub_agents FK_441ba2caba11e077ce3fbfa2cd8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agents
    ADD CONSTRAINT "FK_441ba2caba11e077ce3fbfa2cd8" FOREIGN KEY ("ownerId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_sources FK_451d387a182fa8dd8002dfc3a77; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "FK_451d387a182fa8dd8002dfc3a77" FOREIGN KEY ("threadId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_sources FK_4706f6223313959b7437a2b48df; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "FK_4706f6223313959b7437a2b48df" FOREIGN KEY ("memoryEntryId") REFERENCES public.agents_memory_entries(id) ON DELETE CASCADE;


--
-- Name: agents_observations FK_4cfd8a70ebb0a5b0cf047dca3cf; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observations
    ADD CONSTRAINT "FK_4cfd8a70ebb0a5b0cf047dca3cf" FOREIGN KEY ("observationScopeId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: ai_preference FK_4ea340a1847ad0e40a0b0360fe4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_preference
    ADD CONSTRAINT "FK_4ea340a1847ad0e40a0b0360fe4" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: agents_observations FK_501e2d1701a10e24fb69ab5fc5f; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observations
    ADD CONSTRAINT "FK_501e2d1701a10e24fb69ab5fc5f" FOREIGN KEY ("parentId") REFERENCES public.agents_observations(id);


--
-- Name: agents_memory_entry_candidates FK_5123f71435736664d2676084a85; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_candidates
    ADD CONSTRAINT "FK_5123f71435736664d2676084a85" FOREIGN KEY ("resourceId") REFERENCES public.agents_resources(id) ON DELETE CASCADE;


--
-- Name: agent_eval_run FK_54ee897f442cc7393a6d6165334; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_run
    ADD CONSTRAINT "FK_54ee897f442cc7393a6d6165334" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: instance_ai_observation_cursors FK_5b6319b2e9a37c1064a72428f9a; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observation_cursors
    ADD CONSTRAINT "FK_5b6319b2e9a37c1064a72428f9a" FOREIGN KEY ("observationScopeId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: agent_chat_attachments FK_5c048535b2132b40dfed2e640e5; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_chat_attachments
    ADD CONSTRAINT "FK_5c048535b2132b40dfed2e640e5" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_published_version FK_5c76fb7ee939fe2530374d3f75a; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_published_version
    ADD CONSTRAINT "FK_5c76fb7ee939fe2530374d3f75a" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE RESTRICT;


--
-- Name: agent_checkpoints FK_5e31c210f896d539964bf99fe32; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_checkpoints
    ADD CONSTRAINT "FK_5e31c210f896d539964bf99fe32" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: credential_dependency FK_5ec8e8c8d3539f3696cf73b43bf; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.credential_dependency
    ADD CONSTRAINT "FK_5ec8e8c8d3539f3696cf73b43bf" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: project_relation FK_5f0643f6717905a05164090dde7; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_relation
    ADD CONSTRAINT "FK_5f0643f6717905a05164090dde7" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: workflow_review_activity FK_61048bf6220dd354c955a9d9379; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity
    ADD CONSTRAINT "FK_61048bf6220dd354c955a9d9379" FOREIGN KEY ("workflowReviewRequestId") REFERENCES public.workflow_review_request(id) ON DELETE CASCADE;


--
-- Name: project_relation FK_61448d56d61802b5dfde5cdb002; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_relation
    ADD CONSTRAINT "FK_61448d56d61802b5dfde5cdb002" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_workflow FK_619f5b0544bcec60c3387e82f2f; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_workflow
    ADD CONSTRAINT "FK_619f5b0544bcec60c3387e82f2f" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: insights_by_period FK_6414cfed98daabbfdd61a1cfbc0; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_by_period
    ADD CONSTRAINT "FK_6414cfed98daabbfdd61a1cfbc0" FOREIGN KEY ("metaId") REFERENCES public.insights_metadata("metaId") ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes FK_64d965bd072ea24fb6da55468cd; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT "FK_64d965bd072ea24fb6da55468cd" FOREIGN KEY ("clientId") REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: agents_observation_cursors FK_64e92819f4b413661ed6e2c3c3d; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_cursors
    ADD CONSTRAINT "FK_64e92819f4b413661ed6e2c3c3d" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_session_tools FK_6596a328affd8d4967ffb303eee; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_session_tools
    ADD CONSTRAINT "FK_6596a328affd8d4967ffb303eee" FOREIGN KEY ("toolId") REFERENCES public.chat_hub_tools(id) ON DELETE CASCADE;


--
-- Name: type_availability_policy_attachment FK_674705e4c8a3d3eb0736f8e8eee; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy_attachment
    ADD CONSTRAINT "FK_674705e4c8a3d3eb0736f8e8eee" FOREIGN KEY ("policyId") REFERENCES public.type_availability_policy(id) ON DELETE RESTRICT;


--
-- Name: agent_credential_dependency FK_6a6948884969cb4204a1975578b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_credential_dependency
    ADD CONSTRAINT "FK_6a6948884969cb4204a1975578b" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_6afb260449dd7a9b85355d4e0c9; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_6afb260449dd7a9b85355d4e0c9" FOREIGN KEY ("executionId") REFERENCES public.execution_entity(id) ON DELETE SET NULL;


--
-- Name: agents_observation_locks FK_6b55089892e447c2f82e5ec60ed; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_locks
    ADD CONSTRAINT "FK_6b55089892e447c2f82e5ec60ed" FOREIGN KEY ("observationScopeId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: activity_event FK_6bf94d5542661d2e1b9e0c41436; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.activity_event
    ADD CONSTRAINT "FK_6bf94d5542661d2e1b9e0c41436" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: insights_raw FK_6e2e33741adef2a7c5d66befa4e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.insights_raw
    ADD CONSTRAINT "FK_6e2e33741adef2a7c5d66befa4e" FOREIGN KEY ("metaId") REFERENCES public.insights_metadata("metaId") ON DELETE CASCADE;


--
-- Name: workflow_publish_history FK_6eab5bd9eedabe9c54bd879fc40; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publish_history
    ADD CONSTRAINT "FK_6eab5bd9eedabe9c54bd879fc40" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: dynamic_credential_user_entry FK_6edec973a6450990977bb854c38; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_user_entry
    ADD CONSTRAINT "FK_6edec973a6450990977bb854c38" FOREIGN KEY ("resolverId") REFERENCES public.dynamic_credential_resolver(id) ON DELETE CASCADE;


--
-- Name: project_pool_settings FK_6f5617b5fb0db43f92e39f5b626; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_pool_settings
    ADD CONSTRAINT "FK_6f5617b5fb0db43f92e39f5b626" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: oauth_access_tokens FK_7234a36d8e49a1fa85095328845; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_access_tokens
    ADD CONSTRAINT "FK_7234a36d8e49a1fa85095328845" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: type_availability_policy_scope FK_73c152c542cea477208c3106193; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.type_availability_policy_scope
    ADD CONSTRAINT "FK_73c152c542cea477208c3106193" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: installed_nodes FK_73f857fc5dce682cef8a99c11dbddbc969618951; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.installed_nodes
    ADD CONSTRAINT "FK_73f857fc5dce682cef8a99c11dbddbc969618951" FOREIGN KEY (package) REFERENCES public.installed_packages("packageName") ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: oauth_access_tokens FK_78b26968132b7e5e45b75876481; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_access_tokens
    ADD CONSTRAINT "FK_78b26968132b7e5e45b75876481" FOREIGN KEY ("clientId") REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: workflow_builder_session FK_7983c618db48f47bf5a4cc1e1e4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_builder_session
    ADD CONSTRAINT "FK_7983c618db48f47bf5a4cc1e1e4" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: agent_channel_status FK_7a723e6aad04d88057dea6a21f4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_channel_status
    ADD CONSTRAINT "FK_7a723e6aad04d88057dea6a21f4" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_sessions FK_7bc13b4c7e6afbfaf9be326c189; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_sessions
    ADD CONSTRAINT "FK_7bc13b4c7e6afbfaf9be326c189" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE SET NULL;


--
-- Name: folder FK_804ea52f6729e3940498bd54d78; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder
    ADD CONSTRAINT "FK_804ea52f6729e3940498bd54d78" FOREIGN KEY ("parentFolderId") REFERENCES public.folder(id) ON DELETE CASCADE;


--
-- Name: shared_credentials FK_812c2852270da1247756e77f5a4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_credentials
    ADD CONSTRAINT "FK_812c2852270da1247756e77f5a4" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_reviewers FK_81d0a2584aa4e8e5e0d6aa68f32; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_reviewers
    ADD CONSTRAINT "FK_81d0a2584aa4e8e5e0d6aa68f32" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: ai_builder_temporary_workflow FK_85a87a1ba0f61999fe11dc56325; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_builder_temporary_workflow
    ADD CONSTRAINT "FK_85a87a1ba0f61999fe11dc56325" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_sources FK_87640d646b020c3be8e16cd0fa6; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "FK_87640d646b020c3be8e16cd0fa6" FOREIGN KEY ("candidateId") REFERENCES public.agents_memory_entry_candidates(id) ON DELETE CASCADE;


--
-- Name: agent_history FK_8771675f44c58fb40e0feb9ee35; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_history
    ADD CONSTRAINT "FK_8771675f44c58fb40e0feb9ee35" FOREIGN KEY ("publishedById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: agents_observation_cursors FK_87aa187d27ea67eafd164905154; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observation_cursors
    ADD CONSTRAINT "FK_87aa187d27ea67eafd164905154" FOREIGN KEY ("observationScopeId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: agent_history FK_87cd5a8da20304b089ea2f83fec; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_history
    ADD CONSTRAINT "FK_87cd5a8da20304b089ea2f83fec" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: instance_ai_mcp_registry_connections FK_8b42c08a531d76410980c639a5b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_mcp_registry_connections
    ADD CONSTRAINT "FK_8b42c08a531d76410980c639a5b" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: instance_ai_iteration_logs FK_8bfcc6c51fd3d69b1eae8aebd49; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_iteration_logs
    ADD CONSTRAINT "FK_8bfcc6c51fd3d69b1eae8aebd49" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: trusted_key FK_8c2938d746943dd8f608d23c891; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.trusted_key
    ADD CONSTRAINT "FK_8c2938d746943dd8f608d23c891" FOREIGN KEY ("sourceId") REFERENCES public.trusted_key_source(id) ON DELETE CASCADE;


--
-- Name: test_case_execution FK_8e4b4774db42f1e6dda3452b2af; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_case_execution
    ADD CONSTRAINT "FK_8e4b4774db42f1e6dda3452b2af" FOREIGN KEY ("testRunId") REFERENCES public.test_run(id) ON DELETE CASCADE;


--
-- Name: instance_ai_thread_grants FK_908202dbc0a9b52f669c11d730c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_thread_grants
    ADD CONSTRAINT "FK_908202dbc0a9b52f669c11d730c" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: data_table_column FK_930b6e8faaf88294cef23484160; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table_column
    ADD CONSTRAINT "FK_930b6e8faaf88294cef23484160" FOREIGN KEY ("dataTableId") REFERENCES public.data_table(id) ON DELETE CASCADE;


--
-- Name: agents FK_940597dfe9753375309ce6aeea0; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT "FK_940597dfe9753375309ce6aeea0" FOREIGN KEY ("activeVersionId") REFERENCES public.agent_history("versionId") ON DELETE SET NULL;


--
-- Name: dynamic_credential_user_entry FK_945ba70b342a066d1306b12ccd2; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_user_entry
    ADD CONSTRAINT "FK_945ba70b342a066d1306b12ccd2" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: folder_tag FK_94a60854e06f2897b2e0d39edba; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder_tag
    ADD CONSTRAINT "FK_94a60854e06f2897b2e0d39edba" FOREIGN KEY ("folderId") REFERENCES public.folder(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_locks FK_9594c0983cfee1c8ff49b05848b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_locks
    ADD CONSTRAINT "FK_9594c0983cfee1c8ff49b05848b" FOREIGN KEY ("resourceId") REFERENCES public.agents_resources(id) ON DELETE CASCADE;


--
-- Name: execution_annotations FK_97f863fa83c4786f19565084960; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotations
    ADD CONSTRAINT "FK_97f863fa83c4786f19565084960" FOREIGN KEY ("executionId") REFERENCES public.execution_entity(id) ON DELETE CASCADE;


--
-- Name: chat_hub_agents FK_9c61ad497dcbae499c96a6a78ba; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_agents
    ADD CONSTRAINT "FK_9c61ad497dcbae499c96a6a78ba" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE SET NULL;


--
-- Name: agent_eval_rating FK_9cadae6591c64498f1b58a2cef3; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_rating
    ADD CONSTRAINT "FK_9cadae6591c64498f1b58a2cef3" FOREIGN KEY ("resultId") REFERENCES public.agent_eval_result(id) ON DELETE CASCADE;


--
-- Name: workflow_review_activity_comment FK_9cfac4b106553d0930a1962bea0; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity_comment
    ADD CONSTRAINT "FK_9cfac4b106553d0930a1962bea0" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: agent_eval_dataset FK_9d3a6fd750f7746de453cf4d5ed; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_dataset
    ADD CONSTRAINT "FK_9d3a6fd750f7746de453cf4d5ed" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_sessions FK_9f9293d9f552496c40e0d1a8f80; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_sessions
    ADD CONSTRAINT "FK_9f9293d9f552496c40e0d1a8f80" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE SET NULL;


--
-- Name: agent_workflow_dependency FK_a2694df196a66064edbdbe38b94; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_workflow_dependency
    ADD CONSTRAINT "FK_a2694df196a66064edbdbe38b94" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: agents FK_a30d560207c4071d98aa03c179c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents
    ADD CONSTRAINT "FK_a30d560207c4071d98aa03c179c" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: execution_annotation_tags FK_a3697779b366e131b2bbdae2976; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotation_tags
    ADD CONSTRAINT "FK_a3697779b366e131b2bbdae2976" FOREIGN KEY ("tagId") REFERENCES public.annotation_tag_entity(id) ON DELETE CASCADE;


--
-- Name: dynamic_credential_user_entry FK_a36dc616fabc3f736bb82410a22; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_user_entry
    ADD CONSTRAINT "FK_a36dc616fabc3f736bb82410a22" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: shared_workflow FK_a45ea5f27bcfdc21af9b4188560; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_workflow
    ADD CONSTRAINT "FK_a45ea5f27bcfdc21af9b4188560" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: evaluation_collection FK_a48ce930c3bc7604894b8f0eaad; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_collection
    ADD CONSTRAINT "FK_a48ce930c3bc7604894b8f0eaad" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: workflow_dependency FK_a4ff2d9b9628ea988fa9e7d0bf8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_dependency
    ADD CONSTRAINT "FK_a4ff2d9b9628ea988fa9e7d0bf8" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: oauth_user_consents FK_a651acea2f6c97f8c4514935486; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_user_consents
    ADD CONSTRAINT "FK_a651acea2f6c97f8c4514935486" FOREIGN KEY ("clientId") REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: oauth_refresh_tokens FK_a699f3ed9fd0c1b19bc2608ac53; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT "FK_a699f3ed9fd0c1b19bc2608ac53" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: dynamic_credential_entry FK_a6d1dd080958304a47a02952aab; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_entry
    ADD CONSTRAINT "FK_a6d1dd080958304a47a02952aab" FOREIGN KEY (credential_id) REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_observations FK_a80e0ee839a2f10ba4b86e19998; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observations
    ADD CONSTRAINT "FK_a80e0ee839a2f10ba4b86e19998" FOREIGN KEY ("supersededBy") REFERENCES public.instance_ai_observations(id);


--
-- Name: folder FK_a8260b0b36939c6247f385b8221; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder
    ADD CONSTRAINT "FK_a8260b0b36939c6247f385b8221" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_authors FK_a9c79ab0c352aa0496c39ea56a4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_authors
    ADD CONSTRAINT "FK_a9c79ab0c352aa0496c39ea56a4" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes FK_aa8d3560484944c19bdf79ffa16; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT "FK_aa8d3560484944c19bdf79ffa16" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_candidates FK_ac7ada75df7cc8ced228921d5a9; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_candidates
    ADD CONSTRAINT "FK_ac7ada75df7cc8ced228921d5a9" FOREIGN KEY ("threadId") REFERENCES public.agents_threads(id) ON DELETE CASCADE;


--
-- Name: agent_files FK_aca4514cb500494b64356c2e164; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_files
    ADD CONSTRAINT "FK_aca4514cb500494b64356c2e164" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_acf8926098f063cdbbad8497fd1; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_acf8926098f063cdbbad8497fd1" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE SET NULL;


--
-- Name: agent_execution FK_add2432fb6034cc18b6af299dce; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution
    ADD CONSTRAINT "FK_add2432fb6034cc18b6af299dce" FOREIGN KEY ("threadId") REFERENCES public.agent_execution_threads(id) ON DELETE CASCADE;


--
-- Name: ai_preference FK_aeb2ce3354b55bd61c8d7e17169; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_preference
    ADD CONSTRAINT "FK_aeb2ce3354b55bd61c8d7e17169" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: oauth_refresh_tokens FK_b388696ce4d8be7ffbe8d3e4b69; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.oauth_refresh_tokens
    ADD CONSTRAINT "FK_b388696ce4d8be7ffbe8d3e4b69" FOREIGN KEY ("clientId") REFERENCES public.oauth_clients(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_candidates FK_b3d0f5fe54565580bc1f5febb6e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_candidates
    ADD CONSTRAINT "FK_b3d0f5fe54565580bc1f5febb6e" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: workflow_publish_history FK_b4cfbc7556d07f36ca177f5e473; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publish_history
    ADD CONSTRAINT "FK_b4cfbc7556d07f36ca177f5e473" FOREIGN KEY ("versionId") REFERENCES public.workflow_history("versionId") ON DELETE SET NULL;


--
-- Name: agent_task_run_lock FK_b57a2862ae869aab24e54cefd48; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_run_lock
    ADD CONSTRAINT "FK_b57a2862ae869aab24e54cefd48" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: workflow_publication_trigger_status FK_b7b496d8d1a21158c65f475cd88; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publication_trigger_status
    ADD CONSTRAINT "FK_b7b496d8d1a21158c65f475cd88" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: chat_hub_tools FK_b8030b47af9213f1fd15450fb7f; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_tools
    ADD CONSTRAINT "FK_b8030b47af9213f1fd15450fb7f" FOREIGN KEY ("ownerId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_reviewers FK_ba29e1cc5cdba43ce7b810b3ddd; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_reviewers
    ADD CONSTRAINT "FK_ba29e1cc5cdba43ce7b810b3ddd" FOREIGN KEY ("workflowReviewRequestId") REFERENCES public.workflow_review_request(id) ON DELETE CASCADE;


--
-- Name: instance_ai_pending_confirmations FK_ba67ee8dc311830a2eea89b6e96; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_pending_confirmations
    ADD CONSTRAINT "FK_ba67ee8dc311830a2eea89b6e96" FOREIGN KEY ("threadId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: role_mapping_rule FK_bb66e404c35996b0d6946177501; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule
    ADD CONSTRAINT "FK_bb66e404c35996b0d6946177501" FOREIGN KEY (role) REFERENCES public.role(slug) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: project_secrets_provider_access FK_bd264b81209355b543878deedb1; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_secrets_provider_access
    ADD CONSTRAINT "FK_bd264b81209355b543878deedb1" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_publish_history FK_c01316f8c2d7101ec4fa9809267; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publish_history
    ADD CONSTRAINT "FK_c01316f8c2d7101ec4fa9809267" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: execution_annotation_tags FK_c1519757391996eb06064f0e7c8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_annotation_tags
    ADD CONSTRAINT "FK_c1519757391996eb06064f0e7c8" FOREIGN KEY ("annotationId") REFERENCES public.execution_annotations(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request FK_c218d1df94adc3b169dee3cc06c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request
    ADD CONSTRAINT "FK_c218d1df94adc3b169dee3cc06c" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_authors FK_c255ae5087010c1ab73ac8684af; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_authors
    ADD CONSTRAINT "FK_c255ae5087010c1ab73ac8684af" FOREIGN KEY ("workflowReviewRequestId") REFERENCES public.workflow_review_request(id) ON DELETE CASCADE;


--
-- Name: data_table FK_c2a794257dee48af7c9abf681de; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.data_table
    ADD CONSTRAINT "FK_c2a794257dee48af7c9abf681de" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: agents_memory_entry_sources FK_c38e8a57a36b880e39a52ada2e8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "FK_c38e8a57a36b880e39a52ada2e8" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: project_relation FK_c6b99592dc96b0d836d7a21db91; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project_relation
    ADD CONSTRAINT "FK_c6b99592dc96b0d836d7a21db91" FOREIGN KEY (role) REFERENCES public.role(slug);


--
-- Name: agents_memory_entry_sources FK_cb7c15d22fd068a0806aa57fc03; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_sources
    ADD CONSTRAINT "FK_cb7c15d22fd068a0806aa57fc03" FOREIGN KEY ("observationId") REFERENCES public.agents_observations(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_chat_hub_messages_agentId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_chat_hub_messages_agentId" FOREIGN KEY ("agentId") REFERENCES public.chat_hub_agents(id) ON DELETE SET NULL;


--
-- Name: chat_hub_sessions FK_chat_hub_sessions_agentId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_sessions
    ADD CONSTRAINT "FK_chat_hub_sessions_agentId" FOREIGN KEY ("agentId") REFERENCES public.chat_hub_agents(id) ON DELETE SET NULL;


--
-- Name: agents_observations FK_d206432be97b7ed88d187479b1b; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_observations
    ADD CONSTRAINT "FK_d206432be97b7ed88d187479b1b" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: agent_background_job FK_d46c6f00730c2ef8bcb6ee24b67; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_background_job
    ADD CONSTRAINT "FK_d46c6f00730c2ef8bcb6ee24b67" FOREIGN KEY ("parentAgentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request FK_d53ef208e6055f328dd7b897e51; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request
    ADD CONSTRAINT "FK_d53ef208e6055f328dd7b897e51" FOREIGN KEY ("closedById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: instance_ai_observations FK_d54fc84a6c8ac91b5e0db0378a4; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observations
    ADD CONSTRAINT "FK_d54fc84a6c8ac91b5e0db0378a4" FOREIGN KEY ("observationScopeId") REFERENCES public.instance_ai_threads(id) ON DELETE CASCADE;


--
-- Name: dynamic_credential_entry FK_d61a12235d268a49af6a3c09c13; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.dynamic_credential_entry
    ADD CONSTRAINT "FK_d61a12235d268a49af6a3c09c13" FOREIGN KEY (resolver_id) REFERENCES public.dynamic_credential_resolver(id) ON DELETE CASCADE;


--
-- Name: evaluation_collection FK_d634a0c93fd7de68a87eab951b2; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_collection
    ADD CONSTRAINT "FK_d634a0c93fd7de68a87eab951b2" FOREIGN KEY ("evaluationConfigId") REFERENCES public.evaluation_config(id) ON DELETE CASCADE;


--
-- Name: test_run FK_d6870d3b6e4c185d33926f423c8; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_run
    ADD CONSTRAINT "FK_d6870d3b6e4c185d33926f423c8" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: shared_workflow FK_daa206a04983d47d0a9c34649ce; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.shared_workflow
    ADD CONSTRAINT "FK_daa206a04983d47d0a9c34649ce" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_observations FK_daef2195a4a846eb70eed15e039; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_observations
    ADD CONSTRAINT "FK_daef2195a4a846eb70eed15e039" FOREIGN KEY ("parentId") REFERENCES public.instance_ai_observations(id);


--
-- Name: folder_tag FK_dc88164176283de80af47621746; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.folder_tag
    ADD CONSTRAINT "FK_dc88164176283de80af47621746" FOREIGN KEY ("tagId") REFERENCES public.tag_entity(id) ON DELETE CASCADE;


--
-- Name: role_mapping_rule_project FK_dd7ce4dfa09e95b36a626bd9de3; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_mapping_rule_project
    ADD CONSTRAINT "FK_dd7ce4dfa09e95b36a626bd9de3" FOREIGN KEY ("roleMappingRuleId") REFERENCES public.role_mapping_rule(id) ON DELETE CASCADE;


--
-- Name: workflow_published_version FK_df3428a541b802d6a63ac56e330; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_published_version
    ADD CONSTRAINT "FK_df3428a541b802d6a63ac56e330" FOREIGN KEY ("publishedVersionId") REFERENCES public.workflow_history("versionId") ON DELETE RESTRICT;


--
-- Name: instance_ai_pending_confirmations FK_df5fd25c8bbfd2b042602600d8e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_pending_confirmations
    ADD CONSTRAINT "FK_df5fd25c8bbfd2b042602600d8e" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: agent_eval_rating FK_e06a7408573a3e152e673977d2c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_rating
    ADD CONSTRAINT "FK_e06a7408573a3e152e673977d2c" FOREIGN KEY ("ratedById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: user_api_keys FK_e131705cbbc8fb589889b02d457; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.user_api_keys
    ADD CONSTRAINT "FK_e131705cbbc8fb589889b02d457" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_e22538eb50a71a17954cd7e076c; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_e22538eb50a71a17954cd7e076c" FOREIGN KEY ("sessionId") REFERENCES public.chat_hub_sessions(id) ON DELETE CASCADE;


--
-- Name: workflow_review_request_workflow FK_e44b652e6dc99ef1364a2d85504; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_workflow
    ADD CONSTRAINT "FK_e44b652e6dc99ef1364a2d85504" FOREIGN KEY ("workflowReviewRequestId") REFERENCES public.workflow_review_request(id) ON DELETE CASCADE;


--
-- Name: test_case_execution FK_e48965fac35d0f5b9e7f51d8c44; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_case_execution
    ADD CONSTRAINT "FK_e48965fac35d0f5b9e7f51d8c44" FOREIGN KEY ("executionId") REFERENCES public.execution_entity(id) ON DELETE SET NULL;


--
-- Name: agent_workflow_dependency FK_e5511a5e9eab71b7e516bdc04e9; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_workflow_dependency
    ADD CONSTRAINT "FK_e5511a5e9eab71b7e516bdc04e9" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: chat_hub_messages FK_e5d1fa722c5a8d38ac204746662; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_messages
    ADD CONSTRAINT "FK_e5d1fa722c5a8d38ac204746662" FOREIGN KEY ("previousMessageId") REFERENCES public.chat_hub_messages(id) ON DELETE CASCADE;


--
-- Name: chat_hub_session_tools FK_e649bf1295f4ed8d4299ed290f9; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_session_tools
    ADD CONSTRAINT "FK_e649bf1295f4ed8d4299ed290f9" FOREIGN KEY ("sessionId") REFERENCES public.chat_hub_sessions(id) ON DELETE CASCADE;


--
-- Name: agent_chat_subscriptions FK_e79153bd179c011e779d5016796; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_chat_subscriptions
    ADD CONSTRAINT "FK_e79153bd179c011e779d5016796" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: ai_preference FK_e9059770c01bfda6062d78d9f8e; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.ai_preference
    ADD CONSTRAINT "FK_e9059770c01bfda6062d78d9f8e" FOREIGN KEY ("userId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: chat_hub_sessions FK_e9ecf8ede7d989fcd18790fe36a; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.chat_hub_sessions
    ADD CONSTRAINT "FK_e9ecf8ede7d989fcd18790fe36a" FOREIGN KEY ("ownerId") REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: user FK_eaea92ee7bfb9c1b6cd01505d56; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT "FK_eaea92ee7bfb9c1b6cd01505d56" FOREIGN KEY ("roleSlug") REFERENCES public.role(slug);


--
-- Name: agent_eval_dataset FK_eda9e5fa5558d3f16bc2f6c21b6; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_eval_dataset
    ADD CONSTRAINT "FK_eda9e5fa5558d3f16bc2f6c21b6" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: workflow_publication_trigger_status FK_ef1994db9d0ac1b6a5c89b5f729; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_publication_trigger_status
    ADD CONSTRAINT "FK_ef1994db9d0ac1b6a5c89b5f729" FOREIGN KEY ("versionId") REFERENCES public.workflow_history("versionId") ON DELETE CASCADE;


--
-- Name: agent_execution_threads FK_f00b52d74fe11838e1fe086deea; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_execution_threads
    ADD CONSTRAINT "FK_f00b52d74fe11838e1fe086deea" FOREIGN KEY ("taskVersionId") REFERENCES public.agent_history("versionId") ON DELETE SET NULL;


--
-- Name: agents_memory_entry_candidates FK_f1857f6716aa258393dd6f33243; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agents_memory_entry_candidates
    ADD CONSTRAINT "FK_f1857f6716aa258393dd6f33243" FOREIGN KEY ("sourceMessageId") REFERENCES public.agents_messages(id) ON DELETE SET NULL;


--
-- Name: evaluation_collection FK_f4561f38b5a22a4f090d5cd3eae; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_collection
    ADD CONSTRAINT "FK_f4561f38b5a22a4f090d5cd3eae" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: agent_task_definition FK_f45d0535a2ed59b6c2dd6da98a0; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_task_definition
    ADD CONSTRAINT "FK_f45d0535a2ed59b6c2dd6da98a0" FOREIGN KEY ("agentId") REFERENCES public.agents(id) ON DELETE CASCADE;


--
-- Name: workflow_review_activity FK_fcf78b037a72fc7aa01ab237e08; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_activity
    ADD CONSTRAINT "FK_fcf78b037a72fc7aa01ab237e08" FOREIGN KEY ("createdById") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: evaluation_config FK_fd7542bb123074760285dc1bbf3; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.evaluation_config
    ADD CONSTRAINT "FK_fd7542bb123074760285dc1bbf3" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: agent_credential_dependency FK_fec7ee37062350d6a4a2979327d; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.agent_credential_dependency
    ADD CONSTRAINT "FK_fec7ee37062350d6a4a2979327d" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE CASCADE;


--
-- Name: instance_ai_threads FK_instance_ai_threads_projectId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_ai_threads
    ADD CONSTRAINT "FK_instance_ai_threads_projectId" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: instance_credential_assignment FK_instance_credential_assignment_credential; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.instance_credential_assignment
    ADD CONSTRAINT "FK_instance_credential_assignment_credential" FOREIGN KEY ("credentialId") REFERENCES public.credentials_entity(id) ON DELETE RESTRICT;


--
-- Name: poller_state FK_poller_state_workflowId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.poller_state
    ADD CONSTRAINT "FK_poller_state_workflowId" FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: promotion_config FK_promotion_config_connectionId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_config
    ADD CONSTRAINT "FK_promotion_config_connectionId" FOREIGN KEY ("connectionId") REFERENCES public.promotion_connection(id) ON DELETE CASCADE;


--
-- Name: promotion_connection_project FK_promotion_connection_project_connectionId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_connection_project
    ADD CONSTRAINT "FK_promotion_connection_project_connectionId" FOREIGN KEY ("connectionId") REFERENCES public.promotion_connection(id) ON DELETE CASCADE;


--
-- Name: promotion_connection_project FK_promotion_connection_project_projectId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_connection_project
    ADD CONSTRAINT "FK_promotion_connection_project_projectId" FOREIGN KEY ("projectId") REFERENCES public.project(id) ON DELETE CASCADE;


--
-- Name: promotion_connection FK_promotion_connection_providerId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.promotion_connection
    ADD CONSTRAINT "FK_promotion_connection_providerId" FOREIGN KEY ("providerId") REFERENCES public.promotion_provider(id) ON DELETE RESTRICT;


--
-- Name: role_scope FK_role; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_scope
    ADD CONSTRAINT "FK_role" FOREIGN KEY ("roleSlug") REFERENCES public.role(slug) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: scheduled_task FK_scheduled_task_jobId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.scheduled_task
    ADD CONSTRAINT "FK_scheduled_task_jobId" FOREIGN KEY ("jobId") REFERENCES public.scheduled_job(id) ON DELETE CASCADE;


--
-- Name: role_scope FK_scope; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.role_scope
    ADD CONSTRAINT "FK_scope" FOREIGN KEY ("scopeSlug") REFERENCES public.scope(slug) ON UPDATE CASCADE ON DELETE CASCADE;


--
-- Name: test_run FK_test_run_collection_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_run
    ADD CONSTRAINT "FK_test_run_collection_id" FOREIGN KEY ("collectionId") REFERENCES public.evaluation_collection(id) ON DELETE SET NULL;


--
-- Name: test_run FK_test_run_evaluation_config_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.test_run
    ADD CONSTRAINT "FK_test_run_evaluation_config_id" FOREIGN KEY ("evaluationConfigId") REFERENCES public.evaluation_config(id) ON DELETE SET NULL;


--
-- Name: workflow_review_request_workflow FK_workflow_review_request_workflow_baselineVersionId; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_review_request_workflow
    ADD CONSTRAINT "FK_workflow_review_request_workflow_baselineVersionId" FOREIGN KEY ("baselineVersionId") REFERENCES public.workflow_history("versionId") ON DELETE SET NULL;


--
-- Name: auth_identity auth_identity_userId_fkey; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.auth_identity
    ADD CONSTRAINT "auth_identity_userId_fkey" FOREIGN KEY ("userId") REFERENCES public."user"(id);


--
-- Name: credentials_entity credentials_entity_resolverId_foreign; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.credentials_entity
    ADD CONSTRAINT "credentials_entity_resolverId_foreign" FOREIGN KEY ("resolverId") REFERENCES public.dynamic_credential_resolver(id) ON DELETE SET NULL;


--
-- Name: execution_data execution_data_fk; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_data
    ADD CONSTRAINT execution_data_fk FOREIGN KEY ("executionId") REFERENCES public.execution_entity(id) ON DELETE CASCADE;


--
-- Name: execution_entity fk_execution_entity_workflow_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.execution_entity
    ADD CONSTRAINT fk_execution_entity_workflow_id FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: webhook_entity fk_webhook_entity_workflow_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.webhook_entity
    ADD CONSTRAINT fk_webhook_entity_workflow_id FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: workflow_entity fk_workflow_parent_folder; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflow_entity
    ADD CONSTRAINT fk_workflow_parent_folder FOREIGN KEY ("parentFolderId") REFERENCES public.folder(id) ON DELETE CASCADE;


--
-- Name: workflows_tags fk_workflows_tags_tag_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflows_tags
    ADD CONSTRAINT fk_workflows_tags_tag_id FOREIGN KEY ("tagId") REFERENCES public.tag_entity(id) ON DELETE CASCADE;


--
-- Name: workflows_tags fk_workflows_tags_workflow_id; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.workflows_tags
    ADD CONSTRAINT fk_workflows_tags_workflow_id FOREIGN KEY ("workflowId") REFERENCES public.workflow_entity(id) ON DELETE CASCADE;


--
-- Name: project projects_creatorId_foreign; Type: FK CONSTRAINT; Schema: public; Owner: n8n
--

ALTER TABLE ONLY public.project
    ADD CONSTRAINT "projects_creatorId_foreign" FOREIGN KEY ("creatorId") REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: geo_response geo_response_is_id_fkey; Type: FK CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.geo_response
    ADD CONSTRAINT geo_response_is_id_fkey FOREIGN KEY (is_id) REFERENCES core.ai_task(task_id);


--
-- Name: wix_order_item wix_order_item_siparis_id_fkey; Type: FK CONSTRAINT; Schema: raw; Owner: n8n
--

ALTER TABLE ONLY raw.wix_order_item
    ADD CONSTRAINT wix_order_item_siparis_id_fkey FOREIGN KEY (siparis_id) REFERENCES raw.wix_order(siparis_id) ON DELETE CASCADE;


--
-- Name: SCHEMA core; Type: ACL; Schema: -; Owner: n8n
--

GRANT USAGE ON SCHEMA core TO ai_reader;
GRANT USAGE ON SCHEMA core TO ai_writer;
GRANT USAGE ON SCHEMA core TO human_approver;
GRANT USAGE ON SCHEMA core TO action_executor;
GRANT USAGE ON SCHEMA core TO function_owner;


--
-- Name: SCHEMA mart; Type: ACL; Schema: -; Owner: n8n
--

GRANT USAGE ON SCHEMA mart TO ai_reader;


--
-- Name: FUNCTION ai_bulgu_gorev_ac(p_slug text, p_sebep text, p_oncelik integer); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_bulgu_gorev_ac(p_slug text, p_sebep text, p_oncelik integer) FROM PUBLIC;


--
-- Name: FUNCTION ai_claim_approved_action(p_worker_id text, p_lease_seconds integer); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_claim_approved_action(p_worker_id text, p_lease_seconds integer) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_claim_approved_action(p_worker_id text, p_lease_seconds integer) TO action_executor;


--
-- Name: FUNCTION ai_claim_task(p_worker_id text, p_lease_seconds integer, p_task_type text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_claim_task(p_worker_id text, p_lease_seconds integer, p_task_type text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_claim_task(p_worker_id text, p_lease_seconds integer, p_task_type text) TO ai_writer;


--
-- Name: FUNCTION ai_complete_action_execution(p_execution_id bigint, p_lease_token uuid, p_result_class text, p_result_summary text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_complete_action_execution(p_execution_id bigint, p_lease_token uuid, p_result_class text, p_result_summary text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_complete_action_execution(p_execution_id bigint, p_lease_token uuid, p_result_class text, p_result_summary text) TO action_executor;


--
-- Name: FUNCTION ai_complete_task_with_proposed_decision(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_karar_tipi text, p_oneri text, p_anlik_id_text text, p_kanit_kalitesi text, p_yanlislama_kosulu text, p_urun text, p_kanal text, p_beklenen_etki text, p_risk text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_complete_task_with_proposed_decision(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_karar_tipi text, p_oneri text, p_anlik_id_text text, p_kanit_kalitesi text, p_yanlislama_kosulu text, p_urun text, p_kanal text, p_beklenen_etki text, p_risk text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_complete_task_with_proposed_decision(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_karar_tipi text, p_oneri text, p_anlik_id_text text, p_kanit_kalitesi text, p_yanlislama_kosulu text, p_urun text, p_kanal text, p_beklenen_etki text, p_risk text) TO ai_writer;


--
-- Name: FUNCTION ai_decide_action(p_action_id bigint, p_decision text, p_reason text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_decide_action(p_action_id bigint, p_decision text, p_reason text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_decide_action(p_action_id bigint, p_decision text, p_reason text) TO human_approver;


--
-- Name: FUNCTION ai_enqueue_task(p_source_type text, p_source_id bigint, p_task_type text, p_idempotency_key text, p_context_profile text, p_priority integer, p_eligible_after timestamp with time zone, p_ai_enqueue boolean, p_enqueue_reason text, p_cutoff_version text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_enqueue_task(p_source_type text, p_source_id bigint, p_task_type text, p_idempotency_key text, p_context_profile text, p_priority integer, p_eligible_after timestamp with time zone, p_ai_enqueue boolean, p_enqueue_reason text, p_cutoff_version text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_enqueue_task(p_source_type text, p_source_id bigint, p_task_type text, p_idempotency_key text, p_context_profile text, p_priority integer, p_eligible_after timestamp with time zone, p_ai_enqueue boolean, p_enqueue_reason text, p_cutoff_version text) TO human_approver;


--
-- Name: FUNCTION ai_executive_brief_context(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_executive_brief_context() FROM PUBLIC;


--
-- Name: FUNCTION ai_executive_brief_existing(p_key text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_executive_brief_existing(p_key text) FROM PUBLIC;


--
-- Name: FUNCTION ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_fail_task(p_task_id bigint, p_lease_token uuid, p_result_class text, p_fail_reason text) TO ai_writer;


--
-- Name: FUNCTION ai_generate_company_intelligence_task(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_generate_company_intelligence_task() FROM PUBLIC;


--
-- Name: FUNCTION ai_generate_measurement_plans(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_generate_measurement_plans() FROM PUBLIC;


--
-- Name: FUNCTION ai_generated_question_existing(text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_generated_question_existing(text) FROM PUBLIC;


--
-- Name: FUNCTION ai_get_model_policy(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_get_model_policy() FROM PUBLIC;


--
-- Name: FUNCTION ai_get_pending_actions(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_get_pending_actions() FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_get_pending_actions() TO human_approver;


--
-- Name: FUNCTION ai_jsonb_has_forbidden_key(p_value jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_jsonb_has_forbidden_key(p_value jsonb) FROM PUBLIC;


--
-- Name: FUNCTION ai_load_jarvis_task_state(p_task_id bigint); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_load_jarvis_task_state(p_task_id bigint) FROM PUBLIC;


--
-- Name: FUNCTION ai_log_provider_attempt(p_task_id bigint, p_provider text, p_model text, p_attempt integer, p_started_at timestamp with time zone, p_finished_at timestamp with time zone, p_latency_ms integer, p_result_class text, p_rate_limit boolean, p_timeout boolean, p_validation_result text, p_failover_reason text, p_context_profile text, p_context_version text, p_context_hash text, p_safe_summary text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_log_provider_attempt(p_task_id bigint, p_provider text, p_model text, p_attempt integer, p_started_at timestamp with time zone, p_finished_at timestamp with time zone, p_latency_ms integer, p_result_class text, p_rate_limit boolean, p_timeout boolean, p_validation_result text, p_failover_reason text, p_context_profile text, p_context_version text, p_context_hash text, p_safe_summary text) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_log_provider_attempt(p_task_id bigint, p_provider text, p_model text, p_attempt integer, p_started_at timestamp with time zone, p_finished_at timestamp with time zone, p_latency_ms integer, p_result_class text, p_rate_limit boolean, p_timeout boolean, p_validation_result text, p_failover_reason text, p_context_profile text, p_context_version text, p_context_hash text, p_safe_summary text) TO ai_writer;


--
-- Name: FUNCTION ai_log_provider_usage(p_task_id bigint, p_provider text, p_attempt integer, p_input_tokens integer, p_output_tokens integer, p_estimated boolean); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_log_provider_usage(p_task_id bigint, p_provider text, p_attempt integer, p_input_tokens integer, p_output_tokens integer, p_estimated boolean) FROM PUBLIC;


--
-- Name: FUNCTION ai_orchestrator_health(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_orchestrator_health() FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_orchestrator_health() TO ai_reader;


--
-- Name: FUNCTION ai_process_evidence_followups(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_process_evidence_followups() FROM PUBLIC;


--
-- Name: FUNCTION ai_propose_action(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_action_type text, p_payload jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_propose_action(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_action_type text, p_payload jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION core.ai_propose_action(p_task_id bigint, p_lease_token uuid, p_idempotency_key text, p_action_type text, p_payload jsonb) TO ai_writer;


--
-- Name: FUNCTION ai_provider_allowed(p text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_provider_allowed(p text) FROM PUBLIC;


--
-- Name: FUNCTION ai_question_context(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_question_context() FROM PUBLIC;


--
-- Name: FUNCTION ai_route_question(p_soru bigint, p_departments text[], p_reason text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_route_question(p_soru bigint, p_departments text[], p_reason text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_claim(p_worker text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_claim(p_worker text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_complete(p_job bigint, p_token uuid, p_result text, p_type text, p_reason text, p_ref text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_complete(p_job bigint, p_token uuid, p_result text, p_type text, p_reason text, p_ref text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_context(p_job bigint, p_token uuid); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_context(p_job bigint, p_token uuid) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_fail(p_job bigint, p_token uuid, p_error text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_fail(p_job bigint, p_token uuid, p_error text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_log(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_log(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_log_usage(p_job bigint, p_provider text, p_input integer, p_output integer, p_estimated boolean); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_log_usage(p_job bigint, p_provider text, p_input integer, p_output integer, p_estimated boolean) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_log_v2(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text, p_hash text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_log_v2(p_job bigint, p_token uuid, p_provider text, p_model text, p_started timestamp with time zone, p_finished timestamp with time zone, p_class text, p_validation text, p_reason text, p_hash text) FROM PUBLIC;


--
-- Name: FUNCTION ai_rt_sync(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_rt_sync() FROM PUBLIC;


--
-- Name: FUNCTION ai_save_jarvis_task_state(p_task_id bigint, p_expected_version bigint, p_state jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_save_jarvis_task_state(p_task_id bigint, p_expected_version bigint, p_state jsonb) FROM PUBLIC;


--
-- Name: FUNCTION ai_write_executive_brief(p_key text, p_provider text, p_model text, p_hash text, p_content jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_write_executive_brief(p_key text, p_provider text, p_model text, p_hash text, p_content jsonb) FROM PUBLIC;


--
-- Name: FUNCTION ai_write_generated_question(p_key text, p_provider text, p_hash text, p_data jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.ai_write_generated_question(p_key text, p_provider text, p_hash text, p_data jsonb) FROM PUBLIC;


--
-- Name: FUNCTION human_conclude_decision(p_karar bigint, p_metric text, p_baseline numeric, p_observed numeric, p_actor text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.human_conclude_decision(p_karar bigint, p_metric text, p_baseline numeric, p_observed numeric, p_actor text) FROM PUBLIC;


--
-- Name: FUNCTION human_decide_karar(p_karar bigint, p_decision text, p_note text, p_approver text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.human_decide_karar(p_karar bigint, p_decision text, p_note text, p_approver text) FROM PUBLIC;


--
-- Name: FUNCTION human_supersede_decision(p_old bigint, p_canonical bigint, p_approver text, p_reason text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.human_supersede_decision(p_old bigint, p_canonical bigint, p_approver text, p_reason text) FROM PUBLIC;


--
-- Name: FUNCTION jarvis_decide_company_action(p_action_id bigint, p_decision text, p_reason text, p_expected_hash text); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.jarvis_decide_company_action(p_action_id bigint, p_decision text, p_reason text, p_expected_hash text) FROM PUBLIC;


--
-- Name: FUNCTION jarvis_record_company_vote(); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.jarvis_record_company_vote() FROM PUBLIC;


--
-- Name: FUNCTION jarvis_sync_company_action(); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.jarvis_sync_company_action() FROM PUBLIC;


--
-- Name: FUNCTION jarvis_sync_personal_action(); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.jarvis_sync_personal_action() FROM PUBLIC;


--
-- Name: FUNCTION lead_saklama_temizligi(); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.lead_saklama_temizligi() FROM PUBLIC;


--
-- Name: FUNCTION lead_zenginlestir(p_il text); Type: ACL; Schema: core; Owner: n8n
--

REVOKE ALL ON FUNCTION core.lead_zenginlestir(p_il text) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_al(p_worker text, p_kira_s integer); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_al(p_worker text, p_kira_s integer) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_bitir(p_is_id bigint, p_jeton uuid, p_metin text, p_dosyalar jsonb, p_ekran text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_bitir(p_is_id bigint, p_jeton uuid, p_metin text, p_dosyalar jsonb, p_ekran text) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_ekle(p_isteyen text, p_hedef text, p_istem text, p_idempotency_key text, p_girdi_dosyalari jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_ekle(p_isteyen text, p_hedef text, p_istem text, p_idempotency_key text, p_girdi_dosyalari jsonb) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_getir(p_is_id bigint); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_getir(p_is_id bigint) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_hata(p_is_id bigint, p_jeton uuid, p_hata text, p_ekran text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_hata(p_is_id bigint, p_jeton uuid, p_hata text, p_ekran text) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_insan(p_is_id bigint, p_jeton uuid, p_sebep text, p_ekran text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_insan(p_is_id bigint, p_jeton uuid, p_sebep text, p_ekran text) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_isi_sunuldu(p_is_id bigint, p_slug text, p_uyum text); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_isi_sunuldu(p_is_id bigint, p_slug text, p_uyum text) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_nabiz_oku(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_nabiz_oku() FROM PUBLIC;


--
-- Name: FUNCTION tarayici_nabiz_yaz(p_worker text, p_ayrinti jsonb); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_nabiz_yaz(p_worker text, p_ayrinti jsonb) FROM PUBLIC;


--
-- Name: FUNCTION tarayici_sayim(); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_sayim() FROM PUBLIC;


--
-- Name: FUNCTION tarayici_sunulacak(p_limit integer); Type: ACL; Schema: core; Owner: function_owner
--

REVOKE ALL ON FUNCTION core.tarayici_sunulacak(p_limit integer) FROM PUBLIC;


--
-- Name: TABLE ai_calisma_log; Type: ACL; Schema: core; Owner: n8n
--

GRANT INSERT ON TABLE core.ai_calisma_log TO function_owner;


--
-- Name: SEQUENCE ai_calisma_log_calisma_id_seq; Type: ACL; Schema: core; Owner: n8n
--

GRANT USAGE ON SEQUENCE core.ai_calisma_log_calisma_id_seq TO function_owner;


--
-- Name: TABLE ayar; Type: ACL; Schema: core; Owner: n8n
--

GRANT SELECT ON TABLE core.ayar TO ai_reader;


--
-- Name: TABLE kanit_anlik; Type: ACL; Schema: core; Owner: n8n
--

GRANT SELECT ON TABLE core.kanit_anlik TO ai_reader;


--
-- Name: TABLE karar; Type: ACL; Schema: core; Owner: n8n
--

GRANT SELECT,INSERT ON TABLE core.karar TO function_owner;


--
-- Name: SEQUENCE karar_karar_id_seq; Type: ACL; Schema: core; Owner: n8n
--

GRANT USAGE ON SEQUENCE core.karar_karar_id_seq TO function_owner;


--
-- Name: TABLE source_authority; Type: ACL; Schema: core; Owner: n8n
--

GRANT SELECT ON TABLE core.source_authority TO ai_reader;


--
-- Name: TABLE urun_maliyet; Type: ACL; Schema: core; Owner: n8n
--

GRANT SELECT ON TABLE core.urun_maliyet TO ai_reader;


--
-- Name: TABLE acik_isler; Type: ACL; Schema: mart; Owner: n8n
--

GRANT SELECT ON TABLE mart.acik_isler TO ai_reader;


--
-- Name: TABLE karar_ozet; Type: ACL; Schema: mart; Owner: n8n
--

GRANT SELECT ON TABLE mart.karar_ozet TO ai_reader;


--
-- Name: TABLE sirket_gundemi; Type: ACL; Schema: mart; Owner: n8n
--

GRANT SELECT ON TABLE mart.sirket_gundemi TO ai_reader;


--
-- PostgreSQL database dump complete
--

\unrestrict fbh7IIr5r43sldc7ceHEx2gfcFdL1aUDeTO93PMcHMLpGywK3bqacxRNgrc86nB

