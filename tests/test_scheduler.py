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
