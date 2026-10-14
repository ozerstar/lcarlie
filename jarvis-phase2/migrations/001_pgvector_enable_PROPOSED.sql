-- PROPOSED_MIGRATION: do not run without explicit production approval.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
DO $$
BEGIN
  IF (SELECT extversion FROM pg_extension WHERE extname = 'vector') <> '0.8.6' THEN
    RAISE EXCEPTION 'Expected pgvector 0.8.6';
  END IF;
END $$;
COMMIT;
