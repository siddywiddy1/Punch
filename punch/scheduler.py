from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from punch.db import Database

logger = logging.getLogger("punch.scheduler")

SubmitFn = Callable[..., Awaitable[int]]


class PunchScheduler:
    def __init__(self, db: Database, submit_fn: SubmitFn):
        self.db = db
        self.submit_fn = submit_fn
        self._scheduler = AsyncIOScheduler()
        self._job_map: dict[int, str] = {}  # cron_job_id -> apscheduler_job_id

    async def load_jobs(self):
        """Load all enabled cron jobs from the database."""
        jobs = await self.db.list_cron_jobs()
        for job in jobs:
            if job["enabled"]:
                self._add_job(job)
        logger.info(f"Loaded {len(self._job_map)} cron jobs")

    def _add_job(self, job: dict):
        parts = job["schedule"].split()
        if len(parts) != 5:
            logger.error(f"Invalid cron schedule for job {job['id']}: {job['schedule']}")
            return

        trigger = CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
        ap_job = self._scheduler.add_job(
            self._trigger_job, trigger,
            args=[job["id"]],
            id=f"cron_{job['id']}",
            name=job["name"],
            replace_existing=True,
        )
        self._job_map[job["id"]] = ap_job.id

    async def _trigger_job(self, cron_job_id: int):
        job = await self.db.get_cron_job(cron_job_id)
        if not job or not job["enabled"]:
            return

        logger.info(f"Cron trigger: {job['name']} (agent={job['agent_type']})")
        try:
            task_id = await self.submit_fn(job["agent_type"], job["prompt"], source="cron")
            await self.db.update_cron_job(cron_job_id, last_run="datetime('now')")
            logger.info(f"Cron job {job['name']} created task {task_id}")
        except Exception as e:
            logger.error(f"Cron job {job['name']} failed: {e}")

    async def add_job(self, cron_job_id: int):
        """Add a single job from the database."""
        job = await self.db.get_cron_job(cron_job_id)
        if job and job["enabled"]:
            self._add_job(job)

    async def remove_job(self, cron_job_id: int):
        """Remove a scheduled job."""
        ap_job_id = self._job_map.pop(cron_job_id, None)
        if ap_job_id:
            try:
                self._scheduler.remove_job(ap_job_id)
            except Exception:
                pass

    async def reload_job(self, cron_job_id: int):
        """Reload a job from the database (after config change)."""
        await self.remove_job(cron_job_id)
        await self.add_job(cron_job_id)

    def get_jobs(self) -> list:
        return self._scheduler.get_jobs()

    def start(self):
        self._scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        self._scheduler.shutdown()
        logger.info("Scheduler shutdown")
