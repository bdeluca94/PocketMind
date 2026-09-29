#!/usr/bin/env bash
cd "$(dirname "$0")"

VENV_DIR="./.venv-macos"

if [ -f "$VENV_DIR/bin/python" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Starting PocketMind..."
    echo "A browser window will open shortly. (Keep this window open while you use the app.)"
    echo
    python backend/server.py
    exit $?
fi

if [ -f "./PocketMind" ]; then
    echo
    echo "PocketMind is already in this folder - double-click that (or run"
    echo "./PocketMind) instead if you don't have an internet connection"
    echo "right now. It needs no setup and no internet at all."
    echo
    echo "This launcher (launch_macos.command) is a separate option for"
    echo "running from the Python source directly, and it does still need"
    echo "an internet connection for its one-time setup below."
    echo
fi

echo
echo "============================================"
echo " PocketMind - first time setup"
echo "============================================"
echo
echo "This will take a few minutes and needs an internet connection."
echo "It only happens once."
echo

if ! command -v python3 &> /dev/null; then
    echo "Python was not found on this Mac."
    echo "Please install it from https://python.org, then run this file again."
    read -p "Press Enter to close..."
    exit 1
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

echo "Setting up the AI engine..."

if [ "$(uname -m)" = "arm64" ]; then
    echo "Apple Silicon detected - installing the GPU-accelerated (Metal) version."
    CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --no-cache-dir --quiet \
      || { echo "GPU version had an issue - using the standard version instead."; pip install llama-cpp-python --quiet; }
else
    echo "Intel Mac detected - installing the standard version (runs on your Mac's processor)."
    pip install llama-cpp-python --quiet
fi

pip install -r backend/requirements.txt --quiet

echo
echo "Setup complete!"
echo
echo "Starting PocketMind..."
python backend/server.py
