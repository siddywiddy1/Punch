import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from punch.telegram_bot import PunchTelegramBot


@pytest.mark.asyncio
async def test_bot_init():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    assert bot.token == "fake-token"


@pytest.mark.asyncio
async def test_parse_agent_from_message():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    agent, prompt = bot._parse_message("/email Check my inbox")
    assert agent == "email"
    assert prompt == "Check my inbox"


@pytest.mark.asyncio
async def test_parse_agent_default():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    agent, prompt = bot._parse_message("What's the weather?")
    assert agent == "general"
    assert prompt == "What's the weather?"


@pytest.mark.asyncio
async def test_parse_agent_types():
    bot = PunchTelegramBot(token="fake-token", submit_fn=AsyncMock(), db=MagicMock())
    for cmd in ["email", "code", "research", "browser", "macos"]:
        agent, prompt = bot._parse_message(f"/{cmd} do something")
        assert agent == cmd
