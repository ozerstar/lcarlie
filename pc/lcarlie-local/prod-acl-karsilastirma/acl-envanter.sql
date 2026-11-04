-- lcarlie: yetki (ACL) / rol / sahiplik / kill-switch envanteri. SALT OKUNUR.
-- Ayni dosya hem uretimde hem yerelde calistirilir; cikti satir bazinda normalize edilmistir:
--   bolum|nesne|alan1|alan2|...
-- Normalizasyon:
--   * Kurulumu yapan superuser (oid 10; uretimde genelde "postgres", yerelde "lcarlie_admin") -> <bootstrap_superuser>
--   * Grantee 0 -> PUBLIC; NULL ACL -> PostgreSQL varsayilan ACL'si (acldefault) acilarak yazilir
--   * Grantor YAZILMAZ (kurulum yontemine gore degisir, guvenlik anlami tasimaz)
--   * pg_*, information_schema, pg_toast ve eklentiye ait (pg_depend deptype='e') nesneler haric
--   * Parola, parola hash'i ve veri satiri YAZILMAZ. Tek istisna: core.ai_orchestrator_config ve
--     core.ai_action_type referans/ayar satirlari (adinda secret/token/password/key gecen degerler maskelenir).
-- Calistirma: psql -X -At -F '|' -v ON_ERROR_STOP=1 -f acl-envanter.sql
\set ON_ERROR_STOP 1
\set QUIET on
SET default_transaction_read_only = on;
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';

-- 0) meta (bilgi amacli; diff'te beklenen fark)
SELECT 'meta|server_version_num|' || current_setting('server_version_num');
-- karsilastir.sh bu adi pg_dump/pg_dumpall ciktilarinda <bootstrap_superuser> ile degistirmek icin kullanir.
SELECT 'meta|bootstrap_superuser|' || rolname FROM pg_roles WHERE oid = 10;
SELECT 'meta|current_user|' || current_user;
SELECT 'meta|database|' || current_database();

-- 1) roller (parola yok). Uretimde olup yerelde olmayan / tersi burada gorunur.
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'rol|' || r.ad || '|super=' || a.rolsuper || '|inherit=' || a.rolinherit || '|createrole=' || a.rolcreaterole
       || '|createdb=' || a.rolcreatedb || '|login=' || a.rolcanlogin || '|replication=' || a.rolreplication
       || '|bypassrls=' || a.rolbypassrls || '|connlimit=' || a.rolconnlimit
       || '|valid_until=' || coalesce(a.rolvaliduntil::text, '-')
FROM pg_roles a JOIN _r r ON r.oid = a.oid
WHERE a.rolname !~ '^pg_'
ORDER BY 1;

-- 1b) rol duzeyi ayarlar (ALTER ROLE ... SET); degerler maskelenmez ama parola icermez
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'rol_ayar|' || coalesce(r.ad, '*') || '|db=' || coalesce(d.datname, '*') || '|' || s.cfg
FROM pg_db_role_setting x
LEFT JOIN _r r ON r.oid = x.setrole AND x.setrole <> 0
LEFT JOIN pg_database d ON d.oid = x.setdatabase
CROSS JOIN LATERAL unnest(x.setconfig) AS s(cfg)
WHERE (x.setdatabase = 0 OR d.datname = current_database())
ORDER BY 1;

-- 2) rol uyelikleri (PG16+: inherit_option / set_option)
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'uyelik|' || rr.ad || '<-' || mm.ad || '|admin=' || m.admin_option
       || '|inherit=' || m.inherit_option || '|set=' || m.set_option
FROM pg_auth_members m
JOIN _r rr ON rr.oid = m.roleid
JOIN _r mm ON mm.oid = m.member
WHERE rr.ad !~ '^pg_' OR mm.ad !~ '^pg_'
ORDER BY 1;

-- 3) veritabani ACL'si (yalnizca bu veritabani)
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'db_acl|' || current_database() || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM pg_database d
CROSS JOIN LATERAL aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) e
JOIN _r g ON g.oid = e.grantee
WHERE d.datname = current_database()
ORDER BY 1;
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'db_sahip|' || current_database() || '|' || r.ad
FROM pg_database d JOIN _r r ON r.oid = d.datdba WHERE d.datname = current_database();

-- 4) sema sahipleri ve ACL'leri
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e')
SELECT 'sema_sahip|' || n.nspname || '|' || r.ad
FROM pg_namespace n JOIN _ns USING (oid) JOIN _r r ON r.oid = n.nspowner
WHERE NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_namespace'::regclass AND x.objid = n.oid)
ORDER BY 1;
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e')
SELECT 'sema_acl|' || n.nspname || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM pg_namespace n JOIN _ns USING (oid)
CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) e
JOIN _r g ON g.oid = e.grantee
WHERE NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_namespace'::regclass AND x.objid = n.oid)
ORDER BY 1;

-- 5) iliski (tablo/view/matview/sequence/foreign table/partitioned) sahipleri, RLS ve ACL'leri

WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _rel AS (SELECT c.oid, c.relkind, c.relowner, c.relacl, c.relrowsecurity, c.relforcerowsecurity, quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS ad FROM pg_class c JOIN _ns n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','v','m','S','f','p') AND NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_class'::regclass AND x.objid = c.oid))
SELECT 'iliski_sahip|' || c.ad || '|kind=' || c.relkind::text || '|' || r.ad
       || '|rls=' || c.relrowsecurity || '|force_rls=' || c.relforcerowsecurity
FROM _rel c JOIN _r r ON r.oid = c.relowner
ORDER BY 1;
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _rel AS (SELECT c.oid, c.relkind, c.relowner, c.relacl, c.relrowsecurity, c.relforcerowsecurity, quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS ad FROM pg_class c JOIN _ns n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','v','m','S','f','p') AND NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_class'::regclass AND x.objid = c.oid))
SELECT 'iliski_acl|' || c.ad || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM _rel c
CROSS JOIN LATERAL aclexplode(coalesce(c.relacl, acldefault(CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END::"char", c.relowner))) e
JOIN _r g ON g.oid = e.grantee
ORDER BY 1;

-- 5b) kolon duzeyi yetkiler
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _rel AS (SELECT c.oid, c.relkind, c.relowner, c.relacl, c.relrowsecurity, c.relforcerowsecurity, quote_ident(n.nspname) || '.' || quote_ident(c.relname) AS ad FROM pg_class c JOIN _ns n ON n.oid = c.relnamespace WHERE c.relkind IN ('r','v','m','S','f','p') AND NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_class'::regclass AND x.objid = c.oid))
SELECT 'kolon_acl|' || c.ad || '.' || quote_ident(a.attname) || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM _rel c
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped AND a.attacl IS NOT NULL
CROSS JOIN LATERAL aclexplode(a.attacl) e
JOIN _r g ON g.oid = e.grantee
ORDER BY 1;

-- 5c) RLS politikalari
WITH _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_')
SELECT 'politika|' || quote_ident(p.schemaname) || '.' || quote_ident(p.tablename) || '|' || p.policyname
       || '|' || p.permissive || '|' || p.cmd || '|roles=' || array_to_string(ARRAY(SELECT unnest(p.roles) ORDER BY 1), ',')
       || '|using_md5=' || coalesce(md5(p.qual), '-') || '|check_md5=' || coalesce(md5(p.with_check), '-')
FROM pg_policies p
WHERE p.schemaname IN (SELECT nspname FROM _ns)
ORDER BY 1;

-- 6) fonksiyon/prosedur sahipleri, guvenlik nitelikleri, govde ozeti ve ACL'leri

WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _fn AS (SELECT p.oid, p.prokind, p.proowner, p.proacl, p.prosecdef, p.provolatile, p.proconfig, p.prosrc, l.lanname, quote_ident(n.nspname) || '.' || quote_ident(p.proname) || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS ad FROM pg_proc p JOIN _ns n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang WHERE NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_proc'::regclass AND x.objid = p.oid))
SELECT 'fonksiyon|' || f.ad || '|kind=' || f.prokind::text || '|' || r.ad || '|secdef=' || f.prosecdef
       || '|volatile=' || f.provolatile::text || '|lang=' || f.lanname
       || '|config=' || coalesce(array_to_string(f.proconfig, ';'), '-')
FROM _fn f JOIN _r r ON r.oid = f.proowner
ORDER BY 1;
-- Govde ozeti ayri bolumde: govde farklari (or. risk_class duzeltmesi) yetki farklarindan ayri okunur.
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _fn AS (SELECT p.oid, p.prokind, p.proowner, p.proacl, p.prosecdef, p.provolatile, p.proconfig, p.prosrc, l.lanname, quote_ident(n.nspname) || '.' || quote_ident(p.proname) || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS ad FROM pg_proc p JOIN _ns n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang WHERE NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_proc'::regclass AND x.objid = p.oid))
SELECT 'fonksiyon_govde|' || f.ad || '|md5=' || md5(f.prosrc)
FROM _fn f WHERE f.lanname IN ('sql','plpgsql')
ORDER BY 1;
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e'),
     _fn AS (SELECT p.oid, p.prokind, p.proowner, p.proacl, p.prosecdef, p.provolatile, p.proconfig, p.prosrc, l.lanname, quote_ident(n.nspname) || '.' || quote_ident(p.proname) || '(' || pg_get_function_identity_arguments(p.oid) || ')' AS ad FROM pg_proc p JOIN _ns n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang WHERE NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_proc'::regclass AND x.objid = p.oid))
SELECT 'fonksiyon_acl|' || f.ad || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM _fn f
CROSS JOIN LATERAL aclexplode(coalesce(f.proacl, acldefault('f', f.proowner))) e
JOIN _r g ON g.oid = e.grantee
ORDER BY 1;

-- 7) tip ACL'leri (yalnizca acikca degistirilmis olanlar; varsayilanlar gurultu yaratir)
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC'),
     _ns AS (SELECT oid, nspname FROM pg_namespace WHERE nspname NOT IN ('pg_catalog','information_schema','pg_toast') AND nspname !~ '^pg_(temp|toast_temp)_'),
     _ext AS (SELECT classid, objid FROM pg_depend WHERE deptype = 'e')
SELECT 'tip_acl|' || quote_ident(n.nspname) || '.' || quote_ident(t.typname) || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM pg_type t JOIN _ns n ON n.oid = t.typnamespace
CROSS JOIN LATERAL aclexplode(t.typacl) e
JOIN _r g ON g.oid = e.grantee
WHERE t.typacl IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM _ext x WHERE x.classid = 'pg_type'::regclass AND x.objid = t.oid)
ORDER BY 1;

-- 8) varsayilan yetkiler (ALTER DEFAULT PRIVILEGES)
WITH _r AS (SELECT oid, CASE WHEN oid = 10 THEN '<bootstrap_superuser>' ELSE rolname END AS ad FROM pg_roles UNION ALL SELECT 0::oid, 'PUBLIC')
SELECT 'varsayilan_acl|' || r.ad || '|sema=' || coalesce(n.nspname, '*') || '|tur=' || d.defaclobjtype::text
       || '|' || g.ad || '|' || e.privilege_type || '|grantable=' || e.is_grantable
FROM pg_default_acl d
JOIN _r r ON r.oid = d.defaclrole
LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
CROSS JOIN LATERAL aclexplode(d.defaclacl) e
JOIN _r g ON g.oid = e.grantee
ORDER BY 1;

-- 9) eklentiler (surum farki fonksiyon/tip farklarini aciklayabilir)
SELECT 'eklenti|' || e.extname || '|' || e.extversion || '|sema=' || n.nspname
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
ORDER BY 1;

-- 10) kill-switch / orkestrator ayarlari (updated_at bilerek yazilmaz)
SELECT 'ayar|core.ai_orchestrator_config|' || c.config_key || '|'
       || CASE WHEN c.config_key ~* '(secret|token|password|passwd|api_?key|credential)' THEN '<MASKELENDI>'
               ELSE c.config_value END
FROM core.ai_orchestrator_config c
ORDER BY 1;
-- orchestrator_enabled_after icin acik satir: anahtar YOKSA da bunu belirt.
SELECT 'ayar_kontrol|orchestrator_enabled_after|'
       || coalesce((SELECT 'deger=' || config_value FROM core.ai_orchestrator_config WHERE config_key = 'orchestrator_enabled_after'),
                   'ANAHTAR_YOK');

-- 11) action firewall referans satirlari (risk sinifi, onay modu, calistirma izni)
SELECT 'action_type|' || t.action_type || '|risk=' || t.risk_class || '|approval=' || t.approval_mode
       || '|execution_enabled=' || t.execution_enabled || '|schema=' || t.schema_version
FROM core.ai_action_type t
ORDER BY 1;

ROLLBACK;
