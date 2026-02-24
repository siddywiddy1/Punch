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
