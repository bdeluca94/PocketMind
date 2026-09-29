# PocketMind

A private, offline AI chat assistant that runs entirely on your own computer — no internet connection, no cloud service, no account, nothing sent anywhere. It's designed to live on a USB drive (or a folder copied from one) so you can carry a full local AI setup with you between machines, but it works just as well installed directly on one computer.

Built with [llama.cpp](https://github.com/ggml-org/llama.cpp) (via `llama-cpp-python`) for text and vision inference, and [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp) (via `stable-diffusion-cpp-python`) for image generation and editing. GPU acceleration (NVIDIA CUDA, Apple Metal) is used automatically when available, falling back to CPU otherwise.

## Features

- **Chat** with streamed replies, four pre-configured model tiers (fast/balanced/best-quality/vision), and support for adding your own `.gguf` models.
- **Personas and custom agents** — built-in conversation styles (Coding Helper, Writing Assistant, Explain Simply, Default) plus your own custom agents, each with its own instructions and prioritized document categories.
- **Document library (RAG)** — upload PDF, Word, Excel, or PowerPoint files and the assistant automatically retrieves relevant excerpts while answering, with automatic categorization. Scanned/image-only PDFs are read via an OCR fallback.
- **Image generation and editing** — describe an image in plain language ("draw a lighthouse at sunset") to generate one, or attach a photo and describe a change to edit it, all on-device via FLUX.
- **Vision** — attach a photo or screenshot and ask about it.
- **Voice input and read-aloud** — fully offline speech-to-text and text-to-speech.
- **Memory** — say "remember that…" and it's brought up automatically in future conversations.
- **Document export** — turn any reply into a downloadable Word document, Excel spreadsheet, or PowerPoint deck; export whole conversations as Markdown or plain text.
- **Drive encryption** — an optional passphrase lock encrypts conversations and documents at rest.
- **Backup & restore** — export everything to a single `.zip`, or restore from one.

## Project structure

```
backend/    FastAPI server, RAG/document pipeline, image generation, security, etc.
frontend/   Vanilla JS/HTML/CSS single-page UI
build/      Platform build scripts that package everything into one executable
assets/     App icon source files
```

## Running it

### Option A — build the standalone executable (recommended for end users)

1. Install [Python 3.12](https://www.python.org/downloads/) and, on Windows, the [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
2. Run the build script for your platform from `build/`:
   - Windows: `build\build_windows.bat`
   - macOS: `build/build_macos.sh`
   - Linux: `build/build_linux.sh`
3. Run the resulting executable (in `dist/`) — it's self-contained and can be copied anywhere, including a USB drive.
4. On first launch, use the Model section in the sidebar to download the chat/vision models you want (see below) — no manual file placement needed for those.

### Option B — run from source

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pip install llama-cpp-python stable-diffusion-cpp-python  # see note below on GPU builds
python server.py
```

Then open `http://127.0.0.1:8420` in a browser. `frontend/` is served automatically by the backend — no separate frontend build step.

`llama-cpp-python` and `stable-diffusion-cpp-python` aren't pinned in `requirements.txt` because the right build differs by platform and GPU vendor — see each project's own installation instructions for a CUDA/Metal-accelerated build rather than the plain CPU wheel from PyPI.

## Model files (not included in this repository)

This repo contains source code only. Model weights are third-party, multi-gigabyte open-weight files, handled two different ways:

- **Chat, vision, and document-embedding models** are downloaded automatically by the app itself — pick a model in the sidebar's Model section (or let it fetch the embedding model on first document upload) and it downloads, verifies, and installs the file into `models/` for you. No manual steps.
- **Image generation** (FLUX.1-schnell and its VAE/CLIP-L/T5-XXL encoder files) has no in-app downloader yet — search Hugging Face for a GGUF-quantized FLUX.1-schnell build and its accompanying `ae.safetensors`, `clip_l.safetensors`, and `t5xxl_fp8_e4m3fn.safetensors` files, and place all four in `models/` with those exact filenames (see `backend/imagegen.py`). Without them, everything except image generation/editing works normally.
- **Voice input** downloads its [faster-whisper](https://github.com/SYSTRAN/faster-whisper) model automatically on first use, into `whisper_models/`.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE). This means anyone can use, study, and modify this code, but any distributed derivative work must also be released under the GPL and its source made available.

## Disclaimer

This is a personal, hobby project shared as-is. It comes with no warranty of any kind — see the LICENSE for the full disclaimer.
