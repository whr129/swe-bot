#!/bin/bash
# Run LeetBot - prefers venv, then python3.12
cd "$(dirname "$0")"
if [ -f venv/bin/python ]; then
    exec ./venv/bin/python run.py "$@"
else
    PYTHON=$(command -v python3.12 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
    exec "$PYTHON" run.py "$@"
fi
