from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PunchConfig:
    # Database
    db_path: str = field(default_factory=lambda: os.getenv("PUNCH_DB_PATH", "punch.db"))

    # Web server
    web_host: str = field(default_factory=lambda: os.getenv("PUNCH_WEB_HOST", "127.0.0.1"))
    web_port: int = field(default_factory=lambda: int(os.getenv("PUNCH_WEB_PORT", "8080")))

    # API key for dashboard/API authentication (required for non-localhost access)
    api_key: str | None = field(default_factory=lambda: os.getenv("PUNCH_API_KEY"))

    # Claude Code
    claude_command: str = field(default_factory=lambda: os.getenv("PUNCH_CLAUDE_CMD", "claude"))
    max_concurrent_tasks: int = field(default_factory=lambda: int(os.getenv("PUNCH_MAX_CONCURRENT", "4")))

    # Telegram
    telegram_token: str | None = field(default_factory=lambda: os.getenv("PUNCH_TELEGRAM_TOKEN"))
    telegram_allowed_users: list[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("PUNCH_TELEGRAM_USERS", "").split(",") if x.strip()
    ])

    # Browser — CDP URL for connecting to your real Chrome (launch Chrome with --remote-debugging-port=9222)
    browser_cdp_url: str | None = field(default_factory=lambda: os.getenv("PUNCH_BROWSER_CDP_URL"))

    # Data directories
    data_dir: str = field(default_factory=lambda: os.getenv("PUNCH_DATA_DIR", "data"))
    screenshots_dir: str = field(default_factory=lambda: os.getenv("PUNCH_SCREENSHOTS_DIR", "data/screenshots"))
    workspaces_dir: str = field(default_factory=lambda: os.getenv("PUNCH_WORKSPACES_DIR", "data/workspaces"))

    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("PUNCH_LOG_LEVEL", "INFO"))

    def ensure_dirs(self):
        for d in [self.data_dir, self.screenshots_dir, self.workspaces_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)

    async def apply_db_settings(self, db) -> None:
        """Override config with values saved in DB settings (from onboarding/settings UI).

        This bridges the gap between the web UI settings and the runtime config.
        Environment variables take precedence — DB values are only used as fallbacks.
        """
        # Only override if the env var was NOT set (so env vars always win)
        if not os.getenv("PUNCH_TELEGRAM_TOKEN"):
            token = await db.get_setting("telegram_token")
            if token:
                self.telegram_token = token

        if not os.getenv("PUNCH_TELEGRAM_USERS"):
            users_str = await db.get_setting("telegram_allowed_users")
            if users_str:
                self.telegram_allowed_users = [
                    int(x) for x in users_str.split(",") if x.strip()
                ]

        if not os.getenv("PUNCH_CLAUDE_CMD"):
            cmd = await db.get_setting("claude_command")
            if cmd:
                self.claude_command = cmd

        if not os.getenv("PUNCH_MAX_CONCURRENT"):
            mc = await db.get_setting("max_concurrent_tasks")
            if mc:
                self.max_concurrent_tasks = int(mc)

        if not os.getenv("PUNCH_LOG_LEVEL"):
            level = await db.get_setting("log_level")
            if level:
                self.log_level = level

        if not os.getenv("PUNCH_API_KEY"):
            key = await db.get_setting("api_key")
            if key:
                self.api_key = key
