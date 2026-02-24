# Punch: Lightweight Self-Hosted AI Assistant

## Overview

Punch is a lightweight, self-hosted AI assistant that runs on a Mac Mini 2014 (macOS Monterey). It uses Claude Code CLI (Max plan, subprocess per task) as its AI backend to autonomously manage tasks, emails, code, scheduling, browser automation, and full macOS control.

Inspired by OpenClaw but built lean: single Python process, SQLite storage, HTMX dashboard, Telegram bot.

## Requirements

- **Channels**: Telegram bot + Web Dashboard (HTMX)
- **AI backend**: Claude Code CLI via Max plan. Subprocess per task (`claude --print` for one-shot, `claude -p` for multi-step, `claude --resume` for follow-ups). No API keys.
- **Autonomy**: Fully autonomous. Acts on its own, user reviews after the fact.
- **Integrations**: GitHub (`gh` CLI), Gmail (Google API), Google Calendar (Google API), Chrome (Playwright), macOS (AppleScript/osascript), file system, shell
- **Heartbeat**: Configurable cron jobs per task type via APScheduler
- **Dashboard**: Full-featured — agents, tasks, cron jobs, browser sessions, files, logs, settings
- **Network**: Accessible via Tailscale on port 8080
- **Target**: Mac Mini 2014, macOS Monterey, Python 3.10-3.11
- **Dependencies**: Minimal. Python + SQLite + Playwright. No Node.js, no Docker.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    PUNCH                             │
│              (Single Python Process)                 │
│                                                      │
│  ┌─────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ FastAPI  │  │ Telegram │  │   Task Scheduler  │  │
│  │ Web UI   │  │   Bot    │  │   (APScheduler)   │  │
│  │ + HTMX   │  │          │  │                   │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │              │                 │             │
│       └──────────────┼─────────────────┘             │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │  Task Router   │                      │
│              │  & Orchestrator│                      │
│              └───────┬────────┘                      │
│                      │                               │
│       ┌──────────────┼──────────────┐                │
│       │              │              │                │
│  ┌────▼────┐   ┌─────▼─────┐  ┌────▼──────┐        │
│  │ Claude  │   │  Tool     │  │ Browser   │        │
│  │ Code    │   │  Plugins  │  │ Control   │        │
│  │ Runner  │   │           │  │(Playwright)│        │
│  └────┬────┘   └─────┬─────┘  └────┬──────┘        │
│       │              │              │                │
│       └──────────────┼──────────────┘                │
│                      │                               │
│              ┌───────▼────────┐                      │
│              │    SQLite DB   │                      │
│              │  (all state)   │                      │
│              └────────────────┘                      │
└─────────────────────────────────────────────────────┘
         │                    │
    Tailscale             Telegram API
    (port 8080)
```

## Components

### 1. Claude Code Runner

The AI brain. Spawns Claude Code CLI subprocesses:

- **One-shot**: `claude --print -p "..."` for quick queries
- **Multi-step**: `claude -p "..."` with working directory for complex tasks
- **Resume**: `claude --resume <session-id> -p "..."` for follow-ups
- **Concurrency**: Max 2-3 concurrent processes (Mac Mini hardware limit)
- **Agent types**: Different system prompts for email, code, research, macOS, browser agents
- **Working directories**: Each task type runs in its own directory
- **Output capture**: All stdout/stderr stored in SQLite
- **Timeouts**: Configurable per task type (default 5 min quick, 30 min code)

### 2. Dashboard (FastAPI + HTMX)

Server-rendered HTML with HTMX for reactivity. Tailwind CSS via CDN.

Pages:
- **Home**: Activity feed, recent tasks, quick actions
- **Agents**: Agent types, current state, recent activity, config
- **Tasks**: Full task list with filters (status, agent, date), click-through to logs
- **Cron Jobs**: Scheduled jobs with frequency, last/next run, enable/disable
- **Browser**: Live sessions with screenshots, URL, manual control option
- **Files**: File browser for managed directories
- **Settings**: Integration configs, agent system prompts, cron schedules
- **Logs**: System log viewer with search and filtering

### 3. Telegram Bot

- Long-polling (no webhook, simpler on Tailscale)
- Receives commands and natural language messages
- Sends task results, notifications, summaries
- Inline keyboards for quick actions
- Photo/document support for screenshots and files

### 4. Task Scheduler (APScheduler)

Configurable cron jobs stored in SQLite:

```
- name: "Email Triage"
  schedule: "*/15 * * * *"
  agent: "email"
  prompt: "Check for new emails, categorize, handle routine, flag important to Telegram"

- name: "GitHub Watch"
  schedule: "0 * * * *"
  agent: "code"
  prompt: "Check PRs, issues, CI status. Handle routine, notify of issues."

- name: "Calendar Prep"
  schedule: "0 8 * * *"
  agent: "scheduler"
  prompt: "Review today's calendar, prepare briefing, send morning summary to Telegram"

- name: "Daily Report"
  schedule: "0 18 * * *"
  agent: "reporter"
  prompt: "Compile today's activity, send summary to Telegram"
```

### 5. Tool Plugins

| Tool | Implementation |
|------|---------------|
| Gmail | `google-api-python-client` (OAuth2) |
| Google Calendar | `google-api-python-client` (OAuth2) |
| GitHub | `gh` CLI (already available) |
| Chrome/Browser | `playwright` (bundled Chromium) |
| File System | Python `pathlib` + `shutil` |
| macOS Control | `osascript` (AppleScript) |
| Shell | `subprocess` |
| Telegram | `python-telegram-bot` |

### 6. Task Router & Orchestrator

- Routes incoming requests (Telegram, dashboard, cron) to handlers
- Manages task queue with priority levels
- Enforces concurrency limits
- Tracks task state: pending → running → completed/failed
- Stores all results in SQLite

## Database Schema (SQLite)

```sql
-- Tasks
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY,
    agent_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, running, completed, failed
    priority INTEGER DEFAULT 0,
    result TEXT,
    error TEXT,
    session_id TEXT,  -- Claude Code session ID for resume
    working_dir TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Cron jobs
CREATE TABLE cron_jobs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,  -- cron expression
    agent_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent configs
CREATE TABLE agents (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    system_prompt TEXT NOT NULL,
    working_dir TEXT,
    timeout_seconds INTEGER DEFAULT 300,
    max_concurrent INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Conversation logs
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    role TEXT NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Settings (key-value store)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Browser sessions
CREATE TABLE browser_sessions (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    url TEXT,
    screenshot_path TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Tailscale Access

- FastAPI binds to `0.0.0.0:8080`
- Dashboard at `http://<mac-mini-tailscale-ip>:8080`
- No port forwarding, no public exposure
- Tailscale handles encryption

## macOS Monterey Compatibility

| Concern | Solution |
|---------|----------|
| Python | 3.10-3.11 via Homebrew |
| Playwright | Bundled Chromium, Monterey compatible |
| SQLite | Built into Python |
| Claude Code CLI | Pre-installed, Max plan auth |
| APScheduler | Pure Python |
| Memory footprint | ~150-300MB total |

## Project Structure

```
punch/
├── main.py                 # Entry point, starts all services
├── config.py               # Configuration management
├── db.py                   # SQLite database setup and migrations
├── runner.py               # Claude Code CLI subprocess runner
├── orchestrator.py         # Task routing and queue management
├── scheduler.py            # APScheduler cron job management
├── telegram_bot.py         # Telegram bot handlers
├── browser.py              # Playwright browser control
├── tools/
│   ├── __init__.py
│   ├── gmail.py            # Gmail integration
│   ├── calendar_tool.py    # Google Calendar integration
│   ├── github.py           # GitHub via gh CLI
│   ├── filesystem.py       # File system operations
│   ├── macos.py            # macOS AppleScript automation
│   └── shell.py            # Shell command execution
├── web/
│   ├── app.py              # FastAPI app and routes
│   ├── templates/
│   │   ├── base.html       # Base template with nav, Tailwind, HTMX
│   │   ├── home.html
│   │   ├── agents.html
│   │   ├── tasks.html
│   │   ├── task_detail.html
│   │   ├── cron.html
│   │   ├── browser.html
│   │   ├── files.html
│   │   ├── settings.html
│   │   └── logs.html
│   └── static/
│       └── (minimal custom CSS if needed)
├── requirements.txt
└── README.md
```

## Dependencies (requirements.txt)

```
fastapi>=0.104.0
uvicorn>=0.24.0
jinja2>=3.1.0
python-multipart>=0.0.6
python-telegram-bot>=20.0
apscheduler>=3.10.0
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.1.0
playwright>=1.40.0
aiosqlite>=0.19.0
httpx>=0.25.0
```
