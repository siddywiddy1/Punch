import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from punch.db import Database
from punch.runner import ClaudeRunner
from punch.health import HealthChecker


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def health_checker(db):
    runner = ClaudeRunner(claude_command="echo", max_concurrent=2)
    scheduler = MagicMock()
    scheduler._scheduler = MagicMock()
    scheduler._scheduler.running = True
    scheduler.get_jobs.return_value = []
    return HealthChecker(db=db, runner=runner, scheduler=scheduler)


@pytest.mark.asyncio
async def test_check_db(health_checker):
    result = await health_checker._check_db()
    assert result["ok"] is True
    assert "task_count" in result


@pytest.mark.asyncio
async def test_check_scheduler(health_checker):
    result = health_checker._check_scheduler()
    assert result["ok"] is True
    assert result["running"] is True


@pytest.mark.asyncio
async def test_check_telegram_not_configured(health_checker):
    result = health_checker._check_telegram()
    assert result["ok"] is True
    assert result["status"] == "not_configured"


@pytest.mark.asyncio
async def test_check_all_structure(health_checker):
    result = await health_checker.check_all()
    assert "status" in result
    assert "components" in result
    assert "timestamp" in result
    assert set(result["components"].keys()) == {"claude_cli", "database", "scheduler", "telegram"}
