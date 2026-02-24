# Punch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a lightweight, self-hosted AI assistant ("Punch") that uses Claude Code CLI (Max plan) to autonomously manage tasks, email, code, scheduling, browser automation, and full macOS control — accessible via Telegram and a web dashboard over Tailscale.

**Architecture:** Single Python process monolith. FastAPI serves the HTMX dashboard. APScheduler runs cron jobs in-process. Claude Code CLI is invoked as subprocesses. SQLite stores all state. Telegram bot uses long-polling. Playwright controls Chrome headlessly. Runs headless on Mac Mini 2014 (macOS Monterey) — no GUI overhead means ~4-6GB RAM available.

**Tech Stack:** Python 3.10+, FastAPI, HTMX, Tailwind CSS (CDN), SQLite (aiosqlite), APScheduler, python-telegram-bot, Playwright, google-api-python-client

**Design doc:** `docs/plans/2026-02-23-punch-design.md`

---

## Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `punch/config.py`
- Create: `punch/__init__.py`
- Create: `punch/requirements.txt`
- Create: `punch/main.py` (stub)
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

**Step 1: Create project directories**

```bash
mkdir -p punch/tools punch/web/templates punch/web/static tests
touch punch/__init__.py punch/tools/__init__.py tests/__init__.py
```

**Step 2: Write requirements.txt**

Create `punch/requirements.txt`:

```
fastapi>=0.104.0,<1.0
uvicorn[standard]>=0.24.0,<1.0
jinja2>=3.1.0,<4.0
python-multipart>=0.0.6,<1.0
python-telegram-bot>=20.0,<22.0
apscheduler>=3.10.0,<4.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.1.0
playwright>=1.40.0
aiosqlite>=0.19.0,<1.0
httpx>=0.25.0,<1.0
pytest>=7.0
pytest-asyncio>=0.21.0
```

**Step 3: Write the failing test for config**

Create `tests/test_config.py`:

```python
import os
import pytest
from punch.config import PunchConfig


def test_config_defaults():
    config = PunchConfig()
    assert config.db_path == "punch.db"
    assert config.web_host == "0.0.0.0"
    assert config.web_port == 8080
    assert config.max_concurrent_tasks == 4
    assert config.claude_command == "claude"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PUNCH_DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("PUNCH_WEB_PORT", "9090")
    monkeypatch.setenv("PUNCH_MAX_CONCURRENT", "2")
    config = PunchConfig()
    assert config.db_path == "/tmp/test.db"
    assert config.web_port == 9090
    assert config.max_concurrent_tasks == 2


def test_config_telegram_token():
    config = PunchConfig()
    assert config.telegram_token is None  # Not set by default


def test_config_data_dir_created(tmp_path, monkeypatch):
    data_dir = tmp_path / "punch_data"
    monkeypatch.setenv("PUNCH_DATA_DIR", str(data_dir))
    config = PunchConfig()
    config.ensure_dirs()
    assert data_dir.exists()
```

**Step 4: Run test to verify it fails**

```bash
cd /Users/siddy/Documents/Code/Punch && python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'punch.config'`

**Step 5: Implement config.py**

Create `punch/config.py`:

```python
import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PunchConfig:
    # Database
    db_path: str = field(default_factory=lambda: os.getenv("PUNCH_DB_PATH", "punch.db"))

    # Web server
    web_host: str = field(default_factory=lambda: os.getenv("PUNCH_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("PUNCH_WEB_PORT", "8080")))

    # Claude Code
    claude_command: str = field(default_factory=lambda: os.getenv("PUNCH_CLAUDE_CMD", "claude"))
    max_concurrent_tasks: int = field(default_factory=lambda: int(os.getenv("PUNCH_MAX_CONCURRENT", "4")))

    # Telegram
    telegram_token: str | None = field(default_factory=lambda: os.getenv("PUNCH_TELEGRAM_TOKEN"))
    telegram_allowed_users: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("PUNCH_TELEGRAM_USERS", "").split(",") if x.strip()
    ])

    # Data directories
    data_dir: str = field(default_factory=lambda: os.getenv("PUNCH_DATA_DIR", "data"))
    screenshots_dir: str = field(default_factory=lambda: os.getenv("PUNCH_SCREENSHOTS_DIR", "data/screenshots"))
    workspaces_dir: str = field(default_factory=lambda: os.getenv("PUNCH_WORKSPACES_DIR", "data/workspaces"))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("PUNCH_LOG_LEVEL", "INFO"))

    def ensure_dirs(self):
        for d in [self.data_dir, self.screenshots_dir, self.workspaces_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)
```

**Step 6: Run test to verify it passes**

```bash
python -m pytest tests/test_config.py -v
```

Expected: ALL PASS

**Step 7: Create main.py stub**

Create `punch/main.py`:

```python
#!/usr/bin/env python3
"""Punch: Lightweight self-hosted AI assistant."""

import asyncio
import logging
import signal
import sys

from punch.config import PunchConfig

logger = logging.getLogger("punch")


async def main():
    config = PunchConfig()
    config.ensure_dirs()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Punch starting up...")

    # Components will be added in subsequent tasks
    logger.info("Punch ready.")

    # Keep running until interrupted
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    logger.info("Punch shutting down.")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 8: Commit**

```bash
git add punch/ tests/ && git commit -m "feat: project scaffolding with config and main entry point"
```

---

## Task 2: Database Layer

**Files:**
- Create: `punch/db.py`
- Create: `tests/test_db.py`

**Step 1: Write failing tests**

Create `tests/test_db.py`:

```python
import pytest
import pytest_asyncio
from punch.db import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_initialize_creates_tables(db):
    tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t["name"] for t in tables]
    assert "tasks" in table_names
    assert "cron_jobs" in table_names
    assert "agents" in table_names
    assert "conversations" in table_names
    assert "settings" in table_names
    assert "browser_sessions" in table_names


@pytest.mark.asyncio
async def test_create_task(db):
    task_id = await db.create_task(agent_type="general", prompt="Hello world")
    task = await db.get_task(task_id)
    assert task["agent_type"] == "general"
    assert task["prompt"] == "Hello world"
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_update_task_status(db):
    task_id = await db.create_task(agent_type="general", prompt="Test")
    await db.update_task(task_id, status="running")
    task = await db.get_task(task_id)
    assert task["status"] == "running"


@pytest.mark.asyncio
async def test_list_tasks_filtered(db):
    await db.create_task(agent_type="email", prompt="Check email")
    await db.create_task(agent_type="code", prompt="Fix bug")
    await db.create_task(agent_type="email", prompt="Send reply")

    email_tasks = await db.list_tasks(agent_type="email")
    assert len(email_tasks) == 2

    all_tasks = await db.list_tasks()
    assert len(all_tasks) == 3


@pytest.mark.asyncio
async def test_cron_job_crud(db):
    job_id = await db.create_cron_job(
        name="Email Check", schedule="*/15 * * * *",
        agent_type="email", prompt="Check emails"
    )
    job = await db.get_cron_job(job_id)
    assert job["name"] == "Email Check"
    assert job["enabled"] == 1

    await db.update_cron_job(job_id, enabled=False)
    job = await db.get_cron_job(job_id)
    assert job["enabled"] == 0


@pytest.mark.asyncio
async def test_agent_crud(db):
    agent_id = await db.create_agent(
        name="email", system_prompt="You are an email assistant.",
        working_dir="/tmp/email", timeout_seconds=300
    )
    agent = await db.get_agent("email")
    assert agent["system_prompt"] == "You are an email assistant."
    assert agent["timeout_seconds"] == 300


@pytest.mark.asyncio
async def test_add_conversation_log(db):
    task_id = await db.create_task(agent_type="general", prompt="Test")
    await db.add_conversation(task_id, role="user", content="Hello")
    await db.add_conversation(task_id, role="assistant", content="Hi there")

    logs = await db.get_conversation(task_id)
    assert len(logs) == 2
    assert logs[0]["role"] == "user"
    assert logs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_settings_get_set(db):
    await db.set_setting("theme", "dark")
    value = await db.get_setting("theme")
    assert value == "dark"

    await db.set_setting("theme", "light")
    value = await db.get_setting("theme")
    assert value == "light"


@pytest.mark.asyncio
async def test_get_setting_default(db):
    value = await db.get_setting("nonexistent", default="fallback")
    assert value == "fallback"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_db.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'punch.db'`

**Step 3: Implement db.py**

Create `punch/db.py`:

```python
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
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_db.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/db.py tests/test_db.py && git commit -m "feat: SQLite database layer with full CRUD for tasks, agents, cron jobs, settings"
```

---

## Task 3: Claude Code Runner

**Files:**
- Create: `punch/runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write failing tests**

Create `tests/test_runner.py`:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from punch.runner import ClaudeRunner, RunResult


def test_run_result_dataclass():
    result = RunResult(stdout="hello", stderr="", exit_code=0, session_id=None)
    assert result.success
    assert result.stdout == "hello"


def test_run_result_failure():
    result = RunResult(stdout="", stderr="error", exit_code=1, session_id=None)
    assert not result.success


@pytest.mark.asyncio
async def test_runner_builds_oneshot_command():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Hello", oneshot=True)
    assert "claude" in cmd
    assert "--print" in cmd


@pytest.mark.asyncio
async def test_runner_builds_command_with_system_prompt():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Hello", system_prompt="You are helpful", oneshot=True)
    assert "--system-prompt" in cmd


@pytest.mark.asyncio
async def test_runner_builds_resume_command():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Continue", session_id="abc123")
    assert "--resume" in cmd
    assert "abc123" in cmd


@pytest.mark.asyncio
async def test_runner_respects_concurrency_limit():
    runner = ClaudeRunner(claude_command="echo", max_concurrent=1)
    assert runner._semaphore._value == 1
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_runner.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement runner.py**

Create `punch/runner.py`:

```python
import asyncio
import logging
import json
from dataclasses import dataclass

logger = logging.getLogger("punch.runner")


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    session_id: str | None

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ClaudeRunner:
    def __init__(self, claude_command: str = "claude", max_concurrent: int = 4):
        self.claude_command = claude_command
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _build_command(
        self,
        prompt: str,
        oneshot: bool = False,
        system_prompt: str | None = None,
        session_id: str | None = None,
        working_dir: str | None = None,
        output_format: str = "text",
    ) -> list[str]:
        cmd = [self.claude_command]

        if oneshot:
            cmd.append("--print")

        if session_id:
            cmd.extend(["--resume", session_id])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        if output_format == "json":
            cmd.extend(["--output-format", "json"])

        cmd.extend(["-p", prompt])

        return cmd

    async def run(
        self,
        prompt: str,
        oneshot: bool = False,
        system_prompt: str | None = None,
        session_id: str | None = None,
        working_dir: str | None = None,
        timeout: int = 300,
        output_format: str = "text",
    ) -> RunResult:
        cmd = self._build_command(
            prompt=prompt,
            oneshot=oneshot,
            system_prompt=system_prompt,
            session_id=session_id,
            output_format=output_format,
        )

        logger.info(f"Running Claude Code: {' '.join(cmd[:5])}...")

        async with self._semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                # Try to extract session ID from JSON output
                new_session_id = None
                if output_format == "json":
                    try:
                        data = json.loads(stdout)
                        new_session_id = data.get("session_id")
                        stdout = data.get("result", stdout)
                    except json.JSONDecodeError:
                        pass

                result = RunResult(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode or 0,
                    session_id=new_session_id or session_id,
                )
                logger.info(f"Claude Code finished: exit={result.exit_code}, output_len={len(result.stdout)}")
                return result

            except asyncio.TimeoutError:
                logger.warning(f"Claude Code timed out after {timeout}s")
                if proc:
                    proc.kill()
                return RunResult(
                    stdout="",
                    stderr=f"Task timed out after {timeout} seconds",
                    exit_code=-1,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error(f"Claude Code error: {e}")
                return RunResult(
                    stdout="",
                    stderr=str(e),
                    exit_code=-1,
                    session_id=session_id,
                )

    async def quick(self, prompt: str, system_prompt: str | None = None, timeout: int = 120) -> str:
        """Convenience: one-shot query, returns just the text."""
        result = await self.run(prompt=prompt, oneshot=True, system_prompt=system_prompt, timeout=timeout)
        if result.success:
            return result.stdout.strip()
        raise RuntimeError(f"Claude Code failed: {result.stderr}")
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_runner.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/runner.py tests/test_runner.py && git commit -m "feat: Claude Code CLI runner with concurrency limiting and timeout handling"
```

---

## Task 4: Task Orchestrator

**Files:**
- Create: `punch/orchestrator.py`
- Create: `tests/test_orchestrator.py`

**Step 1: Write failing tests**

Create `tests/test_orchestrator.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from punch.db import Database
from punch.runner import ClaudeRunner, RunResult
from punch.orchestrator import Orchestrator


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def orchestrator(db):
    runner = ClaudeRunner(claude_command="echo", max_concurrent=2)
    orch = Orchestrator(db=db, runner=runner)
    return orch


@pytest.mark.asyncio
async def test_submit_task(orchestrator):
    task_id = await orchestrator.submit("general", "Hello world")
    assert task_id > 0
    task = await orchestrator.db.get_task(task_id)
    assert task["status"] == "pending"


@pytest.mark.asyncio
async def test_submit_with_priority(orchestrator):
    task_id = await orchestrator.submit("general", "Urgent!", priority=10)
    task = await orchestrator.db.get_task(task_id)
    assert task["priority"] == 10


@pytest.mark.asyncio
async def test_execute_task_updates_status(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Done!", stderr="", exit_code=0, session_id="sess1"
    ))

    task_id = await orchestrator.submit("general", "Do something")
    await orchestrator.execute_task(task_id)

    task = await orchestrator.db.get_task(task_id)
    assert task["status"] == "completed"
    assert task["result"] == "Done!"
    assert task["session_id"] == "sess1"


@pytest.mark.asyncio
async def test_execute_task_handles_failure(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="", stderr="Something broke", exit_code=1, session_id=None
    ))

    task_id = await orchestrator.submit("general", "Fail")
    await orchestrator.execute_task(task_id)

    task = await orchestrator.db.get_task(task_id)
    assert task["status"] == "failed"
    assert task["error"] == "Something broke"


@pytest.mark.asyncio
async def test_execute_task_uses_agent_config(orchestrator, db):
    await db.create_agent(
        name="email", system_prompt="You are an email assistant.",
        working_dir="/tmp/email", timeout_seconds=120
    )
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Email sent", stderr="", exit_code=0, session_id=None
    ))

    task_id = await orchestrator.submit("email", "Send email to Bob")
    await orchestrator.execute_task(task_id)

    call_kwargs = orchestrator.runner.run.call_args.kwargs
    assert call_kwargs["system_prompt"] == "You are an email assistant."
    assert call_kwargs["working_dir"] == "/tmp/email"
    assert call_kwargs["timeout"] == 120
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: FAIL

**Step 3: Implement orchestrator.py**

Create `punch/orchestrator.py`:

```python
import asyncio
import logging
from typing import Callable, Awaitable

from punch.db import Database
from punch.runner import ClaudeRunner

logger = logging.getLogger("punch.orchestrator")

# Callbacks for notifications (set by telegram bot, web, etc.)
NotifyCallback = Callable[[int, str, str], Awaitable[None]]  # task_id, status, message


class Orchestrator:
    def __init__(self, db: Database, runner: ClaudeRunner):
        self.db = db
        self.runner = runner
        self._notify_callbacks: list[NotifyCallback] = []
        self._processing = False

    def on_notify(self, callback: NotifyCallback):
        self._notify_callbacks.append(callback)

    async def _notify(self, task_id: int, status: str, message: str):
        for cb in self._notify_callbacks:
            try:
                await cb(task_id, status, message)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

    async def submit(self, agent_type: str, prompt: str, priority: int = 0,
                     working_dir: str | None = None, source: str = "manual") -> int:
        task_id = await self.db.create_task(
            agent_type=agent_type, prompt=prompt,
            priority=priority, working_dir=working_dir, source=source,
        )
        logger.info(f"Task {task_id} submitted: agent={agent_type}, source={source}")
        return task_id

    async def execute_task(self, task_id: int) -> None:
        task = await self.db.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        # Get agent config if available
        agent = await self.db.get_agent(task["agent_type"])
        system_prompt = agent["system_prompt"] if agent else None
        working_dir = task.get("working_dir") or (agent["working_dir"] if agent else None)
        timeout = agent["timeout_seconds"] if agent else 300

        # Mark as running
        await self.db.update_task(task_id, status="running")
        await self._notify(task_id, "running", f"Starting: {task['prompt'][:100]}")

        # Log the prompt
        await self.db.add_conversation(task_id, role="user", content=task["prompt"])

        # Determine if one-shot or multi-step
        oneshot = not any(kw in task["prompt"].lower() for kw in [
            "fix", "implement", "build", "deploy", "commit", "create", "write", "refactor",
            "update", "modify", "change", "add", "remove", "delete", "install",
        ])

        result = await self.runner.run(
            prompt=task["prompt"],
            oneshot=oneshot,
            system_prompt=system_prompt,
            session_id=task.get("session_id"),
            working_dir=working_dir,
            timeout=timeout,
        )

        # Log the response
        await self.db.add_conversation(task_id, role="assistant", content=result.stdout)

        if result.success:
            await self.db.update_task(
                task_id, status="completed",
                result=result.stdout, session_id=result.session_id,
            )
            await self._notify(task_id, "completed", result.stdout[:500])
            logger.info(f"Task {task_id} completed successfully")
        else:
            await self.db.update_task(
                task_id, status="failed",
                error=result.stderr, session_id=result.session_id,
            )
            await self._notify(task_id, "failed", f"Error: {result.stderr[:500]}")
            logger.warning(f"Task {task_id} failed: {result.stderr[:200]}")

    async def process_queue(self) -> None:
        """Process pending tasks from the queue."""
        pending = await self.db.get_pending_tasks()
        if not pending:
            return

        for task in pending:
            # Fire and forget — concurrency is managed by the runner's semaphore
            asyncio.create_task(self.execute_task(task["id"]))

    async def start_processing(self, interval: float = 5.0):
        """Start the background task processor."""
        self._processing = True
        logger.info("Task processor started")
        while self._processing:
            try:
                await self.process_queue()
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
            await asyncio.sleep(interval)

    def stop_processing(self):
        self._processing = False
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_orchestrator.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/orchestrator.py tests/test_orchestrator.py && git commit -m "feat: task orchestrator with queue processing and notification callbacks"
```

---

## Task 5: Task Scheduler (APScheduler + Cron Jobs)

**Files:**
- Create: `punch/scheduler.py`
- Create: `tests/test_scheduler.py`

**Step 1: Write failing tests**

Create `tests/test_scheduler.py`:

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from punch.db import Database
from punch.scheduler import PunchScheduler


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_scheduler_loads_jobs(db):
    await db.create_cron_job(
        name="Test Job", schedule="*/5 * * * *",
        agent_type="general", prompt="Test"
    )
    submit_fn = AsyncMock(return_value=1)
    scheduler = PunchScheduler(db=db, submit_fn=submit_fn)
    await scheduler.load_jobs()
    assert len(scheduler.get_jobs()) == 1


@pytest.mark.asyncio
async def test_scheduler_skips_disabled_jobs(db):
    job_id = await db.create_cron_job(
        name="Disabled", schedule="*/5 * * * *",
        agent_type="general", prompt="Skip me"
    )
    await db.update_cron_job(job_id, enabled=False)

    submit_fn = AsyncMock(return_value=1)
    scheduler = PunchScheduler(db=db, submit_fn=submit_fn)
    await scheduler.load_jobs()
    assert len(scheduler.get_jobs()) == 0


@pytest.mark.asyncio
async def test_scheduler_trigger_submits_task(db):
    job_id = await db.create_cron_job(
        name="Trigger Test", schedule="*/5 * * * *",
        agent_type="email", prompt="Check emails"
    )
    submit_fn = AsyncMock(return_value=42)
    scheduler = PunchScheduler(db=db, submit_fn=submit_fn)
    await scheduler._trigger_job(job_id)
    submit_fn.assert_called_once_with("email", "Check emails", source="cron")
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: FAIL

**Step 3: Implement scheduler.py**

Create `punch/scheduler.py`:

```python
import asyncio
import logging
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from punch.db import Database

logger = logging.getLogger("punch.scheduler")

SubmitFn = Callable[..., Awaitable[int]]


class PunchScheduler:
    def __init__(self, db: Database, submit_fn: SubmitFn):
        self.db = db
        self.submit_fn = submit_fn
        self._scheduler = AsyncIOScheduler()
        self._job_map: dict[int, str] = {}  # cron_job_id -> apscheduler_job_id

    async def load_jobs(self):
        """Load all enabled cron jobs from the database."""
        jobs = await self.db.list_cron_jobs()
        for job in jobs:
            if job["enabled"]:
                self._add_job(job)
        logger.info(f"Loaded {len(self._job_map)} cron jobs")

    def _add_job(self, job: dict):
        parts = job["schedule"].split()
        if len(parts) != 5:
            logger.error(f"Invalid cron schedule for job {job['id']}: {job['schedule']}")
            return

        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        ap_job = self._scheduler.add_job(
            self._trigger_job, trigger,
            args=[job["id"]],
            id=f"cron_{job['id']}",
            name=job["name"],
            replace_existing=True,
        )
        self._job_map[job["id"]] = ap_job.id

    async def _trigger_job(self, cron_job_id: int):
        job = await self.db.get_cron_job(cron_job_id)
        if not job or not job["enabled"]:
            return

        logger.info(f"Cron trigger: {job['name']} (agent={job['agent_type']})")
        try:
            task_id = await self.submit_fn(job["agent_type"], job["prompt"], source="cron")
            await self.db.update_cron_job(cron_job_id, last_run="datetime('now')")
            logger.info(f"Cron job {job['name']} created task {task_id}")
        except Exception as e:
            logger.error(f"Cron job {job['name']} failed: {e}")

    async def add_job(self, cron_job_id: int):
        """Add a single job from the database."""
        job = await self.db.get_cron_job(cron_job_id)
        if job and job["enabled"]:
            self._add_job(job)

    async def remove_job(self, cron_job_id: int):
        """Remove a scheduled job."""
        ap_job_id = self._job_map.pop(cron_job_id, None)
        if ap_job_id:
            try:
                self._scheduler.remove_job(ap_job_id)
            except Exception:
                pass

    async def reload_job(self, cron_job_id: int):
        """Reload a job from the database (after config change)."""
        await self.remove_job(cron_job_id)
        await self.add_job(cron_job_id)

    def get_jobs(self) -> list:
        return self._scheduler.get_jobs()

    def start(self):
        self._scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        self._scheduler.shutdown()
        logger.info("Scheduler shutdown")
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/scheduler.py tests/test_scheduler.py && git commit -m "feat: cron job scheduler with database-backed configuration"
```

---

## Task 6: FastAPI Web App Skeleton + Base Template

**Files:**
- Create: `punch/web/app.py`
- Create: `punch/web/__init__.py`
- Create: `punch/web/templates/base.html`
- Create: `punch/web/templates/home.html`
- Create: `tests/test_web.py`

**Step 1: Write failing tests**

Create `tests/test_web.py`:

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from punch.db import Database
from punch.web.app import create_app


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def client(db):
    app = create_app(db=db, orchestrator=None, scheduler=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_home_page(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Punch" in resp.text


@pytest.mark.asyncio
async def test_tasks_page(client):
    resp = await client.get("/tasks")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_agents_page(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cron_page(client):
    resp = await client.get("/cron")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_create_task(client, db):
    resp = await client.post("/api/tasks", json={
        "agent_type": "general",
        "prompt": "Test task",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] > 0


@pytest.mark.asyncio
async def test_api_list_tasks(client, db):
    await db.create_task(agent_type="general", prompt="Task 1")
    await db.create_task(agent_type="email", prompt="Task 2")
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_web.py -v
```

Expected: FAIL

**Step 3: Create web/__init__.py**

```bash
touch punch/web/__init__.py
```

**Step 4: Implement web/app.py**

Create `punch/web/app.py`:

```python
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from punch.db import Database

logger = logging.getLogger("punch.web")

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(db: Database, orchestrator=None, scheduler=None) -> FastAPI:
    app = FastAPI(title="Punch", docs_url="/api/docs")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # Store references for route handlers
    app.state.db = db
    app.state.orchestrator = orchestrator
    app.state.scheduler = scheduler

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- HTML Pages ---

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        recent_tasks = await db.list_tasks(limit=20)
        return templates.TemplateResponse("home.html", {
            "request": request, "tasks": recent_tasks, "page": "home",
        })

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(request: Request, status: str = None, agent_type: str = None):
        tasks = await db.list_tasks(status=status, agent_type=agent_type, limit=100)
        agents = await db.list_agents()
        return templates.TemplateResponse("tasks.html", {
            "request": request, "tasks": tasks, "agents": agents,
            "page": "tasks", "filter_status": status, "filter_agent": agent_type,
        })

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    async def task_detail(request: Request, task_id: int):
        task = await db.get_task(task_id)
        conversation = await db.get_conversation(task_id) if task else []
        return templates.TemplateResponse("task_detail.html", {
            "request": request, "task": task, "conversation": conversation, "page": "tasks",
        })

    @app.get("/agents", response_class=HTMLResponse)
    async def agents_page(request: Request):
        agents = await db.list_agents()
        return templates.TemplateResponse("agents.html", {
            "request": request, "agents": agents, "page": "agents",
        })

    @app.get("/cron", response_class=HTMLResponse)
    async def cron_page(request: Request):
        jobs = await db.list_cron_jobs()
        agents = await db.list_agents()
        return templates.TemplateResponse("cron.html", {
            "request": request, "jobs": jobs, "agents": agents, "page": "cron",
        })

    @app.get("/browser", response_class=HTMLResponse)
    async def browser_page(request: Request):
        sessions = await db.list_browser_sessions()
        return templates.TemplateResponse("browser.html", {
            "request": request, "sessions": sessions, "page": "browser",
        })

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        settings = await db.list_settings()
        return templates.TemplateResponse("settings.html", {
            "request": request, "settings": settings, "page": "settings",
        })

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        # Recent tasks with their conversations serve as logs
        tasks = await db.list_tasks(limit=50)
        return templates.TemplateResponse("logs.html", {
            "request": request, "tasks": tasks, "page": "logs",
        })

    # --- API Endpoints ---

    @app.post("/api/tasks")
    async def api_create_task(request: Request):
        body = await request.json()
        agent_type = body.get("agent_type", "general")
        prompt = body.get("prompt", "")
        priority = body.get("priority", 0)

        if orchestrator:
            task_id = await orchestrator.submit(agent_type, prompt, priority=priority, source="api")
        else:
            task_id = await db.create_task(agent_type=agent_type, prompt=prompt, priority=priority, source="api")

        return {"task_id": task_id}

    @app.get("/api/tasks")
    async def api_list_tasks(status: str = None, agent_type: str = None, limit: int = 50):
        return await db.list_tasks(status=status, agent_type=agent_type, limit=limit)

    @app.get("/api/tasks/{task_id}")
    async def api_get_task(task_id: int):
        task = await db.get_task(task_id)
        if not task:
            return JSONResponse({"error": "Not found"}, status_code=404)
        conversation = await db.get_conversation(task_id)
        return {"task": task, "conversation": conversation}

    # --- HTMX Partials ---

    @app.post("/htmx/tasks/create", response_class=HTMLResponse)
    async def htmx_create_task(request: Request, agent_type: str = Form(...), prompt: str = Form(...)):
        if orchestrator:
            task_id = await orchestrator.submit(agent_type, prompt, source="dashboard")
            asyncio.create_task(orchestrator.execute_task(task_id))
        else:
            task_id = await db.create_task(agent_type=agent_type, prompt=prompt, source="dashboard")
        tasks = await db.list_tasks(limit=20)
        return templates.TemplateResponse("partials/task_list.html", {
            "request": request, "tasks": tasks,
        })

    @app.get("/htmx/tasks/refresh", response_class=HTMLResponse)
    async def htmx_refresh_tasks(request: Request, status: str = None, agent_type: str = None):
        tasks = await db.list_tasks(status=status, agent_type=agent_type, limit=100)
        return templates.TemplateResponse("partials/task_list.html", {
            "request": request, "tasks": tasks,
        })

    # --- Cron Job API ---

    @app.post("/api/cron")
    async def api_create_cron(request: Request):
        body = await request.json()
        job_id = await db.create_cron_job(
            name=body["name"], schedule=body["schedule"],
            agent_type=body["agent_type"], prompt=body["prompt"],
        )
        if scheduler:
            await scheduler.add_job(job_id)
        return {"job_id": job_id}

    @app.put("/api/cron/{job_id}/toggle")
    async def api_toggle_cron(job_id: int):
        job = await db.get_cron_job(job_id)
        if not job:
            return JSONResponse({"error": "Not found"}, status_code=404)
        new_state = not job["enabled"]
        await db.update_cron_job(job_id, enabled=new_state)
        if scheduler:
            await scheduler.reload_job(job_id)
        return {"enabled": new_state}

    @app.delete("/api/cron/{job_id}")
    async def api_delete_cron(job_id: int):
        if scheduler:
            await scheduler.remove_job(job_id)
        await db.delete_cron_job(job_id)
        return {"ok": True}

    # --- Agent API ---

    @app.post("/api/agents")
    async def api_create_agent(request: Request):
        body = await request.json()
        agent_id = await db.create_agent(
            name=body["name"], system_prompt=body["system_prompt"],
            working_dir=body.get("working_dir"), timeout_seconds=body.get("timeout_seconds", 300),
        )
        return {"agent_id": agent_id}

    @app.put("/api/agents/{name}")
    async def api_update_agent(name: str, request: Request):
        body = await request.json()
        await db.update_agent(name, **body)
        return {"ok": True}

    @app.get("/api/agents")
    async def api_list_agents():
        return await db.list_agents()

    # --- Settings API ---

    @app.get("/api/settings")
    async def api_list_settings():
        return await db.list_settings()

    @app.put("/api/settings/{key}")
    async def api_set_setting(key: str, request: Request):
        body = await request.json()
        await db.set_setting(key, body["value"])
        return {"ok": True}

    return app
```

**Step 5: Create base.html template**

Create `punch/web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en" class="h-full bg-gray-950">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Punch{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        punch: {
                            50: '#fef2f2', 100: '#fee2e2', 200: '#fecaca',
                            300: '#fca5a5', 400: '#f87171', 500: '#ef4444',
                            600: '#dc2626', 700: '#b91c1c', 800: '#991b1b',
                            900: '#7f1d1d', 950: '#450a0a',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        .htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
        .htmx-request .htmx-indicator { opacity: 1; }
        .htmx-request.htmx-indicator { opacity: 1; }
        @keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .animate-pulse-dot { animation: pulse-dot 1.5s ease-in-out infinite; }
    </style>
</head>
<body class="h-full dark">
    <div class="flex h-full">
        <!-- Sidebar -->
        <nav class="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
            <div class="p-4 border-b border-gray-800">
                <h1 class="text-xl font-bold text-punch-500">Punch</h1>
                <p class="text-xs text-gray-500 mt-1">AI Assistant</p>
            </div>
            <div class="flex-1 py-3">
                {% set nav_items = [
                    ("home", "/", "Home", "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"),
                    ("agents", "/agents", "Agents", "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"),
                    ("tasks", "/tasks", "Tasks", "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"),
                    ("cron", "/cron", "Cron Jobs", "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"),
                    ("browser", "/browser", "Browser", "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"),
                    ("settings", "/settings", "Settings", "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z"),
                    ("logs", "/logs", "Logs", "M4 6h16M4 10h16M4 14h16M4 18h16"),
                ] %}
                {% for key, url, label, icon_path in nav_items %}
                <a href="{{ url }}"
                   class="flex items-center px-4 py-2 text-sm {% if page == key %}text-punch-400 bg-gray-800{% else %}text-gray-400 hover:text-gray-200 hover:bg-gray-800/50{% endif %} transition-colors">
                    <svg class="w-5 h-5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="{{ icon_path }}"/>
                    </svg>
                    {{ label }}
                </a>
                {% endfor %}
            </div>
            <div class="p-4 border-t border-gray-800">
                <div class="flex items-center">
                    <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse-dot mr-2"></div>
                    <span class="text-xs text-gray-500">System running</span>
                </div>
            </div>
        </nav>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto bg-gray-950 text-gray-100">
            <div class="max-w-6xl mx-auto p-6">
                {% block content %}{% endblock %}
            </div>
        </main>
    </div>
</body>
</html>
```

**Step 6: Create home.html template**

Create `punch/web/templates/home.html`:

```html
{% extends "base.html" %}
{% block title %}Punch - Home{% endblock %}
{% block content %}
<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Dashboard</h2>
        <button onclick="document.getElementById('new-task-modal').classList.toggle('hidden')"
                class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium transition-colors">
            New Task
        </button>
    </div>

    <!-- New Task Modal -->
    <div id="new-task-modal" class="hidden bg-gray-900 rounded-lg p-6 border border-gray-800">
        <h3 class="text-lg font-semibold mb-4">Create Task</h3>
        <form hx-post="/htmx/tasks/create" hx-target="#task-feed" hx-swap="innerHTML"
              hx-on::after-request="document.getElementById('new-task-modal').classList.add('hidden')">
            <div class="space-y-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Agent</label>
                    <select name="agent_type" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
                        <option value="general">General</option>
                        <option value="email">Email</option>
                        <option value="code">Code</option>
                        <option value="research">Research</option>
                        <option value="browser">Browser</option>
                        <option value="macos">macOS</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Prompt</label>
                    <textarea name="prompt" rows="3"
                              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
                              placeholder="What should the agent do?"></textarea>
                </div>
                <button type="submit" class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">
                    Submit
                </button>
            </div>
        </form>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-4 gap-4">
        {% set running = tasks|selectattr("status", "equalto", "running")|list|length %}
        {% set completed = tasks|selectattr("status", "equalto", "completed")|list|length %}
        {% set failed = tasks|selectattr("status", "equalto", "failed")|list|length %}
        {% set pending = tasks|selectattr("status", "equalto", "pending")|list|length %}
        {% for label, count, color in [("Running", running, "yellow"), ("Pending", pending, "blue"), ("Completed", completed, "green"), ("Failed", failed, "red")] %}
        <div class="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div class="text-sm text-gray-400">{{ label }}</div>
            <div class="text-2xl font-bold text-{{ color }}-400 mt-1">{{ count }}</div>
        </div>
        {% endfor %}
    </div>

    <!-- Recent Tasks -->
    <div>
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold">Recent Activity</h3>
            <div hx-get="/htmx/tasks/refresh" hx-trigger="every 10s" hx-target="#task-feed" hx-swap="innerHTML"
                 class="text-xs text-gray-500">Auto-refreshing</div>
        </div>
        <div id="task-feed" class="space-y-2">
            {% include "partials/task_list.html" %}
        </div>
    </div>
</div>
{% endblock %}
```

**Step 7: Create partials/task_list.html**

Create `punch/web/templates/partials/task_list.html`:

```html
{% for task in tasks %}
<a href="/tasks/{{ task.id }}" class="block bg-gray-900 rounded-lg p-4 border border-gray-800 hover:border-gray-700 transition-colors">
    <div class="flex items-center justify-between">
        <div class="flex items-center space-x-3">
            {% if task.status == "running" %}
            <div class="w-2 h-2 rounded-full bg-yellow-500 animate-pulse-dot"></div>
            {% elif task.status == "completed" %}
            <div class="w-2 h-2 rounded-full bg-green-500"></div>
            {% elif task.status == "failed" %}
            <div class="w-2 h-2 rounded-full bg-red-500"></div>
            {% else %}
            <div class="w-2 h-2 rounded-full bg-gray-500"></div>
            {% endif %}
            <span class="text-sm font-medium">{{ task.agent_type }}</span>
            <span class="text-sm text-gray-400">{{ task.prompt[:80] }}{% if task.prompt|length > 80 %}...{% endif %}</span>
        </div>
        <div class="flex items-center space-x-3">
            <span class="text-xs px-2 py-1 rounded-full
                {% if task.status == 'running' %}bg-yellow-900/50 text-yellow-400
                {% elif task.status == 'completed' %}bg-green-900/50 text-green-400
                {% elif task.status == 'failed' %}bg-red-900/50 text-red-400
                {% else %}bg-gray-800 text-gray-400{% endif %}">
                {{ task.status }}
            </span>
            <span class="text-xs text-gray-600">{{ task.created_at }}</span>
        </div>
    </div>
</a>
{% endfor %}
{% if not tasks %}
<div class="text-center py-8 text-gray-600">No tasks yet. Create one above.</div>
{% endif %}
```

**Step 8: Create stub templates for other pages**

Create these minimal templates so routes don't 500:

`punch/web/templates/tasks.html`:
```html
{% extends "base.html" %}
{% block title %}Tasks - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Tasks</h2>
        <div class="flex space-x-2">
            <a href="/tasks" class="px-3 py-1 text-sm rounded-lg {% if not filter_status %}bg-gray-800 text-white{% else %}text-gray-400 hover:text-white{% endif %}">All</a>
            {% for s in ["pending", "running", "completed", "failed"] %}
            <a href="/tasks?status={{ s }}" class="px-3 py-1 text-sm rounded-lg {% if filter_status == s %}bg-gray-800 text-white{% else %}text-gray-400 hover:text-white{% endif %}">{{ s|capitalize }}</a>
            {% endfor %}
        </div>
    </div>
    <div id="task-feed" hx-get="/htmx/tasks/refresh{% if filter_status %}?status={{ filter_status }}{% endif %}" hx-trigger="every 10s" hx-swap="innerHTML" class="space-y-2">
        {% include "partials/task_list.html" %}
    </div>
</div>
{% endblock %}
```

`punch/web/templates/task_detail.html`:
```html
{% extends "base.html" %}
{% block title %}Task #{{ task.id }} - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <div class="flex items-center space-x-4">
        <a href="/tasks" class="text-gray-400 hover:text-white">&larr; Back</a>
        <h2 class="text-2xl font-bold">Task #{{ task.id }}</h2>
        <span class="text-xs px-2 py-1 rounded-full
            {% if task.status == 'running' %}bg-yellow-900/50 text-yellow-400
            {% elif task.status == 'completed' %}bg-green-900/50 text-green-400
            {% elif task.status == 'failed' %}bg-red-900/50 text-red-400
            {% else %}bg-gray-800 text-gray-400{% endif %}">{{ task.status }}</span>
    </div>
    <div class="bg-gray-900 rounded-lg p-6 border border-gray-800">
        <div class="grid grid-cols-2 gap-4 text-sm mb-6">
            <div><span class="text-gray-400">Agent:</span> {{ task.agent_type }}</div>
            <div><span class="text-gray-400">Source:</span> {{ task.source }}</div>
            <div><span class="text-gray-400">Created:</span> {{ task.created_at }}</div>
            <div><span class="text-gray-400">Completed:</span> {{ task.completed_at or "-" }}</div>
        </div>
        <div class="mb-4">
            <h3 class="text-sm text-gray-400 mb-2">Prompt</h3>
            <pre class="bg-gray-800 rounded p-4 text-sm whitespace-pre-wrap">{{ task.prompt }}</pre>
        </div>
        {% if task.result %}
        <div class="mb-4">
            <h3 class="text-sm text-gray-400 mb-2">Result</h3>
            <pre class="bg-gray-800 rounded p-4 text-sm whitespace-pre-wrap">{{ task.result }}</pre>
        </div>
        {% endif %}
        {% if task.error %}
        <div class="mb-4">
            <h3 class="text-sm text-red-400 mb-2">Error</h3>
            <pre class="bg-red-900/20 rounded p-4 text-sm whitespace-pre-wrap text-red-300">{{ task.error }}</pre>
        </div>
        {% endif %}
    </div>
    {% if conversation %}
    <div>
        <h3 class="text-lg font-semibold mb-4">Conversation Log</h3>
        <div class="space-y-3">
            {% for msg in conversation %}
            <div class="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <div class="text-xs text-gray-500 mb-2">{{ msg.role }} &middot; {{ msg.created_at }}</div>
                <pre class="text-sm whitespace-pre-wrap">{{ msg.content }}</pre>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}
```

`punch/web/templates/agents.html`:
```html
{% extends "base.html" %}
{% block title %}Agents - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Agents</h2>
        <button onclick="document.getElementById('new-agent-modal').classList.toggle('hidden')"
                class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">New Agent</button>
    </div>
    <div id="new-agent-modal" class="hidden bg-gray-900 rounded-lg p-6 border border-gray-800">
        <h3 class="text-lg font-semibold mb-4">Create Agent</h3>
        <form id="agent-form" class="space-y-4">
            <div>
                <label class="block text-sm text-gray-400 mb-1">Name</label>
                <input name="name" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="e.g. email, code, research">
            </div>
            <div>
                <label class="block text-sm text-gray-400 mb-1">System Prompt</label>
                <textarea name="system_prompt" rows="4" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="You are an email assistant..."></textarea>
            </div>
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Working Directory</label>
                    <input name="working_dir" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="/path/to/workspace">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Timeout (seconds)</label>
                    <input name="timeout_seconds" type="number" value="300" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
                </div>
            </div>
            <button type="submit" class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">Create</button>
        </form>
        <script>
            document.getElementById('agent-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const fd = new FormData(e.target);
                const body = Object.fromEntries(fd);
                body.timeout_seconds = parseInt(body.timeout_seconds);
                await fetch('/api/agents', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
                location.reload();
            });
        </script>
    </div>
    <div class="grid grid-cols-1 gap-4">
        {% for agent in agents %}
        <div class="bg-gray-900 rounded-lg p-6 border border-gray-800">
            <div class="flex items-center justify-between mb-3">
                <h3 class="text-lg font-semibold text-punch-400">{{ agent.name }}</h3>
                <span class="text-xs text-gray-500">timeout: {{ agent.timeout_seconds }}s</span>
            </div>
            <pre class="bg-gray-800 rounded p-3 text-xs text-gray-300 whitespace-pre-wrap mb-2">{{ agent.system_prompt }}</pre>
            {% if agent.working_dir %}
            <div class="text-xs text-gray-500">Working dir: {{ agent.working_dir }}</div>
            {% endif %}
        </div>
        {% endfor %}
        {% if not agents %}
        <div class="text-center py-8 text-gray-600">No agents configured. Create one to get started.</div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

`punch/web/templates/cron.html`:
```html
{% extends "base.html" %}
{% block title %}Cron Jobs - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <div class="flex items-center justify-between">
        <h2 class="text-2xl font-bold">Cron Jobs</h2>
        <button onclick="document.getElementById('new-cron-modal').classList.toggle('hidden')"
                class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">New Job</button>
    </div>
    <div id="new-cron-modal" class="hidden bg-gray-900 rounded-lg p-6 border border-gray-800">
        <h3 class="text-lg font-semibold mb-4">Create Cron Job</h3>
        <form id="cron-form" class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Name</label>
                    <input name="name" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="Email Triage">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Schedule (cron)</label>
                    <input name="schedule" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" placeholder="*/15 * * * *">
                </div>
            </div>
            <div>
                <label class="block text-sm text-gray-400 mb-1">Agent Type</label>
                <select name="agent_type" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
                    <option value="general">General</option>
                    <option value="email">Email</option>
                    <option value="code">Code</option>
                    <option value="research">Research</option>
                    <option value="browser">Browser</option>
                    <option value="macos">macOS</option>
                </select>
            </div>
            <div>
                <label class="block text-sm text-gray-400 mb-1">Prompt</label>
                <textarea name="prompt" rows="3" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"></textarea>
            </div>
            <button type="submit" class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">Create</button>
        </form>
        <script>
            document.getElementById('cron-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const body = Object.fromEntries(new FormData(e.target));
                await fetch('/api/cron', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
                location.reload();
            });
        </script>
    </div>
    <div class="space-y-3">
        {% for job in jobs %}
        <div class="bg-gray-900 rounded-lg p-4 border border-gray-800 flex items-center justify-between">
            <div>
                <div class="flex items-center space-x-3">
                    <span class="font-medium">{{ job.name }}</span>
                    <code class="text-xs bg-gray-800 px-2 py-1 rounded text-gray-400">{{ job.schedule }}</code>
                    <span class="text-xs text-gray-500">{{ job.agent_type }}</span>
                </div>
                <p class="text-sm text-gray-400 mt-1">{{ job.prompt[:100] }}{% if job.prompt|length > 100 %}...{% endif %}</p>
                {% if job.last_run %}<div class="text-xs text-gray-600 mt-1">Last run: {{ job.last_run }}</div>{% endif %}
            </div>
            <div class="flex items-center space-x-3">
                <button onclick="toggleCron({{ job.id }})" class="text-xs px-3 py-1 rounded-lg {% if job.enabled %}bg-green-900/50 text-green-400{% else %}bg-gray-800 text-gray-500{% endif %}">
                    {{ "Enabled" if job.enabled else "Disabled" }}
                </button>
                <button onclick="deleteCron({{ job.id }})" class="text-xs text-red-400 hover:text-red-300">Delete</button>
            </div>
        </div>
        {% endfor %}
        {% if not jobs %}
        <div class="text-center py-8 text-gray-600">No cron jobs configured.</div>
        {% endif %}
    </div>
</div>
<script>
    async function toggleCron(id) {
        await fetch(`/api/cron/${id}/toggle`, { method: 'PUT' });
        location.reload();
    }
    async function deleteCron(id) {
        if (confirm('Delete this cron job?')) {
            await fetch(`/api/cron/${id}`, { method: 'DELETE' });
            location.reload();
        }
    }
</script>
{% endblock %}
```

`punch/web/templates/browser.html`:
```html
{% extends "base.html" %}
{% block title %}Browser - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <h2 class="text-2xl font-bold">Browser Sessions</h2>
    <div class="space-y-4">
        {% for session in sessions %}
        <div class="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div class="flex items-center justify-between mb-2">
                <span class="text-sm font-medium">Session #{{ session.id }}</span>
                <span class="text-xs px-2 py-1 rounded-full {% if session.status == 'active' %}bg-green-900/50 text-green-400{% else %}bg-gray-800 text-gray-400{% endif %}">{{ session.status }}</span>
            </div>
            {% if session.url %}<div class="text-sm text-gray-400">{{ session.url }}</div>{% endif %}
            {% if session.screenshot_path %}<img src="/static/screenshots/{{ session.screenshot_path }}" class="mt-2 rounded border border-gray-800 max-w-full">{% endif %}
        </div>
        {% endfor %}
        {% if not sessions %}
        <div class="text-center py-8 text-gray-600">No browser sessions.</div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

`punch/web/templates/settings.html`:
```html
{% extends "base.html" %}
{% block title %}Settings - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <h2 class="text-2xl font-bold">Settings</h2>
    <div class="bg-gray-900 rounded-lg p-6 border border-gray-800">
        <form id="settings-form" class="space-y-4">
            <div>
                <label class="block text-sm text-gray-400 mb-1">Setting Key</label>
                <input name="key" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm">
            </div>
            <div>
                <label class="block text-sm text-gray-400 mb-1">Value</label>
                <textarea name="value" rows="2" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"></textarea>
            </div>
            <button type="submit" class="px-4 py-2 bg-punch-600 hover:bg-punch-700 rounded-lg text-sm font-medium">Save</button>
        </form>
        <script>
            document.getElementById('settings-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const fd = new FormData(e.target);
                await fetch(`/api/settings/${fd.get('key')}`, {
                    method: 'PUT', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({value: fd.get('value')}),
                });
                location.reload();
            });
        </script>
    </div>
    <div class="space-y-2">
        {% for s in settings %}
        <div class="bg-gray-900 rounded-lg p-4 border border-gray-800 flex items-center justify-between">
            <div>
                <span class="text-sm font-medium text-punch-400">{{ s.key }}</span>
                <span class="text-sm text-gray-400 ml-4">{{ s.value[:100] }}</span>
            </div>
            <span class="text-xs text-gray-600">{{ s.updated_at }}</span>
        </div>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

`punch/web/templates/logs.html`:
```html
{% extends "base.html" %}
{% block title %}Logs - Punch{% endblock %}
{% block content %}
<div class="space-y-6">
    <h2 class="text-2xl font-bold">Logs</h2>
    <div class="space-y-2" hx-get="/htmx/tasks/refresh" hx-trigger="every 10s" hx-swap="innerHTML">
        {% for task in tasks %}
        <a href="/tasks/{{ task.id }}" class="block bg-gray-900 rounded-lg p-3 border border-gray-800 hover:border-gray-700">
            <div class="flex items-center justify-between text-xs">
                <div class="flex items-center space-x-2">
                    <span class="text-gray-500">{{ task.created_at }}</span>
                    <span class="px-2 py-0.5 rounded {% if task.status == 'completed' %}bg-green-900/50 text-green-400{% elif task.status == 'failed' %}bg-red-900/50 text-red-400{% elif task.status == 'running' %}bg-yellow-900/50 text-yellow-400{% else %}bg-gray-800 text-gray-400{% endif %}">{{ task.status }}</span>
                    <span class="text-gray-400">{{ task.agent_type }}</span>
                </div>
                <span class="text-gray-500">{{ task.source }}</span>
            </div>
            <div class="text-sm text-gray-300 mt-1">{{ task.prompt[:120] }}{% if task.prompt|length > 120 %}...{% endif %}</div>
        </a>
        {% endfor %}
    </div>
</div>
{% endblock %}
```

**Step 9: Create partials directory**

```bash
mkdir -p punch/web/templates/partials
```

**Step 10: Run tests**

```bash
python -m pytest tests/test_web.py -v
```

Expected: ALL PASS

**Step 11: Commit**

```bash
git add punch/web/ tests/test_web.py && git commit -m "feat: FastAPI web app with HTMX dashboard, all pages, and REST API"
```

---

## Task 7: Telegram Bot

**Files:**
- Create: `punch/telegram_bot.py`
- Create: `tests/test_telegram.py`

**Step 1: Write failing tests**

Create `tests/test_telegram.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from punch.telegram_bot import PunchTelegramBot


@pytest.mark.asyncio
async def test_bot_init():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    assert bot.token == "fake-token"


@pytest.mark.asyncio
async def test_parse_agent_from_message():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    agent, prompt = bot._parse_message("/email Check my inbox")
    assert agent == "email"
    assert prompt == "Check my inbox"


@pytest.mark.asyncio
async def test_parse_agent_default():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    agent, prompt = bot._parse_message("What's the weather?")
    assert agent == "general"
    assert prompt == "What's the weather?"


@pytest.mark.asyncio
async def test_parse_agent_types():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    for cmd in ["email", "code", "research", "browser", "macos"]:
        agent, prompt = bot._parse_message(f"/{cmd} do something")
        assert agent == cmd
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_telegram.py -v
```

Expected: FAIL

**Step 3: Implement telegram_bot.py**

Create `punch/telegram_bot.py`:

```python
import logging
from typing import Callable, Awaitable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

from punch.db import Database

logger = logging.getLogger("punch.telegram")

SubmitFn = Callable[..., Awaitable[int]]
AGENT_COMMANDS = {"email", "code", "research", "browser", "macos", "general"}


class PunchTelegramBot:
    def __init__(self, token: str, submit_fn: SubmitFn, db: Database,
                 allowed_users: list[int] | None = None,
                 execute_fn: Callable | None = None):
        self.token = token
        self.submit_fn = submit_fn
        self.execute_fn = execute_fn
        self.db = db
        self.allowed_users = allowed_users or []
        self._app: Application | None = None

    def _parse_message(self, text: str) -> tuple[str, str]:
        """Parse agent type and prompt from message text."""
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0][1:].lower()
            if cmd in AGENT_COMMANDS:
                prompt = parts[1] if len(parts) > 1 else ""
                return cmd, prompt
        return "general", text

    def _is_authorized(self, user_id: int) -> bool:
        return not self.allowed_users or user_id in self.allowed_users

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            return
        await update.message.reply_text(
            "Punch AI Assistant\n\n"
            "Send any message to create a task.\n"
            "Use /email, /code, /research, /browser, /macos to specify agent type.\n"
            "/status - View recent tasks\n"
            "/help - Show this message"
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return
        tasks = await self.db.list_tasks(limit=5)
        if not tasks:
            await update.message.reply_text("No tasks yet.")
            return

        lines = ["Recent tasks:\n"]
        for t in tasks:
            emoji = {"running": "🔄", "completed": "✅", "failed": "❌", "pending": "⏳"}.get(t["status"], "❓")
            lines.append(f"{emoji} #{t['id']} [{t['agent_type']}] {t['prompt'][:50]}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return

        text = update.message.text
        if not text:
            return

        agent_type, prompt = self._parse_message(text)
        if not prompt:
            await update.message.reply_text("Please provide a prompt after the command.")
            return

        task_id = await self.submit_fn(agent_type, prompt, source="telegram")
        await update.message.reply_text(f"Task #{task_id} created ({agent_type} agent).\nProcessing...")

        # Execute the task immediately if execute_fn is available
        if self.execute_fn:
            import asyncio
            asyncio.create_task(self._execute_and_reply(task_id, update))

    async def _execute_and_reply(self, task_id: int, update: Update):
        try:
            await self.execute_fn(task_id)
            task = await self.db.get_task(task_id)
            if task["status"] == "completed":
                result = task["result"] or "Done (no output)"
                # Telegram has a 4096 char limit
                if len(result) > 4000:
                    result = result[:4000] + "\n... (truncated)"
                await update.message.reply_text(f"✅ Task #{task_id} completed:\n\n{result}")
            else:
                error = task.get("error", "Unknown error")
                await update.message.reply_text(f"❌ Task #{task_id} failed:\n\n{error[:2000]}")
        except Exception as e:
            await update.message.reply_text(f"❌ Task #{task_id} error: {str(e)[:500]}")

    async def notify(self, task_id: int, status: str, message: str):
        """Send a notification to all allowed users."""
        if not self._app or not self.allowed_users:
            return
        emoji = {"running": "🔄", "completed": "✅", "failed": "❌"}.get(status, "📋")
        text = f"{emoji} Task #{task_id} [{status}]\n{message[:3000]}"
        for user_id in self.allowed_users:
            try:
                await self._app.bot.send_message(chat_id=user_id, text=text)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")

    def build(self) -> Application:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("help", self._handle_start))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        # Agent-specific commands
        for cmd in AGENT_COMMANDS:
            self._app.add_handler(CommandHandler(cmd, self._handle_message))
        # Catch-all for plain text
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        return self._app

    async def start(self):
        app = self.build()
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_telegram.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/telegram_bot.py tests/test_telegram.py && git commit -m "feat: Telegram bot with agent routing, status command, and notifications"
```

---

## Task 8: Browser Control (Playwright)

**Files:**
- Create: `punch/browser.py`
- Create: `tests/test_browser.py`

**Step 1: Write failing tests**

Create `tests/test_browser.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from punch.browser import BrowserManager


def test_browser_manager_init():
    bm = BrowserManager(screenshots_dir="/tmp/screenshots")
    assert bm.screenshots_dir == "/tmp/screenshots"
    assert bm._browser is None


@pytest.mark.asyncio
async def test_browser_manager_not_started():
    bm = BrowserManager(screenshots_dir="/tmp/screenshots")
    assert not bm.is_running
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_browser.py -v
```

Expected: FAIL

**Step 3: Implement browser.py**

Create `punch/browser.py`:

```python
import asyncio
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("punch.browser")


class BrowserManager:
    def __init__(self, screenshots_dir: str = "data/screenshots"):
        self.screenshots_dir = screenshots_dir
        self._browser = None
        self._playwright = None

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    async def start(self):
        from playwright.async_api import async_playwright
        Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        logger.info("Browser started (headless Chromium)")

    async def stop(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser stopped")

    async def new_page(self):
        if not self._browser:
            await self.start()
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        return await context.new_page()

    async def screenshot(self, page, name: str | None = None) -> str:
        if not name:
            name = f"screenshot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        path = Path(self.screenshots_dir) / name
        await page.screenshot(path=str(path))
        return str(path)

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL, take screenshot, return page info."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            title = await page.title()
            screenshot_path = await self.screenshot(page)
            content = await page.content()
            return {
                "url": page.url,
                "title": title,
                "screenshot": screenshot_path,
                "content_length": len(content),
            }
        finally:
            await page.close()

    async def execute_script(self, url: str, script: str) -> dict:
        """Navigate to URL and execute JavaScript."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            result = await page.evaluate(script)
            screenshot_path = await self.screenshot(page)
            return {
                "url": page.url,
                "result": result,
                "screenshot": screenshot_path,
            }
        finally:
            await page.close()

    async def fill_form(self, url: str, fields: dict[str, str], submit_selector: str | None = None) -> dict:
        """Navigate to URL, fill form fields, optionally submit."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            for selector, value in fields.items():
                await page.fill(selector, value)
            if submit_selector:
                await page.click(submit_selector)
                await page.wait_for_load_state("networkidle")
            screenshot_path = await self.screenshot(page)
            return {
                "url": page.url,
                "screenshot": screenshot_path,
            }
        finally:
            await page.close()

    async def scrape_text(self, url: str, selector: str = "body") -> str:
        """Navigate to URL and extract text content."""
        page = await self.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            element = await page.query_selector(selector)
            if element:
                return await element.inner_text()
            return ""
        finally:
            await page.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_browser.py -v
```

Expected: ALL PASS

**Step 5: Commit**

```bash
git add punch/browser.py tests/test_browser.py && git commit -m "feat: Playwright browser manager with navigation, screenshots, forms, and scraping"
```

---

## Task 9: Tool Plugins — Shell, Filesystem, macOS

**Files:**
- Create: `punch/tools/shell.py`
- Create: `punch/tools/filesystem.py`
- Create: `punch/tools/macos.py`
- Create: `punch/tools/github.py`
- Create: `tests/test_tools.py`

**Step 1: Write failing tests**

Create `tests/test_tools.py`:

```python
import pytest
from punch.tools.shell import run_shell
from punch.tools.filesystem import list_dir, read_file, write_file, search_files
from punch.tools.macos import run_applescript, notify, get_frontmost_app


@pytest.mark.asyncio
async def test_run_shell():
    result = await run_shell("echo hello")
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_run_shell_failure():
    result = await run_shell("false")
    assert result["exit_code"] != 0


@pytest.mark.asyncio
async def test_list_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    items = await list_dir(str(tmp_path))
    names = [i["name"] for i in items]
    assert "a.txt" in names
    assert "b.txt" in names


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    content = await read_file(str(f))
    assert content == "hello world"


@pytest.mark.asyncio
async def test_write_file(tmp_path):
    f = tmp_path / "output.txt"
    await write_file(str(f), "test content")
    assert f.read_text() == "test content"


@pytest.mark.asyncio
async def test_search_files(tmp_path):
    (tmp_path / "hello.txt").write_text("find me here")
    (tmp_path / "other.txt").write_text("nothing")
    results = await search_files(str(tmp_path), "find me")
    assert len(results) == 1
    assert "hello.txt" in results[0]["path"]
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: FAIL

**Step 3: Implement shell.py**

Create `punch/tools/shell.py`:

```python
import asyncio
import logging

logger = logging.getLogger("punch.tools.shell")


async def run_shell(command: str, cwd: str | None = None, timeout: int = 60) -> dict:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }
    except asyncio.TimeoutError:
        return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}
```

**Step 4: Implement filesystem.py**

Create `punch/tools/filesystem.py`:

```python
import os
import asyncio
from pathlib import Path
from typing import Optional


async def list_dir(path: str, pattern: str = "*") -> list[dict]:
    p = Path(path)
    items = []
    for entry in sorted(p.glob(pattern)):
        stat = entry.stat()
        items.append({
            "name": entry.name,
            "path": str(entry),
            "is_dir": entry.is_dir(),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    return items


async def read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


async def write_file(path: str, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


async def search_files(directory: str, query: str, extensions: list[str] | None = None) -> list[dict]:
    results = []
    for root, dirs, files in os.walk(directory):
        for fname in files:
            if extensions and not any(fname.endswith(ext) for ext in extensions):
                continue
            fpath = os.path.join(root, fname)
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
                if query.lower() in content.lower():
                    # Find the line containing the match
                    for i, line in enumerate(content.split("\n")):
                        if query.lower() in line.lower():
                            results.append({
                                "path": fpath,
                                "line": i + 1,
                                "content": line.strip()[:200],
                            })
                            break
            except (PermissionError, UnicodeDecodeError):
                continue
    return results


async def file_info(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"exists": False}
    stat = p.stat()
    return {
        "exists": True,
        "path": str(p.resolve()),
        "is_dir": p.is_dir(),
        "size": stat.st_size,
        "modified": stat.st_mtime,
    }
```

**Step 5: Implement macos.py**

Create `punch/tools/macos.py`:

```python
import asyncio
import logging

logger = logging.getLogger("punch.tools.macos")


async def run_applescript(script: str, timeout: int = 30) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript error: {stderr.decode()}")
    return stdout.decode().strip()


async def notify(title: str, message: str) -> None:
    script = f'display notification "{message}" with title "{title}"'
    await run_applescript(script)


async def get_frontmost_app() -> str:
    return await run_applescript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )


async def open_app(app_name: str) -> None:
    await run_applescript(f'tell application "{app_name}" to activate')


async def open_url(url: str) -> None:
    await run_applescript(f'open location "{url}"')


async def get_clipboard() -> str:
    return await run_applescript("the clipboard")


async def set_clipboard(text: str) -> None:
    await run_applescript(f'set the clipboard to "{text}"')


async def list_running_apps() -> list[str]:
    result = await run_applescript(
        'tell application "System Events" to get name of every application process whose background only is false'
    )
    return [app.strip() for app in result.split(",")]


async def keystroke(text: str, app: str | None = None) -> None:
    if app:
        script = f'tell application "{app}" to activate\ndelay 0.5\ntell application "System Events" to keystroke "{text}"'
    else:
        script = f'tell application "System Events" to keystroke "{text}"'
    await run_applescript(script)
```

**Step 6: Implement github.py**

Create `punch/tools/github.py`:

```python
import asyncio
import json
import logging

logger = logging.getLogger("punch.tools.github")


async def _run_gh(args: list[str], timeout: int = 30) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return {
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "exit_code": proc.returncode or 0,
    }


async def list_repos(limit: int = 20) -> list[dict]:
    result = await _run_gh(["repo", "list", "--json", "name,description,updatedAt,url", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def list_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    result = await _run_gh(["issue", "list", "-R", repo, "--state", state,
                            "--json", "number,title,state,createdAt,author", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def list_prs(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    result = await _run_gh(["pr", "list", "-R", repo, "--state", state,
                            "--json", "number,title,state,createdAt,author,headRefName", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def get_pr(repo: str, number: int) -> dict:
    result = await _run_gh(["pr", "view", str(number), "-R", repo,
                            "--json", "number,title,state,body,author,createdAt,headRefName"])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return {}


async def create_issue(repo: str, title: str, body: str = "") -> dict:
    args = ["issue", "create", "-R", repo, "--title", title]
    if body:
        args.extend(["--body", body])
    result = await _run_gh(args)
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


async def repo_status(repo_path: str) -> dict:
    """Get git status for a local repo."""
    proc = await asyncio.create_subprocess_exec(
        "git", "status", "--porcelain",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_path,
    )
    stdout, _ = await proc.communicate()
    return {
        "changes": stdout.decode().strip().split("\n") if stdout.strip() else [],
        "clean": not stdout.strip(),
    }
```

**Step 7: Run tests**

```bash
python -m pytest tests/test_tools.py -v
```

Expected: ALL PASS

**Step 8: Commit**

```bash
git add punch/tools/ tests/test_tools.py && git commit -m "feat: tool plugins for shell, filesystem, macOS automation, and GitHub"
```

---

## Task 10: Gmail & Google Calendar Integration

**Files:**
- Create: `punch/tools/gmail.py`
- Create: `punch/tools/calendar_tool.py`

**Step 1: Implement gmail.py**

Create `punch/tools/gmail.py`:

```python
import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger("punch.tools.gmail")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]


def _get_service(credentials_path: str = "data/gmail_credentials.json",
                 token_path: str = "data/gmail_token.json"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


async def list_messages(query: str = "is:unread", max_results: int = 10,
                        credentials_path: str = "data/gmail_credentials.json") -> list[dict]:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        results = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = results.get("messages", [])
        detailed = []
        for msg in messages:
            full = service.users().messages().get(userId="me", id=msg["id"], format="metadata").execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            detailed.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "date": headers.get("Date", ""),
                "snippet": full.get("snippet", ""),
            })
        return detailed
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def get_message(msg_id: str, credentials_path: str = "data/gmail_credentials.json") -> dict:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        # Extract body
        body = ""
        payload = msg.get("payload", {})
        if "body" in payload and payload["body"].get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        return {
            "id": msg_id,
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body": body,
        }
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def send_email(to: str, subject: str, body: str,
                     credentials_path: str = "data/gmail_credentials.json") -> dict:
    import asyncio
    def _send():
        service = _get_service(credentials_path)
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"id": result["id"], "status": "sent"}
    return await asyncio.get_event_loop().run_in_executor(None, _send)
```

**Step 2: Implement calendar_tool.py**

Create `punch/tools/calendar_tool.py`:

```python
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("punch.tools.calendar")

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service(credentials_path: str = "data/calendar_credentials.json",
                 token_path: str = "data/calendar_token.json"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds)


async def list_events(days_ahead: int = 7, max_results: int = 20,
                      credentials_path: str = "data/calendar_credentials.json") -> list[dict]:
    import asyncio
    def _fetch():
        service = _get_service(credentials_path)
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        results = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=max_results, singleEvents=True, orderBy="startTime",
        ).execute()
        events = results.get("items", [])
        return [{
            "id": e["id"],
            "summary": e.get("summary", "No title"),
            "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
            "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        } for e in events]
    return await asyncio.get_event_loop().run_in_executor(None, _fetch)


async def create_event(summary: str, start: str, end: str, description: str = "",
                       location: str = "",
                       credentials_path: str = "data/calendar_credentials.json") -> dict:
    import asyncio
    def _create():
        service = _get_service(credentials_path)
        event = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        result = service.events().insert(calendarId="primary", body=event).execute()
        return {"id": result["id"], "link": result.get("htmlLink", "")}
    return await asyncio.get_event_loop().run_in_executor(None, _create)
```

**Step 3: Commit**

```bash
git add punch/tools/gmail.py punch/tools/calendar_tool.py && git commit -m "feat: Gmail and Google Calendar integration via Google API"
```

---

## Task 11: Wire Everything Together in main.py

**Files:**
- Modify: `punch/main.py`

**Step 1: Implement the full main.py**

Update `punch/main.py`:

```python
#!/usr/bin/env python3
"""Punch: Lightweight self-hosted AI assistant."""

import asyncio
import logging
import signal
import sys

from punch.config import PunchConfig
from punch.db import Database
from punch.runner import ClaudeRunner
from punch.orchestrator import Orchestrator
from punch.scheduler import PunchScheduler
from punch.browser import BrowserManager

logger = logging.getLogger("punch")


async def seed_default_agents(db: Database):
    """Create default agent configs if they don't exist."""
    defaults = [
        ("general", "You are Punch, a capable AI assistant. Help the user with any task.", None, 300),
        ("email", "You are Punch's email agent. You manage Gmail: reading, drafting, sending emails, and triaging the inbox. Be concise and professional.", None, 300),
        ("code", "You are Punch's code agent. You write, review, debug, and deploy code. Use git best practices. Run tests before committing.", None, 1800),
        ("research", "You are Punch's research agent. Search the web, read documents, and synthesize information into clear summaries.", None, 600),
        ("browser", "You are Punch's browser agent. Navigate websites, fill forms, extract data, and take screenshots.", None, 300),
        ("macos", "You are Punch's macOS agent. Control applications, manage files, run shell commands, and automate workflows on macOS.", None, 300),
    ]
    for name, prompt, working_dir, timeout in defaults:
        existing = await db.get_agent(name)
        if not existing:
            await db.create_agent(name=name, system_prompt=prompt,
                                  working_dir=working_dir, timeout_seconds=timeout)
            logger.info(f"Created default agent: {name}")


async def main():
    config = PunchConfig()
    config.ensure_dirs()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger.info("Punch starting up...")

    # Initialize database
    db = Database(config.db_path)
    await db.initialize()
    logger.info("Database initialized")

    # Seed defaults
    await seed_default_agents(db)

    # Claude Code runner
    runner = ClaudeRunner(
        claude_command=config.claude_command,
        max_concurrent=config.max_concurrent_tasks,
    )

    # Orchestrator
    orchestrator = Orchestrator(db=db, runner=runner)

    # Browser manager
    browser = BrowserManager(screenshots_dir=config.screenshots_dir)

    # Scheduler
    scheduler = PunchScheduler(db=db, submit_fn=orchestrator.submit)
    await scheduler.load_jobs()
    scheduler.start()
    logger.info("Scheduler started")

    # Telegram bot (if configured)
    telegram_bot = None
    if config.telegram_token:
        from punch.telegram_bot import PunchTelegramBot
        telegram_bot = PunchTelegramBot(
            token=config.telegram_token,
            submit_fn=orchestrator.submit,
            execute_fn=orchestrator.execute_task,
            db=db,
            allowed_users=config.telegram_allowed_users,
        )
        orchestrator.on_notify(telegram_bot.notify)
        await telegram_bot.start()
        logger.info("Telegram bot started")
    else:
        logger.warning("PUNCH_TELEGRAM_TOKEN not set — Telegram bot disabled")

    # Web server
    from punch.web.app import create_app
    import uvicorn

    app = create_app(db=db, orchestrator=orchestrator, scheduler=scheduler)

    uvicorn_config = uvicorn.Config(
        app=app,
        host=config.web_host,
        port=config.web_port,
        log_level=config.log_level.lower(),
    )
    server = uvicorn.Server(uvicorn_config)

    # Start task processor
    processor_task = asyncio.create_task(orchestrator.start_processing())

    logger.info(f"Punch ready at http://{config.web_host}:{config.web_port}")

    # Graceful shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    # Run uvicorn until stopped
    server_task = asyncio.create_task(server.serve())

    await stop_event.wait()

    logger.info("Punch shutting down...")
    orchestrator.stop_processing()
    scheduler.shutdown()
    if telegram_bot:
        await telegram_bot.stop()
    await browser.stop()
    server.should_exit = True
    await server_task
    await db.close()
    logger.info("Punch stopped.")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Run existing tests to ensure nothing is broken**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS

**Step 3: Commit**

```bash
git add punch/main.py && git commit -m "feat: wire all components together in main entry point with graceful startup/shutdown"
```

---

## Task 12: Setup Script & launchd Service

**Files:**
- Create: `setup.sh`
- Create: `punch.plist` (launchd service for auto-start)

**Step 1: Create setup.sh**

Create `setup.sh`:

```bash
#!/bin/bash
set -e

echo "=== Punch Setup ==="

# Check Python version
PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "Python: $PY_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r punch/requirements.txt

# Install Playwright browsers
echo "Installing Playwright Chromium..."
python -m playwright install chromium

# Create data directories
mkdir -p data/screenshots data/workspaces

# Create .env template if it doesn't exist
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# Punch Configuration
# PUNCH_TELEGRAM_TOKEN=your-bot-token-here
# PUNCH_TELEGRAM_USERS=123456789  # comma-separated Telegram user IDs
# PUNCH_WEB_PORT=8080
# PUNCH_MAX_CONCURRENT=4
# PUNCH_LOG_LEVEL=INFO
ENVEOF
    echo "Created .env template — edit it with your settings"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env with your Telegram bot token"
echo "2. Run: source venv/bin/activate && python -m punch.main"
echo "3. Access dashboard at http://localhost:8080"
echo ""
echo "For Gmail/Calendar, place your Google OAuth credentials at:"
echo "  data/gmail_credentials.json"
echo "  data/calendar_credentials.json"
```

**Step 2: Create launchd plist for auto-start**

Create `punch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.punch.assistant</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/siddy/Documents/Code/Punch/venv/bin/python</string>
        <string>-m</string>
        <string>punch.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/siddy/Documents/Code/Punch</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/siddy/Documents/Code/Punch/data/punch.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/siddy/Documents/Code/Punch/data/punch_error.log</string>
</dict>
</plist>
```

**Step 3: Add install-service helper to setup.sh**

Append to `setup.sh`:

```bash
echo "To auto-start on boot:"
echo "  cp punch.plist ~/Library/LaunchAgents/com.punch.assistant.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.punch.assistant.plist"
echo ""
echo "To stop:"
echo "  launchctl unload ~/Library/LaunchAgents/com.punch.assistant.plist"
```

**Step 4: Commit**

```bash
chmod +x setup.sh && git add setup.sh punch.plist && git commit -m "feat: setup script and launchd service for headless Mac Mini deployment"
```

---

## Task 13: Integration Test — End to End

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
"""Integration test: verify all components wire together correctly."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from punch.config import PunchConfig
from punch.db import Database
from punch.runner import ClaudeRunner
from punch.orchestrator import Orchestrator
from punch.scheduler import PunchScheduler
from punch.web.app import create_app


@pytest_asyncio.fixture
async def system(tmp_path):
    """Set up the full system (minus Telegram and real Claude Code)."""
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()

    runner = ClaudeRunner(claude_command="echo", max_concurrent=2)
    orchestrator = Orchestrator(db=db, runner=runner)
    scheduler = PunchScheduler(db=db, submit_fn=orchestrator.submit)
    await scheduler.load_jobs()

    app = create_app(db=db, orchestrator=orchestrator, scheduler=scheduler)
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    yield {"db": db, "orchestrator": orchestrator, "scheduler": scheduler, "client": client}

    await client.aclose()
    scheduler.shutdown()
    await db.close()


@pytest.mark.asyncio
async def test_full_flow(system):
    client = system["client"]
    db = system["db"]

    # 1. Dashboard loads
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Punch" in resp.text

    # 2. Create agent via API
    resp = await client.post("/api/agents", json={
        "name": "test-agent",
        "system_prompt": "You are a test agent.",
        "timeout_seconds": 60,
    })
    assert resp.status_code == 200

    # 3. Create task via API
    resp = await client.post("/api/tasks", json={
        "agent_type": "test-agent",
        "prompt": "Hello world",
    })
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 4. Task appears in list
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert any(t["id"] == task_id for t in tasks)

    # 5. Create cron job
    resp = await client.post("/api/cron", json={
        "name": "Test Cron",
        "schedule": "0 * * * *",
        "agent_type": "test-agent",
        "prompt": "Periodic test",
    })
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # 6. Toggle cron job
    resp = await client.put(f"/api/cron/{job_id}/toggle")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # 7. Settings
    resp = await client.put("/api/settings/test_key", json={"value": "test_value"})
    assert resp.status_code == 200

    resp = await client.get("/api/settings")
    assert any(s["key"] == "test_key" for s in resp.json())

    # 8. All pages load without error
    for path in ["/tasks", "/agents", "/cron", "/browser", "/settings", "/logs"]:
        resp = await client.get(path)
        assert resp.status_code == 200, f"Page {path} failed"
```

**Step 2: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py && git commit -m "feat: end-to-end integration test verifying all components work together"
```

---

## Task 14: Create .gitignore and Final Cleanup

**Files:**
- Create: `.gitignore`

**Step 1: Create .gitignore**

Create `.gitignore`:

```
__pycache__/
*.py[cod]
*$py.class
venv/
.env
data/
*.db
*.log
.pytest_cache/
*.egg-info/
dist/
build/
```

**Step 2: Run full test suite one last time**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: ALL PASS

**Step 3: Commit**

```bash
git add .gitignore && git commit -m "chore: add .gitignore for Python project"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Project scaffolding + config | `config.py`, `main.py` (stub) |
| 2 | Database layer | `db.py` |
| 3 | Claude Code runner | `runner.py` |
| 4 | Task orchestrator | `orchestrator.py` |
| 5 | Cron scheduler | `scheduler.py` |
| 6 | Web dashboard (FastAPI + HTMX) | `web/app.py`, all templates |
| 7 | Telegram bot | `telegram_bot.py` |
| 8 | Browser control | `browser.py` |
| 9 | Tool plugins (shell, fs, macOS, GitHub) | `tools/*.py` |
| 10 | Gmail & Calendar | `tools/gmail.py`, `tools/calendar_tool.py` |
| 11 | Wire everything in main.py | `main.py` (full) |
| 12 | Setup script + launchd | `setup.sh`, `punch.plist` |
| 13 | Integration tests | `tests/test_integration.py` |
| 14 | .gitignore + cleanup | `.gitignore` |

Total: ~2000 lines of Python + ~600 lines of HTML templates. Minimal dependencies. Single process. Ready for headless Mac Mini deployment.
