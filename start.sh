#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import cv2, numpy" >/dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

port="8000"
if [ -n "$1" ]; then
    port="$1"
fi

echo "Starting server on http://127.0.0.1:$port"
python server.py --port "$port"