"""SQLite database for task tracking, stage history, and run logs."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER DEFAULT 0,
    input_path TEXT,
    output_path TEXT,
    current_stage INTEGER DEFAULT 0,
    total_stages INTEGER,
    queued_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS stages (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    stage_index INTEGER NOT NULL,
    stage_name TEXT NOT NULL,
    skill_name TEXT,
    model TEXT,
    backend TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    container_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    iterations INTEGER DEFAULT 0,
    verification_passed INTEGER,
    tokens_used INTEGER DEFAULT 0,
    duration_seconds REAL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    stage_id TEXT NOT NULL REFERENCES stages(id),
    iteration INTEGER NOT NULL,
    action TEXT,
    result TEXT,
    tokens_used INTEGER DEFAULT 0,
    duration_seconds REAL,
    timestamp TEXT
);
"""


class HuginnDB:
    """Database interface for Huginn task tracking."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # --- Tasks ---

    def create_task(
        self,
        pipeline_name: str,
        input_path: str,
        output_path: str,
        total_stages: int,
        metadata: str | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO tasks (id, pipeline_name, status, input_path, output_path,
               total_stages, queued_at, metadata)
               VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)""",
            (task_id, pipeline_name, input_path, output_path, total_stages, now, metadata),
        )
        self.conn.commit()
        return task_id

    def update_task(self, task_id: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        self.conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def get_task(self, task_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY queued_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks ORDER BY queued_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Stages ---

    def create_stage(
        self,
        task_id: str,
        stage_index: int,
        stage_name: str,
        skill_name: str,
        model: str,
        backend: str,
    ) -> str:
        stage_id = str(uuid.uuid4())[:8]
        self.conn.execute(
            """INSERT INTO stages (id, task_id, stage_index, stage_name, skill_name,
               model, backend, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (stage_id, task_id, stage_index, stage_name, skill_name, model, backend),
        )
        self.conn.commit()
        return stage_id

    def update_stage(self, stage_id: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [stage_id]
        self.conn.execute(f"UPDATE stages SET {sets} WHERE id = ?", vals)
        self.conn.commit()

    def get_stages(self, task_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM stages WHERE task_id = ? ORDER BY stage_index", (task_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Runs ---

    def log_run(
        self,
        stage_id: str,
        iteration: int,
        action: str,
        result: str,
        tokens_used: int = 0,
        duration_seconds: float = 0,
    ) -> str:
        run_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO runs (id, stage_id, iteration, action, result,
               tokens_used, duration_seconds, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, stage_id, iteration, action, result, tokens_used, duration_seconds, now),
        )
        self.conn.commit()
        return run_id

    def get_runs(self, stage_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE stage_id = ? ORDER BY iteration", (stage_id,)
        ).fetchall()
        return [dict(r) for r in rows]
