#!/bin/bash
set -e

# Start API server in background on Railway's PORT
python -m uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000} &

# Start Telegram bot (foreground — Railway tracks this process)
python bot.py
