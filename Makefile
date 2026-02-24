.PHONY: install start stop restart update status logs test clean

PYTHON ?= python3
VENV = venv
PIP = $(VENV)/bin/pip
PYTON_BIN = $(VENV)/bin/python
SERVICE = com.punch.assistant
PLIST = ~/Library/LaunchAgents/$(SERVICE).plist

# === Setup ===

install: ## Full install: venv, deps, playwright, .env
	@echo "=== Installing Punch ==="
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIP) install -r punch/requirements.txt
	$(PYTON_BIN) -m playwright install chromium
	@mkdir -p data/screenshots data/workspaces
	@test -f .env || cp .env.example .env
	@echo ""
	@echo "Done! Edit .env, then run: make start"

# === Running ===

start: ## Start Punch in foreground
	@echo "Starting Punch..."
	$(PYTON_BIN) -m punch.main

start-bg: ## Start Punch as a background launchd service
	@cp punch.plist $(PLIST)
	launchctl load $(PLIST)
	@echo "Punch started as background service"
	@echo "Dashboard: http://localhost:8080"

stop: ## Stop the background service
	-launchctl unload $(PLIST)
	@echo "Punch stopped"

restart: stop start-bg ## Restart the background service

status: ## Check if Punch is running
	@launchctl list | grep $(SERVICE) && echo "Punch is running" || echo "Punch is not running"

# === Updates ===

update: ## Pull latest code, update deps, restart
	@echo "=== Updating Punch ==="
	git pull --ff-only
	$(PIP) install -r punch/requirements.txt --upgrade
	$(PYTON_BIN) -m playwright install chromium
	@echo ""
	@echo "Update complete."
	@if launchctl list | grep -q $(SERVICE); then \
		echo "Restarting service..."; \
		launchctl unload $(PLIST); \
		cp punch.plist $(PLIST); \
		launchctl load $(PLIST); \
		echo "Punch restarted with new version."; \
	else \
		echo "Run 'make start' or 'make start-bg' to start."; \
	fi

# === Monitoring ===

logs: ## Tail the log file
	@tail -f data/punch.log

logs-error: ## Tail the error log
	@tail -f data/punch_error.log

# === Development ===

test: ## Run test suite
	$(PYTON_BIN) -m pytest tests/ -v

test-quick: ## Run tests without verbose
	$(PYTON_BIN) -m pytest tests/ -q

# === Cleanup ===

clean: ## Remove venv, data, db
	rm -rf $(VENV) data/ *.db .pytest_cache __pycache__

uninstall: stop clean ## Stop service, remove everything
	-rm -f $(PLIST)
	@echo "Punch uninstalled"

# === Help ===

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
