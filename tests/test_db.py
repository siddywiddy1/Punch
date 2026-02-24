from __future__ import annotations

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
