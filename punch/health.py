"""Punch health checks: monitors system components."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("punch.health")


class HealthChecker:
    def __init__(self, db, runner, scheduler, telegram_bot=None):
        self.db = db
        self.runner = runner
        self.scheduler = scheduler
        self.telegram_bot = telegram_bot
        self._last_status: dict | None = None

    async def check_all(self) -> dict:
        checks = await asyncio.gather(
            self._check_claude(),
            self._check_db(),
            return_exceptions=True,
        )
        claude_ok = checks[0] if not isinstance(checks[0], Exception) else {"ok": False, "error": str(checks[0])}
        db_ok = checks[1] if not isinstance(checks[1], Exception) else {"ok": False, "error": str(checks[1])}
        scheduler_status = self._check_scheduler()
        telegram_status = self._check_telegram()

        components = {
            "claude_cli": claude_ok,
            "database": db_ok,
            "scheduler": scheduler_status,
            "telegram": telegram_status,
        }

        all_ok = all(c.get("ok") for c in components.values())
        any_ok = any(c.get("ok") for c in components.values())

        result = {
            "status": "healthy" if all_ok else ("degraded" if any_ok else "unhealthy"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": components,
        }
        self._last_status = result
        return result

    async def _check_claude(self) -> dict:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.runner.claude_command, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            version = stdout.decode("utf-8", errors="replace").strip()
            return {"ok": proc.returncode == 0, "version": version}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _check_db(self) -> dict:
        try:
            result = await self.db.fetch_one("SELECT COUNT(*) as cnt FROM tasks")
            return {"ok": True, "task_count": result["cnt"] if result else 0}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _check_scheduler(self) -> dict:
        if not self.scheduler:
            return {"ok": False, "error": "Not configured"}
        running = self.scheduler._scheduler.running
        job_count = len(self.scheduler.get_jobs())
        return {"ok": running, "running": running, "job_count": job_count}

    def _check_telegram(self) -> dict:
        if not self.telegram_bot:
            return {"ok": True, "status": "not_configured"}
        has_app = self.telegram_bot._app is not None
        return {"ok": has_app, "status": "running" if has_app else "stopped"}
