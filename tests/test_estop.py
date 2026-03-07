import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
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
async def test_estop_cancels_pending(orchestrator, db):
    t1 = await orchestrator.submit("general", "Task 1")
    t2 = await orchestrator.submit("general", "Task 2")

    result = await orchestrator.estop()
    assert result["cancelled"] == 2

    task1 = await db.get_task(t1)
    task2 = await db.get_task(t2)
    assert task1["status"] == "failed"
    assert task2["status"] == "failed"
    assert "Emergency stop" in task1["error"]


@pytest.mark.asyncio
async def test_estop_prevents_execution(orchestrator, db):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Done", stderr="", exit_code=0, session_id=None
    ))

    await orchestrator.estop()
    task_id = await orchestrator.submit("general", "Should not run")
    await orchestrator.execute_task(task_id)

    task = await db.get_task(task_id)
    assert task["status"] == "failed"
    assert "stopped" in task["error"]
    orchestrator.runner.run.assert_not_called()


@pytest.mark.asyncio
async def test_estop_prevents_queue_processing(orchestrator, db):
    await orchestrator.estop()
    await orchestrator.submit("general", "Pending task")

    await orchestrator.process_queue()

    tasks = await db.get_pending_tasks()
    assert len(tasks) == 1  # still pending, not picked up


@pytest.mark.asyncio
async def test_resume_after_estop(orchestrator, db):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Done", stderr="", exit_code=0, session_id=None
    ))

    await orchestrator.estop()
    assert orchestrator.is_stopped is True

    orchestrator.resume()
    assert orchestrator.is_stopped is False

    task_id = await orchestrator.submit("general", "Should run now")
    await orchestrator.execute_task(task_id)

    task = await db.get_task(task_id)
    assert task["status"] == "completed"


@pytest.mark.asyncio
async def test_delegate(orchestrator, db):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Research result", stderr="", exit_code=0, session_id=None
    ))

    parent_id = await orchestrator.submit("general", "Parent task")
    result = await orchestrator.delegate(parent_id, "research", "Find info about X")

    assert result == "Research result"
    tasks = await db.list_tasks()
    assert len(tasks) == 2
    delegated = [t for t in tasks if t["source"].startswith("delegation:")]
    assert len(delegated) == 1
