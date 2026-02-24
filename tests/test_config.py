import os
import pytest
from punch.config import PunchConfig


def test_config_defaults():
    config = PunchConfig()
    assert config.db_path == "punch.db"
    assert config.web_host == "127.0.0.1"
    assert config.web_port == 8080
    assert config.max_concurrent_tasks == 4
    assert config.claude_command == "claude"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PUNCH_DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("PUNCH_WEB_PORT", "9090")
    monkeypatch.setenv("PUNCH_MAX_CONCURRENT", "2")
    config = PunchConfig()
    assert config.db_path == "/tmp/test.db"
    assert config.web_port == 9090
    assert config.max_concurrent_tasks == 2


def test_config_telegram_token():
    config = PunchConfig()
    assert config.telegram_token is None  # Not set by default


def test_config_data_dir_created(tmp_path, monkeypatch):
    data_dir = tmp_path / "punch_data"
    monkeypatch.setenv("PUNCH_DATA_DIR", str(data_dir))
    config = PunchConfig()
    config.ensure_dirs()
    assert data_dir.exists()
