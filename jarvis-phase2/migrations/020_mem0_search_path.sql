-- 020 — mem0_writer search_path'ine public eklenmesi
--
-- SORUN (019'dan sonra ölçüldü)
-- 019 search_path'i yalnız 'mem0' yaptı. Tablo yaratma denemesi şu hatayı verdi:
--     psycopg.errors.UndefinedObject: type "vector" does not exist
--     LINE 4:   vector vector(1024),
-- Sebep: pgvector'ün 'vector' TİPİ public şemasında tanımlı (ölçüldü:
-- pg_extension -> public). search_path'te public olmayınca tip çözülemiyor.
--
-- NEDEN 'mem0, public' SIRASI ÖNEMLİ
-- mem0'ın sürücüsü tabloyu şemasız tek tanımlayıcıyla yaratıyor; tablo
-- search_path'in İLK YAZILABİLİR şemasına düşer. 'mem0' başta olduğu için
-- tablo yine mem0'a düşer -- public'e değil. Sıra tersine çevrilseydi
-- tablo n8n'in 136 tablosunun yanına düşerdi.
--
-- public'E YAZMA RİSKİ YOK
-- mem0_writer'ın public şemasında CREATE hakkı yok (PostgreSQL 15'ten beri
-- PUBLIC'in varsayılan CREATE hakkı kaldırıldı; 17.11'de ölçüldü: false).
-- Eklenen tek şey USAGE -- yani "oradaki tipi okuyabil", "oraya yazabil" değil.
-- Aşağıdaki doğrulama bunu iddia etmiyor, SINIYOR.

\set ON_ERROR_STOP on
BEGIN;

ALTER ROLE mem0_writer SET search_path = mem0, public;

DO $$
DECLARE
  t text;
BEGIN
  IF has_schema_privilege('mem0_writer','public','CREATE') THEN
    RAISE EXCEPTION 'mem0_writer public''e yazabiliyor -- tablo oraya duserdi';
  END IF;
  IF NOT has_schema_privilege('mem0_writer','public','USAGE') THEN
    RAISE EXCEPTION 'mem0_writer public''i kullanamiyor -- vector tipi yine cozulmez';
  END IF;

  -- Kanit siniri 019'daki gibi duruyor mu: hala tek bir tablo bile okunamamali.
  FOR t IN
    SELECT c.oid::regclass::text
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('core','mart','raw','ai_semantic') AND c.relkind IN ('r','v','m')
  LOOP
    IF has_table_privilege('mem0_writer', t, 'SELECT') THEN
      RAISE EXCEPTION 'mem0_writer % okuyabiliyor -- kanit siniri delinmis', t;
    END IF;
  END LOOP;
END $$;

COMMIT;
