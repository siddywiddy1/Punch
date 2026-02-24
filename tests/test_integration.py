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
    scheduler.start()

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
