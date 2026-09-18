-- Run only after 002 semantic-memory rollback and dependency verification.
BEGIN;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_depend d
    JOIN pg_extension e ON e.oid = d.refobjid
    WHERE e.extname = 'vector' AND d.deptype = 'e'
      AND d.classid = 'pg_class'::regclass
  ) THEN
    RAISE EXCEPTION 'pgvector has dependent relations; rollback refused';
  END IF;
END $$;
DROP EXTENSION IF EXISTS vector;
COMMIT;
