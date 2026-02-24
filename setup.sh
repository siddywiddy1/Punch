#!/bin/bash
set -e

echo "=== Punch Setup ==="

# Check Python version
PYTHON=${PYTHON:-python3}
PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "Python: $PY_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r punch/requirements.txt

# Install Playwright browsers
echo "Installing Playwright Chromium..."
python -m playwright install chromium

# Create data directories
mkdir -p data/screenshots data/workspaces

# Create .env template if it doesn't exist
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# Punch Configuration
# PUNCH_TELEGRAM_TOKEN=your-bot-token-here
# PUNCH_TELEGRAM_USERS=123456789  # comma-separated Telegram user IDs
# PUNCH_WEB_PORT=8080
# PUNCH_MAX_CONCURRENT=4
# PUNCH_LOG_LEVEL=INFO
ENVEOF
    echo "Created .env template — edit it with your settings"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env with your Telegram bot token"
echo "2. Run: source venv/bin/activate && python -m punch.main"
echo "3. Access dashboard at http://localhost:8080"
echo ""
echo "For Gmail/Calendar, place your Google OAuth credentials at:"
echo "  data/gmail_credentials.json"
echo "  data/calendar_credentials.json"
echo ""
echo "To auto-start on boot:"
echo "  cp punch.plist ~/Library/LaunchAgents/com.punch.assistant.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.punch.assistant.plist"
echo ""
echo "To stop:"
echo "  launchctl unload ~/Library/LaunchAgents/com.punch.assistant.plist"
