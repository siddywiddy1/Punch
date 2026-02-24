import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from punch.runner import ClaudeRunner, RunResult


def test_run_result_dataclass():
    result = RunResult(stdout="hello", stderr="", exit_code=0, session_id=None)
    assert result.success
    assert result.stdout == "hello"


def test_run_result_failure():
    result = RunResult(stdout="", stderr="error", exit_code=1, session_id=None)
    assert not result.success


@pytest.mark.asyncio
async def test_runner_builds_oneshot_command():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Hello", oneshot=True)
    assert "claude" in cmd
    assert "--print" in cmd


@pytest.mark.asyncio
async def test_runner_builds_command_with_system_prompt():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Hello", system_prompt="You are helpful", oneshot=True)
    assert "--system-prompt" in cmd


@pytest.mark.asyncio
async def test_runner_builds_resume_command():
    runner = ClaudeRunner(claude_command="claude", max_concurrent=2)
    cmd = runner._build_command(prompt="Continue", session_id="abc123")
    assert "--resume" in cmd
    assert "abc123" in cmd


@pytest.mark.asyncio
async def test_runner_respects_concurrency_limit():
    runner = ClaudeRunner(claude_command="echo", max_concurrent=1)
    assert runner._semaphore._value == 1
