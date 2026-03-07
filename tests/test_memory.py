import pytest
import pytest_asyncio
from punch.db import Database
from punch.memory import Memory


@pytest_asyncio.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def memory(db):
    return Memory(db)


@pytest.mark.asyncio
async def test_store_and_search(memory):
    await memory.store("api_key_location", "API keys are in .env file", category="config")
    results = await memory.search("api_key")
    assert len(results) == 1
    assert results[0]["key"] == "api_key_location"


@pytest.mark.asyncio
async def test_search_by_content(memory):
    await memory.store("deploy_notes", "Always run tests before deploying to prod")
    results = await memory.search("deploying")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_with_category(memory):
    await memory.store("pref1", "dark mode", category="user_pref")
    await memory.store("pref2", "vim bindings", category="user_pref")
    await memory.store("note1", "dark theme config", category="notes")

    results = await memory.search("dark", category="user_pref")
    assert len(results) == 1
    assert results[0]["key"] == "pref1"


@pytest.mark.asyncio
async def test_get_context_empty(memory):
    ctx = await memory.get_context("nonexistent")
    assert ctx == ""


@pytest.mark.asyncio
async def test_get_context_with_results(memory):
    await memory.store("server_ip", "Production server is 10.0.0.1")
    ctx = await memory.get_context("server")
    assert "server_ip" in ctx
    assert "10.0.0.1" in ctx


@pytest.mark.asyncio
async def test_store_from_task(memory, db):
    task_id = await db.create_task(agent_type="general", prompt="test")
    mem_id = await memory.store_from_task(task_id, "result_key", "task completed successfully")
    results = await memory.search("result_key")
    assert len(results) == 1
    assert results[0]["source_task_id"] == task_id


@pytest.mark.asyncio
async def test_db_memory_crud(db):
    mem_id = await db.create_memory(key="test", content="hello", category="general")
    memories = await db.list_memories()
    assert len(memories) == 1
    assert memories[0]["key"] == "test"

    await db.delete_memory(mem_id)
    memories = await db.list_memories()
    assert len(memories) == 0
