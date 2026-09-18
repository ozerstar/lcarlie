from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class TaskStateStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with closing(self._connect()) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS task_state (
                task_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
            )""")
            db.commit()

    def _connect(self):
        return sqlite3.connect(self.path)

    def save(self, task_id: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, sort_keys=True)
        with closing(self._connect()) as db:
            db.execute("""INSERT INTO task_state(task_id,state_json) VALUES(?,?)
                ON CONFLICT(task_id) DO UPDATE SET state_json=excluded.state_json,
                version=task_state.version+1""", (task_id, payload))
            db.commit()

    def load(self, task_id: str) -> dict[str, Any]:
        with closing(self._connect()) as db:
            row = db.execute("SELECT state_json FROM task_state WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return json.loads(row[0])
