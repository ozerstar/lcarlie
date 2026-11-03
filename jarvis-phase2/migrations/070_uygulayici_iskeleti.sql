-- 070 — UYGULAYICI İSKELETİ (sahip kararı 03.11.2026: "hepsini yap")
--
-- ÖNCESİ
-- Onay → uygulama hattı vardı ama tek tür yürütülüyordu: action-worker.js
-- REQUEST_HUMAN_REVIEW dışındaki her işi FAILED_FINAL ile kapatıyordu ve
-- core.ai_claim_approved_action() TÜR AYIRMIYORDU. Yeni bir tür açılsaydı
-- eski işçi onu kapıp başarısız sayardı.
--
-- BU MIGRATION
-- 1. core.ai_claim_approved_action_tipli(): yalnız verilen türleri kapar.
--    Her işçi kendi türlerini alır; tanımadığı işi YAKMAZ.
-- 2. core.ai_action_tavan: tür başına günlük adet ve tutar tavanı.
--    core.ai_action_tavan_dolu() uygulamadan ÖNCE çağrılır. Satırı olmayan
--    tür UYGULANMAZ (varsayılan kapalı).
-- 3. Acil durdurma: core.ai_orchestrator_config 'uygulayici_acik'. false
--    olunca dış dünyaya yazan uygulayıcı HİÇBİR iş kapmaz
--    (action_worker_enabled ise tüm hattı durdurur).
-- 4. core.ai_sistem_onerisi(): bir zamanlayıcının (ör. "zarar eden reklam"
--    dedektörü) onay kuyruğuna öneri düşürmesi. Görev + öneri tek işlemde;
--    tür sözleşmesi yine ai_propose_action içinde doğrulanır.
--    ai_task.source_type listesine 'SISTEM' eklenir: BULGU kotasını
--    (ai_bulgu_gorev_ac) tüketmesin, kaynağı ayrı görünsün.
--
-- NE DEĞİŞMİYOR
-- Hiçbir türün execution_enabled'ı burada açılmaz. Her tür kendi
-- migration'ında, uygulayıcısı + doğrulaması yazıldıktan sonra açılır.
-- Onay kapısı (human_approver, parmak izi) aynen geçerli.
--
-- GERİ ALMA: migrations/rollback/070_uygulayici_iskeleti_ROLLBACK.sql

BEGIN;

ALTER TABLE core.ai_task DROP CONSTRAINT ai_task_source_type_check;
ALTER TABLE core.ai_task ADD CONSTRAINT ai_task_source_type_check
  CHECK (source_type = ANY (ARRAY['ACIK_SORU','BULGU','KARAR','IC_MESAJ','MANUAL','SISTEM']));

CREATE OR REPLACE FUNCTION core.ai_claim_approved_action_tipli(
    p_worker_id text, p_lease_seconds integer, p_types text[])
 RETURNS TABLE(execution_id bigint, action_id bigint, action_type text, payload jsonb,
               execution_key text, lease_token uuid, attempt_count integer)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core', 'pg_temp'
AS $function$
DECLARE v_execution_id bigint; v_enabled boolean;
BEGIN
  SELECT config_value::boolean INTO v_enabled FROM core.ai_orchestrator_config WHERE config_key='action_worker_enabled';
  IF NOT COALESCE(v_enabled,false) THEN RETURN; END IF;
  IF p_worker_id IS NULL OR btrim(p_worker_id)='' THEN RAISE EXCEPTION 'worker id required'; END IF;
  IF p_lease_seconds<30 OR p_lease_seconds>900 THEN RAISE EXCEPTION 'lease seconds out of range'; END IF;
  IF p_types IS NULL OR cardinality(p_types)=0 THEN RAISE EXCEPTION 'action types required'; END IF;
  SELECT e.execution_id INTO v_execution_id
    FROM core.ai_action_execution e
    JOIN core.ai_action_proposal a ON a.action_id=e.action_id
    JOIN core.ai_action_type t ON t.action_type=a.action_type
   WHERE e.state IN ('OPEN','FAILED_RETRYABLE') AND e.attempt_count<e.max_attempts
     AND a.state='APPROVED' AND t.execution_enabled AND a.action_type = ANY(p_types)
   ORDER BY e.execution_id FOR UPDATE OF e SKIP LOCKED LIMIT 1;
  IF v_execution_id IS NULL THEN RETURN; END IF;
  UPDATE core.ai_action_execution e SET state='LEASED',lease_owner=p_worker_id,lease_token=gen_random_uuid(),
         lease_until=clock_timestamp()+make_interval(secs=>p_lease_seconds),attempt_count=e.attempt_count+1
   WHERE e.execution_id=v_execution_id;
  UPDATE core.ai_action_proposal a SET state='EXECUTING' FROM core.ai_action_execution e
   WHERE e.execution_id=v_execution_id AND a.action_id=e.action_id;
  RETURN QUERY SELECT e.execution_id,a.action_id,a.action_type,a.payload,e.execution_key,e.lease_token,e.attempt_count
    FROM core.ai_action_execution e JOIN core.ai_action_proposal a ON a.action_id=e.action_id
   WHERE e.execution_id=v_execution_id;
END $function$;
REVOKE ALL ON FUNCTION core.ai_claim_approved_action_tipli(text,integer,text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_claim_approved_action_tipli(text,integer,text[]) TO action_executor;

CREATE TABLE IF NOT EXISTS core.ai_action_tavan (
  action_type   text PRIMARY KEY REFERENCES core.ai_action_type(action_type),
  gunluk_adet   integer NOT NULL CHECK (gunluk_adet >= 0),
  gunluk_tutar  numeric CHECK (gunluk_tutar IS NULL OR gunluk_tutar >= 0),
  not_metni     text NOT NULL,
  guncelleme    timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE core.ai_action_tavan IS
  'Tur basina gunluk uygulama tavani. Satir yoksa tur UYGULANMAZ (varsayilan kapali).';

CREATE OR REPLACE FUNCTION core.ai_action_tavan_dolu(p_action_type text, p_tutar numeric DEFAULT 0)
 RETURNS text
 LANGUAGE plpgsql
 STABLE
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core', 'pg_temp'
AS $function$
DECLARE t core.ai_action_tavan%ROWTYPE; v_adet int; v_tutar numeric;
BEGIN
  SELECT * INTO t FROM core.ai_action_tavan WHERE action_type=p_action_type;
  IF NOT FOUND THEN RETURN 'tavan tanimsiz: ' || p_action_type; END IF;
  SELECT count(*), COALESCE(sum(NULLIF(a.payload->>'tutar','')::numeric),0) INTO v_adet, v_tutar
    FROM core.ai_action_execution e JOIN core.ai_action_proposal a ON a.action_id=e.action_id
   WHERE a.action_type=p_action_type AND e.state='EXECUTED'
     AND e.finished_at >= date_trunc('day', clock_timestamp());
  IF v_adet >= t.gunluk_adet THEN
    RETURN format('gunluk adet tavani dolu: %s/%s', v_adet, t.gunluk_adet);
  END IF;
  IF t.gunluk_tutar IS NOT NULL AND v_tutar + COALESCE(p_tutar,0) > t.gunluk_tutar THEN
    RETURN format('gunluk tutar tavani dolu: %s + %s > %s', v_tutar, COALESCE(p_tutar,0), t.gunluk_tutar);
  END IF;
  RETURN NULL;
END $function$;
REVOKE ALL ON FUNCTION core.ai_action_tavan_dolu(text,numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_action_tavan_dolu(text,numeric) TO action_executor;

INSERT INTO core.ai_orchestrator_config(config_key, config_value, description)
VALUES ('uygulayici_acik', 'true',
        'Acil durdurma: false iken dis dunyaya yazan uygulayici hicbir onayli isi kapmaz.')
ON CONFLICT (config_key) DO NOTHING;

CREATE OR REPLACE FUNCTION core.ai_sistem_onerisi(
    p_kaynak text, p_action_type text, p_anahtar text, p_payload jsonb, p_sebep text)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core', 'pg_temp'
AS $function$
DECLARE v_task_id bigint; v_token uuid := gen_random_uuid(); v_cutoff text; v_key text;
BEGIN
  IF NOT (pg_has_role(session_user,'ai_writer','MEMBER')
          OR (SELECT rolsuper FROM pg_roles WHERE rolname=session_user)) THEN
    RAISE EXCEPTION 'ai_writer membership required';
  END IF;
  IF p_kaynak IS NULL OR p_kaynak !~ '^[a-z0-9][a-z0-9_-]{2,40}$' THEN RAISE EXCEPTION 'kaynak bicimi gecersiz'; END IF;
  IF p_anahtar IS NULL OR p_anahtar !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{2,120}$' THEN RAISE EXCEPTION 'anahtar bicimi gecersiz'; END IF;
  IF p_sebep IS NULL OR length(btrim(p_sebep)) < 40 THEN
    RAISE EXCEPTION 'sebep en az 40 karakter olmali (ici bos oneri onay degildir)';
  END IF;
  v_key := 'sistem:' || p_kaynak || ':' || p_anahtar;
  -- Ayni anahtar ikinci kez oneri uretmez (tekrar calistirmak guvenli).
  IF EXISTS (SELECT 1 FROM core.ai_task WHERE idempotency_key=v_key) THEN RETURN NULL; END IF;
  SELECT config_value INTO v_cutoff FROM core.ai_orchestrator_config WHERE config_key='cutoff_version';
  INSERT INTO core.ai_task(source_type, source_id, task_type, priority, eligible_after, idempotency_key,
                           cutoff_version, ai_enqueue, enqueue_reason, context_profile,
                           state, lease_owner, lease_token, lease_until, attempt_count)
  VALUES ('SISTEM', ('x' || substr(md5(v_key), 1, 15))::bit(60)::bigint, 'PROPOSE_ACTION', 100,
          clock_timestamp(), v_key, v_cutoff, false, left(btrim(p_sebep), 500), 'default',
          'LEASED', 'sistem:' || p_kaynak, v_token, clock_timestamp() + interval '2 minutes', 1)
  RETURNING task_id INTO v_task_id;
  RETURN core.ai_propose_action(v_task_id, v_token, 'action:' || v_key, p_action_type, p_payload);
END $function$;
REVOKE ALL ON FUNCTION core.ai_sistem_onerisi(text,text,text,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_sistem_onerisi(text,text,text,jsonb,text) TO ai_writer;

COMMIT;
