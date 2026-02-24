from __future__ import annotations

import aiosqlite
from datetime import datetime
from typing import Any


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                result TEXT,
                error TEXT,
                session_id TEXT,
                working_dir TEXT,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cron_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                last_run TIMESTAMP,
                next_run TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                system_prompt TEXT NOT NULL,
                working_dir TEXT,
                timeout_seconds INTEGER DEFAULT 300,
                max_concurrent INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS browser_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id),
                url TEXT,
                screenshot_path TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent_type);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_conversations_task ON conversations(task_id);
        """)
        await self._conn.commit()

    # --- Generic helpers ---

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def execute(self, sql: str, params: tuple = ()) -> int:
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor.lastrowid

    # --- Tasks ---

    async def create_task(self, agent_type: str, prompt: str, priority: int = 0,
                          working_dir: str | None = None, source: str = "manual") -> int:
        return await self.execute(
            "INSERT INTO tasks (agent_type, prompt, priority, working_dir, source) VALUES (?, ?, ?, ?, ?)",
            (agent_type, prompt, priority, working_dir, source),
        )

    async def get_task(self, task_id: int) -> dict | None:
        return await self.fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))

    async def update_task(self, task_id: int, **kwargs) -> None:
        if "status" in kwargs:
            if kwargs["status"] == "running":
                kwargs.setdefault("started_at", datetime.utcnow().isoformat())
            elif kwargs["status"] in ("completed", "failed"):
                kwargs.setdefault("completed_at", datetime.utcnow().isoformat())
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [task_id]
        await self.execute(f"UPDATE tasks SET {sets} WHERE id = ?", tuple(vals))

    async def list_tasks(self, agent_type: str | None = None, status: str | None = None,
                         limit: int = 50, offset: int = 0) -> list[dict]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if agent_type:
            sql += " AND agent_type = ?"
            params.append(agent_type)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return await self.fetch_all(sql, tuple(params))

    async def get_pending_tasks(self) -> list[dict]:
        return await self.fetch_all(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
        )

    # --- Cron Jobs ---

    async def create_cron_job(self, name: str, schedule: str, agent_type: str, prompt: str) -> int:
        return await self.execute(
            "INSERT INTO cron_jobs (name, schedule, agent_type, prompt) VALUES (?, ?, ?, ?)",
            (name, schedule, agent_type, prompt),
        )

    async def get_cron_job(self, job_id: int) -> dict | None:
        return await self.fetch_one("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))

    async def update_cron_job(self, job_id: int, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id]
        await self.execute(f"UPDATE cron_jobs SET {sets} WHERE id = ?", tuple(vals))

    async def list_cron_jobs(self) -> list[dict]:
        return await self.fetch_all("SELECT * FROM cron_jobs ORDER BY name")

    async def delete_cron_job(self, job_id: int) -> None:
        await self.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))

    # --- Agents ---

    async def create_agent(self, name: str, system_prompt: str,
                           working_dir: str | None = None, timeout_seconds: int = 300) -> int:
        return await self.execute(
            "INSERT INTO agents (name, system_prompt, working_dir, timeout_seconds) VALUES (?, ?, ?, ?)",
            (name, system_prompt, working_dir, timeout_seconds),
        )

    async def get_agent(self, name: str) -> dict | None:
        return await self.fetch_one("SELECT * FROM agents WHERE name = ?", (name,))

    async def update_agent(self, name: str, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [name]
        await self.execute(f"UPDATE agents SET {sets} WHERE name = ?", tuple(vals))

    async def list_agents(self) -> list[dict]:
        return await self.fetch_all("SELECT * FROM agents ORDER BY name")

    # --- Conversations ---

    async def add_conversation(self, task_id: int, role: str, content: str) -> int:
        return await self.execute(
            "INSERT INTO conversations (task_id, role, content) VALUES (?, ?, ?)",
            (task_id, role, content),
        )

    async def get_conversation(self, task_id: int) -> list[dict]:
        return await self.fetch_all(
            "SELECT * FROM conversations WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )

    # --- Settings ---

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (key, value),
        )

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = await self.fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    async def list_settings(self) -> list[dict]:
        return await self.fetch_all("SELECT * FROM settings ORDER BY key")

    # --- Browser Sessions ---

    async def create_browser_session(self, task_id: int, url: str | None = None) -> int:
        return await self.execute(
            "INSERT INTO browser_sessions (task_id, url) VALUES (?, ?)",
            (task_id, url),
        )

    async def update_browser_session(self, session_id: int, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [session_id]
        await self.execute(f"UPDATE browser_sessions SET {sets} WHERE id = ?", tuple(vals))

    async def list_browser_sessions(self, status: str | None = None) -> list[dict]:
        if status:
            return await self.fetch_all(
                "SELECT * FROM browser_sessions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        return await self.fetch_all("SELECT * FROM browser_sessions ORDER BY created_at DESC")
