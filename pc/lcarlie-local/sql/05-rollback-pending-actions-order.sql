-- lcarlie: 05-fix-pending-actions-order.sql GERI ALMA betigi.
-- core.ai_get_pending_actions() fonksiyonunu dump'taki ORIJINAL govdeye (metin siralamali, hatali) dondurur.
-- Sahip, ACL, SECURITY DEFINER, STABLE, search_path, COST/ROWS aynen korunur ve dogrulanir.
-- Guvenlik kilidi: mevcut govde 05-fix ile yazilan govde degilse HICBIR SEY degistirmeden durur.
-- Calistir (yerel):
--   docker exec -i lcarlie-pg psql -U lcarlie_admin -d lcarlie -X -v ON_ERROR_STOP=1 < sql/05-rollback-pending-actions-order.sql

\set ON_ERROR_STOP 1
BEGIN;

CREATE TEMP TABLE _fn_once ON COMMIT DROP AS
SELECT p.prosecdef, p.provolatile, p.proparallel, p.proleakproof, p.proisstrict, p.procost, p.prorows,
       p.proconfig, pg_get_userbyid(p.proowner) AS sahip, p.proacl::text AS acl,
       pg_get_function_result(p.oid) AS donus, l.lanname, md5(p.prosrc) AS govde_md5,
       position('ORDER BY CASE a.risk_class' IN p.prosrc) > 0 AS duzeltilmis
FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
WHERE p.oid = 'core.ai_get_pending_actions()'::regprocedure;

DO $$
BEGIN
  IF NOT (SELECT duzeltilmis FROM _fn_once) THEN
    RAISE EXCEPTION 'Fonksiyon 05-fix ile duzeltilmis surum degil (md5=%). Geri alinacak bir sey yok; degisiklik yapilmadi.',
      (SELECT govde_md5 FROM _fn_once);
  END IF;
END $$;

CREATE OR REPLACE FUNCTION core.ai_get_pending_actions()
 RETURNS TABLE(action_id bigint, task_id bigint, action_type text, payload jsonb, payload_hash text, risk_class text, policy_version text, proposed_at timestamp with time zone, expires_at timestamp with time zone)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 COST 100 ROWS 1000
 SET search_path TO 'pg_catalog', 'core'
AS $function$ SELECT a.action_id,a.task_id,a.action_type,a.payload,a.payload_hash,a.risk_class,a.policy_version,a.proposed_at,a.expires_at FROM core.ai_action_proposal a WHERE a.state='PROPOSED' AND a.expires_at>clock_timestamp() ORDER BY a.risk_class DESC,a.action_id ASC $function$;

DO $$
DECLARE o _fn_once%ROWTYPE; s record;
BEGIN
  SELECT * INTO o FROM _fn_once;
  SELECT p.prosecdef, p.provolatile, p.proparallel, p.proleakproof, p.proisstrict, p.procost, p.prorows,
         p.proconfig, pg_get_userbyid(p.proowner) AS sahip, p.proacl::text AS acl,
         pg_get_function_result(p.oid) AS donus, l.lanname, md5(p.prosrc) AS govde_md5
    INTO s
  FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
  WHERE p.oid = 'core.ai_get_pending_actions()'::regprocedure;
  IF s.govde_md5 <> 'ecbab1157eda086afc9e652e17b1f197' THEN
    RAISE EXCEPTION 'Geri alinan govde orijinal dump govdesiyle ayni degil (md5=%). ROLLBACK.', s.govde_md5;
  END IF;
  IF (s.prosecdef, s.provolatile, s.proparallel, s.proleakproof, s.proisstrict, s.procost, s.prorows,
      s.proconfig, s.sahip, s.acl, s.donus, s.lanname)
     IS DISTINCT FROM
     (o.prosecdef, o.provolatile, o.proparallel, o.proleakproof, o.proisstrict, o.procost, o.prorows,
      o.proconfig, o.sahip, o.acl, o.donus, o.lanname) THEN
    RAISE EXCEPTION 'Nitelik/sahip/ACL degisti: once=% sonra=%. ROLLBACK.', row_to_json(o), row_to_json(s);
  END IF;
  RAISE NOTICE 'Orijinal govde geri yuklendi (md5=%); nitelikler korundu.', s.govde_md5;
END $$;

COMMIT;
