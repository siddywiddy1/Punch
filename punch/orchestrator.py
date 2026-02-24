from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Awaitable, List

from punch.db import Database
from punch.runner import ClaudeRunner

logger = logging.getLogger("punch.orchestrator")

# Callbacks for notifications (set by telegram bot, web, etc.)
NotifyCallback = Callable[[int, str, str], Awaitable[None]]  # task_id, status, message

# Keywords that indicate a multi-step task (not oneshot)
_MULTI_STEP_KEYWORDS = [
    "fix", "implement", "build", "deploy", "commit", "create", "write", "refactor",
    "update", "modify", "change", "add", "remove", "delete", "install",
]


class Orchestrator:
    def __init__(self, db: Database, runner: ClaudeRunner):
        self.db = db
        self.runner = runner
        self._notify_callbacks: List[NotifyCallback] = []
        self._processing = False

    def on_notify(self, callback: NotifyCallback):
        """Register a notification callback (for Telegram, web, etc.)."""
        self._notify_callbacks.append(callback)

    async def _notify(self, task_id: int, status: str, message: str):
        """Send notifications to all registered callbacks."""
        for cb in self._notify_callbacks:
            try:
                await cb(task_id, status, message)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")

    async def submit(self, agent_type: str, prompt: str, priority: int = 0,
                     working_dir: str | None = None, source: str = "manual") -> int:
        """Create a new task in the database and return its ID."""
        task_id = await self.db.create_task(
            agent_type=agent_type, prompt=prompt,
            priority=priority, working_dir=working_dir, source=source,
        )
        logger.info(f"Task {task_id} submitted: agent={agent_type}, source={source}")
        return task_id

    async def execute_task(self, task_id: int) -> None:
        """Execute a single task: fetch config, run, update status, notify."""
        task = await self.db.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        # Get agent config if available
        agent = await self.db.get_agent(task["agent_type"])
        system_prompt = agent["system_prompt"] if agent else None
        working_dir = task.get("working_dir") or (agent["working_dir"] if agent else None)
        timeout = agent["timeout_seconds"] if agent else 300

        # Parse allowed_tools from agent config (stored as JSON array string)
        allowed_tools = None
        if agent and agent.get("allowed_tools"):
            try:
                allowed_tools = json.loads(agent["allowed_tools"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Mark as running
        await self.db.update_task(task_id, status="running")
        await self._notify(task_id, "running", f"Starting: {task['prompt'][:100]}")

        # Log the prompt
        await self.db.add_conversation(task_id, role="user", content=task["prompt"])

        # Determine if one-shot or multi-step based on prompt keywords
        oneshot = not any(kw in task["prompt"].lower() for kw in _MULTI_STEP_KEYWORDS)

        result = await self.runner.run(
            prompt=task["prompt"],
            oneshot=oneshot,
            system_prompt=system_prompt,
            session_id=task.get("session_id"),
            working_dir=working_dir,
            timeout=timeout,
            allowed_tools=allowed_tools,
        )

        # Log the response
        await self.db.add_conversation(task_id, role="assistant", content=result.stdout)

        if result.success:
            await self.db.update_task(
                task_id, status="completed",
                result=result.stdout, session_id=result.session_id,
            )
            await self._notify(task_id, "completed", result.stdout[:500])
            logger.info(f"Task {task_id} completed successfully")
        else:
            await self.db.update_task(
                task_id, status="failed",
                error=result.stderr, session_id=result.session_id,
            )
            await self._notify(task_id, "failed", f"Error: {result.stderr[:500]}")
            logger.warning(f"Task {task_id} failed: {result.stderr[:200]}")

    async def process_queue(self) -> None:
        """Process pending tasks from the queue."""
        pending = await self.db.get_pending_tasks()
        if not pending:
            return

        for task in pending:
            # Fire and forget - concurrency is managed by the runner's semaphore
            asyncio.create_task(self.execute_task(task["id"]))

    async def start_processing(self, interval: float = 5.0):
        """Start the background task processor loop."""
        self._processing = True
        logger.info("Task processor started")
        while self._processing:
            try:
                await self.process_queue()
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
            await asyncio.sleep(interval)

    def stop_processing(self):
        """Stop the background task processor loop."""
        self._processing = False
