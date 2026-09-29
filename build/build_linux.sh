#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

echo "Building the standalone Linux app (PocketMind)..."
echo "This runs once, on a Linux PC, to produce the binary."
echo

python3 -m venv .venv-build-linux
source .venv-build-linux/bin/activate
pip install --upgrade pip --quiet

echo "Installing dependencies (CPU build - works on any Linux PC)..."
pip install llama-cpp-python --quiet
pip install -r backend/requirements.txt --quiet
pip install pyinstaller --quiet

echo "Building executable..."
pyinstaller --onefile --name PocketMind \
  --add-data "frontend:frontend" \
  --hidden-import uvicorn.logging \
  --hidden-import uvicorn.protocols \
  --hidden-import uvicorn.protocols.http \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan \
  --hidden-import uvicorn.lifespan.on \
  --paths backend \
  backend/server.py

echo
echo "Done. Find the PocketMind binary in the 'dist' folder."
echo "Copy it to the root of the USB drive."
