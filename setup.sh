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

# Create .env from template if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env from template — edit it with your settings"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env with your Telegram bot token (optional)"
echo "2. Run: make start"
echo "3. Access dashboard at http://localhost:8080"
echo "4. Complete the onboarding wizard in your browser"
echo ""
echo "For Gmail/Calendar, place your Google OAuth credentials at:"
echo "  data/gmail_credentials.json"
echo "  data/calendar_credentials.json"
echo ""
echo "To auto-start on boot: make start-bg"
echo "To stop: make stop"
