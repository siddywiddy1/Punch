from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PunchConfig:
    # Database
    db_path: str = field(default_factory=lambda: os.getenv("PUNCH_DB_PATH", "punch.db"))

    # Web server
    web_host: str = field(default_factory=lambda: os.getenv("PUNCH_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("PUNCH_WEB_PORT", "8080")))

    # Claude Code
    claude_command: str = field(default_factory=lambda: os.getenv("PUNCH_CLAUDE_CMD", "claude"))
    max_concurrent_tasks: int = field(default_factory=lambda: int(os.getenv("PUNCH_MAX_CONCURRENT", "4")))

    # Telegram
    telegram_token: str | None = field(default_factory=lambda: os.getenv("PUNCH_TELEGRAM_TOKEN"))
    telegram_allowed_users: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("PUNCH_TELEGRAM_USERS", "").split(",") if x.strip()
    ])

    # Data directories
    data_dir: str = field(default_factory=lambda: os.getenv("PUNCH_DATA_DIR", "data"))
    screenshots_dir: str = field(default_factory=lambda: os.getenv("PUNCH_SCREENSHOTS_DIR", "data/screenshots"))
    workspaces_dir: str = field(default_factory=lambda: os.getenv("PUNCH_WORKSPACES_DIR", "data/workspaces"))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("PUNCH_LOG_LEVEL", "INFO"))

    def ensure_dirs(self):
        for d in [self.data_dir, self.screenshots_dir, self.workspaces_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)
