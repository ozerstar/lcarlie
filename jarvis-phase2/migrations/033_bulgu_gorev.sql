-- =============================================================================
-- 033 · BULGUDAN GOREV: Jarvis kendi isini acabilsin
--
-- SAHIP KARARI (22.09.2026): "jarvis gorev acsin"
--
-- NE DEGISIYOR
-- Bugune kadar core.ai_enqueue_task yalnizca human_approver'a verilmisti.
-- Jarvis bir sorun BULABILIYOR ama o sorun icin kendine is ACAMIYORDU;
-- findings.jsonl'e yaziyor ve orada bekliyordu. Artik bulgudan is acabilir.
--
-- 🔴 ONAY KAPISI YERINDE KALIYOR. Degisen sey "ne uzerinde calisilacagina
--    kim karar veriyor". Acilan is yine PROPOSE_ACTION'dir: dongu bir
--    ONERI uretir, oneri onay kuyruguna duser, uygulanmasi icin sahibin
--    onayi gerekir. Bu fonksiyon hicbir seyi uygulamaz.
--
-- 🔴 SINIRLAR BETIKTE DEGIL BURADA. Betik degistirilse, kopyalansa ya da
--    elle calistirilsa bile tavanlar asilamaz. Sinirlari cagiran tarafa
--    birakmak, sinir koymamakla ayni seydir.
--
--    1) 24 saatte en fazla 6 bulgu isi
--    2) ayni anda en fazla 12 acik bulgu isi
--    3) ayni imzadan IKINCI KEZ is acilamaz (idempotency_key UNIQUE);
--       ayni 404 her kosuda yeni is acsaydi kuyruk bir gunde tikanirdi
--    4) sebep en az 40 karakter: "ici bos oneri onay degildir" kurali
--       (bkz. agency_store.py) burada da gecerli
--
-- GERI ALMA: rollback/033_bulgu_gorev_ROLLBACK.sql
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION core.ai_bulgu_gorev_ac(
    p_slug    text,
    p_sebep   text,
    p_oncelik integer DEFAULT 120
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $fn$
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
$fn$;

COMMENT ON FUNCTION core.ai_bulgu_gorev_ac(text, text, integer) IS
  'Bulgudan PROPOSE_ACTION isi acar. Tavanlar ve tekillik BURADA zorlanir; '
  'onay kapisi degismez - acilan is bir ONERI uretir, uygulamaz.';

ALTER FUNCTION core.ai_bulgu_gorev_ac(text, text, integer) OWNER TO function_owner;

REVOKE ALL ON FUNCTION core.ai_bulgu_gorev_ac(text, text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION core.ai_bulgu_gorev_ac(text, text, integer) TO ai_writer;
GRANT EXECUTE ON FUNCTION core.ai_bulgu_gorev_ac(text, text, integer) TO human_approver;

COMMIT;
