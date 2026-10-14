-- PROPOSED_MIGRATION: separate from extension enablement.
BEGIN;
CREATE SCHEMA IF NOT EXISTS ai_semantic;
REVOKE ALL ON SCHEMA ai_semantic FROM PUBLIC;

CREATE TABLE ai_semantic.memory_embedding (
  embedding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_type text NOT NULL,
  source_ref text NOT NULL,
  content_hash text NOT NULL,
  model_id text NOT NULL,
  model_revision text NOT NULL,
  embedding vector(1024) NOT NULL,
  evidence_ref text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (source_type, source_ref, content_hash, model_id, model_revision)
);

CREATE INDEX memory_embedding_cosine_idx
ON ai_semantic.memory_embedding USING hnsw (embedding vector_cosine_ops);

REVOKE ALL ON ALL TABLES IN SCHEMA ai_semantic FROM PUBLIC;
COMMIT;
