\set ON_ERROR_STOP on
BEGIN;

-- Kismi (partial) unique index ON CONFLICT cikarimiyla eslesmiyor.
-- harici_id her kayitta zorunlu olsun; web oturumu icin oturum kimligi,
-- Meta icin thread/message id yazilir. Boylece upsert sade ve saglam olur.

DROP INDEX IF EXISTS lcarlie.konusma_harici_tekil;
DROP INDEX IF EXISTS lcarlie.mesaj_harici_tekil;

ALTER TABLE lcarlie.konusma ALTER COLUMN harici_id SET NOT NULL;
ALTER TABLE lcarlie.mesaj    ALTER COLUMN harici_id SET NOT NULL;

ALTER TABLE lcarlie.konusma
  ADD CONSTRAINT konusma_kanal_harici_tekil UNIQUE (kanal, harici_id);
ALTER TABLE lcarlie.mesaj
  ADD CONSTRAINT mesaj_konusma_harici_tekil UNIQUE (konusma_id, harici_id);

COMMIT;

\echo '--- KISITLAR ---'
SELECT conrelid::regclass || ' | ' || conname || ' | ' || pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace='lcarlie'::regnamespace AND contype IN ('u','f')
ORDER BY 1;
