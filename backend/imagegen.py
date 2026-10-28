"""
Local image generation (FLUX.1-schnell via stable-diffusion.cpp).

Mirrors rag.py's embedder: a lazily-loaded, idle-unloaded native model,
serialized against every other native call (chat, embedding) through the
same NATIVE_INFERENCE_LOCK rag.py already defines — two ggml-based native
calls running concurrently on separate threads is the exact crash this
project already hit and fixed once (see NATIVE_INFERENCE_LOCK's own
docstring in rag.py); a diffusion model is no exception to that.

FLUX.1-schnell over FLUX.1-dev or any Qwen-Image version, deliberately:
schnell is Apache 2.0 (dev is non-commercial-licensed) and its whole design
point is 4-step generation, which matters a lot more here than usual —
this runs on CPU (see below), where dev's ~20+ steps would be painfully
slow. An earlier attempt at Qwen-Image 2.1 hit a hard, upstream "get sd
version from file failed" load failure — that model's stable-diffusion.cpp
support is new enough to still be getting foundational fixes (multiple
open bugs against this exact model at the time), unlike FLUX, which has
been supported since near the project's start.

GPU: when the official prebuilt Vulkan build of stable-diffusion.cpp's
sd-cli is present in an `sd/` folder next to the app (see _sd_cli_path),
generation runs in that separate process instead of in-process — measured on
the dev machine at ~100s for a 512x512 FLUX image (RTX 4060, 8GB, weights
streamed from RAM) versus ~5 minutes at the same size on CPU through
stable-diffusion-cpp-python, which has no GPU backend in this app's build
(it's compiled from source without CUDA — see build_windows.bat). Vulkan
rather than CUDA so the same binary works on NVIDIA, AMD, and Intel GPUs
without shipping a CUDA runtime, which matters for a drive that moves between
PCs. A separate process also hands all its RAM/VRAM back the moment it exits,
so there's no resident image model to idle-unload on this path. Where no
sd-cli binary exists (e.g. macOS/Linux builds), generation falls back to the
in-process CPU library below.
"""

from __future__ import annotations

import io
import logging
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import rag as rag_mod

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

MODELS_DIR = ROOT / "models"

DIFFUSION_MODEL = MODELS_DIR / "flux1-schnell-q4_k.gguf"
CLIP_L = MODELS_DIR / "clip_l.safetensors"
T5XXL = MODELS_DIR / "t5xxl_fp8_e4m3fn.safetensors"
VAE = MODELS_DIR / "ae.safetensors"

_sd = None
_sd_lock = threading.Lock()
_sd_last_used = 0.0
_sd_idle_seconds = 300  # matches rag.py's embedder idle-unload window
_unload_watcher_started = False


SD_DIR = ROOT / "sd"

# Generous on purpose: this only exists to stop a wedged process from holding
# the generation lock (and the GPU) forever, not to cap a legitimately slow
# machine — CPU-only fallback on a weak laptop can take a long time.
CLI_TIMEOUT_SECONDS = 20 * 60


def image_model_installed() -> bool:
    return DIFFUSION_MODEL.exists() and CLIP_L.exists() and T5XXL.exists() and VAE.exists()


def _sd_cli_path() -> Path | None:
    exe = SD_DIR / ("sd-cli.exe" if sys.platform == "win32" else "sd-cli")
    return exe if exe.exists() else None


def get_sd():
    """Lazily loads the diffusion pipeline (~12GB across four files), same
    reasoning as rag.py's get_embedder(): image generation is occasional,
    not worth keeping resident for the whole session."""
    global _sd, _sd_last_used, _unload_watcher_started
    with _sd_lock:
        if _sd is None:
            if not image_model_installed():
                raise RuntimeError(
                    "The image generation model isn't installed yet."
                )
            from stable_diffusion_cpp import StableDiffusion

            _sd = StableDiffusion(
                diffusion_model_path=str(DIFFUSION_MODEL),
                clip_l_path=str(CLIP_L),
                t5xxl_path=str(T5XXL),
                vae_path=str(VAE),
                # Left unset, stable-diffusion-cpp-python defaults n_threads
                # to HALF the CPU count (its own docstring: "default: half
                # the number of CPUs") — unlike llama-cpp-python, which has
                # no such halving and is already given the full core count
                # in get_llm(). Since this build is CPU-only for image
                # generation (see this module's own docstring), that default
                # was quietly leaving half of every machine's cores idle for
                # the single slowest operation in the whole app.
                n_threads=os.cpu_count() or 4,
                rng_type="cpu",
                # Matches stable-diffusion.cpp's own documented FLUX
                # recipe: CLIP is small enough that forcing it onto CPU
                # avoids shuffling it to/from a GPU for no real benefit,
                # even where one's present.
                keep_clip_on_cpu=True,
                flash_attn=True,
                diffusion_flash_attn=True,
                verbose=False,
            )
            if not _unload_watcher_started:
                _unload_watcher_started = True
                threading.Thread(target=_idle_watcher, daemon=True).start()
        _sd_last_used = time.time()
        return _sd


def _idle_watcher():
    global _sd
    while True:
        time.sleep(30)
        with _sd_lock:
            if _sd is not None and (time.time() - _sd_last_used) > _sd_idle_seconds:
                _sd = None


# 512, not 1024: FLUX's cost grows steeply with pixel count, and a plain
# 1024x1024 request ran 30+ minutes on CPU without finishing. 512x512 is the
# size every earlier test of this feature actually used.
DEFAULT_SIZE = 512
MAX_EDIT_DIMENSION = 512  # keeps an edit's runtime in the same ballpark as a plain generation


def _generate_with_cli(cli: Path, prompt: str, seed: int, width: int, height: int,
                       source=None, strength: float = 0.9) -> bytes:
    """Runs one generation in the bundled sd-cli process (see module
    docstring). Text encoders stay on CPU (matches the in-process path's
    keep_clip_on_cpu, and T5's ~5GB compute buffer wouldn't fit in 8GB of
    VRAM alongside everything else), and the diffusion weights are held in RAM
    and streamed to the GPU as needed (--offload-to-cpu) so an 8GB card — or
    one already partly used by the chat model — doesn't run out of VRAM."""
    with tempfile.TemporaryDirectory(prefix="pocketmind_sd_") as tmp:
        out_path = Path(tmp) / "out.png"
        cmd = [
            str(cli),
            "--diffusion-model", str(DIFFUSION_MODEL),
            "--vae", str(VAE),
            "--clip_l", str(CLIP_L),
            "--t5xxl", str(T5XXL),
            "-p", prompt,
            "--cfg-scale", "1.0",
            "--sampling-method", "euler",
            "--steps", "4",
            "-W", str(width),
            "-H", str(height),
            "--seed", str(seed),
            "--backend", "te=cpu",
            "--offload-to-cpu",
            "--flash-attn", "on",
            "-o", str(out_path),
        ]
        if source is not None:
            init_path = Path(tmp) / "init.png"
            source.save(init_path, format="PNG")
            cmd += ["-i", str(init_path), "--strength", str(strength)]

        # Keeps a console window from flashing up on Windows when the app is
        # launched as a windowed exe.
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            proc = subprocess.run(
                cmd, cwd=str(cli.parent), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=CLI_TIMEOUT_SECONDS, creationflags=flags,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Image generation took too long and was stopped. Try a shorter "
                "description, or check that your graphics drivers are up to date."
            )
        if proc.returncode != 0 or not out_path.exists():
            logging.error("sd-cli failed (exit %s): %s", proc.returncode, (proc.stderr or "")[-2000:])
            raise RuntimeError("Couldn't generate that image. Try a different or shorter description.")
        return out_path.read_bytes()


def generate_image(
    prompt: str,
    width: int = DEFAULT_SIZE,
    height: int = DEFAULT_SIZE,
    init_image: bytes | None = None,
    strength: float = 0.9,
    before_generate=None,
) -> bytes:
    """Generates one image from a text prompt, returned as PNG bytes.

    Passing init_image (raw bytes of an uploaded photo) switches this from
    plain text-to-image to image-to-image editing: FLUX partially noises
    that image rather than starting from pure noise, then denoises it
    toward the prompt — width/height are then taken from the source image
    itself (downscaled to fit MAX_EDIT_DIMENSION if larger, since a photo
    straight off a phone can be far bigger than anything worth spending
    CPU-only inference time on) rather than the defaults above, so the
    result keeps the original's proportions instead of being stretched or
    cropped to a fixed square.

    strength controls how much of the original survives: 0 would return it
    unchanged, 1 ignores it entirely (equivalent to plain text-to-image).
    Not prescribed by stable-diffusion.cpp or FLUX the way schnell's
    cfg_scale/steps are — tuned empirically, and evidently borderline: at
    0.6, a real test edit ("change the apple to a green apple," fed a photo
    of a red one) came back with the apple still red, and 0.85 fixed that
    in the same test while keeping the same composition, table, and
    lighting — but a later repeat of that exact same request at 0.85 (same
    prompt, same source photo, only a fresh random seed) again came back
    still red, pixel-sampled to confirm rather than eyeballed. So 0.85
    isn't a reliable floor, just a value that sometimes works; raised to
    0.9 for more margin. schnell's 4 steps combined with cfg_scale=1.0 (low
    text guidance, appropriate for from-scratch generation) leave little
    room at lower strength to override a clearly-stated attribute like
    color, and some run-to-run variance from the random seed seems
    inherent regardless. Lower it if an edit feels like it's discarding too
    much of the original; if edits still intermittently don't take at 0.9,
    that's this same variance, not a new bug — the fix worth reaching for
    then is a retry affordance in the UI, not pushing strength toward 1.0
    (which stops being an "edit" and starts regenerating from scratch).

    cfg_scale=1.0 and sample_steps=4 are schnell's own documented defaults,
    not this app's choice — it's a distilled model tuned specifically for
    very few steps; the ~20+ steps and cfg_scale ~3.5 a non-distilled model
    like FLUX.1-dev wants would just waste time here without improving the
    result.

    Holds NATIVE_INFERENCE_LOCK for the actual generation, same as every
    other native chat/embedding call in this app — see this module's own
    docstring for why. On the sd-cli path the generation itself runs in a
    separate process, so the crash that lock exists for can't happen there;
    it's still held so an image never competes with a chat reply for the same
    GPU memory and CPU cores at once."""
    seed = random.randint(0, 2**31 - 1)
    source = None
    if init_image is not None:
        from PIL import Image

        source = Image.open(io.BytesIO(init_image)).convert("RGB")
        width, height = source.size
        if max(width, height) > MAX_EDIT_DIMENSION:
            scale = MAX_EDIT_DIMENSION / max(width, height)
            width, height = int(width * scale), int(height * scale)
            source = source.resize((width, height))
        # FLUX's own architecture needs both dimensions on a 16px grid —
        # source photos essentially never land on one already.
        width -= width % 16
        height -= height % 16
        if source.size != (width, height):
            source = source.crop((0, 0, width, height))

    cli = _sd_cli_path()
    if cli is not None:
        with rag_mod.NATIVE_INFERENCE_LOCK:
            # Called under the lock so it can't race an in-flight chat reply.
            # The caller uses it to drop the resident chat model: on an 8GB
            # GPU the chat model alone takes ~4.7GB+, leaving the image
            # process too little VRAM — measured 239s with it loaded versus
            # ~100s without. The chat model simply reloads on the next message.
            if before_generate is not None:
                before_generate()
            return _generate_with_cli(cli, prompt, seed, width, height, source, strength)

    sd = get_sd()
    kwargs = dict(
        prompt=prompt,
        cfg_scale=1.0,
        sample_method="euler",
        sample_steps=4,
        seed=seed,
        width=width,
        height=height,
    )
    if source is not None:
        kwargs.update(init_image=source, strength=strength)

    with rag_mod.NATIVE_INFERENCE_LOCK:
        images = sd.generate_image(**kwargs)
    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue()
