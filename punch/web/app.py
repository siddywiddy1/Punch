from __future__ import annotations

import json
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

    @app.get("/projects", response_class=HTMLResponse)
    async def projects_page(request: Request, status: str = None):
        projects = await db.list_projects(status=status)
        # Attach task counts to each project
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

    # --- Project API ---

    _VALID_PROJECT_STATUSES = {"draft", "active", "completed", "archived"}
    _VALID_PT_STATUSES = {"pending", "running", "completed", "failed", "skipped"}
    _MAX_BRIEF_SIZE = 50_000
    _MAX_PROMPT_SIZE = 20_000

    def _validate_depends_on(deps) -> list[int] | None:
        """Validate depends_on is a list of integers. Returns None on invalid input."""
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
        # Optionally create inline tasks
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
        # Validate deps reference tasks in the same project
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
