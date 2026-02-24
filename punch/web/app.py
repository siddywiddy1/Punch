from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from punch.db import Database

logger = logging.getLogger("punch.web")

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# --- Settings Schema ---

SETTINGS_SCHEMA = [
    {
        "key": "claude",
        "label": "Claude",
        "icon": "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
        "fields": [
            {"key": "claude_command", "label": "Claude Command Path", "type": "text", "default": "claude",
             "help": "Path to the Claude CLI binary"},
            {"key": "max_concurrent_tasks", "label": "Max Concurrent Tasks", "type": "number", "default": "4",
             "help": "Maximum number of tasks running simultaneously"},
        ],
    },
    {
        "key": "telegram",
        "label": "Telegram",
        "icon": "M12 19l9 2-9-18-9 18 9-2zm0 0v-8",
        "fields": [
            {"key": "telegram_token", "label": "Bot Token", "type": "password", "default": "",
             "help": "Token from @BotFather on Telegram"},
            {"key": "telegram_allowed_users", "label": "Allowed User IDs", "type": "text", "default": "",
             "help": "Comma-separated Telegram user IDs (get yours from @userinfobot)"},
        ],
    },
    {
        "key": "web",
        "label": "Web",
        "icon": "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9",
        "fields": [
            {"key": "web_host", "label": "Host", "type": "text", "default": "127.0.0.1",
             "help": "Bind address for the web server"},
            {"key": "web_port", "label": "Port", "type": "number", "default": "8080",
             "help": "Port number for the web server"},
            {"key": "api_key", "label": "API Key", "type": "password", "default": "",
             "help": "API key for authentication (leave empty for localhost-only mode)"},
        ],
    },
    {
        "key": "system",
        "label": "System",
        "icon": "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z",
        "fields": [
            {"key": "log_level", "label": "Log Level", "type": "select", "default": "INFO",
             "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
             "help": "Logging verbosity level"},
            {"key": "data_dir", "label": "Data Directory", "type": "text", "default": "data",
             "help": "Directory for storing data files"},
        ],
    },
]


def create_app(db: Database, orchestrator=None, scheduler=None, api_key: str | None = None) -> FastAPI:
    app = FastAPI(title="Punch", docs_url="/api/docs")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # Store references for route handlers
    app.state.db = db
    app.state.orchestrator = orchestrator
    app.state.scheduler = scheduler

    # Paths that skip onboarding redirect
    _SKIP_ONBOARDING = ("/static", "/api/", "/onboarding", "/htmx/onboarding")

    # API key authentication + onboarding middleware
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        # Skip auth if no API key configured (localhost-only mode)
        if api_key:
            if not path.startswith("/static"):
                provided = (
                    request.headers.get("X-API-Key")
                    or request.query_params.get("api_key")
                    or request.cookies.get("punch_api_key")
                )
                if provided != api_key:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

        # Onboarding redirect: if onboarding_complete not set, redirect HTML pages
        if not any(path.startswith(p) for p in _SKIP_ONBOARDING):
            onboarding_done = await db.get_setting("onboarding_complete")
            if not onboarding_done and path != "/onboarding":
                return RedirectResponse("/onboarding", status_code=302)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- HTML Pages ---

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        onboarding_done = await db.get_setting("onboarding_complete")
        if not onboarding_done:
            return RedirectResponse("/onboarding", status_code=302)
        return RedirectResponse("/chat", status_code=302)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        recent_tasks = await db.list_tasks(limit=20)
        return templates.TemplateResponse("home.html", {
            "request": request, "tasks": recent_tasks, "page": "dashboard",
        })

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(request: Request, status: str = None, agent_type: str = None):
        tasks = await db.list_tasks(status=status, agent_type=agent_type, limit=100)
        agents = await db.list_agents()
        return templates.TemplateResponse("tasks.html", {
            "request": request, "tasks": tasks, "agents": agents,
            "page": "tasks", "filter_status": status, "filter_agent": agent_type,
        })

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    async def task_detail(request: Request, task_id: int):
        task = await db.get_task(task_id)
        conversation = await db.get_conversation(task_id) if task else []
        return templates.TemplateResponse("task_detail.html", {
            "request": request, "task": task, "conversation": conversation, "page": "tasks",
        })

    @app.get("/agents", response_class=HTMLResponse)
    async def agents_page(request: Request):
        agents = await db.list_agents()
        return templates.TemplateResponse("agents.html", {
            "request": request, "agents": agents, "page": "agents",
        })

    @app.get("/cron", response_class=HTMLResponse)
    async def cron_page(request: Request):
        jobs = await db.list_cron_jobs()
        agents = await db.list_agents()
        return templates.TemplateResponse("cron.html", {
            "request": request, "jobs": jobs, "agents": agents, "page": "cron",
        })

    @app.get("/browser", response_class=HTMLResponse)
    async def browser_page(request: Request):
        sessions = await db.list_browser_sessions()
        return templates.TemplateResponse("browser.html", {
            "request": request, "sessions": sessions, "page": "browser",
        })

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        settings_list = await db.list_settings()
        settings_map = {s["key"]: s["value"] for s in settings_list}
        return templates.TemplateResponse("settings.html", {
            "request": request, "settings": settings_map,
            "schema": SETTINGS_SCHEMA, "page": "settings",
        })

    @app.get("/projects", response_class=HTMLResponse)
    async def projects_page(request: Request, status: str = None):
        projects = await db.list_projects(status=status)
        for p in projects:
            pts = await db.list_project_tasks(p["id"])
            p["task_count"] = len(pts)
            p["done_count"] = sum(1 for t in pts if t["status"] in ("completed", "failed", "skipped"))
        return templates.TemplateResponse("projects.html", {
            "request": request, "projects": projects, "page": "projects",
            "filter_status": status,
        })

    @app.get("/projects/{project_id}", response_class=HTMLResponse)
    async def project_detail_page(request: Request, project_id: int):
        project = await db.get_project(project_id)
        project_tasks = await db.list_project_tasks(project_id) if project else []
        agents = await db.list_agents()
        return templates.TemplateResponse("project_detail.html", {
            "request": request, "project": project, "project_tasks": project_tasks,
            "agents": agents, "page": "projects",
        })

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        tasks = await db.list_tasks(limit=50)
        return templates.TemplateResponse("logs.html", {
            "request": request, "tasks": tasks, "page": "logs",
        })

    # --- Chat Pages ---

    @app.get("/chat", response_class=HTMLResponse)
    async def chat_redirect(request: Request):
        chats = await db.list_chats(limit=1)
        if chats:
            return RedirectResponse(f"/chat/{chats[0]['id']}", status_code=302)
        # Create a new chat
        chat_id = await db.create_chat()
        return RedirectResponse(f"/chat/{chat_id}", status_code=302)

    @app.get("/chat/{chat_id}", response_class=HTMLResponse)
    async def chat_page(request: Request, chat_id: int):
        chat = await db.get_chat(chat_id)
        if not chat or not chat["is_active"]:
            return RedirectResponse("/chat", status_code=302)
        messages = await db.get_chat_messages(chat_id)
        chats = await db.list_chats(limit=50)
        return templates.TemplateResponse("chat.html", {
            "request": request, "chat": chat, "messages": messages,
            "chats": chats, "page": "chat",
        })

    # --- Chat HTMX ---

    @app.post("/htmx/chat/{chat_id}/send", response_class=HTMLResponse)
    async def htmx_chat_send(request: Request, chat_id: int, message: str = Form(...)):
        if orchestrator:
            # Store user message and create pending assistant message
            await db.add_chat_message(chat_id, role="user", content=message)
            await db.add_chat_message(chat_id, role="assistant", content="", status="pending")
            # Kick off async chat processing
            asyncio.create_task(_process_chat(chat_id, message))
        messages = await db.get_chat_messages(chat_id)
        return templates.TemplateResponse("partials/chat_messages.html", {
            "request": request, "messages": messages, "chat_id": chat_id,
        })

    async def _process_chat(chat_id: int, message: str):
        """Background task: run chat and update pending message."""
        try:
            chat = await db.get_chat(chat_id)
            if not chat:
                return
            agent = await db.get_agent("general")
            system_prompt = agent["system_prompt"] if agent else None

            result = await orchestrator.runner.run(
                prompt=message,
                oneshot=False,
                system_prompt=system_prompt,
                session_id=chat.get("session_id"),
                output_format="json",
            )

            if result.session_id:
                await db.update_chat(chat_id, session_id=result.session_id)

            response = result.stdout if result.success else f"Error: {result.stderr}"

            # Find and update the pending message
            msgs = await db.get_chat_messages(chat_id)
            for msg in reversed(msgs):
                if msg["role"] == "assistant" and msg["status"] == "pending":
                    await db.update_chat_message(msg["id"], content=response, status="complete")
                    break

            await db.update_chat(chat_id)

            # Auto-title
            if chat["title"] == "New Chat":
                title = message[:50].strip()
                if len(message) > 50:
                    title += "..."
                await db.update_chat(chat_id, title=title)
        except Exception as e:
            logger.error(f"Chat processing error for chat {chat_id}: {e}")
            msgs = await db.get_chat_messages(chat_id)
            for msg in reversed(msgs):
                if msg["role"] == "assistant" and msg["status"] == "pending":
                    await db.update_chat_message(msg["id"], content=f"Error: {str(e)}", status="complete")
                    break

    @app.get("/htmx/chat/{chat_id}/messages", response_class=HTMLResponse)
    async def htmx_chat_messages(request: Request, chat_id: int):
        messages = await db.get_chat_messages(chat_id)
        return templates.TemplateResponse("partials/chat_messages.html", {
            "request": request, "messages": messages, "chat_id": chat_id,
        })

    @app.post("/htmx/chat/new", response_class=HTMLResponse)
    async def htmx_chat_new(request: Request):
        chat_id = await db.create_chat()
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = f"/chat/{chat_id}"
        return response

    @app.delete("/htmx/chat/{chat_id}", response_class=HTMLResponse)
    async def htmx_chat_delete(request: Request, chat_id: int):
        await db.delete_chat(chat_id)
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/chat"
        return response

    # --- Chat API ---

    @app.post("/api/chat")
    async def api_create_chat(request: Request):
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        title = body.get("title", "New Chat") if body else "New Chat"
        chat_id = await db.create_chat(title=title)
        return {"chat_id": chat_id}

    @app.post("/api/chat/{chat_id}/message")
    async def api_send_message(chat_id: int, request: Request):
        body = await request.json()
        message = body.get("message", "")
        if not message:
            return JSONResponse({"error": "message is required"}, status_code=400)
        if not orchestrator:
            return JSONResponse({"error": "No orchestrator"}, status_code=500)
        response = await orchestrator.chat(chat_id, message)
        return {"response": response}

    @app.get("/api/chat/{chat_id}/messages")
    async def api_list_messages(chat_id: int):
        messages = await db.get_chat_messages(chat_id)
        return {"messages": messages}

    # --- Onboarding ---

    @app.get("/onboarding", response_class=HTMLResponse)
    async def onboarding_page(request: Request):
        onboarding_done = await db.get_setting("onboarding_complete")
        if onboarding_done:
            return RedirectResponse("/chat", status_code=302)
        return templates.TemplateResponse("onboarding.html", {"request": request})

    @app.post("/htmx/onboarding/check-claude", response_class=HTMLResponse)
    async def htmx_onboarding_check_claude(request: Request):
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            version = stdout.decode("utf-8", errors="replace").strip()
            success = proc.returncode == 0
        except Exception:
            version = ""
            success = False
        return templates.TemplateResponse("partials/onboarding_claude_check.html", {
            "request": request, "success": success, "version": version,
        })

    @app.post("/htmx/onboarding/save-telegram", response_class=HTMLResponse)
    async def htmx_onboarding_save_telegram(request: Request,
                                             telegram_token: str = Form(""),
                                             telegram_users: str = Form("")):
        if telegram_token.strip():
            await db.set_setting("telegram_token", telegram_token.strip())
        if telegram_users.strip():
            await db.set_setting("telegram_allowed_users", telegram_users.strip())
        return templates.TemplateResponse("partials/onboarding_telegram_saved.html", {
            "request": request, "saved": bool(telegram_token.strip()),
        })

    @app.post("/htmx/onboarding/complete", response_class=HTMLResponse)
    async def htmx_onboarding_complete(request: Request):
        await db.set_setting("onboarding_complete", "true")
        response = HTMLResponse("")
        response.headers["HX-Redirect"] = "/chat"
        return response

    # --- Settings HTMX ---

    @app.post("/htmx/settings/save", response_class=HTMLResponse)
    async def htmx_settings_save(request: Request):
        form = await request.form()
        for section in SETTINGS_SCHEMA:
            for field in section["fields"]:
                value = form.get(field["key"], "")
                if value:
                    await db.set_setting(field["key"], str(value))
        return templates.TemplateResponse("partials/settings_saved.html", {"request": request})

    # --- API Endpoints ---

    @app.post("/api/tasks")
    async def api_create_task(request: Request):
        body = await request.json()
        agent_type = body.get("agent_type", "general")
        prompt = body.get("prompt", "")
        priority = body.get("priority", 0)

        if orchestrator:
            task_id = await orchestrator.submit(agent_type, prompt, priority=priority, source="api")
        else:
            task_id = await db.create_task(agent_type=agent_type, prompt=prompt, priority=priority, source="api")

        return {"task_id": task_id}

    @app.get("/api/tasks")
    async def api_list_tasks(status: str = None, agent_type: str = None, limit: int = 50):
        return await db.list_tasks(status=status, agent_type=agent_type, limit=limit)

    @app.get("/api/tasks/{task_id}")
    async def api_get_task(task_id: int):
        task = await db.get_task(task_id)
        if not task:
            return JSONResponse({"error": "Not found"}, status_code=404)
        conversation = await db.get_conversation(task_id)
        return {"task": task, "conversation": conversation}

    # --- HTMX Partials ---

    @app.post("/htmx/tasks/create", response_class=HTMLResponse)
    async def htmx_create_task(request: Request, agent_type: str = Form(...), prompt: str = Form(...)):
        if orchestrator:
            task_id = await orchestrator.submit(agent_type, prompt, source="dashboard")
            asyncio.create_task(orchestrator.execute_task(task_id))
        else:
            task_id = await db.create_task(agent_type=agent_type, prompt=prompt, source="dashboard")
        tasks = await db.list_tasks(limit=20)
        return templates.TemplateResponse("partials/task_list.html", {
            "request": request, "tasks": tasks,
        })

    @app.get("/htmx/tasks/refresh", response_class=HTMLResponse)
    async def htmx_refresh_tasks(request: Request, status: str = None, agent_type: str = None):
        tasks = await db.list_tasks(status=status, agent_type=agent_type, limit=100)
        return templates.TemplateResponse("partials/task_list.html", {
            "request": request, "tasks": tasks,
        })

    # --- Cron Job API ---

    @app.post("/api/cron")
    async def api_create_cron(request: Request):
        body = await request.json()
        job_id = await db.create_cron_job(
            name=body["name"], schedule=body["schedule"],
            agent_type=body["agent_type"], prompt=body["prompt"],
        )
        if scheduler:
            await scheduler.add_job(job_id)
        return {"job_id": job_id}

    @app.put("/api/cron/{job_id}/toggle")
    async def api_toggle_cron(job_id: int):
        job = await db.get_cron_job(job_id)
        if not job:
            return JSONResponse({"error": "Not found"}, status_code=404)
        new_state = not job["enabled"]
        await db.update_cron_job(job_id, enabled=new_state)
        if scheduler:
            await scheduler.reload_job(job_id)
        return {"enabled": new_state}

    @app.delete("/api/cron/{job_id}")
    async def api_delete_cron(job_id: int):
        if scheduler:
            await scheduler.remove_job(job_id)
        await db.delete_cron_job(job_id)
        return {"ok": True}

    # --- Agent API ---

    @app.post("/api/agents")
    async def api_create_agent(request: Request):
        body = await request.json()
        agent_id = await db.create_agent(
            name=body["name"], system_prompt=body["system_prompt"],
            working_dir=body.get("working_dir"), timeout_seconds=body.get("timeout_seconds", 300),
        )
        return {"agent_id": agent_id}

    @app.put("/api/agents/{name}")
    async def api_update_agent(name: str, request: Request):
        body = await request.json()
        await db.update_agent(name, **body)
        return {"ok": True}

    @app.get("/api/agents")
    async def api_list_agents():
        return await db.list_agents()

    # --- Settings API ---

    @app.get("/api/settings")
    async def api_list_settings():
        return await db.list_settings()

    @app.put("/api/settings/{key}")
    async def api_set_setting(key: str, request: Request):
        body = await request.json()
        await db.set_setting(key, body["value"])
        return {"ok": True}

    # --- Project API ---

    _VALID_PROJECT_STATUSES = {"draft", "active", "completed", "archived"}
    _VALID_PT_STATUSES = {"pending", "running", "completed", "failed", "skipped"}
    _MAX_BRIEF_SIZE = 50_000
    _MAX_PROMPT_SIZE = 20_000

    def _validate_depends_on(deps) -> list[int] | None:
        if not isinstance(deps, list):
            return None
        if not all(isinstance(d, int) for d in deps):
            return None
        return deps

    @app.post("/api/projects")
    async def api_create_project(request: Request):
        body = await request.json()
        name = body.get("name")
        if not name or not isinstance(name, str):
            return JSONResponse({"error": "name is required"}, status_code=400)
        brief = body.get("brief", "")
        if len(brief) > _MAX_BRIEF_SIZE:
            return JSONResponse({"error": f"brief exceeds {_MAX_BRIEF_SIZE} chars"}, status_code=400)
        project_id = await db.create_project(name=name, brief=brief)
        for i, t in enumerate(body.get("tasks", [])):
            raw_deps = t.get("depends_on", [])
            deps = _validate_depends_on(raw_deps)
            if deps is None:
                return JSONResponse({"error": "depends_on must be a list of integers"}, status_code=400)
            prompt = t.get("prompt", "")
            if len(prompt) > _MAX_PROMPT_SIZE:
                return JSONResponse({"error": f"task prompt exceeds {_MAX_PROMPT_SIZE} chars"}, status_code=400)
            await db.create_project_task(
                project_id=project_id, title=t.get("title", f"Task {i+1}"),
                agent_type=t.get("agent_type", "general"),
                prompt=prompt, position=t.get("position", i),
                depends_on=json.dumps(deps),
            )
        return {"project_id": project_id}

    @app.get("/api/projects")
    async def api_list_projects(status: str = None, limit: int = 50):
        return await db.list_projects(status=status, limit=limit)

    @app.get("/api/projects/{project_id}")
    async def api_get_project(project_id: int):
        project = await db.get_project(project_id)
        if not project:
            return JSONResponse({"error": "Not found"}, status_code=404)
        tasks = await db.list_project_tasks(project_id)
        return {"project": project, "tasks": tasks}

    @app.put("/api/projects/{project_id}")
    async def api_update_project(project_id: int, request: Request):
        body = await request.json()
        if "status" in body and body["status"] not in _VALID_PROJECT_STATUSES:
            return JSONResponse({"error": f"Invalid status. Must be one of: {_VALID_PROJECT_STATUSES}"}, status_code=400)
        if "brief" in body and len(body.get("brief", "")) > _MAX_BRIEF_SIZE:
            return JSONResponse({"error": f"brief exceeds {_MAX_BRIEF_SIZE} chars"}, status_code=400)
        await db.update_project(project_id, **body)
        return {"ok": True}

    @app.delete("/api/projects/{project_id}")
    async def api_delete_project(project_id: int):
        await db.delete_project(project_id)
        return {"ok": True}

    @app.post("/api/projects/{project_id}/start")
    async def api_start_project(project_id: int):
        if not orchestrator:
            return JSONResponse({"error": "No orchestrator"}, status_code=500)
        project = await db.get_project(project_id)
        if not project:
            return JSONResponse({"error": "Not found"}, status_code=404)
        if project["status"] != "draft":
            return JSONResponse({"error": f"Cannot start project with status '{project['status']}'"}, status_code=400)
        await orchestrator.start_project(project_id)
        return {"ok": True}

    @app.post("/api/projects/{project_id}/tasks")
    async def api_add_project_task(project_id: int, request: Request):
        body = await request.json()
        title = body.get("title")
        if not title or not isinstance(title, str):
            return JSONResponse({"error": "title is required"}, status_code=400)
        raw_deps = body.get("depends_on", [])
        deps = _validate_depends_on(raw_deps)
        if deps is None:
            return JSONResponse({"error": "depends_on must be a list of integers"}, status_code=400)
        prompt = body.get("prompt", "")
        if len(prompt) > _MAX_PROMPT_SIZE:
            return JSONResponse({"error": f"prompt exceeds {_MAX_PROMPT_SIZE} chars"}, status_code=400)
        if deps:
            existing = await db.list_project_tasks(project_id)
            existing_ids = {t["id"] for t in existing}
            invalid_deps = [d for d in deps if d not in existing_ids]
            if invalid_deps:
                return JSONResponse({"error": f"depends_on references non-existent tasks: {invalid_deps}"}, status_code=400)
        pt_id = await db.create_project_task(
            project_id=project_id, title=title,
            agent_type=body.get("agent_type", "general"),
            prompt=prompt, position=body.get("position", 0),
            depends_on=json.dumps(deps),
        )
        return {"project_task_id": pt_id}

    @app.put("/api/project-tasks/{pt_id}")
    async def api_update_project_task(pt_id: int, request: Request):
        body = await request.json()
        if "status" in body and body["status"] not in _VALID_PT_STATUSES:
            return JSONResponse({"error": f"Invalid status. Must be one of: {_VALID_PT_STATUSES}"}, status_code=400)
        if "prompt" in body and len(body.get("prompt", "")) > _MAX_PROMPT_SIZE:
            return JSONResponse({"error": f"prompt exceeds {_MAX_PROMPT_SIZE} chars"}, status_code=400)
        if "depends_on" in body:
            if isinstance(body["depends_on"], list):
                deps = _validate_depends_on(body["depends_on"])
                if deps is None:
                    return JSONResponse({"error": "depends_on must be a list of integers"}, status_code=400)
                body["depends_on"] = json.dumps(deps)
            else:
                return JSONResponse({"error": "depends_on must be a list"}, status_code=400)
        await db.update_project_task(pt_id, **body)
        return {"ok": True}

    @app.delete("/api/project-tasks/{pt_id}")
    async def api_delete_project_task(pt_id: int):
        await db.delete_project_task(pt_id)
        return {"ok": True}

    # --- Project HTMX ---

    @app.get("/htmx/projects/{project_id}/tasks", response_class=HTMLResponse)
    async def htmx_project_tasks(request: Request, project_id: int):
        project = await db.get_project(project_id)
        project_tasks = await db.list_project_tasks(project_id) if project else []
        return templates.TemplateResponse("partials/project_task_list.html", {
            "request": request, "project": project, "project_tasks": project_tasks,
        })

    return app
