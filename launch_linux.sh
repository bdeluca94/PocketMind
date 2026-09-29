#!/usr/bin/env bash
cd "$(dirname "$0")"

VENV_DIR="./.venv-linux"

if [ -f "$VENV_DIR/bin/python" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Starting PocketMind..."
    echo "A browser window will open shortly. (Keep this window open while you use the app.)"
    echo
    python backend/server.py
    exit $?
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
    echo "Python was not found on this PC."
    echo "Please install it (e.g. 'sudo apt install python3 python3-venv')"
    echo "then run this file again."
    read -p "Press Enter to close..."
    exit 1
fi

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

echo "Setting up the AI engine..."

if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA graphics card detected - installing the GPU-accelerated version."
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 --quiet \
      || { echo "GPU version had an issue - using the standard version instead."; pip install llama-cpp-python --quiet; }
else
    echo "No NVIDIA graphics card detected - installing the standard version (runs on your PC's processor)."
    pip install llama-cpp-python --quiet
fi

pip install -r backend/requirements.txt --quiet

echo
echo "Setup complete!"
echo
echo "Starting PocketMind..."
python backend/server.py
