"""
Portable local-AI backend.

Serves:
  - A static chat frontend (../frontend)
  - A /api/chat endpoint that streams tokens from a local GGUF model
    using llama-cpp-python (CPU or GPU, fully offline).

Run with: python server.py
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import os
import sys
import glob
import platform
import re
import subprocess
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path


def _add_cuda_dll_directories() -> None:
    """Makes a CUDA-enabled llama-cpp-python actually able to find its GPU
    DLLs at import time, on Windows, in BOTH the frozen standalone .exe and
    the script-launcher's own venv. Must run before the first `import
    llama_cpp` anywhere in the app (server.py's own get_llm() and rag.py's
    get_embedder() both import it lazily on first use, so doing this here,
    at module load, covers both).

    Two things make this necessary rather than automatic:

    1. This app deliberately avoids a multi-GB CUDA Toolkit system install —
       instead, the build installs two small pip packages
       (nvidia-cublas-cu12, nvidia-cuda-runtime-cu12) that carry just the
       runtime DLLs llama.cpp's CUDA backend needs. Nothing on PATH points
       at them by default the way a real Toolkit install would.
    2. Even after locating them, `os.add_dll_directory()` alone isn't
       enough: llama_cpp's own loader calls `ctypes.CDLL(path,
       winmode=ctypes.RTLD_GLOBAL)`, and that specific call bypasses
       add_dll_directory's "safe DLL search mode" resolution on Windows —
       only classic PATH-based search still works for it. So both are set
       here, not just one.

    Silently does nothing if these directories aren't present (a non-CUDA/
    CPU-only build, or any OS other than Windows) — llama_cpp then loads
    however it otherwise would have."""
    if sys.platform != "win32":
        return
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(sys.prefix) / "Lib" / "site-packages"
    dll_dirs = [
        base / "nvidia" / "cublas" / "bin",
        base / "nvidia" / "cuda_runtime" / "bin",
        base / "llama_cpp" / "lib",
    ]
    found = [p for p in dll_dirs if p.is_dir()]
    for p in found:
        os.add_dll_directory(str(p))
    if found:
        os.environ["PATH"] = os.pathsep.join(str(p) for p in found) + os.pathsep + os.environ.get("PATH", "")


_add_cuda_dll_directories()

import requests
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

import personas as personas_mod
import conversations as conversations_mod
import agents as agents_mod
import rag as rag_mod
import imagegen as imagegen_mod
import voice as voice_mod
import context_manager as ctx_mod
import docgen as docgen_mod
import security as security_mod
import backup as backup_mod
import memory as memory_mod
import version as version_mod

# ---------------------------------------------------------------------------
# Paths
#
# Two different roots matter here:
#  - DATA_ROOT: where user data lives (models, PDFs, conversations). This
#    must be next to the actual executable/drive so it persists and stays
#    portable — NOT inside PyInstaller's temp extraction folder.
#  - BUNDLE_ROOT: where bundled read-only assets (the frontend) live. In a
#    frozen build that's PyInstaller's temp folder (sys._MEIPASS); in
#    script mode it's just the project folder.
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    DATA_ROOT = Path(sys.executable).resolve().parent
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", DATA_ROOT))
else:
    DATA_ROOT = Path(__file__).resolve().parent.parent
    BUNDLE_ROOT = DATA_ROOT

ROOT = DATA_ROOT  # kept as an alias since other modules import server.ROOT-style paths independently
MODELS_DIR = DATA_ROOT / "models"
FRONTEND_DIR = BUNDLE_ROOT / "frontend"
# Existence alone is the signal — no content needed, so no JSON parsing to
# get wrong. Lives on the drive rather than in the browser's own storage,
# same reasoning as everything else in this app: the drive is the one
# source of truth, and it's what makes "the same drive on a different PC
# picks up where you left off" true for this too, not just conversations
# and documents.
ONBOARDING_SEEN_FILE = DATA_ROOT / "onboarding_seen"

app = FastAPI(title="PocketMind")


@app.on_event("startup")
def _warm_document_search_on_startup():
    # Runs the one-time cost of building rag's chunk-vector cache (see its
    # docstring) on a background thread while the app is still loading,
    # instead of paying it on whichever chat message happens to arrive
    # first. Daemon so it never blocks shutdown if it's still running.
    threading.Thread(target=rag_mod.warm_vector_cache, daemon=True).start()

# ---------------------------------------------------------------------------
# Curated, beginner-friendly model catalog
# Sizes are approximate download sizes for the quantization chosen.
# All are open-weight models with permissive/open licenses, hosted on
# Hugging Face. Plain-language labels instead of technical quant names.
# ---------------------------------------------------------------------------
MODEL_CATALOG = [
    {
        "id": "fast",
        "label": "Fast & Light",
        "blurb": "Replies quickly, works well even on older laptops. Good for quick questions.",
        "size_gb": 0.8,
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
    },
    {
        "id": "balanced",
        "label": "Balanced (Recommended)",
        "blurb": "A strong all-rounder for most modern PCs and laptops.",
        "size_gb": 4.4,
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    },
    {
        "id": "quality",
        "label": "Best Quality",
        "blurb": "Smarter, more capable answers. Needs a fairly modern PC with 16GB+ RAM (or a GPU).",
        "size_gb": 8.37,
        "filename": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf",
    },
    {
        "id": "vision",
        "label": "Image Analysis & Editing",
        "blurb": "Understands images you attach to chat — describe a photo, read a screenshot, answer questions about a picture. Ask for a change (\"make the sky more dramatic\") and it hands off to the image generator to actually edit it. Also works as a general assistant.",
        "size_gb": 5.35,
        # MiniCPM-V 2.6, not Qwen2.5-VL: this app's GPU build pins
        # llama-cpp-python to 0.3.4 (the newest version with a prebuilt
        # Windows CUDA wheel — see build_windows.bat), and that version
        # predates Qwen25VLChatHandler entirely, so a Qwen2.5-VL model
        # can't load on the GPU build at all. MiniCPMv26ChatHandler has
        # been in llama-cpp-python since well before 0.3.4, and MiniCPM-V
        # 2.6 is a strong open vision-language model in its own right
        # (particularly for OCR/document/screenshot-style images, which
        # this feature's own blurb calls out).
        "filename": "MiniCPM-V-2_6-Q4_K_M.gguf",
        "url": "https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf/resolve/main/ggml-model-Q4_K_M.gguf",
        # Vision models ship with a second file — the "vision encoder" that
        # turns an image into something the language model can read. Both
        # files have to be installed for this entry to actually work; see
        # _run_model_download below. Named with the model's own name rather
        # than the repo's generic "mmproj-model-f16.gguf" so a second vision
        # model added later can't collide with this one on disk.
        "mmproj_filename": "mmproj-MiniCPM-V-2_6-F16.gguf",
        "mmproj_url": "https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf/resolve/main/mmproj-model-f16.gguf",
    },
]

_download_state = {"active": False, "progress": 0, "total": 0, "error": None, "filename": None}
_embed_download_state = {"active": False, "progress": 0, "total": 0, "error": None, "filename": None}


class _BusyCounter:
    """Drop-in replacement for threading.Event where several independent
    writers can be in flight at once.

    A plain Event is wrong here: PDF ingest and category writes both touch
    documents/index.db and both raise this flag, but with an Event whichever
    one finishes first calls clear() and drops the protection for the other.
    The window that opens is exactly the one this flag exists to close — the
    security endpoints would see an idle database and start encrypting a file
    that's still being written. Counting means the flag only falls when the
    last writer is actually done.

    Keeps set/clear/is_set naming so existing call sites read unchanged."""

    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    def set(self) -> None:
        with self._lock:
            self._count += 1

    def clear(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)

    def is_set(self) -> bool:
        with self._lock:
            return self._count > 0


_pdf_upload_active = _BusyCounter()
_security_op_active = threading.Event()
# Set by /api/chat/stop, checked between tokens in token_stream() below to
# cut generation short. Global rather than per-request: only one chat
# generation can run at a time anyway (NATIVE_INFERENCE_LOCK), so there's
# never more than one to stop.
_stop_chat_event = threading.Event()


GGUF_MAGIC = b"GGUF"


def _verify_gguf(path: Path, expected_size: int) -> str | None:
    """Sanity-checks a downloaded model file. Returns an error message if
    something's wrong, or None if it looks good.

    We can't check against an official checksum here (no network access to
    Hugging Face's API from this environment to fetch one), but we can
    catch the failure mode that actually matters in practice — a
    truncated or corrupted download — via two cheap checks: the file is
    exactly the size the server said it would be, and it starts with the
    GGUF format's own magic bytes."""
    try:
        actual_size = path.stat().st_size
    except OSError:
        return "The downloaded file went missing unexpectedly."

    if expected_size and actual_size != expected_size:
        return (
            f"The download looks incomplete ({actual_size:,} of "
            f"{expected_size:,} bytes). Your connection may have dropped."
        )

    try:
        with open(path, "rb") as f:
            header = f.read(4)
    except OSError:
        return "Couldn't read the downloaded file to verify it."

    if header != GGUF_MAGIC:
        return "The downloaded file doesn't look like a valid model file. It may have been corrupted in transit."

    return None


def _download_one(entry: dict, state: dict) -> bool:
    """Downloads a single catalog entry's file into MODELS_DIR and verifies
    it. Returns True on success; on failure sets state['error'] and returns
    False. Deliberately doesn't touch state['active'] — callers manage that,
    so a multi-file install (see _run_model_download) can span several of
    these without the UI seeing a false "done" in between files."""
    state.update(progress=0, total=0, error=None, filename=entry["filename"])
    dest = MODELS_DIR / entry["filename"]
    tmp = MODELS_DIR / (entry["filename"] + ".part")
    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        with requests.get(entry["url"], stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            state["total"] = total
            written = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
                        state["progress"] = written

        problem = _verify_gguf(tmp, total)
        if problem:
            state["error"] = problem
            tmp.unlink(missing_ok=True)
            return False

        os.replace(tmp, dest)  # overwrite-safe on Windows, unlike Path.rename()
        return True
    except Exception:
        state["error"] = "Couldn't finish the download. Check your internet connection and try again."
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return False


def _run_download(entry: dict, state: dict) -> None:
    """Shared download-with-progress entry point for a single-file catalog
    item, writing into whichever state dict belongs to this download (main
    model vs. embedding model) so the two never cross-talk if both happen
    to be triggered around the same time."""
    state["active"] = True
    try:
        _download_one(entry, state)
    finally:
        state["active"] = False


def _run_model_download(entry: dict, state: dict) -> None:
    """Downloads a catalog entry's main model file, and its companion
    vision-encoder ("mmproj") file too if the entry has one — both have to
    succeed for a vision model to be usable. Reported as one continuous
    "active" install even though it's two downloads, so the existing
    progress UI doesn't need to know the difference."""
    state["active"] = True
    try:
        if not _download_one(entry, state):
            return
        if entry.get("mmproj_filename"):
            mmproj_entry = {"filename": entry["mmproj_filename"], "url": entry["mmproj_url"]}
            _download_one(mmproj_entry, state)
    finally:
        state["active"] = False


def detect_hardware() -> dict:
    """Best-effort, friendly hardware summary. Never raises."""
    system = platform.system()  # 'Windows', 'Linux', 'Darwin'
    gpu_label = "CPU only"
    accelerated = False

    try:
        if system == "Darwin" and platform.machine() == "arm64":
            gpu_label = "Apple Silicon (GPU-accelerated)"
            accelerated = True
        else:
            # NVIDIA check (Windows/Linux)
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_label = f"NVIDIA {result.stdout.strip().splitlines()[0]} (GPU-accelerated)"
                accelerated = True
    except Exception:
        pass  # nvidia-smi not present, or any other environment quirk — fall back to CPU label

    return {
        "os": system,
        "gpu_label": gpu_label,
        "accelerated": accelerated,
        "cpu_threads": os.cpu_count() or 4,
    }


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
_llm = None
_llm_lock = threading.Lock()
_model_path = None

SELECTED_MODEL_FILE = MODELS_DIR / ".selected_model"


def _installed_chat_models() -> list[str]:
    """All installed chat models (full paths) — embedding models and
    vision "mmproj" companion files excluded, since neither is itself
    something to load as the main chat model.

    Ordered to match MODEL_CATALOG (Fast & Light, Balanced, Best Quality,
    Image Analysis) rather than alphabetically by filename, since that's
    the order these are meant to appear in the Model dropdown. Anything a
    user installed themselves (not in the catalog) sorts after all four,
    alphabetically among themselves.

    The image generator's own diffusion weights (flux1-schnell-q4_k.gguf)
    happen to end in .gguf too but aren't excluded by prefix like embed-/
    mmproj- files are, so they're excluded by name explicitly — llama.cpp
    can't load them as a chat model at all; imagegen.py loads them
    separately via stable-diffusion.cpp."""
    catalog_order = {m["filename"]: i for i, m in enumerate(MODEL_CATALOG)}
    candidates = glob.glob(str(MODELS_DIR / "*.gguf"))
    candidates = [
        c for c in candidates
        if not os.path.basename(c).startswith("embed-")
        and not os.path.basename(c).startswith("mmproj-")
        and os.path.basename(c) != imagegen_mod.DIFFUSION_MODEL.name
    ]
    candidates.sort(key=lambda c: (catalog_order.get(os.path.basename(c), len(MODEL_CATALOG)), os.path.basename(c)))
    return candidates


def _is_catalog_model(filename: str) -> bool:
    """True for one of the built-in models this drive ships with — those
    can be switched between freely but never removed, only models a user
    installs themselves (via "Install your own model") can be."""
    return any(m["filename"] == filename for m in MODEL_CATALOG)


def _mmproj_path_for(model_filename: str) -> Path | None:
    """Vision-capable catalog models ship with a companion "mmproj" vision
    encoder file. Returns its path if the given model has one and it's
    actually installed; otherwise None (a plain text model)."""
    entry = next(
        (m for m in MODEL_CATALOG if m["filename"] == model_filename and m.get("mmproj_filename")),
        None,
    )
    if entry is None:
        return None
    mmproj_path = MODELS_DIR / entry["mmproj_filename"]
    return mmproj_path if mmproj_path.exists() else None


def find_model() -> str | None:
    """Picks the model to use: whichever one was explicitly selected (if it
    still exists), otherwise the first chat .gguf file found in /models."""
    candidates = _installed_chat_models()
    if not candidates:
        return None

    if SELECTED_MODEL_FILE.exists():
        try:
            selected_name = SELECTED_MODEL_FILE.read_text().strip()
        except OSError:
            selected_name = ""
        for c in candidates:
            if os.path.basename(c) == selected_name:
                return c

    return candidates[0]


def get_llm():
    """Lazily load the model on first request (keeps startup instant).

    use_mmap=False forces llama.cpp to fully copy the model's weights into
    RAM up front, rather than memory-mapping the GGUF file straight off
    disk. This costs a slower first load (and needs enough free RAM to
    hold the whole model), but it's what makes "safe to unplug the USB
    drive once loaded" actually true — with mmap on, the OS can still
    reach back to the file on the drive at any time to page in parts of
    the model it hasn't touched yet, and pulling the drive mid-session
    would crash the app.
    """
    global _llm, _model_path
    with _llm_lock:
        if _llm is None:
            try:
                import llama_cpp
                from llama_cpp import Llama
            except ImportError:
                raise RuntimeError(
                    "The AI engine isn't installed yet. Please run the "
                    "launcher for your operating system first (it installs "
                    "this automatically)."
                )

            _model_path = find_model()
            if _model_path is None:
                raise RuntimeError(
                    "No AI model is installed yet. Use the \"Get a model\" "
                    "screen to download one."
                )

            # n_gpu_layers=-1 offloads everything to GPU if one is available
            # and llama-cpp-python was built with GPU support; otherwise it
            # silently falls back to CPU-only.
            n_threads = os.cpu_count() or 4
            try:
                # A vision-capable model (see MODEL_CATALOG's "vision" entry)
                # needs its companion mmproj file loaded as a chat_handler —
                # that's what actually lets it read an attached image. Plain
                # text models get chat_handler=None, same as before. Done
                # inside this try so a corrupt mmproj file gets the same
                # friendly "reinstall it" error as a corrupt main model file,
                # instead of an unrelated generic one.
                chat_handler = None
                mmproj_path = _mmproj_path_for(os.path.basename(_model_path))
                if mmproj_path is not None:
                    from llama_cpp.llama_chat_format import MiniCPMv26ChatHandler
                    chat_handler = MiniCPMv26ChatHandler(clip_model_path=str(mmproj_path), verbose=False)

                # select_model() (switching the active model — including the
                # automatic switch on attaching a photo or a large code file)
                # only takes _llm_lock, which is deliberately cheap and never
                # blocks on generation: it just drops the global _llm
                # reference so the NEXT request loads the new model. But
                # that means a switch can land while a PREVIOUS turn is
                # still mid-generation — and constructing a new Llama() here
                # is itself native code. Without also holding
                # NATIVE_INFERENCE_LOCK, that construction could run
                # concurrently with the old model's still-in-flight
                # inference (held in token_stream()/_embed() via this same
                # lock), which is exactly the two-native-calls-at-once
                # pattern that used to crash the app. Taking it here makes
                # a new load wait for any in-flight generation to finish
                # first, same as generation already waits for embedding
                # and vice versa.
                with rag_mod.NATIVE_INFERENCE_LOCK:
                    _llm = Llama(
                        model_path=_model_path,
                        # 8192 for every model, not just vision — a dropped code
                        # file (see the frontend's whole-file attach flow, which
                        # sends the file's full text as part of the message
                        # rather than chunking/embedding it like a PDF) needs the
                        # same headroom an attached image does.
                        n_ctx=8192,
                        n_threads=n_threads,
                        n_gpu_layers=-1,
                        use_mmap=False,   # copy weights fully into RAM — see note below
                        chat_handler=chat_handler,
                        verbose=False,
                        # Reduces memory-bandwidth pressure during
                        # generation — the actual bottleneck on both the
                        # CPU-only script-launcher path and a GPU one, more
                        # so than raw compute. Requires each other: llama.cpp
                        # only supports a quantized KV cache (type_k/type_v
                        # below Q8_0's ~2x memory saving over the F16
                        # default) when flash attention is also on.
                        flash_attn=True,
                        type_k=llama_cpp.GGML_TYPE_Q8_0,
                        type_v=llama_cpp.GGML_TYPE_Q8_0,
                    )
            except Exception as e:
                failed_file = os.path.basename(_model_path or "")
                _model_path = None
                raise RuntimeError(
                    f"Couldn't load the AI model ({failed_file}). "
                    "The file may be corrupted or incomplete — try deleting it from "
                    "the models folder and reinstalling it."
                ) from e
        return _llm


def friendly_model_error(e: Exception) -> str:
    """Turn any exception from get_llm() into a message safe to show the user."""
    if isinstance(e, RuntimeError):
        return str(e)
    return "Something went wrong loading the AI model. Try restarting the app."


@app.get("/api/status")
def status():
    model = find_model()
    return {
        "ready": model is not None,
        "model_file": os.path.basename(model) if model else None,
        "models_dir": str(MODELS_DIR),
        "hardware": detect_hardware(),
        "running_from": str(DATA_ROOT),
        "version": version_mod.APP_VERSION,
        "security": {"enabled": security_mod.is_enabled(), "unlocked": security_mod.is_unlocked()},
        "onboarding_seen": ONBOARDING_SEEN_FILE.exists(),
        # True only once the model is fully loaded into RAM (use_mmap=False
        # above) and no downloads are actively writing to the drive.
        "safe_to_eject": (
            _llm is not None
            and not _download_state["active"]
            and not _embed_download_state["active"]
            and not _pdf_upload_active.is_set()
            and not _security_op_active.is_set()
        ),
    }


@app.post("/api/onboarding-seen")
def api_mark_onboarding_seen():
    # Just a marker — no content, so nothing to encrypt and nothing that
    # can fail to parse later. Whether someone's clicked through a tour
    # once isn't sensitive, so this deliberately doesn't go through the
    # security module at all, unlike conversations/agents/documents.
    try:
        ONBOARDING_SEEN_FILE.touch()
    except OSError:
        pass  # a read-only drive shouldn't turn "dismiss the tour" into an error
    return {"seen": True}



@app.get("/api/models/catalog")
def models_catalog():
    """List of beginner-friendly model options for the in-app downloader."""
    return {"models": MODEL_CATALOG, "download": _download_state}


@app.get("/api/models/download-status")
def download_status():
    return _download_state


@app.post("/api/models/download/{model_id}")
def download_model(model_id: str):
    entry = next((m for m in MODEL_CATALOG if m["id"] == model_id), None)
    if entry is None:
        return JSONResponse({"error": "Unknown model."}, status_code=404)
    if _download_state["active"]:
        return JSONResponse({"error": "A download is already in progress."}, status_code=409)

    threading.Thread(target=_run_model_download, args=(entry, _download_state), daemon=True).start()
    return {"started": True}


@app.get("/api/models/installed")
def list_installed_models():
    active = find_model()
    result = []
    for c in _installed_chat_models():
        try:
            size_gb = round(os.path.getsize(c) / (1024 ** 3), 2)
        except OSError:
            size_gb = None
        catalog_entry = next((m for m in MODEL_CATALOG if m["filename"] == os.path.basename(c)), None)
        result.append({
            "filename": os.path.basename(c),
            "label": catalog_entry["label"] if catalog_entry else os.path.basename(c),
            "size_gb": size_gb,
            "active": c == active,
            "vision": _mmproj_path_for(os.path.basename(c)) is not None,
            "removable": catalog_entry is None,
            # "fast" / "balanced" / "quality" / "vision" for a base model,
            # None for a custom one — lets the frontend pick a specific
            # catalog model to auto-switch to (e.g. Fast -> Balanced for a
            # large file) without hardcoding filenames on that side too.
            "catalog_id": catalog_entry["id"] if catalog_entry else None,
        })
    return {"models": result}


@app.delete("/api/models/{filename}")
def delete_model(filename: str):
    safe_name = os.path.basename(filename)  # defend against path traversal
    target = MODELS_DIR / safe_name
    if (
        not target.exists()
        or not safe_name.endswith(".gguf")
        or safe_name.startswith(("embed-", "mmproj-"))
        or safe_name == imagegen_mod.DIFFUSION_MODEL.name
    ):
        return JSONResponse({"error": "That model isn't installed."}, status_code=404)
    if _is_catalog_model(safe_name):
        return JSONResponse(
            {"error": "This model came pre-installed on this drive and can't be removed."},
            status_code=403,
        )

    global _llm, _model_path
    with _llm_lock:
        target.unlink()
        # A vision model's mmproj companion isn't a model of its own in the
        # installed list, so it never gets its own uninstall button — it
        # only ever goes away bundled with the main file that needs it.
        mmproj_path = _mmproj_path_for(safe_name)
        if mmproj_path is not None:
            mmproj_path.unlink(missing_ok=True)

        if _model_path == str(target):
            _llm = None
            _model_path = None
        if SELECTED_MODEL_FILE.exists() and SELECTED_MODEL_FILE.read_text().strip() == safe_name:
            SELECTED_MODEL_FILE.unlink(missing_ok=True)

    return {"deleted": safe_name}


@app.post("/api/models/select/{filename}")
def select_model(filename: str):
    safe_name = os.path.basename(filename)  # defend against path traversal
    target = MODELS_DIR / safe_name
    if (
        not target.exists()
        or not safe_name.endswith(".gguf")
        or safe_name.startswith("embed-")
        or safe_name == imagegen_mod.DIFFUSION_MODEL.name
    ):
        return JSONResponse({"error": "That model isn't installed."}, status_code=404)

    global _llm, _model_path
    with _llm_lock:
        SELECTED_MODEL_FILE.write_text(safe_name)
        if _model_path != str(target):
            # Drop the currently loaded model (if any) so the next chat
            # message loads the newly selected one instead.
            _llm = None
            _model_path = None
    return {"selected": safe_name}


def _save_uploaded_model(fileobj, tmp: Path) -> str | None:
    """Runs in a worker thread: streams a user-supplied model file to disk
    in chunks (never holds the whole multi-GB file in memory) and verifies
    it. Returns an error message, or None on success."""
    with open(tmp, "wb") as out:
        while True:
            chunk = fileobj.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    # No server-reported size to check a user's own file against — the
    # GGUF header check is the meaningful part here.
    return _verify_gguf(tmp, 0)


@app.post("/api/models/upload")
async def upload_model(file: UploadFile = File(...)):
    """Lets a user install their own already-downloaded .gguf model,
    dropped in from the sidebar, instead of only picking from the catalog."""
    if _download_state["active"]:
        return JSONResponse({"error": "Another model install is already in progress. Wait for it to finish and try again."}, status_code=409)

    safe_name = os.path.basename(file.filename or "")
    if not safe_name.lower().endswith(".gguf"):
        return JSONResponse({"error": "Only .gguf model files are supported."}, status_code=400)
    if (
        safe_name.startswith(("embed-", "mmproj-"))
        or safe_name == SELECTED_MODEL_FILE.name
        or _is_catalog_model(safe_name)
    ):
        return JSONResponse({"error": "That filename is reserved. Rename the file and try again."}, status_code=400)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / safe_name
    tmp = MODELS_DIR / (safe_name + ".part")

    _download_state.update(active=True, progress=0, total=0, error=None, filename=safe_name)
    try:
        problem = await asyncio.to_thread(_save_uploaded_model, file.file, tmp)
        if problem:
            tmp.unlink(missing_ok=True)
            return JSONResponse({"error": problem}, status_code=400)
        os.replace(tmp, dest)  # overwrite-safe on Windows, unlike Path.rename()
        return {"installed": safe_name}
    except Exception:
        tmp.unlink(missing_ok=True)
        return JSONResponse({"error": "Couldn't save that file. Try again."}, status_code=500)
    finally:
        _download_state["active"] = False


# A small/weak model's trained reflex to disclaim file access — see
# context_manager.py's fit_to_context docstring for how the prompt already
# tries to head this off. That's a probabilistic fix (an instruction the
# model usually, not always, follows); this is a deterministic backstop for
# when it doesn't. Only ever applied when doc_hits was non-empty for this
# turn (see its one call site below) — that's the one condition under which
# "I don't have access to that file" is PROVABLY false, since real excerpts
# were actually placed in the model's own context. Requires a first-person
# pronoun AND a negated access/view/open/read verb close together, rather
# than a flat phrase list, specifically to avoid ever stripping a sentence
# that's actually part of the document's own content (e.g. a document that
# itself discusses restricted building access) rather than the model
# talking about itself.
_FIRST_PERSON_RE = re.compile(r"\bi\b|\bi'm\b|\bi've\b", re.IGNORECASE)
_DISCLAIMER_RE = re.compile(
    r"\b(?:don'?t|do\s+not|can'?t|cannot|am\s+not|isn'?t|not)\b[^.!?]{0,40}?"
    r"\b(?:access|ability|view|open|read)\b",
    re.IGNORECASE,
)
_TRANSITION_RE = re.compile(
    r"^\s*(however|but|that said|still|nonetheless|nevertheless)[,:]?\s*",
    re.IGNORECASE,
)


def _strip_leading_disclaimer(text: str) -> str:
    """If `text` opens with a stock "I can't access/read/open that file"
    disclaimer, drops that sentence (and a following transition word like
    "However,") so the user sees the model's actual answer without the
    confusing, false preamble. Returns text unchanged if the opening
    sentence doesn't look like one."""
    stripped = text.lstrip()
    match = re.match(r"^[^.!?]*[.!?]\s*", stripped)
    if not match:
        return text
    first_sentence = match.group(0)
    if not (_FIRST_PERSON_RE.search(first_sentence) and _DISCLAIMER_RE.search(first_sentence)):
        return text
    rest = _TRANSITION_RE.sub("", stripped[match.end():], count=1)
    # The sentence right after the one just removed is now the new opening
    # — capitalize it so the reply doesn't visibly start mid-case (e.g.
    # "the document says..." instead of "The document says...").
    if rest[:1].isalpha() and rest[:1].islower():
        rest = rest[0].upper() + rest[1:]
    return rest


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    persona_id = body.get("persona", "default")
    use_documents = body.get("use_documents", True)
    category_id = body.get("category_id") or None
    auto_route = bool(body.get("auto_route", True))
    conversation_id = body.get("conversation_id") or None
    # An image attached to the *current* turn only — not stored as part of
    # message history, so it never has to flow through document retrieval
    # or context-fitting, both of which assume plain-string message content.
    image = body.get("image") or None

    if not messages:
        return JSONResponse({"error": "messages[] is required"}, status_code=400)

    if not all(isinstance(m, dict) and "role" in m and "content" in m for m in messages):
        return JSONResponse({"error": "Each message needs a 'role' and 'content'."}, status_code=400)

    if image is not None and (not isinstance(image, str) or not image.startswith("data:image/")):
        return JSONResponse({"error": "That doesn't look like a valid image."}, status_code=400)

    try:
        llm = await asyncio.to_thread(get_llm)
    except Exception as e:
        return JSONResponse({"error": friendly_model_error(e)}, status_code=400)

    if image is not None and _mmproj_path_for(os.path.basename(_model_path or "")) is None:
        return JSONResponse(
            {"error": "The current model can't see images. Switch to the \"Image Analysis\" model first."},
            status_code=400,
        )

    # Custom agents are checked first: they're user-created and their ids
    # (uuid4 hex) can't collide with the built-in persona ids ("default",
    # "coding_helper", etc.), so there's no ambiguity in trying agents first.
    # Any failure here (locked drive, corrupt agents.json) degrades to
    # treating persona_id as a built-in persona rather than failing the whole
    # chat request — document retrieval already follows this same "a locked
    # drive shouldn't break chat" philosophy just below.
    custom_agent = None
    try:
        custom_agent = agents_mod.get_agent(persona_id)
    except Exception:
        custom_agent = None

    if custom_agent:
        # An agent with no custom instructions still needs a system prompt —
        # falls back to the Default Assistant's rather than sending an empty
        # one, so a category-only agent (no personality tweak) behaves like
        # a normal, helpful assistant rather than an unprompted model.
        persona_message = {
            "role": "system",
            "content": custom_agent["instructions"] or personas_mod.PERSONAS[0]["system_prompt"],
        }
        # auto_route doubles as "skip all boosting this turn" — see the
        # "search everything instead" retry, which sends auto_route=False
        # and expects that to mean no boosting from ANY source, not just
        # auto-detection. Threading the agent's categories through the same
        # flag keeps that retry semantics correct without a second toggle.
        agent_category_ids = custom_agent["category_ids"] if auto_route else None
    else:
        persona = personas_mod.get_persona(persona_id)
        persona_message = {"role": "system", "content": persona["system_prompt"]}
        agent_category_ids = None

    last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    hits = []
    routed_category = None
    routed_priority = None
    if use_documents and rag_mod.embedding_model_path() is not None:
        try:
            found = await asyncio.to_thread(
                rag_mod.retrieve_with_routing, last_user_msg,
                top_k=4, min_similarity=0.3, category_id=category_id,
                auto_route=auto_route, boost_category_ids=agent_category_ids,
                conversation_id=conversation_id,
            )
            hits = found["hits"]
            routed_category = found["category"]
            routed_priority = found["priority"]
        except Exception:
            hits = []

    # "Remember that ..." is detected here rather than left entirely to the
    # model, so it reliably lands in memory.json even from a small/weak
    # model that might not reliably act on a "you can ask to be remembered"
    # instruction on its own. The newly-added fact is included in THIS same
    # turn's context below (load_memory() runs after add_entry()), so the
    # model naturally sees and can acknowledge it rather than the save
    # happening invisibly.
    remembered_fact = memory_mod.extract_remember_request(last_user_msg)
    if remembered_fact:
        try:
            memory_mod.add_entry(remembered_fact)
        except (ValueError, RuntimeError):
            pass  # empty text, or the drive is locked — either way, just skip saving it

    try:
        memory_entries = memory_mod.load_memory()
    except RuntimeError:
        memory_entries = []  # drive locked — chat still works, just without memory context

    history = [m for m in messages if m["role"] != "system"]
    final_messages = await asyncio.to_thread(
        ctx_mod.fit_to_context, llm, persona_message, hits, history, memory_entries
    )

    # Swapped in only after context-fitting, and only on the outgoing
    # payload — fit_to_context and document retrieval above both assume
    # plain-string content, and this keeps it that way for everything except
    # the one message actually going to the model this turn.
    if image is not None and final_messages and final_messages[-1]["role"] == "user":
        final_messages[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": final_messages[-1]["content"]},
                {"type": "image_url", "image_url": {"url": image}},
            ],
        }

    # Only worth telling the UI about if excerpts actually made it through —
    # announcing "Searched: Finance" on an answer that used no documents at
    # all would be describing a decision that had no effect on the output.
    meta = None
    if hits and (routed_category or routed_priority):
        meta = {}
        if routed_category:
            meta["category"] = routed_category
        if routed_priority:
            meta["priority"] = routed_priority

    def token_stream():
        _stop_chat_event.clear()  # discard any stale stop from a previous, already-finished turn
        if meta:
            yield f"data: {json.dumps({'meta': meta})}\n\n"
        try:
            # Held for the entire generation, not just the call that kicks it
            # off — every token pulled from `stream` below runs more of the
            # model forward, so the lock needs to stay up for the whole loop.
            # See NATIVE_INFERENCE_LOCK's own comment: this is what stops chat
            # generation and the embedding model (paste-text ingestion, PDF
            # upload) from ever actually computing at the same moment on two
            # separate threads, which is what crashed the app.
            with rag_mod.NATIVE_INFERENCE_LOCK:
                stream = llm.create_chat_completion(
                    messages=final_messages,
                    stream=True,
                    temperature=0.7,
                    max_tokens=1024,
                )
                # Only when real document excerpts were actually included
                # this turn (see _strip_leading_disclaimer's own comment for
                # why that's the condition that matters) — buffers just the
                # opening sentence before deciding, so a normal reply pays
                # no visible delay beyond that one sentence's worth of
                # tokens, and a reply that never punctuates within the cap
                # still gets flushed rather than held forever.
                checking_disclaimer = bool(hits)
                buffer = ""
                for chunk in stream:
                    if _stop_chat_event.is_set():
                        break
                    delta = chunk["choices"][0]["delta"].get("content")
                    if not delta:
                        continue
                    if checking_disclaimer:
                        buffer += delta
                        if re.search(r"[.!?]\s", buffer) or len(buffer) > 300:
                            checking_disclaimer = False
                            buffer = _strip_leading_disclaimer(buffer)
                            if buffer:
                                yield f"data: {json.dumps({'token': buffer})}\n\n"
                            buffer = ""
                    else:
                        yield f"data: {json.dumps({'token': delta})}\n\n"
                if checking_disclaimer and buffer:
                    # The reply ended (or was stopped) before ever reaching
                    # the check above — still worth applying to whatever's
                    # left rather than skipping it just because it was short.
                    stripped = _strip_leading_disclaimer(buffer)
                    if stripped:
                        yield f"data: {json.dumps({'token': stripped})}\n\n"
        except Exception:
            # Without this, any exception here (a bad image, a model that
            # chokes on this particular input, anything short of a native
            # crash) just drops the connection mid-stream — the frontend
            # then shows the generic "couldn't reach the AI engine" message
            # with no way to tell that from an actual network problem, and
            # no record of what really went wrong. logging.exception writes
            # the real traceback to the console/log so it's actually
            # diagnosable, while the client gets a clear, specific message.
            logging.exception("Chat generation failed mid-stream")
            yield f"data: {json.dumps({'error': 'Something went wrong while generating a response. Try again, or try a different model.'})}\n\n"
            return
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(token_stream(), media_type="text/event-stream")


@app.post("/api/chat/compact")
async def api_compact_chat(request: Request):
    """Condenses a long conversation into a short summary that replaces the
    full history — this app's own version of Claude Code's own /compact.
    Doesn't touch documents/retrieval at all; it's purely about the
    conversation itself, which otherwise only ever grows: fit_to_context
    (see context_manager.py) already trims the oldest turns silently once a
    request stops fitting the model's context window, and the full history
    still gets saved to disk regardless. Compacting turns that silent,
    unbounded growth into a deliberate, visible summary the user asked for."""
    body = await request.json()
    messages = body.get("messages", [])

    transcript = "\n\n".join(
        f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
        for m in messages if m.get("role") in ("user", "assistant") and m.get("content")
    )
    if not transcript.strip():
        return JSONResponse({"error": "Nothing to compact yet."}, status_code=400)

    try:
        llm = await asyncio.to_thread(get_llm)
    except Exception as e:
        return JSONResponse({"error": friendly_model_error(e)}, status_code=400)

    def run_summary():
        text = ctx_mod.truncate_for_summary(llm, transcript)
        summary_messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the conversation below into concise background "
                    "notes for continuing it later. Preserve every fact, "
                    "decision, name, number, and open thread that would change "
                    "how a future question should be answered — omit only "
                    "small talk and phrasing. Write it as neutral notes, not "
                    "as a reply to anyone."
                ),
            },
            {"role": "user", "content": text},
        ]
        with rag_mod.NATIVE_INFERENCE_LOCK:
            out = llm.create_chat_completion(messages=summary_messages, temperature=0.3, max_tokens=800)
        return out["choices"][0]["message"]["content"]

    try:
        summary = await asyncio.to_thread(run_summary)
    except Exception:
        logging.exception("Conversation compaction failed")
        return JSONResponse({"error": "Couldn't compact this conversation. Try again."}, status_code=500)

    return {"summary": summary.strip()}


@app.post("/api/generate-image")
async def api_generate_image(request: Request):
    """Generates one image using the local FLUX.1-schnell pipeline (see
    imagegen.py) — the frontend's counterpart to attaching a photo for
    Image Analysis, but in the other direction: creating one rather than
    reading one. Returns the PNG as base64 rather than a streamed response,
    since a whole image has to finish generating before there's anything
    meaningful to show anyway, unlike token-by-token chat text.

    init_image_base64 switches this from plain text-to-image to editing an
    uploaded photo — see generate_image's own docstring for what that
    changes. This is the second half of the Image Analysis + FLUX edit
    pipeline: the frontend sends Image Analysis's description of the photo
    (plus the requested change) here as `prompt`, alongside the original
    photo as `init_image_base64`, rather than this endpoint doing any
    analysis itself."""
    if not imagegen_mod.image_model_installed():
        return JSONResponse(
            {"error": "The image generation model isn't installed yet."},
            status_code=400,
        )
    body = await request.json()
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "Describe what you'd like to see first."}, status_code=400)

    init_image_b64 = body.get("init_image_base64")
    init_image_bytes = None
    if init_image_b64:
        try:
            init_image_bytes = base64.b64decode(init_image_b64)
        except (ValueError, TypeError):
            return JSONResponse({"error": "That image couldn't be read."}, status_code=400)
    strength = body.get("strength")
    kwargs = {"init_image": init_image_bytes}
    if strength is not None:
        kwargs["strength"] = strength

    try:
        png_bytes = await asyncio.to_thread(imagegen_mod.generate_image, prompt, **kwargs)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        logging.exception("Image generation failed")
        return JSONResponse(
            {"error": "Couldn't generate that image. Try a different or shorter description."},
            status_code=500,
        )

    return {"image_base64": base64.b64encode(png_bytes).decode("ascii")}


@app.get("/api/memory")
def api_list_memory():
    try:
        return {"entries": memory_mod.load_memory()}
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)


@app.post("/api/memory")
async def api_add_memory(request: Request):
    body = await request.json()
    try:
        entry = memory_mod.add_entry(body.get("text") or "")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    return {"entry": entry}


@app.delete("/api/memory/{entry_id}")
def api_delete_memory(entry_id: str):
    try:
        if not memory_mod.delete_entry(entry_id):
            return JSONResponse({"error": "That memory wasn't found."}, status_code=404)
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    return {"deleted": entry_id}


@app.post("/api/chat/stop")
async def api_chat_stop():
    """Cuts short whatever chat generation is currently running.

    The frontend also aborts its own fetch immediately for a snappy UI, but
    that alone leaves the backend still generating (and holding
    NATIVE_INFERENCE_LOCK) until it hits max_tokens — this is what actually
    stops the model doing more work.
    """
    _stop_chat_event.set()
    return {"stopped": True}


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------
@app.get("/api/personas")
def get_personas():
    return {"personas": personas_mod.PERSONAS}


# ---------------------------------------------------------------------------
# Custom agents
#
# Same error-handling pattern as conversations, since they're stored and
# encrypted the same way: RuntimeError means locked -> 423, ValueError means
# a bad request (blank name, no categories, duplicate name) -> 400.
# ---------------------------------------------------------------------------
@app.get("/api/agents")
def api_list_agents():
    try:
        return {"agents": agents_mod.list_agents()}
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)


@app.post("/api/agents")
async def api_create_agent(request: Request):
    body = await request.json()
    try:
        agent = agents_mod.create_agent(
            body.get("name", ""), body.get("category_ids", []), body.get("instructions", "")
        )
        return {"agent": agent}
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.patch("/api/agents/{agent_id}")
async def api_update_agent(agent_id: str, request: Request):
    body = await request.json()
    try:
        agent = agents_mod.update_agent(
            agent_id,
            name=body.get("name"),
            category_ids=body.get("category_ids"),
            instructions=body.get("instructions"),
        )
        return {"agent": agent}
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.delete("/api/agents/{agent_id}")
def api_delete_agent(agent_id: str):
    try:
        agents_mod.delete_agent(agent_id)
        return {"deleted": True}
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)


# ---------------------------------------------------------------------------
# Saved conversations
# ---------------------------------------------------------------------------
@app.get("/api/conversations")
def api_list_conversations():
    return {"conversations": conversations_mod.list_conversations()}


@app.get("/api/conversations/search")
def api_search_conversations(q: str = ""):
    # search_conversations() itself returns [] while locked (same as
    # list_conversations()) rather than raising — nothing to catch here.
    return {"results": conversations_mod.search_conversations(q)}


@app.post("/api/conversations")
async def api_save_conversation(request: Request):
    body = await request.json()
    try:
        conv_id = conversations_mod.save_conversation(
            body.get("id"), body.get("title", "Untitled chat"), body.get("messages", [])
        )
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    return {"id": conv_id}


@app.get("/api/conversations/{conv_id}")
def api_load_conversation(conv_id: str):
    try:
        data = conversations_mod.load_conversation(conv_id)
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    if data is None:
        return JSONResponse({"error": "Conversation not found."}, status_code=404)
    return data


@app.delete("/api/conversations/{conv_id}")
def api_delete_conversation(conv_id: str):
    conversations_mod.delete_conversation(conv_id)
    try:
        rag_mod.delete_documents_for_conversation(conv_id)
    except Exception:
        pass  # best-effort — a locked drive or missing DB shouldn't block deleting the conversation itself
    return {"deleted": True}


@app.get("/api/conversations/{conv_id}/export")
def api_export_conversation(conv_id: str, format: str = "md"):
    try:
        data = conversations_mod.load_conversation(conv_id)
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    if data is None:
        return JSONResponse({"error": "Conversation not found."}, status_code=404)

    fmt = "txt" if format == "txt" else "md"
    text = conversations_mod.export_text(data, fmt)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", data.get("title", "conversation"))[:40] or "conversation"
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.{fmt}"'},
    )


@app.post("/api/documents/export-docx")
async def api_export_docx(request: Request):
    """Turns one assistant reply's markdown into a real Word document the
    user can download — see docgen.py for the actual conversion. A plain
    per-message action rather than anything tied to a saved conversation:
    the reply's own text (already in the browser) is all that's needed, so
    this doesn't touch conversations_mod at all."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    title = (body.get("title") or "").strip() or None
    if not text:
        return JSONResponse({"error": "Nothing to export."}, status_code=400)
    try:
        docx_bytes = await asyncio.to_thread(docgen_mod.markdown_to_docx, text, title)
    except Exception:
        return JSONResponse({"error": "Couldn't build a Word document from that reply."}, status_code=400)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title or "response")[:40] or "response"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.docx"'},
    )


@app.post("/api/documents/export-xlsx")
async def api_export_xlsx(request: Request):
    """Same idea as /api/documents/export-docx just above, but for the
    table(s) in a reply rather than the whole thing — a paragraph of prose
    doesn't mean anything as a spreadsheet, so this only ever exports what
    markdown_tables_to_xlsx actually finds as pipe tables."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    title = (body.get("title") or "").strip() or None
    if not text:
        return JSONResponse({"error": "Nothing to export."}, status_code=400)
    try:
        xlsx_bytes = await asyncio.to_thread(docgen_mod.markdown_tables_to_xlsx, text)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't build a spreadsheet from that reply."}, status_code=400)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title or "response")[:40] or "response"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.xlsx"'},
    )


@app.post("/api/documents/export-pptx")
async def api_export_pptx(request: Request):
    """Same idea as /api/documents/export-docx above, but as a slide deck —
    see markdown_to_pptx's own docstring for how slide breaks are decided
    and why this is the shakiest of the three export formats."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    title = (body.get("title") or "").strip() or None
    if not text:
        return JSONResponse({"error": "Nothing to export."}, status_code=400)
    try:
        pptx_bytes = await asyncio.to_thread(docgen_mod.markdown_to_pptx, text, title)
    except Exception:
        return JSONResponse({"error": "Couldn't build a slide deck from that reply."}, status_code=400)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title or "response")[:40] or "response"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.pptx"'},
    )


# ---------------------------------------------------------------------------
# Documents (PDF upload for the AI to reference)
# ---------------------------------------------------------------------------
@app.get("/api/documents")
def api_list_documents():
    return {
        "documents": rag_mod.list_documents(),
        "embedding_model_ready": rag_mod.embedding_model_path() is not None,
        "embedding_download": _embed_download_state,
    }


@app.post("/api/documents/install-reader")
def install_document_reader():
    """Downloads the small local embedding model needed to search PDFs."""
    if rag_mod.embedding_model_path() is not None:
        return {"already_installed": True}
    if _embed_download_state["active"]:
        return JSONResponse({"error": "Already installing — please wait."}, status_code=409)

    threading.Thread(target=_run_download, args=(rag_mod.EMBED_MODEL, _embed_download_state), daemon=True).start()
    return {"started": True}


@app.post("/api/documents/upload")
async def api_upload_document(file: UploadFile = File(...)):
    if rag_mod.embedding_model_path() is None:
        return JSONResponse(
            {"error": "The document reader isn't installed yet. Install it first, then upload."},
            status_code=400,
        )
    if rag_mod.ingest_progress["active"]:
        return JSONResponse({"error": "Already processing a document — please wait for it to finish."}, status_code=409)
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    _pdf_upload_active.set()
    try:
        file_bytes = await file.read()
        result = await asyncio.to_thread(rag_mod.ingest_document, file_bytes, file.filename)
        return result
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't read that file. Try a different one."}, status_code=400)
    finally:
        _pdf_upload_active.clear()


@app.post("/api/documents/upload-scoped")
async def api_upload_document_scoped(file: UploadFile = File(...), conversation_id: str = Form(None)):
    """The chat bar's counterpart to /api/documents/upload — a PDF/Word/
    Excel/PowerPoint file dropped directly onto the message box, extracted
    the same way, but scoped to one conversation like paste-text rather
    than filed into the permanent Documents library. Previously, dropping
    one of these onto the chat bar silently mis-read its raw bytes as
    plain text (see ingestTextSnippet's fallback in app.js, now reserved
    for actual text files); this is what fixed that."""
    if rag_mod.embedding_model_path() is None:
        return JSONResponse(
            {"error": "The document reader isn't installed yet. Install it first, then try again."},
            status_code=400,
        )
    if rag_mod.ingest_progress["active"]:
        return JSONResponse({"error": "Already processing a document — please wait for it to finish."}, status_code=409)
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    conv_id = (conversation_id or "").strip() or uuid.uuid4().hex[:10]
    _pdf_upload_active.set()
    try:
        file_bytes = await file.read()
        text = await asyncio.to_thread(rag_mod.extract_document_text, file_bytes, file.filename)
        result = await asyncio.to_thread(rag_mod.ingest_text_snippet, text, file.filename, conv_id)
        result["conversation_id"] = conv_id
        return result
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't read that file. Try a different one."}, status_code=400)
    finally:
        _pdf_upload_active.clear()


@app.get("/api/documents/upload-status")
def api_upload_status():
    return rag_mod.ingest_progress


@app.post("/api/documents/cancel-upload")
def api_cancel_upload():
    if not rag_mod.ingest_progress["active"]:
        return JSONResponse({"error": "No upload is currently in progress."}, status_code=409)
    rag_mod.cancel_ingest()
    return {"cancelling": True}


@app.post("/api/documents/paste-text")
async def api_paste_text(request: Request):
    """Text pasted or dropped directly into the chat bar (e.g. a large
    error message) — chunked and embedded like a PDF, but scoped to one
    conversation: searchable only while chatting there, never listed
    alongside real uploaded documents. See ingest_text_snippet for why."""
    if rag_mod.embedding_model_path() is None:
        return JSONResponse(
            {"error": "The document reader isn't installed yet. Install it first, then try again."},
            status_code=400,
        )
    if rag_mod.ingest_progress["active"]:
        return JSONResponse({"error": "Already processing a document — please wait for it to finish."}, status_code=409)
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)

    body = await request.json()
    text = (body.get("text") or "").strip()
    filename = (body.get("filename") or "pasted-text.txt").strip() or "pasted-text.txt"
    # A brand-new conversation has no id yet on the frontend — this is the
    # single place that ever mints one for such a case, and the caller is
    # expected to adopt whatever id comes back as its conversation id from
    # then on (including in the eventual /api/conversations save), so this
    # snippet and that saved conversation end up tied to the same id.
    conversation_id = (body.get("conversation_id") or "").strip() or uuid.uuid4().hex[:10]

    if not text:
        return JSONResponse({"error": "That's empty — nothing to add."}, status_code=400)

    _pdf_upload_active.set()
    try:
        result = await asyncio.to_thread(rag_mod.ingest_text_snippet, text, filename, conversation_id)
        result["conversation_id"] = conversation_id
        return result
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't process that text. Try again."}, status_code=400)
    finally:
        _pdf_upload_active.clear()


@app.delete("/api/documents/{doc_id}")
def api_delete_document(doc_id: str):
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    try:
        rag_mod.delete_document(doc_id)
    except RuntimeError:
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Categories
#
# Every one of these writes to documents/index.db, which means they're
# subject to the same race the upload/delete endpoints already guard against:
# the security endpoints encrypt or decrypt that file wholesale, and doing
# that mid-write can lose data or (on Windows) fail outright because the file
# is still open. So category writes take the same _pdf_upload_active flag the
# security endpoints already check, rather than introducing a second,
# separate lock that the security code wouldn't know to look at.
# ---------------------------------------------------------------------------
@contextmanager
def _docs_db_write():
    """Marks the documents database as being written to, and refuses if a
    security operation is already in flight. Raises _DocsDbBusy, which the
    callers below turn into a 409."""
    if _security_op_active.is_set():
        raise _DocsDbBusy()
    _pdf_upload_active.set()
    try:
        yield
    finally:
        _pdf_upload_active.clear()


class _DocsDbBusy(Exception):
    pass


def _category_error(e: Exception) -> JSONResponse:
    if isinstance(e, _DocsDbBusy):
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    if isinstance(e, ValueError):
        return JSONResponse({"error": str(e)}, status_code=400)
    if isinstance(e, RuntimeError):
        return JSONResponse({"error": "This drive is locked. Unlock it first."}, status_code=423)
    return JSONResponse({"error": "Couldn't update categories. Try again."}, status_code=500)


@app.get("/api/categories")
def api_list_categories():
    return {"categories": rag_mod.list_categories()}


@app.post("/api/categories")
async def api_create_category(request: Request):
    body = await request.json()
    try:
        with _docs_db_write():
            return {"category": rag_mod.create_category(body.get("name", ""))}
    except Exception as e:
        return _category_error(e)


@app.patch("/api/categories/{cat_id}")
async def api_rename_category(cat_id: str, request: Request):
    body = await request.json()
    try:
        with _docs_db_write():
            return {"category": rag_mod.rename_category(cat_id, body.get("name", ""))}
    except Exception as e:
        return _category_error(e)


@app.delete("/api/categories/{cat_id}")
def api_delete_category(cat_id: str):
    try:
        with _docs_db_write():
            rag_mod.delete_category(cat_id)
        return {"deleted": True}
    except Exception as e:
        return _category_error(e)


@app.patch("/api/documents/{doc_id}/category")
async def api_set_document_category(doc_id: str, request: Request):
    body = await request.json()
    cat_id = body.get("category_id") or None
    try:
        with _docs_db_write():
            rag_mod.set_document_category(doc_id, cat_id)
        return {"updated": True}
    except Exception as e:
        return _category_error(e)


# ---------------------------------------------------------------------------
# Security (optional passphrase lock for conversations + documents)
#
# These deliberately refuse to run while a document is actively being
# uploaded/deleted: encrypting or decrypting the documents database out
# from under an in-progress SQLite write is a real race — on Windows it
# would likely crash outright (the file would still be open), and on
# Linux/Mac it can silently lose whatever was written in that window.
# Simplest reliable fix is mutual exclusion at the API level, since these
# are both rare, deliberate actions rather than anything that overlaps in
# normal use.
# ---------------------------------------------------------------------------
@app.get("/api/security/status")
def api_security_status():
    return {"enabled": security_mod.is_enabled(), "unlocked": security_mod.is_unlocked()}


@app.post("/api/security/enable")
async def api_security_enable(request: Request):
    if security_mod.is_enabled():
        return JSONResponse({"error": "Already enabled."}, status_code=409)
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    body = await request.json()
    passphrase = body.get("passphrase", "")
    _security_op_active.set()
    try:
        await asyncio.to_thread(security_mod.enable, passphrase)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't turn on encryption. Try again."}, status_code=500)
    finally:
        _security_op_active.clear()
    return {"enabled": True}


@app.post("/api/security/unlock")
async def api_security_unlock(request: Request):
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    body = await request.json()
    passphrase = body.get("passphrase", "")
    _security_op_active.set()
    try:
        ok = await asyncio.to_thread(security_mod.unlock, passphrase)
    finally:
        _security_op_active.clear()
    if not ok:
        return JSONResponse({"error": "That passphrase doesn't match."}, status_code=401)
    return {"unlocked": True}


@app.post("/api/security/lock")
def api_security_lock():
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    _security_op_active.set()
    try:
        security_mod.lock()
    finally:
        _security_op_active.clear()
    return {"locked": True}


@app.post("/api/security/disable")
async def api_security_disable(request: Request):
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    body = await request.json()
    passphrase = body.get("passphrase", "")
    _security_op_active.set()
    try:
        ok = await asyncio.to_thread(security_mod.disable, passphrase)
    finally:
        _security_op_active.clear()
    if not ok:
        return JSONResponse({"error": "That passphrase doesn't match."}, status_code=401)
    return {"disabled": True}


# ---------------------------------------------------------------------------
# Backup / restore — bundles conversations, custom agents, and the
# documents library into a single downloadable file, and can restore from
# one. Guarded by the same busy-flags as the security endpoints above,
# since restore in particular rewrites exactly the files a document upload
# or a lock/unlock cycle could be mid-write on.
# ---------------------------------------------------------------------------
@app.get("/api/backup")
def api_create_backup():
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    try:
        data = backup_mod.create_backup()
    except Exception:
        return JSONResponse({"error": "Couldn't create a backup. Try again."}, status_code=500)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="pocketmind-backup-{stamp}.zip"'},
    )


@app.post("/api/backup/inspect")
async def api_inspect_backup(file: UploadFile = File(...)):
    """Reads just the manifest from an uploaded backup file so the frontend
    can show what it contains ("3 conversations, 5 documents, made Sep 11")
    and get explicit confirmation before /api/backup/restore actually
    overwrites anything."""
    data = await file.read()
    try:
        manifest = backup_mod.read_manifest(data)
    except backup_mod.InvalidBackup as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"manifest": manifest}


@app.post("/api/backup/restore")
async def api_restore_backup(file: UploadFile = File(...)):
    if rag_mod.ingest_progress["active"]:
        return JSONResponse({"error": "A document is being processed — wait for it to finish first."}, status_code=409)
    if _pdf_upload_active.is_set():
        return JSONResponse({"error": "Wait for the current document upload to finish first."}, status_code=409)
    if _security_op_active.is_set():
        return JSONResponse({"error": "Security settings are being changed — try again in a moment."}, status_code=409)
    data = await file.read()
    _security_op_active.set()
    try:
        manifest = await asyncio.to_thread(backup_mod.restore_backup, data)
    except backup_mod.InvalidBackup as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Couldn't restore that backup. Try again."}, status_code=500)
    finally:
        _security_op_active.clear()
    return {"restored": True, "manifest": manifest}


# ---------------------------------------------------------------------------
# Voice input
# ---------------------------------------------------------------------------
@app.post("/api/transcribe")
async def api_transcribe(request: Request):
    wav_bytes = await request.body()
    try:
        text = await asyncio.to_thread(voice_mod.transcribe_wav_bytes, wav_bytes)
        return {"text": text}
    except Exception:
        return JSONResponse(
            {"error": "Couldn't transcribe that. Make sure microphone access was allowed and try again."},
            status_code=400,
        )


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
@app.middleware("http")
async def _no_cache_frontend(request: Request, call_next):
    """Never let the browser cache the frontend's own files (index.html,
    app.js, style.css, mermaid.min.js, ...).

    This app ships as a single long-lived local exe that gets replaced
    wholesale on every update — a browser quietly serving a stale cached
    index.html alongside a freshly updated app.js (or the reverse) is
    exactly how one file's change can silently break the whole page: the
    HTML no longer matches what the script expects to find, or a script
    the new HTML expects to load was never fetched at all. That's a real
    incident this app hit directly — a new <script> tag plus the code that
    depended on it worked in every direct test, then broke for real users
    whose browser still had the previous version's index.html cached.
    Loads are effectively free either way since everything's on localhost,
    so there's no real cost to skipping the cache entirely — only downside
    was ever this kind of stale-mismatch bug. API responses are untouched;
    GET/POST/DELETE calls under /api/ were never browser-cached to begin
    with."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    import webbrowser

    port = 8420
    url = f"http://127.0.0.1:{port}"

    def open_browser():
        import time
        time.sleep(1.2)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    print(f"\nPocketMind running at {url}\n(Ctrl+C to stop)\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
