# F0-B Database Contract

The future PostgreSQL repository adapter must authenticate with a dedicated LOGIN that is only a member of `ai_reader` and `ai_writer`.

It may call only:

- `core.ai_claim_task(worker_id, lease_seconds)`
- static SELECT statements in `context_queries.sql`
- `core.ai_log_provider_attempt(...)`
- `core.ai_complete_task_with_proposed_decision(...)`
- `core.ai_fail_task(...)`

It must not use an owner, n8n, human approver, action executor, or function owner credential. F0-C deliberately creates no LOGIN and starts no process.
