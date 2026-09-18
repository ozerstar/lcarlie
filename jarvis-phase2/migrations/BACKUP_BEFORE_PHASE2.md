# Backup Before Phase 2 Activation

Do not run until production activation is explicitly approved.

1. Record current DB size, extension list, schema hashes, roles, grants, and
   `core.ai_*` function definitions.
2. Create a compressed custom-format `pg_dump` of schemas `core`, `mart`, and
   `ai_semantic` when present.
3. Create a schema-only dump of the whole database.
4. Compute SHA-256 for both dumps and record owner/mode/time.
5. Restore both dumps into an isolated PostgreSQL 17 instance and run existing
   security/adversarial checks before production migration.

Secret values must never be written into commands, logs, or reports. Use the
existing protected environment file at execution time.
