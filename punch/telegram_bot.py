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
                 execute_fn: Callable | None = None,
                 start_project_fn: Callable | None = None,
                 chat_fn: Callable | None = None):
        self.token = token
        self.submit_fn = submit_fn
        self.execute_fn = execute_fn
        self.start_project_fn = start_project_fn
        self.chat_fn = chat_fn
        self.db = db
        self.allowed_users = allowed_users or []
        self._app: Application | None = None
        self._user_chats: dict[int, int] = {}  # telegram user_id -> chat_id

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
            "/project - List/manage projects\n"
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

    async def _handle_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plain text messages as chat conversation."""
        if not self._is_authorized(update.effective_user.id):
            return

        text = update.message.text
        if not text:
            return

        user_id = update.effective_user.id

        # Get or create a chat for this Telegram user
        if user_id not in self._user_chats:
            chat_id = await self.db.create_chat(title=f"Telegram Chat")
            self._user_chats[user_id] = chat_id
        chat_id = self._user_chats[user_id]

        # Send typing indicator
        await update.message.chat.send_action("typing")

        try:
            response = await self.chat_fn(chat_id, text)
            # Telegram has a 4096 char limit
            if len(response) > 4000:
                response = response[:4000] + "\n... (truncated)"
            await update.message.reply_text(response)
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)[:500]}")

    async def _handle_newchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start a fresh chat conversation."""
        if not self._is_authorized(update.effective_user.id):
            return

        user_id = update.effective_user.id
        chat_id = await self.db.create_chat(title="Telegram Chat")
        self._user_chats[user_id] = chat_id
        await update.message.reply_text("New chat started. Send a message to begin.")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return

        text = update.message.text
        if not text:
            return

        agent_type, prompt = self._parse_message(text)

        # If it's an agent command, route through old task system
        if text.startswith("/") and agent_type != "general":
            if not prompt:
                await update.message.reply_text("Please provide a prompt after the command.")
                return
            task_id = await self.submit_fn(agent_type, prompt, source="telegram")
            await update.message.reply_text(f"Task #{task_id} created ({agent_type} agent).\nProcessing...")
            if self.execute_fn:
                import asyncio
                asyncio.create_task(self._execute_and_reply(task_id, update))
            return

        # Plain text: route through chat if chat_fn is available
        if self.chat_fn:
            await self._handle_chat_message(update, context)
            return

        # Fallback: old task system
        if not prompt:
            await update.message.reply_text("Please provide a prompt after the command.")
            return

        task_id = await self.submit_fn(agent_type, prompt, source="telegram")
        await update.message.reply_text(f"Task #{task_id} created ({agent_type} agent).\nProcessing...")

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

    async def _handle_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update.effective_user.id):
            return

        text = update.message.text or ""
        parts = text.split(None, 2)
        subcommand = parts[1].lower() if len(parts) > 1 else "list"

        if subcommand == "list":
            projects = await self.db.list_projects(status="active", limit=10)
            if not projects:
                projects = await self.db.list_projects(limit=5)
            if not projects:
                await update.message.reply_text("No projects yet.")
                return
            lines = ["Projects:\n"]
            for p in projects:
                pts = await self.db.list_project_tasks(p["id"])
                done = sum(1 for t in pts if t["status"] in ("completed", "failed", "skipped"))
                emoji = {
                    "draft": "\U0001f4dd", "active": "\u25b6",
                    "completed": "\u2705", "archived": "\U0001f4e6",
                }.get(p["status"], "\u2753")
                lines.append(f"{emoji} #{p['id']} {p['name']} ({done}/{len(pts)} tasks) [{p['status']}]")
            await update.message.reply_text("\n".join(lines))

        elif subcommand == "status" and len(parts) > 2:
            try:
                project_id = int(parts[2])
            except ValueError:
                await update.message.reply_text("Usage: /project status <id>")
                return
            project = await self.db.get_project(project_id)
            if not project:
                await update.message.reply_text(f"Project #{project_id} not found.")
                return
            pts = await self.db.list_project_tasks(project_id)
            lines = [f"{project['name']} [{project['status']}]\n"]
            for pt in pts:
                emoji = {
                    "pending": "\u23f3", "running": "\u25b6",
                    "completed": "\u2705", "failed": "\u274c", "skipped": "\u23ed",
                }.get(pt["status"], "\u2753")
                lines.append(f"  {emoji} #{pt['id']} {pt['title']} [{pt['agent_type']}]")
            await update.message.reply_text("\n".join(lines))

        elif subcommand == "start" and len(parts) > 2:
            if not self.start_project_fn:
                await update.message.reply_text("Project execution not available.")
                return
            try:
                project_id = int(parts[2])
            except ValueError:
                await update.message.reply_text("Usage: /project start <id>")
                return
            project = await self.db.get_project(project_id)
            if not project:
                await update.message.reply_text(f"Project #{project_id} not found.")
                return
            import asyncio
            asyncio.create_task(self.start_project_fn(project_id))
            await update.message.reply_text(f"\u25b6 Starting project #{project_id}: {project['name']}")

        else:
            await update.message.reply_text(
                "Usage:\n"
                "/project - List projects\n"
                "/project status <id> - Show project tasks\n"
                "/project start <id> - Start a project"
            )

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
        self._app.add_handler(CommandHandler("project", self._handle_project))
        self._app.add_handler(CommandHandler("newchat", self._handle_newchat))
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
