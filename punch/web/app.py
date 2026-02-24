from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from punch.db import Database

logger = logging.getLogger("punch.web")

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(db: Database, orchestrator=None, scheduler=None, api_key: str | None = None) -> FastAPI:
    app = FastAPI(title="Punch", docs_url="/api/docs")
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # Store references for route handlers
    app.state.db = db
    app.state.orchestrator = orchestrator
    app.state.scheduler = scheduler

    # API key authentication middleware
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth if no API key configured (localhost-only mode)
        if api_key:
            # Allow static files without auth
            if not request.url.path.startswith("/static"):
                # Check header, query param, or cookie
                provided = (
                    request.headers.get("X-API-Key")
                    or request.query_params.get("api_key")
                    or request.cookies.get("punch_api_key")
                )
                if provided != api_key:
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- HTML Pages ---

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        recent_tasks = await db.list_tasks(limit=20)
        return templates.TemplateResponse("home.html", {
            "request": request, "tasks": recent_tasks, "page": "home",
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
        settings = await db.list_settings()
        return templates.TemplateResponse("settings.html", {
            "request": request, "settings": settings, "page": "settings",
        })

    @app.get("/logs", response_class=HTMLResponse)
    async def logs_page(request: Request):
        # Recent tasks with their conversations serve as logs
        tasks = await db.list_tasks(limit=50)
        return templates.TemplateResponse("logs.html", {
            "request": request, "tasks": tasks, "page": "logs",
        })

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
            import asyncio
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

    return app
