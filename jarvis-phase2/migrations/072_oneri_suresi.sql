-- 072_oneri_suresi.sql  (04.11.2026)
-- Ölçüldü: ai_propose_action her öneriye 24 saat veriyor; süresi dolan öneri PROPOSED kalıyor,
-- ana sayfa kutusunda "bekliyor" görünüyor ama onaylanamıyor/reddedilemiyor ("action proposal expired").
-- 105 (25.09) ve 112 (16.10) böyle takılı kalmıştı. Sahip notu (REQUEST_HUMAN_REVIEW) ise ertesi gün ölüyordu.
BEGIN;

CREATE OR REPLACE FUNCTION core.ai_sistem_onerisi(p_kaynak text, p_action_type text, p_anahtar text, p_payload jsonb, p_sebep text)
 RETURNS bigint
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core', 'pg_temp'
AS $function$
DECLARE v_id bigint; v_task_id bigint; v_token uuid := gen_random_uuid(); v_cutoff text; v_key text;
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
  v_id := core.ai_propose_action(v_task_id, v_token, 'action:' || v_key, p_action_type, p_payload);
  -- 071: yalnız okuma/karar isteyen öneri 24 saatte ölmesin; sahip notu günlerce okuyabilir.
  -- Dış eylemli tipler (fiyat, yayın, mesaj) 24 saatte kalır.
  IF p_action_type = 'REQUEST_HUMAN_REVIEW' THEN
    UPDATE core.ai_action_proposal SET expires_at = proposed_at + interval '7 days' WHERE action_id = v_id;
  END IF;
  RETURN v_id;
END $function$;

CREATE OR REPLACE FUNCTION core.ai_suresi_dolan_onerileri_kapat()
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'core', 'pg_temp'
AS $f$
DECLARE n integer;
BEGIN
  UPDATE core.ai_action_proposal
     SET state = 'CANCELLED', decided_by = 'sistem:sure-doldu', decided_at = clock_timestamp(),
         decision_reason = 'Süresi doldu (' || to_char(expires_at, 'DD.MM.YYYY HH24:MI') || '); karar verilmeden kapandı.'
   WHERE state = 'PROPOSED' AND expires_at <= clock_timestamp();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $f$;
REVOKE ALL ON FUNCTION core.ai_suresi_dolan_onerileri_kapat() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_suresi_dolan_onerileri_kapat() TO ai_writer;

-- Bekleyen inceleme önerileri de 7 güne çıkar (henüz ölmemiş olanlar).
UPDATE core.ai_action_proposal SET expires_at = proposed_at + interval '7 days'
 WHERE state = 'PROPOSED' AND action_type = 'REQUEST_HUMAN_REVIEW' AND expires_at > clock_timestamp();

SELECT core.ai_suresi_dolan_onerileri_kapat();
COMMIT;
