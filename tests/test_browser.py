import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from punch.browser import BrowserManager


def test_browser_manager_init():
    bm = BrowserManager(screenshots_dir="/tmp/screenshots")
    assert bm.screenshots_dir == "/tmp/screenshots"
    assert bm._browser is None


@pytest.mark.asyncio
async def test_browser_manager_not_started():
    bm = BrowserManager(screenshots_dir="/tmp/screenshots")
    assert not bm.is_running
