-- =============================================================================
-- core.ai_claim_task DUZELTMESI  ·  25.09.2026
--
-- IKI KUSUR OLCULDU.
--
-- (1) SURESI DOLMUS KIRA GERI ALINMIYOR -> IS KALICI OLARAK SIZIYOR.
--     Aday sorgusu yalniz `state IN ('OPEN','FAILED_RETRYABLE')` bakiyordu.
--     Bir isci isi kiralayip olurse is LEASED'te kalir, kira suresi gecer ve
--     ONU BIR DAHA KIMSE ALMAZ. Olculdu: task 180
--     (jarvis:CODE_CHANGE_REVIEW:plan-oku) kirasi 21.09.2026 19:16'da doldu,
--     4 gundur LEASED, attempt_count 1/3 -- yani hakki varken bir daha hic
--     denenmedi ve hicbir yerde hata gorunmedi.
--
-- (2) ISCI, KENDISININ OLMAYAN IS TIPINI CEKIYOR -> SONSUZ DONGU.
--     Ayni kuyrugu iki isci paylasiyor:
--       lcarlie-ai-worker (orchestrator/worker.js) -> PROPOSE_DECISION
--       jarvis-phase2      (jarvis/loop.py)        -> PROPOSE_ACTION
--     Fonksiyon tipe bakmadigi icin AI isci bir PROPOSE_ACTION isini
--     kiraliyor, worker.js "unsupported task/profile" diye HATA FIRLATIYOR,
--     islem ROLLBACK oluyor -- ve rollback attempt_count artisini da geri
--     aliyor. Yani is asla max_attempts'e ulasmiyor: her 5 dakikada bir
--     ayni is cekiliyor, ayni hata veriliyor. Olculdu: 25.09'da 52 kez.
--     Jarvis tarafi ayni durumu ZARIFCE ele aliyor (_fail_task ->
--     SKIPPED_NOT_MINE); kusur yalnizca orchestrator tarafinda.
--
-- COZUM. Istege bagli `p_task_type` suzgeci eklendi (DEFAULT NULL = eski
-- davranis, suzme yok). Cagiran taraf kendi tipini soyler; kimse baskasinin
-- isini kiralamaz. Ayrica suresi dolmus kiralar yeniden aday olur.
--
-- 🔴 NEDEN DROP + CREATE, `CREATE OR REPLACE` DEGIL: PostgreSQL'de parametre
--    SAYISI degisince CREATE OR REPLACE yeni bir asiri yukleme (overload)
--    yaratir, eskisini degistirmez. Iki fonksiyon da varsayilanli oldugu
--    icin `ai_claim_task('x',300)` cagrisi BELIRSIZ kalir ve hata verir --
--    yani Jarvis dongusu kirilirdi. Tek fonksiyon birakiyoruz.
--
-- 🔴 SAHIP VE IZINLER GERI VERILIR: fonksiyon SECURITY DEFINER ve sahibi
--    `function_owner`; DROP sonrasi bunu yeniden kurmazsak ai_writer
--    cagiramaz ve iki isci birden sessizce durur.
-- =============================================================================

BEGIN;

-- Beklenen baslangic durumu: tek bir 2 parametreli fonksiyon.
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
   WHERE ns.nspname='core' AND p.proname='ai_claim_task';
  IF n <> 1 THEN
    RAISE EXCEPTION 'Beklenen tek fonksiyon yok (bulunan: %). Elle bak.', n;
  END IF;
END $$;

DROP FUNCTION core.ai_claim_task(text, integer);

CREATE FUNCTION core.ai_claim_task(
  p_worker_id      text,
  p_lease_seconds  integer DEFAULT 300,
  p_task_type      text    DEFAULT NULL   -- NULL = her tip (eski davranis)
)
RETURNS TABLE(task_id bigint, source_type text, source_id bigint, task_type text,
              idempotency_key text, context_profile text, lease_token uuid,
              attempt_count integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'core', 'pg_temp'
AS $function$
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
END $function$;

ALTER FUNCTION core.ai_claim_task(text, integer, text) OWNER TO function_owner;
REVOKE ALL ON FUNCTION core.ai_claim_task(text, integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_claim_task(text, integer, text) TO ai_writer;

-- Kurulum dogrulamasi: tek fonksiyon, sahip ve izin yerinde olmali.
DO $$
DECLARE n int; v_owner text; v_secdef boolean;
BEGIN
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
   WHERE ns.nspname='core' AND p.proname='ai_claim_task';
  IF n <> 1 THEN RAISE EXCEPTION 'Fonksiyon sayisi 1 degil: %', n; END IF;

  SELECT pg_get_userbyid(p.proowner), p.prosecdef INTO v_owner, v_secdef
    FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
   WHERE ns.nspname='core' AND p.proname='ai_claim_task';
  IF v_owner <> 'function_owner' THEN RAISE EXCEPTION 'Sahip yanlis: %', v_owner; END IF;
  IF NOT v_secdef THEN RAISE EXCEPTION 'SECURITY DEFINER kaybolmus'; END IF;

  IF NOT has_function_privilege('ai_writer','core.ai_claim_task(text,integer,text)','EXECUTE')
  THEN RAISE EXCEPTION 'ai_writer EXECUTE izni yok'; END IF;
END $$;

COMMIT;
