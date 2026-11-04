-- lcarlie: core.ai_get_pending_actions() risk_class siralama duzeltmesi (ONERI).
-- YALNIZCA YEREL ortama uygulandi. Uretime uygulanmasi ayri bir insan karari ve inceleme gerektirir.
--
-- Hata: ORDER BY a.risk_class DESC metin olarak siralar -> MEDIUM > LOW > HIGH > CRITICAL.
--       Insan onaylayici kuyrugunda CRITICAL oneriler en alta duser.
-- Duzeltme: yalnizca ORDER BY ifadesi CASE ile degistirilir: CRITICAL > HIGH > MEDIUM > LOW,
--           esitlikte action_id artan. Donus tipi, WHERE kosulu, kolonlar AYNI.
--
-- Korunanlar (CREATE OR REPLACE sahibi ve ACL'yi korur; asagidaki nitelikler acikca yeniden yazilir):
--   LANGUAGE sql, STABLE, SECURITY DEFINER, SET search_path = pg_catalog, core,
--   sahip (function_owner), EXECUTE yetkileri (human_approver, function_owner), COST 100, ROWS 1000.
-- Guvenlik kilitleri:
--   * Mevcut govde beklenen hatali govde degilse (md5 farkli) HICBIR SEY degistirmeden durur.
--   * Uygulama sonrasi nitelik/sahip/ACL/search_path once-sonra karsilastirilir; fark varsa ROLLBACK.
-- Geri alma: 05-rollback-pending-actions-order.sql
-- Calistir (yerel):
--   docker exec -i lcarlie-pg psql -U lcarlie_admin -d lcarlie -X -v ON_ERROR_STOP=1 < sql/05-fix-pending-actions-order.sql

\set ON_ERROR_STOP 1
BEGIN;

CREATE TEMP TABLE _fn_once ON COMMIT DROP AS
SELECT p.prosecdef, p.provolatile, p.proparallel, p.proleakproof, p.proisstrict, p.procost, p.prorows,
       p.proconfig, pg_get_userbyid(p.proowner) AS sahip, p.proacl::text AS acl,
       pg_get_function_result(p.oid) AS donus, l.lanname, md5(p.prosrc) AS govde_md5
FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
WHERE p.oid = 'core.ai_get_pending_actions()'::regprocedure;

DO $$
BEGIN
  IF (SELECT govde_md5 FROM _fn_once) <> 'ecbab1157eda086afc9e652e17b1f197' THEN
    RAISE EXCEPTION 'core.ai_get_pending_actions govdesi beklenen (hatali) surum degil: md5=%. Degisiklik yapilmadi.',
      (SELECT govde_md5 FROM _fn_once);
  END IF;
  IF NOT (SELECT prosecdef FROM _fn_once) THEN
    RAISE EXCEPTION 'Beklenmeyen durum: fonksiyon SECURITY DEFINER degil. Degisiklik yapilmadi.';
  END IF;
END $$;

CREATE OR REPLACE FUNCTION core.ai_get_pending_actions()
 RETURNS TABLE(action_id bigint, task_id bigint, action_type text, payload jsonb, payload_hash text, risk_class text, policy_version text, proposed_at timestamp with time zone, expires_at timestamp with time zone)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 COST 100 ROWS 1000
 SET search_path TO 'pg_catalog', 'core'
AS $function$ SELECT a.action_id,a.task_id,a.action_type,a.payload,a.payload_hash,a.risk_class,a.policy_version,a.proposed_at,a.expires_at FROM core.ai_action_proposal a WHERE a.state='PROPOSED' AND a.expires_at>clock_timestamp() ORDER BY CASE a.risk_class WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0 END DESC,a.action_id ASC $function$;

DO $$
DECLARE o _fn_once%ROWTYPE; s record;
BEGIN
  SELECT * INTO o FROM _fn_once;
  SELECT p.prosecdef, p.provolatile, p.proparallel, p.proleakproof, p.proisstrict, p.procost, p.prorows,
         p.proconfig, pg_get_userbyid(p.proowner) AS sahip, p.proacl::text AS acl,
         pg_get_function_result(p.oid) AS donus, l.lanname
    INTO s
  FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang
  WHERE p.oid = 'core.ai_get_pending_actions()'::regprocedure;
  IF (s.prosecdef, s.provolatile, s.proparallel, s.proleakproof, s.proisstrict, s.procost, s.prorows,
      s.proconfig, s.sahip, s.acl, s.donus, s.lanname)
     IS DISTINCT FROM
     (o.prosecdef, o.provolatile, o.proparallel, o.proleakproof, o.proisstrict, o.procost, o.prorows,
      o.proconfig, o.sahip, o.acl, o.donus, o.lanname) THEN
    RAISE EXCEPTION 'Nitelik/sahip/ACL degisti: once=% sonra=%. ROLLBACK.', row_to_json(o), row_to_json(s);
  END IF;
  RAISE NOTICE 'Nitelikler korundu: secdef=%, volatile=%, sahip=%, search_path=%, acl=%',
    s.prosecdef, s.provolatile, s.sahip, s.proconfig, s.acl;
END $$;

COMMIT;
