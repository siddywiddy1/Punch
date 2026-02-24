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
