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

No GPU offload here yet: this ships CPU-only. The chat model's own CUDA
build (llama-cpp-python, bundled with the ~636MB cuBLAS/cuBLASLt runtime
it needs) is a separate dependency from stable-diffusion-cpp-python here —
building this one with CUDA support too wasn't part of that work. Revisit
if this ever gets its own CUDA-enabled build the way the chat model has.
"""

from __future__ import annotations

import io
import os
import random
import sys
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


def image_model_installed() -> bool:
    return DIFFUSION_MODEL.exists() and CLIP_L.exists() and T5XXL.exists() and VAE.exists()


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


MAX_EDIT_DIMENSION = 1024  # keeps an edit's runtime in the same ballpark as a plain generation


def generate_image(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    init_image: bytes | None = None,
    strength: float = 0.9,
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

    Holds NATIVE_INFERENCE_LOCK for the actual generation call, same as
    every other native chat/embedding call in this app — see this module's
    own docstring for why."""
    sd = get_sd()
    kwargs = dict(
        prompt=prompt,
        cfg_scale=1.0,
        sample_method="euler",
        sample_steps=4,
        seed=random.randint(0, 2**31 - 1),
    )
    if init_image is not None:
        from PIL import Image

        source = Image.open(io.BytesIO(init_image)).convert("RGB")
        w, h = source.size
        if max(w, h) > MAX_EDIT_DIMENSION:
            scale = MAX_EDIT_DIMENSION / max(w, h)
            w, h = int(w * scale), int(h * scale)
            source = source.resize((w, h))
        # FLUX's own architecture needs both dimensions on a 16px grid —
        # source photos essentially never land on one already.
        w -= w % 16
        h -= h % 16
        kwargs.update(init_image=source, strength=strength, width=w, height=h)
    else:
        kwargs.update(width=width, height=height)

    with rag_mod.NATIVE_INFERENCE_LOCK:
        images = sd.generate_image(**kwargs)
    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue()
