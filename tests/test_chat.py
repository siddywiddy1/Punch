"""Tests for chat UI, onboarding, and structured settings features."""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from punch.db import Database
from punch.runner import ClaudeRunner, RunResult
from punch.orchestrator import Orchestrator
from punch.web.app import create_app, SETTINGS_SCHEMA


# --- Fixtures ---

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


@pytest_asyncio.fixture
async def client(db):
    # Set onboarding_complete so middleware doesn't redirect
    await db.set_setting("onboarding_complete", "true")
    app = create_app(db=db, orchestrator=None, scheduler=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_no_onboarding(db):
    """Client without onboarding_complete set."""
    app = create_app(db=db, orchestrator=None, scheduler=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- DB Tests ---

@pytest.mark.asyncio
async def test_create_chat(db):
    chat_id = await db.create_chat(title="Test Chat")
    chat = await db.get_chat(chat_id)
    assert chat is not None
    assert chat["title"] == "Test Chat"
    assert chat["is_active"] == 1
    assert chat["session_id"] is None


@pytest.mark.asyncio
async def test_chat_messages_ordered(db):
    chat_id = await db.create_chat()
    await db.add_chat_message(chat_id, role="user", content="Hello")
    await db.add_chat_message(chat_id, role="assistant", content="Hi there")
    await db.add_chat_message(chat_id, role="user", content="How are you?")

    messages = await db.get_chat_messages(chat_id)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["content"] == "How are you?"


@pytest.mark.asyncio
async def test_chat_message_pending_to_complete(db):
    chat_id = await db.create_chat()
    msg_id = await db.add_chat_message(chat_id, role="assistant", content="", status="pending")

    msg = await db.get_latest_chat_message(chat_id)
    assert msg["status"] == "pending"
    assert msg["content"] == ""

    await db.update_chat_message(msg_id, content="Done!", status="complete")
    msg = await db.get_latest_chat_message(chat_id)
    assert msg["status"] == "complete"
    assert msg["content"] == "Done!"


@pytest.mark.asyncio
async def test_soft_delete_chat(db):
    chat_id = await db.create_chat()
    await db.delete_chat(chat_id)

    # Chat still exists but inactive
    chat = await db.get_chat(chat_id)
    assert chat["is_active"] == 0


@pytest.mark.asyncio
async def test_list_chats_excludes_inactive(db):
    id1 = await db.create_chat(title="Active")
    id2 = await db.create_chat(title="Will Delete")
    await db.delete_chat(id2)

    chats = await db.list_chats()
    assert len(chats) == 1
    assert chats[0]["title"] == "Active"


# --- Orchestrator Tests ---

@pytest.mark.asyncio
async def test_chat_returns_response(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Hello! How can I help?", stderr="", exit_code=0, session_id="sess_abc"
    ))

    chat_id = await orchestrator.db.create_chat()
    response = await orchestrator.chat(chat_id, "Hi there")
    assert response == "Hello! How can I help?"


@pytest.mark.asyncio
async def test_chat_session_resumption(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Response 1", stderr="", exit_code=0, session_id="sess_123"
    ))

    chat_id = await orchestrator.db.create_chat()
    await orchestrator.chat(chat_id, "First message")

    # Verify session_id was saved
    chat = await orchestrator.db.get_chat(chat_id)
    assert chat["session_id"] == "sess_123"

    # Second message should use the session_id
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Response 2", stderr="", exit_code=0, session_id="sess_123"
    ))
    await orchestrator.chat(chat_id, "Second message")

    call_kwargs = orchestrator.runner.run.call_args.kwargs
    assert call_kwargs["session_id"] == "sess_123"


@pytest.mark.asyncio
async def test_chat_auto_titling(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Sure!", stderr="", exit_code=0, session_id=None
    ))

    chat_id = await orchestrator.db.create_chat()
    assert (await orchestrator.db.get_chat(chat_id))["title"] == "New Chat"

    await orchestrator.chat(chat_id, "Help me write a Python script")

    chat = await orchestrator.db.get_chat(chat_id)
    assert chat["title"] == "Help me write a Python script"


@pytest.mark.asyncio
async def test_chat_pending_to_complete_flow(orchestrator):
    orchestrator.runner.run = AsyncMock(return_value=RunResult(
        stdout="Done!", stderr="", exit_code=0, session_id=None
    ))

    chat_id = await orchestrator.db.create_chat()
    await orchestrator.chat(chat_id, "Do something")

    messages = await orchestrator.db.get_chat_messages(chat_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["status"] == "complete"
    assert messages[1]["content"] == "Done!"


# --- Web Tests ---

@pytest.mark.asyncio
async def test_chat_page_loads(client, db):
    chat_id = await db.create_chat(title="Test Chat")
    resp = await client.get(f"/chat/{chat_id}", follow_redirects=True)
    assert resp.status_code == 200
    assert "Test Chat" in resp.text


@pytest.mark.asyncio
async def test_onboarding_redirect_when_no_setting(client_no_onboarding):
    resp = await client_no_onboarding.get("/chat", follow_redirects=False)
    assert resp.status_code == 302
    assert "/onboarding" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_settings_page_has_sections(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    assert "Claude" in resp.text
    assert "Telegram" in resp.text
    assert "Web" in resp.text
    assert "System" in resp.text


@pytest.mark.asyncio
async def test_api_send_message(db):
    await db.set_setting("onboarding_complete", "true")
    # Create orchestrator with mocked runner
    runner = ClaudeRunner(claude_command="echo", max_concurrent=2)
    orch = Orchestrator(db=db, runner=runner)
    orch.runner.run = AsyncMock(return_value=RunResult(
        stdout="API response", stderr="", exit_code=0, session_id=None
    ))

    app = create_app(db=db, orchestrator=orch, scheduler=None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        chat_id = await db.create_chat()
        resp = await client.post(f"/api/chat/{chat_id}/message", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "API response"


# --- Telegram Tests ---

@pytest.mark.asyncio
async def test_telegram_handle_chat_message(db):
    from punch.telegram_bot import PunchTelegramBot

    chat_fn = AsyncMock(return_value="Bot response")
    bot = PunchTelegramBot(
        token="fake-token",
        submit_fn=AsyncMock(),
        db=db,
        allowed_users=[12345],
        chat_fn=chat_fn,
    )

    # Simulate a message
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.text = "Hello bot"
    update.message.chat.send_action = AsyncMock()
    update.message.reply_text = AsyncMock()

    await bot._handle_chat_message(update, None)

    # Should have created a chat and called chat_fn
    chat_fn.assert_called_once()
    update.message.reply_text.assert_called_once_with("Bot response")


@pytest.mark.asyncio
async def test_telegram_newchat_resets(db):
    from punch.telegram_bot import PunchTelegramBot

    bot = PunchTelegramBot(
        token="fake-token",
        submit_fn=AsyncMock(),
        db=db,
        allowed_users=[12345],
        chat_fn=AsyncMock(return_value="ok"),
    )
    bot._user_chats[12345] = 999  # existing chat

    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()

    await bot._handle_newchat(update, None)

    # Should have created a new chat, replacing old one
    assert bot._user_chats[12345] != 999
    update.message.reply_text.assert_called_once()


# --- Dashboard / Home redirect ---

@pytest.mark.asyncio
async def test_dashboard_page_loads(client):
    resp = await client.get("/dashboard")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


@pytest.mark.asyncio
async def test_root_redirects_to_chat(client):
    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/chat" in resp.headers.get("location", "")
