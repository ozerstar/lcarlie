from __future__ import annotations

import json
from typing import Any, Protocol


class SqlExecutor(Protocol):
    def fetch_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None: ...


class PostgresTaskStateStore:
    """Controlled PostgreSQL state store; callers never write tables directly."""

    def __init__(self, executor: SqlExecutor):
        self.executor = executor

    def save(self, task_id: int, state: dict[str, Any], expected_version: int) -> int:
        payload = json.dumps(state, sort_keys=True, separators=(",", ":"))
        row = self.executor.fetch_one(
            "SELECT core.ai_save_jarvis_task_state(%s, %s, %s::jsonb)",
            (task_id, expected_version, payload),
        )
        if row is None:
            raise RuntimeError("state save returned no version")
        return int(row[0])

    def load(self, task_id: int) -> tuple[dict[str, Any], int]:
        row = self.executor.fetch_one(
            "SELECT state_json, version FROM core.ai_load_jarvis_task_state(%s)",
            (task_id,),
        )
        if row is None:
            raise KeyError(task_id)
        state = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return state, int(row[1])
