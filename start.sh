#!/bin/bash
# SophosLLM v2 — Start Script
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if exists
if [ -d "venv" ]; then
  source venv/bin/activate
fi

echo "╔════════════════════════════════════╗"
echo "║   SophosLLM v2 — Sophos Docs AI   ║"
echo "╚════════════════════════════════════╝"
echo ""

# Check data
RAW_COUNT=$(ls data/raw/*.json 2>/dev/null | wc -l | tr -d ' ')
echo "📂 Raw pages: $RAW_COUNT"

# Start Flask
PORT=${FLASK_PORT:-3063}
echo "🚀 Starting on http://0.0.0.0:$PORT"
echo ""

if command -v gunicorn &>/dev/null; then
  exec gunicorn -w 2 -b "0.0.0.0:$PORT" --timeout 120 --log-level info app:app
else
  exec python app.py
fi
