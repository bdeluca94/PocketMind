#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

echo "Building the standalone macOS app (PocketMind)..."
echo "This runs once, on a Mac, to produce the app."
echo

python3 -m venv .venv-build-macos
source .venv-build-macos/bin/activate
pip install --upgrade pip --quiet

echo "Installing dependencies..."
if [ "$(uname -m)" = "arm64" ]; then
    echo "Apple Silicon - building with Metal GPU support..."
    CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --no-cache-dir --quiet
else
    pip install llama-cpp-python --quiet
fi
pip install -r backend/requirements.txt --quiet
pip install pyinstaller --quiet

echo "Building app icon..."
# iconutil only exists on macOS, which is why this conversion step lives
# here rather than in export_icons.py (that script just produces the
# .iconset folder of PNGs, from either platform).
iconutil -c icns assets/PocketMind.iconset -o assets/PocketMind.icns

echo "Building executable..."
pyinstaller --onefile --name PocketMind \
  --icon assets/PocketMind.icns \
  --add-data "frontend:frontend" \
  --collect-all llama_cpp \
  --collect-all faster_whisper \
  --collect-all ctranslate2 \
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
