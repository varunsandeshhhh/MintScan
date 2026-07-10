#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ -x "./venv/bin/python" ]; then
  exec ./venv/bin/python bot.py
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 bot.py
fi

echo "Error: Python interpreter not found. Install Python 3 or create the virtualenv first."
exit 1
