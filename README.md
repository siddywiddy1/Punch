# Punch

A lightweight, self-hosted AI assistant that uses your Claude Code CLI (Max plan) to autonomously manage tasks, email, code, scheduling, browser automation, and full macOS control.

Inspired by [OpenClaw](https://github.com/openclaw/openclaw) but built lean: single Python process, SQLite storage, HTMX dashboard, Telegram bot. Designed to run headless on a Mac Mini.

## Features

- **Claude Code as AI Backend** — Uses your Claude Max plan via CLI subprocess. No API keys needed.
- **Full Autonomy** — Acts on its own: triages email, manages code repos, browses the web, controls macOS apps.
- **Web Dashboard** — Dark-themed HTMX dashboard with real-time task monitoring, agent management, cron jobs, browser sessions, logs.
- **Telegram Bot** — Mobile access. Send commands, get notifications, review results.
- **Configurable Cron Jobs** — Proactive heartbeat system. Email triage every 15 min, GitHub watch hourly, daily summaries — all configurable.
- **Browser Automation** — Headless Chrome via Playwright. Navigate, fill forms, scrape, screenshot.
- **macOS Control** — AppleScript automation. Control any app, manage files, system notifications.
- **Gmail & Calendar** — Google API integration for email and scheduling.
- **GitHub** — Full `gh` CLI integration for repos, PRs, issues.
- **Tailscale Ready** — Access your dashboard from anywhere on your Tailnet.
- **Lightweight** — Single Python process, SQLite database, ~200MB RAM. No Docker, no Node.js.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      PUNCH                           │
│                (Single Python Process)                │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ FastAPI   │  │ Telegram  │  │  Task Scheduler  │  │
│  │ Dashboard │  │ Bot       │  │  (APScheduler)   │  │
│  │ + HTMX    │  │           │  │                  │  │
│  └─────┬─────┘  └─────┬─────┘  └────────┬─────────┘  │
│        └───────────────┼─────────────────┘            │
│                        │                              │
│               ┌────────▼─────────┐                    │
│               │  Task Orchestrator│                    │
│               └────────┬─────────┘                    │
│                        │                              │
│        ┌───────────────┼───────────────┐              │
│   ┌────▼─────┐   ┌─────▼──────┐  ┌────▼───────┐     │
│   │ Claude   │   │ Tool       │  │ Browser    │     │
│   │ Code CLI │   │ Plugins    │  │ (Playwright)│     │
│   └──────────┘   └────────────┘  └────────────┘     │
│                        │                              │
│               ┌────────▼─────────┐                    │
│               │   SQLite DB      │                    │
│               └──────────────────┘                    │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- macOS (tested on Monterey+)
- Python 3.9+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated with your Max plan
- [Tailscale](https://tailscale.com) (optional, for remote access)

### Install

```bash
git clone https://github.com/YOUR_USERNAME/Punch.git
cd Punch
make install
```

Or manually: `./setup.sh`

This will:
1. Create a Python virtual environment
2. Install all dependencies
3. Install Playwright's Chromium browser
4. Create a `.env` template from `.env.example`

### Configure

Edit `.env` with your settings:

```bash
# Required for Telegram bot
PUNCH_TELEGRAM_TOKEN=your-bot-token-here
PUNCH_TELEGRAM_USERS=123456789  # Your Telegram user ID

# Optional
PUNCH_WEB_PORT=8080
PUNCH_MAX_CONCURRENT=4
PUNCH_LOG_LEVEL=INFO
```

#### Telegram Bot Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token to `PUNCH_TELEGRAM_TOKEN` in `.env`
4. Get your user ID by messaging [@userinfobot](https://t.me/userinfobot)
5. Add your ID to `PUNCH_TELEGRAM_USERS`

#### Gmail & Google Calendar (Optional)

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the Gmail API and Calendar API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the credentials JSON files to:
   - `data/gmail_credentials.json`
   - `data/calendar_credentials.json`
5. On first use, Punch will open a browser for OAuth consent (one-time)

### Run

```bash
# Foreground (see logs in terminal)
make start

# Or as a background service (auto-restarts on crash)
make start-bg
```

Dashboard will be available at `http://localhost:8080`

### Manage

```bash
make start-bg   # Start as background service
make stop        # Stop the service
make restart     # Restart with latest code
make status      # Check if running
make logs        # Tail the log file
make logs-error  # Tail the error log
make test        # Run test suite
make help        # Show all commands
```

### Update

When you push new code to the repo, update on your Mac Mini with one command:

```bash
make update
```

This will:
1. `git pull` the latest code
2. Upgrade Python dependencies
3. Update Playwright browser
4. Restart the service if it was running

### Auto-Start on Boot

`make start-bg` installs a launchd service that:
- Starts Punch automatically when your Mac Mini boots
- Restarts it if it crashes
- Logs to `data/punch.log`

## Usage

### Web Dashboard

Access at `http://localhost:8080` (or via Tailscale IP).

| Page | Description |
|------|-------------|
| **Home** | Activity feed, task stats, quick task creation |
| **Agents** | Configure AI agents with custom system prompts and timeouts |
| **Tasks** | Browse all tasks with status filters, view full conversation logs |
| **Cron Jobs** | Manage scheduled tasks — create, enable/disable, delete |
| **Browser** | View active browser sessions with screenshots |
| **Settings** | Key-value configuration store |
| **Logs** | Compact view of all recent task activity |

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/status` | View recent tasks |
| `/email <prompt>` | Email agent task |
| `/code <prompt>` | Code agent task |
| `/research <prompt>` | Research agent task |
| `/browser <prompt>` | Browser agent task |
| `/macos <prompt>` | macOS automation task |
| Any text | General agent task |

### Default Agents

Punch comes with 6 pre-configured agents:

| Agent | Timeout | Purpose |
|-------|---------|---------|
| `general` | 5 min | General-purpose assistant |
| `email` | 5 min | Gmail management — read, draft, send, triage |
| `code` | 30 min | Code writing, reviewing, debugging, deploying |
| `research` | 10 min | Web research and document synthesis |
| `browser` | 5 min | Website navigation, forms, scraping |
| `macos` | 5 min | macOS app control, file management, automation |

Customize system prompts and timeouts in the Agents page.

### Example Cron Jobs

Set these up in the Cron Jobs page:

| Name | Schedule | Agent | Prompt |
|------|----------|-------|--------|
| Email Triage | `*/15 * * * *` | email | Check for new emails, categorize by urgency, handle routine ones, flag important ones to Telegram |
| GitHub Watch | `0 * * * *` | code | Check PRs, issues, and CI status across my repos. Handle anything routine, notify me of issues. |
| Morning Briefing | `0 8 * * *` | general | Review today's calendar, summarize overnight emails, prepare a morning briefing and send to Telegram |
| Daily Report | `0 18 * * *` | general | Compile everything done today across all agents, send summary to Telegram |

## Project Structure

```
punch/
├── main.py              # Entry point — wires all components
├── config.py            # Environment-based configuration
├── db.py                # SQLite database with full CRUD
├── runner.py            # Claude Code CLI subprocess runner
├── orchestrator.py      # Task queue and execution engine
├── scheduler.py         # APScheduler cron job manager
├── telegram_bot.py      # Telegram bot interface
├── browser.py           # Playwright browser automation
├── tools/
│   ├── shell.py         # Shell command execution
│   ├── filesystem.py    # File operations
│   ├── macos.py         # macOS AppleScript automation
│   ├── github.py        # GitHub via gh CLI
│   ├── gmail.py         # Gmail API integration
│   └── calendar_tool.py # Google Calendar API integration
├── web/
│   ├── app.py           # FastAPI app with routes and API
│   └── templates/       # HTMX + Tailwind templates
├── requirements.txt
setup.sh                 # Install script
punch.plist              # macOS launchd service
tests/                   # 46 tests
```

## How It Works

1. **You send a message** via Telegram or the web dashboard
2. **Punch routes it** to the appropriate agent based on the command or context
3. **Claude Code CLI runs** as a subprocess with the agent's system prompt and your message
4. **The result is stored** in SQLite and sent back to you
5. **Cron jobs** trigger proactive tasks on schedule (email checks, GitHub monitoring, etc.)

Claude Code has full access to your Mac's tools — shell, files, browser, apps — so it can take real actions autonomously.

## Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PUNCH_DB_PATH` | `punch.db` | SQLite database file path |
| `PUNCH_WEB_HOST` | `0.0.0.0` | Web server bind address |
| `PUNCH_WEB_PORT` | `8080` | Web server port |
| `PUNCH_CLAUDE_CMD` | `claude` | Claude Code CLI command |
| `PUNCH_MAX_CONCURRENT` | `4` | Max concurrent Claude Code processes |
| `PUNCH_TELEGRAM_TOKEN` | — | Telegram bot token |
| `PUNCH_TELEGRAM_USERS` | — | Comma-separated allowed Telegram user IDs |
| `PUNCH_DATA_DIR` | `data` | Data directory |
| `PUNCH_SCREENSHOTS_DIR` | `data/screenshots` | Browser screenshot directory |
| `PUNCH_WORKSPACES_DIR` | `data/workspaces` | Agent working directories |
| `PUNCH_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## API

Punch exposes a REST API at `/api/`:

```bash
# Tasks
POST   /api/tasks              # Create a task
GET    /api/tasks               # List tasks (with ?status= and ?agent_type= filters)
GET    /api/tasks/{id}          # Get task detail with conversation

# Agents
POST   /api/agents              # Create an agent
PUT    /api/agents/{name}       # Update an agent
GET    /api/agents              # List agents

# Cron Jobs
POST   /api/cron                # Create a cron job
PUT    /api/cron/{id}/toggle    # Toggle enabled/disabled
DELETE /api/cron/{id}           # Delete a cron job

# Settings
GET    /api/settings            # List all settings
PUT    /api/settings/{key}      # Set a value
```

## Development

```bash
# Install deps
pip install -r punch/requirements.txt

# Run tests
python -m pytest tests/ -v

# Run with debug logging
PUNCH_LOG_LEVEL=DEBUG python -m punch.main
```

## Requirements

- **macOS** Monterey (12.0) or later
- **Python** 3.9+
- **Claude Code CLI** with an active Max plan
- **~200MB RAM** at idle, ~500MB with browser sessions active
- **Disk**: SQLite database grows with usage; screenshots stored locally

## License

MIT
