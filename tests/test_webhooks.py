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
async def test_webhook_crud(db):
    wh_id = await db.create_webhook(name="github", agent_type="code", secret="s3cret")
    webhook = await db.get_webhook("github")
    assert webhook is not None
    assert webhook["agent_type"] == "code"
    assert webhook["secret"] == "s3cret"
    assert webhook["enabled"] == 1


@pytest.mark.asyncio
async def test_webhook_list(db):
    await db.create_webhook(name="github", agent_type="code", secret="s1")
    await db.create_webhook(name="slack", agent_type="general", secret="s2")
    webhooks = await db.list_webhooks()
    assert len(webhooks) == 2


@pytest.mark.asyncio
async def test_webhook_update(db):
    wh_id = await db.create_webhook(name="test", agent_type="general", secret="old")
    await db.update_webhook(wh_id, enabled=False)
    webhook = await db.get_webhook("test")
    assert webhook["enabled"] == 0


@pytest.mark.asyncio
async def test_webhook_delete(db):
    wh_id = await db.create_webhook(name="test", agent_type="general", secret="s")
    await db.delete_webhook(wh_id)
    webhook = await db.get_webhook("test")
    assert webhook is None


@pytest.mark.asyncio
async def test_new_tables_exist(db):
    tables = await db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [t["name"] for t in tables]
    assert "memories" in table_names
    assert "webhooks" in table_names
