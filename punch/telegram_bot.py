from __future__ import annotations

import logging
from typing import Callable, Awaitable

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

from punch.db import Database

logger = logging.getLogger("punch.telegram")

SubmitFn = Callable[..., Awaitable[int]]
AGENT_COMMANDS = {"email", "code", "research", "browser", "macos", "general"}


class PunchTelegramBot:
    def __init__(self, token: str, submit_fn: SubmitFn, db: Database,
                 allowed_users: list[int] | None = None,
                 execute_fn: Callable | None = None):
        self.token = token
        self.submit_fn = submit_fn
        self.execute_fn = execute_fn
        self.db = db
        self.allowed_users = allowed_users or []
        self._app: Application | None = None

    def _parse_message(self, text: str) -> tuple[str, str]:
        """Parse agent type and prompt from message text."""
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0][1:].lower()
            if cmd in AGENT_COMMANDS:
                prompt = parts[1] if len(parts) > 1 else ""
                return cmd, prompt
        return "general", text

    def _is_authorized(self, user_id: int) -> bool:
        if not self.allowed_users:
            logger.warning("No allowed users configured — denying all Telegram access")
            return False
        return user_id in self.allowed_users

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            await update.message.reply_text("Unauthorized.")
            return
        await update.message.reply_text(
            "Punch AI Assistant\n\n"
            "Send any message to create a task.\n"
            "Use /email, /code, /research, /browser, /macos to specify agent type.\n"
            "/status - View recent tasks\n"
            "/help - Show this message"
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return
        tasks = await self.db.list_tasks(limit=5)
        if not tasks:
            await update.message.reply_text("No tasks yet.")
            return

        lines = ["Recent tasks:\n"]
        for t in tasks:
            emoji = {"running": "\u25b6", "completed": "\u2705", "failed": "\u274c", "pending": "\u23f3"}.get(t["status"], "\u2753")
            lines.append(f"{emoji} #{t['id']} [{t['agent_type']}] {t['prompt'][:50]}")
        await update.message.reply_text("\n".join(lines))

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return

        text = update.message.text
        if not text:
            return

        agent_type, prompt = self._parse_message(text)
        if not prompt:
            await update.message.reply_text("Please provide a prompt after the command.")
            return

        task_id = await self.submit_fn(agent_type, prompt, source="telegram")
        await update.message.reply_text(f"Task #{task_id} created ({agent_type} agent).\nProcessing...")

        # Execute the task immediately if execute_fn is available
        if self.execute_fn:
            import asyncio
            asyncio.create_task(self._execute_and_reply(task_id, update))

    async def _execute_and_reply(self, task_id: int, update: Update):
        try:
            await self.execute_fn(task_id)
            task = await self.db.get_task(task_id)
            if task["status"] == "completed":
                result = task["result"] or "Done (no output)"
                # Telegram has a 4096 char limit
                if len(result) > 4000:
                    result = result[:4000] + "\n... (truncated)"
                await update.message.reply_text(f"\u2705 Task #{task_id} completed:\n\n{result}")
            else:
                error = task.get("error", "Unknown error")
                await update.message.reply_text(f"\u274c Task #{task_id} failed:\n\n{error[:2000]}")
        except Exception as e:
            await update.message.reply_text(f"\u274c Task #{task_id} error: {str(e)[:500]}")

    async def notify(self, task_id: int, status: str, message: str):
        """Send a notification to all allowed users."""
        if not self._app or not self.allowed_users:
            return
        emoji = {"running": "\u25b6", "completed": "\u2705", "failed": "\u274c"}.get(status, "\U0001f4cb")
        text = f"{emoji} Task #{task_id} [{status}]\n{message[:3000]}"
        for user_id in self.allowed_users:
            try:
                await self._app.bot.send_message(chat_id=user_id, text=text)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")

    def build(self) -> Application:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("help", self._handle_start))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        # Agent-specific commands
        for cmd in AGENT_COMMANDS:
            self._app.add_handler(CommandHandler(cmd, self._handle_message))
        # Catch-all for plain text
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        return self._app

    async def start(self):
        app = self.build()
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started")

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped")
